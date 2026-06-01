"""
SMTP checker worker — verifies email_contacts in Supabase via MX + SMTP RCPT.

Reads rows from the `email_contacts` table where smtp_checked = false,
resolves each domain's MX records, opens an SMTP conversation, and issues
RCPT TO to see whether the mailbox is accepted. Updates smtp_checked and
smtp_valid back on the row.

Env:
    export SUPABASE_URL=https://xbwuvaxtnylqvagdvpxp.supabase.co
    export SUPABASE_SERVICE_KEY=your-service-role-key
    # optional:
    export CHECK_BATCH=200          # max contacts to check per run
    export MAIL_FROM=check@blubalences.com
    export SMTP_TIMEOUT=15

    python smtp_checker.py

NOTE: Many cloud hosts (Railway included) block outbound port 25. If every
contact comes back invalid/unknown, that's almost certainly an egress block
on port 25 rather than bad addresses — verify from a host that allows it.
"""

import logging
import os
import re
import smtplib
import socket
import sys

import dns.resolver
import requests

log = logging.getLogger("smtp_checker")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _supa_headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def supa_get(base, key, table, qs=""):
    r = requests.get(f"{base}/rest/v1/{table}{qs}", headers=_supa_headers(key), timeout=30)
    r.raise_for_status()
    return r.json()


def supa_patch(base, key, table, qs, payload):
    r = requests.patch(f"{base}/rest/v1/{table}{qs}", json=payload, headers=_supa_headers(key), timeout=30)
    r.raise_for_status()


def resolve_mx(domain):
    """Return a list of MX hostnames (best priority first), or []."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=10)
        hosts = sorted((r.preference, str(r.exchange).rstrip(".")) for r in answers)
        return [h for _, h in hosts]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        # Fall back to A record (some domains accept mail on the bare host)
        try:
            dns.resolver.resolve(domain, "A", lifetime=10)
            return [domain]
        except Exception:
            return []
    except Exception as e:
        log.warning("MX lookup failed for %s: %s", domain, e)
        return []


def smtp_probe(email, mx_hosts, mail_from, timeout):
    """
    Returns (valid, note).
      valid = True  -> mailbox accepted (RCPT 250/251)
      valid = False -> mailbox rejected (550 etc.)
      valid = None  -> indeterminate (connection blocked, greylist, 4xx, etc.)
    """
    last_note = "no mx"
    for host in mx_hosts:
        try:
            server = smtplib.SMTP(timeout=timeout)
            server.connect(host, 25)
            server.ehlo_or_helo_if_needed()
            server.mail(mail_from)
            code, msg = server.rcpt(email)
            try:
                server.quit()
            except Exception:
                pass
            msg = msg.decode() if isinstance(msg, bytes) else str(msg)
            if code in (250, 251):
                return True, f"{host}:{code}"
            if 500 <= code < 600:
                return False, f"{host}:{code} {msg[:80]}"
            last_note = f"{host}:{code} {msg[:80]}"  # 4xx greylist/temp -> indeterminate
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, OSError) as e:
            last_note = f"{host}: {e}"
            continue
        except Exception as e:
            last_note = f"{host}: {e}"
            continue
    return None, last_note


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    SUPA_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    SUPA_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not SUPA_URL or not SUPA_KEY:
        log.error("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return 1

    batch     = int(os.environ.get("CHECK_BATCH", "200"))
    mail_from = os.environ.get("MAIL_FROM", "check@blubalences.com")
    timeout   = int(os.environ.get("SMTP_TIMEOUT", "15"))

    def get(table, qs=""):    return supa_get(SUPA_URL, SUPA_KEY, table, qs)
    def patch(table, qs, pl): return supa_patch(SUPA_URL, SUPA_KEY, table, qs, pl)

    rows = get(
        "email_contacts",
        f"?smtp_checked=eq.false&select=id,email&order=id.asc&limit={batch}",
    )
    log.info("%d contact(s) to check (batch=%d)", len(rows), batch)
    if not rows:
        return 0

    # Cache MX lookups per domain within a run
    mx_cache = {}
    valid_n = invalid_n = unknown_n = 0

    for i, row in enumerate(rows):
        email = (row.get("email") or "").strip().lower()
        rid   = row["id"]

        if not EMAIL_RE.match(email):
            patch("email_contacts", f"?id=eq.{rid}", {"smtp_checked": True, "smtp_valid": False})
            invalid_n += 1
            log.info("  [%d/%d] %s -> invalid (malformed)", i + 1, len(rows), email)
            continue

        domain = email.rsplit("@", 1)[1]
        if domain not in mx_cache:
            mx_cache[domain] = resolve_mx(domain)
        mx_hosts = mx_cache[domain]

        if not mx_hosts:
            patch("email_contacts", f"?id=eq.{rid}", {"smtp_checked": True, "smtp_valid": False})
            invalid_n += 1
            log.info("  [%d/%d] %s -> invalid (no MX)", i + 1, len(rows), email)
            continue

        valid, note = smtp_probe(email, mx_hosts, mail_from, timeout)

        if valid is True:
            patch("email_contacts", f"?id=eq.{rid}", {"smtp_checked": True, "smtp_valid": True})
            valid_n += 1
            log.info("  [%d/%d] %s -> VALID (%s)", i + 1, len(rows), email, note)
        elif valid is False:
            patch("email_contacts", f"?id=eq.{rid}", {"smtp_checked": True, "smtp_valid": False})
            invalid_n += 1
            log.info("  [%d/%d] %s -> invalid (%s)", i + 1, len(rows), email, note)
        else:
            # Indeterminate: leave smtp_checked=false so it retries next run.
            unknown_n += 1
            log.info("  [%d/%d] %s -> unknown, will retry (%s)", i + 1, len(rows), email, note)

    log.info("Done. valid=%d invalid=%d unknown=%d", valid_n, invalid_n, unknown_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
