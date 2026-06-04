import imaplib
import socket
import email
import email.utils
import email.header
import random
import time
import os
import ssl
import json
import base64
import re
import urllib.request
import urllib.parse
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

PROXY_HOST = os.environ.get('WEBSHARE_HOST', 'p.webshare.io')
PROXY_PORT = int(os.environ.get('WEBSHARE_PORT', '1080'))
PROXY_USER = os.environ.get('WEBSHARE_USER', '')
PROXY_PASS = os.environ.get('WEBSHARE_PASS', '')

PROVIDER_HOSTS = {
    'gmail':     ('imap.gmail.com', 993, 'smtp.gmail.com', 587),
    'outlook':   ('outlook.office365.com', 993, 'smtp.office365.com', 587),
    'office365': ('outlook.office365.com', 993, 'smtp.office365.com', 587),
    'microsoft': ('outlook.office365.com', 993, 'smtp.office365.com', 587),
    'icloud':    ('imap.mail.me.com', 993, 'smtp.mail.me.com', 587),
    'yahoo':     ('imap.mail.yahoo.com', 993, 'smtp.mail.yahoo.com', 587),
    'aol':       ('imap.aol.com', 993, 'smtp.aol.com', 587),
}

REPLY_TEMPLATES = [
    "Yep, got it!", "Thanks, received it.", "Got it, thanks!",
    "Perfect, thank you.", "Yes, came through.", "Thanks so much!",
    "Awesome, got it.", "Received it, thanks!", "Yep, looks good.",
    "Thanks, all set!", "Got it — thanks!", "Yes, received. Thanks!",
]

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_settings():
    rows = sb.table('settings').select('key,value').execute().data or []
    cfg = {}
    for r in rows:
        v = r.get('value', '') or ''
        if isinstance(v, list): v = v[0] if v else ''
        if isinstance(v, str): v = v.strip('"')
        cfg[r['key']] = v
    return cfg

def load_inbox_emails():
    rows = sb.table('inboxes').select('email').eq('active', True).execute().data or []
    return set(r['email'].lower() for r in rows)

def bell_minutes(min_m, max_m):
    total = sum(random.random() for _ in range(6))
    return round(min_m + (total / 6) * (max_m - min_m))

def mailbox_proxy(mb):
    """Return per-mailbox dedicated proxy dict, or None to use global env proxy."""
    if mb.get('proxy_host'):
        return {
            'host': mb.get('proxy_host'),
            'port': mb.get('proxy_port') or 1080,
            'user': mb.get('proxy_user') or '',
            'pass': mb.get('proxy_pass') or '',
        }
    return None

def make_proxied_socket(host, port, timeout=30, proxy=None):
    p_host = (proxy or {}).get('host') or PROXY_HOST
    p_port = int((proxy or {}).get('port') or PROXY_PORT)
    p_user = (proxy or {}).get('user') if proxy else PROXY_USER
    p_user = p_user if p_user is not None else PROXY_USER
    p_pass = (proxy or {}).get('pass') if proxy else PROXY_PASS
    p_pass = p_pass if p_pass is not None else PROXY_PASS

    if not p_host or not p_user:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(timeout)
        return sock
    relay = socket.create_connection((p_host, p_port), timeout=timeout)
    auth = base64.b64encode(f"{p_user}:{p_pass}".encode()).decode()
    connect_req = (f"CONNECT {host}:{int(port)} HTTP/1.1\r\nHost: {host}:{int(port)}\r\n"
                   f"Proxy-Authorization: Basic {auth}\r\n\r\n")
    relay.sendall(connect_req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = relay.recv(4096)
        if not chunk: break
        resp += chunk
    status_line = resp.split(b"\r\n")[0].decode(errors="replace")
    if " 200 " not in status_line:
        raise Exception(f"Proxy CONNECT failed: {status_line}")
    relay.settimeout(timeout)
    return relay

class ProxiedIMAP4_SSL(imaplib.IMAP4_SSL):
    def __init__(self, host, port, proxy=None):
        self._proxy = proxy
        super().__init__(host, port)
    def _create_socket(self, timeout=None):
        sock = make_proxied_socket(self.host, self.port, proxy=self._proxy)
        ctx = ssl.create_default_context()
        return ctx.wrap_socket(sock, server_hostname=self.host)

def resolve_hosts(mb):
    prov = (mb.get('provider') or 'gmail').lower()
    d_ih, d_ip, d_sh, d_sp = PROVIDER_HOSTS.get(prov, PROVIDER_HOSTS['gmail'])
    return (mb.get('imap_host') or d_ih, mb.get('imap_port') or d_ip,
            mb.get('smtp_host') or d_sh, mb.get('smtp_port') or d_sp)

def imap_connect(host, port, email_addr, password, proxy=None):
    try:
        M = ProxiedIMAP4_SSL(host, int(port), proxy=proxy)
        M.login(email_addr, password)
        return M
    except Exception as e:
        print(f"  IMAP connect failed for {email_addr}: {e}")
        return None

def imap_connect_oauth(host, port, email_addr, access_token, proxy=None):
    try:
        M = ProxiedIMAP4_SSL(host, int(port), proxy=proxy)
        auth_str = f"user={email_addr}\x01auth=Bearer {access_token}\x01\x01"
        M.authenticate('XOAUTH2', lambda _: auth_str.encode())
        return M
    except Exception as e:
        print(f"  IMAP OAuth connect failed for {email_addr}: {e}")
        return None

def outlook_imap_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        'client_id': client_id, 'client_secret': client_secret,
        'refresh_token': refresh_token, 'grant_type': 'refresh_token',
        'scope': 'https://outlook.office365.com/IMAP.AccessAsUser.All offline_access',
    }).encode()
    req = urllib.request.Request(
        'https://login.microsoftonline.com/common/oauth2/v2.0/token', data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())['access_token']

def mailbox_imap_login(mb, host, port, proxy=None):
    """Connect to IMAP using the right auth for the mailbox's provider."""
    prov = (mb.get('provider') or 'gmail').lower()
    email_addr = mb.get('email', '')
    if prov == 'gmail':
        token = gmail_access_token(
            mb.get('gmail_client_id', ''), mb.get('gmail_client_secret', ''),
            mb.get('gmail_refresh_token', ''))
        return imap_connect_oauth(host, port, email_addr, token, proxy=proxy)
    if prov in ('outlook', 'office365', 'microsoft'):
        token = outlook_imap_token(
            mb.get('outlook_client_id', '') or mb.get('gmail_client_id', ''),
            mb.get('outlook_client_secret', '') or mb.get('gmail_client_secret', ''),
            mb.get('outlook_refresh_token', '') or mb.get('gmail_refresh_token', ''))
        return imap_connect_oauth(host, port, email_addr, token, proxy=proxy)
    # yahoo / aol / icloud / custom → app password basic auth
    return imap_connect(host, port, email_addr, mb.get('app_password', ''), proxy=proxy)

# ── Gmail reply (OAuth2 / Gmail API) ─────────────────────────────────────────

def gmail_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        'client_id': client_id, 'client_secret': client_secret,
        'refresh_token': refresh_token, 'grant_type': 'refresh_token'
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())['access_token']
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f"    token endpoint {e.code}: {body}")
        raise

def send_reply_gmail_api(client_id, client_secret, refresh_token,
                         from_addr, to_addr, subject, body,
                         in_reply_to=None, thread_id=None):
    if not (client_id and client_secret and refresh_token):
        print("    Gmail API not configured for this mailbox")
        return False
    try:
        token = gmail_access_token(client_id, client_secret, refresh_token)
        msg = MIMEMultipart('alternative')
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to
        msg.attach(MIMEText(body, 'plain'))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        body_obj = {'raw': raw}
        if thread_id:
            body_obj['threadId'] = thread_id
        payload = json.dumps(body_obj).encode()
        req = urllib.request.Request(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            data=payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print(f"    ✓ Gmail replied to {to_addr}")
        return True
    except Exception as e:
        print(f"    Gmail API reply failed to {to_addr}: {e}")
        return False

# ── Outlook reply (Microsoft Graph API / HTTPS — works on Railway) ────────────

def outlook_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'scope': 'https://graph.microsoft.com/Mail.Send offline_access',
    }).encode()
    req = urllib.request.Request(
        'https://login.microsoftonline.com/common/oauth2/v2.0/token', data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())['access_token']
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f"    Outlook token {e.code}: {body}")
        raise

def send_reply_outlook_graph(client_id, client_secret, refresh_token,
                              from_addr, to_addr, subject, body,
                              in_reply_to=None):
    if not (client_id and client_secret and refresh_token):
        print("    Outlook Graph API not configured for this mailbox")
        return False
    try:
        token = outlook_access_token(client_id, client_secret, refresh_token)
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        }
        if in_reply_to:
            message["internetMessageHeaders"] = [
                {"name": "In-Reply-To", "value": in_reply_to},
                {"name": "References",  "value": in_reply_to},
            ]
        payload = json.dumps({"message": message, "saveToSentItems": True}).encode()
        req = urllib.request.Request(
            'https://graph.microsoft.com/v1.0/me/sendMail',
            data=payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print(f"    ✓ Outlook replied to {to_addr}")
        return True
    except Exception as e:
        print(f"    Outlook Graph reply failed to {to_addr}: {e}")
        return False

# ── Yahoo / AOL / iCloud reply (via Brevo HTTPS — SMTP blocked on Railway) ────

def send_reply_brevo(brevo_api_key, from_addr, from_name,
                     to_addr, subject, body, in_reply_to=None):
    if not brevo_api_key:
        print("    Brevo API key not configured for this mailbox")
        return False
    try:
        html = "<html><body>" + body.replace("\n", "<br>") + "</body></html>"
        payload_obj = {
            "sender": {"email": from_addr, "name": from_name or from_addr},
            "to": [{"email": to_addr}],
            "subject": subject,
            "htmlContent": html,
            "tags": ["warmup-reply"],
        }
        if in_reply_to:
            payload_obj["headers"] = {
                "In-Reply-To": in_reply_to,
                "References": in_reply_to,
            }
        payload = json.dumps(payload_obj).encode()
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=payload,
            headers={'api-key': brevo_api_key, 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print(f"    ✓ Brevo replied to {to_addr} (from {from_addr})")
        return True
    except Exception as e:
        print(f"    Brevo reply failed to {to_addr}: {e}")
        return False

# ── Route reply to the correct sender based on provider ──────────────────────

def send_reply(mb, cfg, to_addr, subject, body, in_reply_to=None, thread_id=None):
    prov = (mb.get('provider') or 'gmail').lower()

    if prov == 'gmail':
        return send_reply_gmail_api(
            mb.get('gmail_client_id', ''),
            mb.get('gmail_client_secret', ''),
            mb.get('gmail_refresh_token', ''),
            from_addr=mb.get('email', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to, thread_id=thread_id,
        )

    elif prov in ('outlook', 'office365', 'microsoft'):
        return send_reply_outlook_graph(
            mb.get('outlook_client_id', '') or mb.get('gmail_client_id', ''),
            mb.get('outlook_client_secret', '') or mb.get('gmail_client_secret', ''),
            mb.get('outlook_refresh_token', '') or mb.get('gmail_refresh_token', ''),
            from_addr=mb.get('email', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to,
        )

    elif prov in ('yahoo', 'aol', 'icloud', 'custom'):
        # SMTP blocked on Railway — route through Brevo sender for this mailbox
        brevo_key = mb.get('brevo_api_key') or cfg.get('brevo_api_key', '')
        return send_reply_brevo(
            brevo_key,
            from_addr=mb.get('email', ''),
            from_name=mb.get('name', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to,
        )

    else:
        print(f"    Unknown provider '{prov}' — attempting Gmail API")
        return send_reply_gmail_api(
            mb.get('gmail_client_id', ''),
            mb.get('gmail_client_secret', ''),
            mb.get('gmail_refresh_token', ''),
            from_addr=mb.get('email', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to, thread_id=thread_id,
        )

def get_body(msg):
    text = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain' and 'attachment' not in str(part.get('Content-Disposition') or ''):
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                        break
                except Exception: continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            text = (payload or b'').decode(msg.get_content_charset() or 'utf-8', errors='replace')
        except Exception: text = ''
    return text

def already_queued(message_id):
    if not message_id: return False
    try:
        res = sb.table('warmup_pending').select('id').eq('message_id', message_id).limit(1).execute()
        return bool(res.data)
    except Exception: return False

# --- spam rescue ---------------------------------------------------------
SPAM_FOLDERS = ["[Gmail]/Spam", "Spam", "Junk", "Junk E-mail", "Junk Email", "Bulk Mail"]

def rescue_from_spam(M, inbox_emails, inbox_name="INBOX"):
    """Move warm-up mail out of Spam/Junk into INBOX; leaves it UNSEEN so the
    reply loop can pick it up. Only rescues mail from our sending inboxes."""
    rescued = 0
    for folder in SPAM_FOLDERS:
        try:
            typ, _ = M.select(f'"{folder}"')
        except Exception:
            continue
        if typ != 'OK':
            continue
        typ, data = M.search(None, 'UNSEEN')
        if typ != 'OK' or not data or not data[0]:
            continue
        for num in data[0].split():
            try:
                _, hdr = M.fetch(num, '(RFC822.HEADER)')
                msg = email.message_from_bytes(hdr[0][1])
                _, from_addr = email.utils.parseaddr(msg.get('From', ''))
                if from_addr.lower() not in inbox_emails:
                    continue
                if folder.startswith('[Gmail]'):
                    M.copy(num, 'INBOX')
                    M.store(num, '+FLAGS', '\\Deleted')
                else:
                    try:
                        M.store(num, '-FLAGS', '($Junk)')
                        M.store(num, '+FLAGS', '($NotJunk)')
                    except Exception: pass
                    M.copy(num, inbox_name)
                    M.store(num, '+FLAGS', '\\Deleted')
                rescued += 1
            except Exception as e:
                print(f"  spam-rescue error on {folder}: {e}")
        try:
            M.expunge()
        except Exception:
            pass
    return rescued

def mark_important(M, num, is_gmail):
    try:
        if is_gmail: M.store(num, '+X-GM-LABELS', '\\Important')
        else: M.store(num, '+FLAGS', '\\Flagged')
    except Exception: pass

def send_queued_replies(mb, cfg):
    mbid = mb.get('id')
    now_ts = time.time()
    try:
        rows = sb.table('warmup_pending').select('*').eq('mailbox_id', mbid).eq('sent', False).execute().data or []
    except Exception as e:
        print(f"  warmup_pending lookup failed: {e}")
        return 0
    sent = 0
    for row in rows:
        if (row.get('reply_after') or 0) > now_ts:
            continue
        ok = send_reply(
            mb, cfg,
            to_addr=row.get('to_addr', ''),
            subject=row.get('subject', ''),
            body=row.get('body', ''),
            in_reply_to=row.get('message_id'),
            thread_id=row.get('thread_id'),
        )
        if ok:
            try:
                sb.table('warmup_pending').update({'sent': True, 'sent_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}).eq('id', row['id']).execute()
                sent += 1
            except Exception as e:
                print(f"    mark sent failed: {e}")
    return sent

def process_mailbox(mb, cfg, inbox_emails, min_m, max_m):
    email_addr = mb.get('email', '')
    password = mb.get('app_password', '')
    name = mb.get('name', email_addr)
    reply_chance = mb.get('reply_chance')
    reply_chance = 0.4 if reply_chance is None else float(reply_chance)
    do_rescue = mb.get('rescue_from_spam', True) is not False

        prov = (mb.get('provider') or 'gmail').lower()
    if prov == 'gmail':
        has_auth = bool(mb.get('gmail_client_id') and mb.get('gmail_client_secret') and mb.get('gmail_refresh_token'))
    elif prov in ('outlook', 'office365', 'microsoft'):
        has_auth = bool((mb.get('outlook_client_id') or mb.get('gmail_client_id')) and
                        (mb.get('outlook_client_secret') or mb.get('gmail_client_secret')) and
                        (mb.get('outlook_refresh_token') or mb.get('gmail_refresh_token')))
    else:
        has_auth = bool(password)
    if not email_addr or not has_auth:
        print(f"  Skipping {email_addr} — missing auth (provider={prov})")
        return

    # Send any previously queued replies whose timer has elapsed
    sent_queued = send_queued_replies(mb, cfg)
    if sent_queued:
        print(f"  Sent {sent_queued} queued replies")

    imap_host, imap_port, _, _ = resolve_hosts(mb)
    is_gmail = 'gmail' in imap_host.lower()

    print(f"\n→ {name} <{email_addr}> [{mb.get('provider','gmail')}]")
    M = mailbox_imap_login(mb, imap_host, imap_port, proxy=mailbox_proxy(mb))
    if not M: return

    opened = 0; queued = 0; rescued = 0
    try:
        if do_rescue:
            rescued = rescue_from_spam(M, inbox_emails)
            if rescued: print(f"  Rescued {rescued} emails from spam")

        M.select('INBOX')
        _, nums = M.search(None, 'UNSEEN')
        ids = nums[0].split() if nums[0] else []
        random.shuffle(ids)

        for num in ids[:20]:
            try:
                # Gmail exposes X-GM-THRID for threading; other providers don't
                if is_gmail:
                    _, data = M.fetch(num, '(X-GM-THRID RFC822)')
                else:
                    _, data = M.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])
                thread_id = None
                if is_gmail:
                    try:
                        meta = data[0][0].decode('utf-8', errors='replace')
                        mth = re.search(r'X-GM-THRID (\d+)', meta)
                        if mth: thread_id = format(int(mth.group(1)), 'x')
                    except Exception: pass

                from_name, from_addr = email.utils.parseaddr(msg.get('From', ''))
                if from_addr.lower() not in inbox_emails: continue

                subj = msg.get('Subject', '')
                msg_id = msg.get('Message-ID', '')
                warmup_type = msg.get('X-Warmup-Type', '').lower()
                is_manual = warmup_type == 'manual'

                M.store(num, '+FLAGS', '\\Seen')
                mark_important(M, num, is_gmail)
                opened += 1

                if already_queued(msg_id):
                    continue

                if random.random() >= reply_chance:
                    continue

                reply_subj = f"Re: {subj}" if not subj.lower().startswith('re:') else subj
                reply_body = random.choice(REPLY_TEMPLATES)

                if is_manual:
                    delay_sec = random.uniform(2, 8)
                    reply_after = time.time() + delay_sec
                else:
                    wait_min = bell_minutes(min_m, max_m)
                    reply_after = time.time() + wait_min * 60

                try:
                    sb.table('warmup_pending').insert({
                        'mailbox_id': mb.get('id'),
                        'to_addr': from_addr,
                        'subject': reply_subj,
                        'body': reply_body,
                        'message_id': msg_id,
                        'thread_id': thread_id,
                        'reply_after': reply_after,
                        'sent': False,
                    }).execute()
                    queued += 1
                    print(f"  Queued reply to {from_addr} (in {round((reply_after - time.time())/60)}m)")
                except Exception as e:
                    print(f"    queue insert failed: {e}")

            except Exception as e:
                print(f"    Error processing email: {e}")

        print(f"  Opened: {opened}  Queued: {queued}")
        try:
            sb.table('warmup_log').insert({
                'mailbox_id': mb.get('id'), 'email': email_addr,
                'opened': opened, 'replied': sent_queued, 'rescued': rescued,
                'ran_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }).execute()
        except Exception as e:
            print(f"  warmup_log insert failed: {e}")
    finally:
        try: M.logout()
        except Exception: pass

def main():
    print("=== Warm-up reply runner ===")
    cfg = load_settings()
    min_m = int(cfg.get('warmup_min_minutes') or 5)
    max_m = int(cfg.get('warmup_max_minutes') or 15)
    print(f"Bell curve: {min_m}–{max_m} min")
    inbox_emails = load_inbox_emails()
    print(f"Watching for emails from: {inbox_emails}")
    res = sb.table('warmup_mailboxes').select('*').eq('active', True).execute()
    mailboxes = res.data or []
    if not mailboxes:
        print("No active warm-up mailboxes found.")
        return
    random.shuffle(mailboxes)
    for mb in mailboxes:
        process_mailbox(mb, cfg, inbox_emails, min_m, max_m)
    print("\n=== Done ===")

def run_loop():
    while True:
        try:
            main()
        except Exception as e:
            print(f"!! run error: {e}")
        time.sleep(60)

if __name__ == '__main__':
    run_loop()
