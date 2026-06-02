import imaplib
import smtplib
import socks
import socket
import email
import email.utils
import random
import time
import os
import ssl
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
    s = socks.socksocket()
    s.set_proxy(socks.HTTP, PROXY_HOST, PROXY_PORT,
                username=PROXY_USER, password=PROXY_PASS)
    s.settimeout(timeout)
    s.connect((host, int(port)))
    return s

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


def send_reply_smtp(smtp_host, smtp_port, username, password,
                    from_addr, to_addr, subject, body, in_reply_to=None):
    msg = MIMEMultipart('alternative')
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = in_reply_to
    msg.attach(MIMEText(body, 'plain'))
    try:
        if int(smtp_port) == 465:
            ctx = ssl.create_default_context()
            sock = make_proxied_socket(smtp_host, smtp_port)
            sock = ctx.wrap_socket(sock, server_hostname=smtp_host)
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.sock = sock
                server.login(username, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            raw = make_proxied_socket(smtp_host, smtp_port)
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.sock = raw
                server.file = server.makefile('rb')
                server.ehlo()
                server.starttls()
                server.login(username, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:
        print(f"    SMTP reply failed to {to_addr}: {e}")


def process_mailbox(mb, inbox_emails, min_m, max_m):
    email_addr = mb.get('email', '')
    password = mb.get('app_password', '')
    name = mb.get('name', email_addr)
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

                # Only process emails from our inboxes
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
                    # Reply instantly
                    delay = random.uniform(2, 8)
                    print(f"  Manual email from {from_addr} — replying in {delay:.0f}s")
                    time.sleep(delay)
                else:
                    # Bell curve delay
                    wait_min = bell_minutes(min_m, max_m)
                    wait_sec = wait_min * 60
                    print(f"  Auto email from {from_addr} — bell curve delay {wait_min}m")
                    time.sleep(min(wait_sec, 300))  # cap at 5min within a single run

                if random.random() < reply_chance:
                    reply_subj = f"Re: {subj}" if not subj.lower().startswith('re:') else subj
                    send_reply_smtp(smtp_host, smtp_port, email_addr, password,
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
