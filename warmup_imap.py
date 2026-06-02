import imaplib
import socket
import email
import email.utils
import random
import time
import os
import ssl
import json
import base64
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
}

REPLY_TEMPLATES = [
    "Yep, got it!",
    "Thanks, received it.",
    "Got it, thanks!",
    "Perfect, thank you.",
    "Yes, came through.",
    "Thanks so much!",
    "Awesome, got it.",
    "Received it, thanks!",
    "Yep, looks good.",
    "Thanks, all set!",
    "Got it — thanks!",
    "Yes, received. Thanks!",
]

sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def load_settings():
    rows = sb.table('settings').select('key,value').execute().data or []
    cfg = {}
    for r in rows:
        v = r.get('value', '') or ''
        if isinstance(v, list):
            v = v[0] if v else ''
        if isinstance(v, str):
            v = v.strip('"')
        cfg[r['key']] = v
    return cfg


def load_inbox_emails():
    rows = sb.table('inboxes').select('email').eq('active', True).execute().data or []
    return set(r['email'].lower() for r in rows)


def bell_minutes(min_m, max_m):
    total = sum(random.random() for _ in range(6))
    return round(min_m + (total / 6) * (max_m - min_m))


def make_proxied_socket(host, port, timeout=30):
    if not PROXY_HOST or not PROXY_USER:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(timeout)
        return sock
    proxy = socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=timeout)
    auth = base64.b64encode(f"{PROXY_USER}:{PROXY_PASS}".encode()).decode()
    connect_req = (
        f"CONNECT {host}:{int(port)} HTTP/1.1\r\n"
        f"Host: {host}:{int(port)}\r\n"
        f"Proxy-Authorization: Basic {auth}\r\n"
        f"\r\n"
    )
    proxy.sendall(connect_req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = proxy.recv(4096)
        if not chunk:
            break
        resp += chunk
    status_line = resp.split(b"\r\n")[0].decode(errors="replace")
    if " 200 " not in status_line:
        raise Exception(f"Proxy CONNECT failed: {status_line}")
    proxy.settimeout(timeout)
    return proxy


class ProxiedIMAP4_SSL(imaplib.IMAP4_SSL):
    def _create_socket(self, timeout=None):
        sock = make_proxied_socket(self.host, self.port)
        ctx = ssl.create_default_context()
        return ctx.wrap_socket(sock, server_hostname=self.host)


def resolve_hosts(mb):
    prov = (mb.get('provider') or 'gmail').lower()
    d_ih, d_ip, d_sh, d_sp = PROVIDER_HOSTS.get(prov, PROVIDER_HOSTS['gmail'])
    return (
        mb.get('imap_host') or d_ih,
        mb.get('imap_port') or d_ip,
        mb.get('smtp_host') or d_sh,
        mb.get('smtp_port') or d_sp,
    )


def imap_connect(host, port, email_addr, password):
    try:
        M = ProxiedIMAP4_SSL(host, int(port))
        M.login(email_addr, password)
        return M
    except Exception as e:
        print(f"  IMAP connect failed for {email_addr}: {e}")
        return None


def gmail_access_token(client_id, client_secret, refresh_token):
    """Exchange a refresh token for a short-lived access token over HTTPS."""
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
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
                         from_addr, to_addr, subject, body, in_reply_to=None):
    """Send a reply through the Gmail API (HTTPS port 443 — no SMTP needed)."""
    if not (client_id and client_secret and refresh_token):
        print("    Gmail API not configured for this mailbox (missing client_id/secret/refresh_token)")
        return
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
        payload = json.dumps({'raw': raw}).encode()

        req = urllib.request.Request(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            print(f"    ✓ Replied to {to_addr}")
        except urllib.error.HTTPError as e:
            errbody = e.read().decode(errors='replace')
            print(f"    Gmail send {e.code}: {errbody}")
    except Exception as e:
        print(f"    Gmail API reply failed to {to_addr}: {e}")


def rescue_from_spam(M, inbox_emails):
    rescued = 0
    for folder in ('[Gmail]/Spam', 'Junk', 'Spam', 'Junk Email'):
        try:
            status, _ = M.select(folder)
            if status != 'OK':
                continue
            _, nums = M.search(None, 'UNSEEN')
            for num in (nums[0].split() if nums[0] else []):
                _, data = M.fetch(num, '(RFC822.HEADER)')
                raw = data[0][1].decode('utf-8', errors='replace')
                msg = email.message_from_string(raw)
                frm = msg.get('From', '')
                _, from_addr = email.utils.parseaddr(frm)
                if from_addr.lower() in inbox_emails:
                    M.copy(num, 'INBOX')
                    M.store(num, '+FLAGS', '\\Deleted')
                    M.expunge()
                    rescued += 1
        except Exception:
            pass
    return rescued


def mark_important(M, num, is_gmail):
    try:
        if is_gmail:
            M.store(num, '+X-GM-LABELS', '\\Important')
        else:
            M.store(num, '+FLAGS', '\\Flagged')
    except Exception as e:
        print(f"    mark important failed: {e}")


def process_mailbox(mb, inbox_emails, min_m, max_m):
    email_addr = mb.get('email', '')
    password = mb.get('app_password', '')
    name = mb.get('name', email_addr)
    client_id = mb.get('gmail_client_id', '')
    client_secret = mb.get('gmail_client_secret', '')
    refresh_token = mb.get('gmail_refresh_token', '')
    reply_chance = mb.get('reply_chance')
    reply_chance = 0.4 if reply_chance is None else float(reply_chance)
    do_rescue = mb.get('rescue_from_spam', True) is not False

    if not email_addr or not password:
        print(f"  Skipping {email_addr} — missing email or app_password")
        return

    imap_host, imap_port, smtp_host, smtp_port = resolve_hosts(mb)
    is_gmail = 'gmail' in imap_host.lower()

    print(f"\n→ {name} <{email_addr}> [{mb.get('provider','gmail')}]")
    M = imap_connect(imap_host, imap_port, email_addr, password)
    if not M:
        return

    replied = 0
    opened = 0
    rescued = 0
    try:
        if do_rescue:
            rescued = rescue_from_spam(M, inbox_emails)
            if rescued:
                print(f"  Rescued {rescued} emails from spam")

        M.select('INBOX')
        _, nums = M.search(None, 'UNSEEN')
        ids = nums[0].split() if nums[0] else []
        random.shuffle(ids)

        for num in ids[:20]:
            try:
                _, data = M.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])

                frm = msg.get('From', '')
                _, from_addr = email.utils.parseaddr(frm)

                if from_addr.lower() not in inbox_emails:
                    continue

                subj = msg.get('Subject', '')
                msg_id = msg.get('Message-ID', '')
                warmup_type = msg.get('X-Warmup-Type', '').lower()
                is_manual = warmup_type == 'manual'

                M.store(num, '+FLAGS', '\\Seen')
                mark_important(M, num, is_gmail)
                opened += 1

                if is_manual:
                    delay = random.uniform(2, 8)
                    print(f"  Manual email from {from_addr} — replying in {delay:.0f}s")
                    time.sleep(delay)
                else:
                    wait_min = bell_minutes(min_m, max_m)
                    wait_sec = wait_min * 60
                    print(f"  Auto email from {from_addr} — bell curve delay {wait_min}m")
                    time.sleep(min(wait_sec, 300))

                if random.random() < reply_chance:
                    reply_subj = f"Re: {subj}" if not subj.lower().startswith('re:') else subj
                    send_reply_gmail_api(
                        client_id, client_secret, refresh_token,
                        from_addr=email_addr, to_addr=from_addr,
                        subject=reply_subj,
                        body=random.choice(REPLY_TEMPLATES),
                        in_reply_to=msg_id)
                    replied += 1

            except Exception as e:
                print(f"    Error processing email: {e}")

        print(f"  Opened: {opened}  Replied: {replied}")

        try:
            sb.table('warmup_log').insert({
                'mailbox_id': mb.get('id'),
                'email': email_addr,
                'opened': opened,
                'replied': replied,
                'rescued': rescued,
                'ran_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }).execute()
        except Exception as e:
            print(f"  warmup_log insert failed: {e}")

    finally:
        try:
            M.logout()
        except Exception:
            pass


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
        process_mailbox(mb, inbox_emails, min_m, max_m)
        time.sleep(random.uniform(10, 30))

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
