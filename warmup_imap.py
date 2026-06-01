import imaplib
import smtplib
import socks
import socket
import email
import email.utils
import random
import time
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

# ── Supabase
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

# ── Webshare proxy (rotating)
PROXY_HOST = os.environ.get('WEBSHARE_HOST', 'p.webshare.io')
PROXY_PORT = int(os.environ.get('WEBSHARE_PORT', '1080'))
PROXY_USER = os.environ.get('WEBSHARE_USER', '')
PROXY_PASS = os.environ.get('WEBSHARE_PASS', '')

# ── Tuning
REPLY_CHANCE = 0.4          # 40% of warm-up emails get a reply
SPAM_RESCUE  = True         # move warm-up emails out of spam
WARMUP_TAG   = 'warmup'     # Brevo tag set in drip-warmup/index.ts

REPLY_TEMPLATES = [
    "Thanks for reaching out! I'll take a look and get back to you.",
    "Got it, appreciate the note.",
    "Thanks! This is helpful.",
    "Received — I'll follow up shortly.",
    "Appreciate you sending this over.",
    "Good timing, I was just thinking about this.",
    "Thanks for the heads up!",
    "Makes sense, I'll keep this in mind.",
]

sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def make_proxied_socket(host, port, timeout=30):
    """Return a SOCKS5 socket routed through Webshare."""
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, PROXY_HOST, PROXY_PORT,
                username=PROXY_USER, password=PROXY_PASS)
    s.settimeout(timeout)
    s.connect((host, int(port)))
    return s


class ProxiedIMAP4_SSL(imaplib.IMAP4_SSL):
    """IMAP4 over SSL routed through a SOCKS5 proxy."""
    def _create_socket(self, timeout=None):
        sock = make_proxied_socket(self.host, self.port)
        import ssl
        ctx = ssl.create_default_context()
        return ctx.wrap_socket(sock, server_hostname=self.host)


def imap_connect(host, port, email_addr, password):
    try:
        M = ProxiedIMAP4_SSL(host, int(port))
        M.login(email_addr, password)
        return M
    except Exception as e:
        print(f"  IMAP connect failed for {email_addr}: {e}")
        return None


def rescue_from_spam(M, email_addr):
    """Move warm-up tagged emails from Spam to Inbox."""
    rescued = 0
    for folder in ('[Gmail]/Spam', 'Junk', 'Spam', 'Junk Email'):
        try:
            status, _ = M.select(folder)
            if status != 'OK':
                continue
            # search for emails with warmup tag in subject or from our inboxes
            _, nums = M.search(None, 'UNSEEN')
            for num in (nums[0].split() if nums[0] else []):
                _, data = M.fetch(num, '(RFC822.HEADER)')
                raw = data[0][1].decode('utf-8', errors='replace')
                msg = email.message_from_string(raw)
                subj = msg.get('Subject', '')
                frm  = msg.get('From', '')
                # heuristic: if it came from one of our sending domains, rescue it
                if any(keyword in subj.lower() for keyword in ['warmup', 'warm-up', 'warm up']) \
                   or 'blubalence' in frm.lower():
                    M.copy(num, 'INBOX')
                    M.store(num, '+FLAGS', '\\Deleted')
                    M.expunge()
                    rescued += 1
        except Exception:
            pass
    return rescued


def mark_read_and_maybe_reply(M, smtp_host, smtp_port, email_addr, password, brevo_key):
    """Open unread warm-up emails, mark read, reply to some."""
    replied = 0
    opened  = 0
    try:
        M.select('INBOX')
        _, nums = M.search(None, 'UNSEEN')
        ids = nums[0].split() if nums[0] else []
        random.shuffle(ids)

        for num in ids[:20]:  # cap at 20 per run per inbox
            try:
                _, data = M.fetch(num, '(RFC822)')
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                subj    = msg.get('Subject', '')
                frm     = msg.get('From', '')
                msg_id  = msg.get('Message-ID', '')
                to_addr = msg.get('To', '')

                # mark read
                M.store(num, '+FLAGS', '\\Seen')
                opened += 1

                # small human delay
                time.sleep(random.uniform(2, 8))

                # reply to a % of them
                if random.random() < REPLY_CHANCE and frm:
                    reply_text = random.choice(REPLY_TEMPLATES)
                    reply_subj = f"Re: {subj}" if not subj.startswith('Re:') else subj

                    from_name, from_addr = email.utils.parseaddr(frm)
                    if not from_addr:
                        continue

                    # send reply via SMTP through proxy
                    send_reply_smtp(
                        smtp_host, smtp_port, email_addr, password,
                        from_addr=email_addr,
                        to_addr=from_addr,
                        subject=reply_subj,
                        body=reply_text,
                        in_reply_to=msg_id,
                    )
                    replied += 1
                    time.sleep(random.uniform(5, 15))

            except Exception as e:
                print(f"    Error processing email: {e}")

    except Exception as e:
        print(f"  INBOX scan error: {e}")

    return opened, replied


def send_reply_smtp(smtp_host, smtp_port, username, password,
                    from_addr, to_addr, subject, body, in_reply_to=None):
    """Send reply via SMTP through Webshare proxy."""
    msg = MIMEMultipart('alternative')
    msg['From']    = from_addr
    msg['To']      = to_addr
    msg['Subject'] = subject
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References']  = in_reply_to

    msg.attach(MIMEText(body, 'plain'))

    # patch socket for this SMTP connection
    orig_socket = socket.socket
    def proxied_socket(*args, **kwargs):
        return make_proxied_socket(smtp_host, smtp_port)

    try:
        # Try SSL first (port 465), fall back to STARTTLS (587)
        if int(smtp_port) == 465:
            import ssl
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


def process_inbox(inbox):
    email_addr  = inbox.get('email', '')
    imap_host   = inbox.get('imap_host', '')
    imap_port   = inbox.get('imap_port', 993)
    smtp_host   = inbox.get('smtp_host', '')
    smtp_port   = inbox.get('smtp_port', 587)
    password    = inbox.get('imap_password', '')
    brevo_key   = inbox.get('brevo_api_key', '')
    name        = inbox.get('name', email_addr)

    if not imap_host or not password:
        print(f"  Skipping {email_addr} — missing imap_host or imap_password")
        return

    print(f"\n→ {name} <{email_addr}>")

    M = imap_connect(imap_host, imap_port, email_addr, password)
    if not M:
        return

    try:
        if SPAM_RESCUE:
            rescued = rescue_from_spam(M, email_addr)
            if rescued:
                print(f"  Rescued {rescued} emails from spam")

        opened, replied = mark_read_and_maybe_reply(
            M, smtp_host, smtp_port, email_addr, password, brevo_key
        )
        print(f"  Opened: {opened}  Replied: {replied}")

        # log to Supabase
        sb.table('warmup_log').insert({
            'inbox_id':   inbox.get('id'),
            'email':      email_addr,
            'opened':     opened,
            'replied':    replied,
            'rescued':    rescued if SPAM_RESCUE else 0,
            'ran_at':     time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }).execute()

    finally:
        try:
            M.logout()
        except Exception:
            pass


def main():
    print("=== Warm-up IMAP runner ===")
    res = sb.table('inboxes').select('*').eq('active', True).execute()
    inboxes = res.data or []

    if not inboxes:
        print("No active inboxes found.")
        return

    # shuffle so order varies each run
    random.shuffle(inboxes)

    for inbox in inboxes:
        process_inbox(inbox)
        # human-like gap between inboxes
        time.sleep(random.uniform(10, 30))

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
