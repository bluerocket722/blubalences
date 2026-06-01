"""
Email checker worker — verifies email_contacts in Supabase via MillionVerifier.

Reads rows from the `email_contacts` table where smtp_checked = false, calls the
MillionVerifier single-verification API for each, and writes smtp_checked /
smtp_valid back on the row. Uses HTTPS so it runs anywhere (Railway included).

Env:
    export SUPABASE_URL=https://xbwuvaxtnylqvagdvpxp.supabase.co
    export SUPABASE_SERVICE_KEY=your-service-role-key
    export MV_API_KEY=your-millionverifier-api-key
    # optional:
    export CHECK_BATCH=200          # max contacts to check per run
    export MV_TIMEOUT=20            # seconds the API waits before giving up

    python smtp_checker.py

Result mapping (MillionVerifier `result` field):
    ok          -> valid   (deliverable)
    catch_all   -> valid   (domain accepts all; deliverable but risky)
    invalid     -> invalid
    disposable  -> invalid  (temp/throwaway mailbox)
    unknown     -> retry next run (leave smtp_checked = false)
    error       -> retry next run
"""

import logging
import os
import re
import sys
import time

import requests

log = logging.getLogger("email_checker")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MV_ENDPOINT = "https://api.millionverifier.com/api/v3/"


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


def mv_verify(api_key, email, timeout):
    """
    Returns (valid, note).
      valid = True  -> deliverable (ok / catch_all)
      valid = False -> not deliverable (invalid / disposable)
      valid = None  -> indeterminate (unknown / error / API failure) -> retry
    """
    try:
        r = requests.get(
            MV_ENDPOINT,
            params={"api": api_key, "email": email, "timeout": timeout},
            timeout=timeout + 10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return None, f"api error: {e}"

    result  = (data.get("result") or "").lower()
    credits = data.get("credits")
    err     = data.get("error") or ""
    note    = f"{result}" + (f" credits={credits}" if credits is not None else "") + (f" {err}" if err else "")

    if result in ("ok", "catch_all"):
        return True, note
    if result in ("invalid", "disposable"):
        return False, note
    # unknown / error / anything else -> retry
    return None, note


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    SUPA_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    SUPA_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    MV_KEY   = os.environ.get("MV_API_KEY", "")
    if not SUPA_URL or not SUPA_KEY:
        log.error("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return 1
    if not MV_KEY:
        log.error("Set MV_API_KEY (MillionVerifier API key)")
        return 1

    batch   = int(os.environ.get("CHECK_BATCH", "200"))
    timeout = int(os.environ.get("MV_TIMEOUT", "20"))

    def get(table, qs=""):    return supa_get(SUPA_URL, SUPA_KEY, table, qs)
    def patch(table, qs, pl): return supa_patch(SUPA_URL, SUPA_KEY, table, qs, pl)

    rows = get(
        "email_contacts",
        f"?smtp_checked=eq.false&select=id,email&order=id.asc&limit={batch}",
    )
    log.info("%d contact(s) to check (batch=%d)", len(rows), batch)
    if not rows:
        return 0

    valid_n = invalid_n = unknown_n = 0

    for i, row in enumerate(rows):
        email = (row.get("email") or "").strip().lower()
        rid   = row["id"]

        if not EMAIL_RE.match(email):
            patch("email_contacts", f"?id=eq.{rid}", {"smtp_checked": True, "smtp_valid": False})
            invalid_n += 1
            log.info("  [%d/%d] %s -> invalid (malformed)", i + 1, len(rows), email)
            continue

        valid, note = mv_verify(MV_KEY, email, timeout)

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

        time.sleep(0.2)  # be gentle on the API

    log.info("Done. valid=%d invalid=%d unknown=%d", valid_n, invalid_n, unknown_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
