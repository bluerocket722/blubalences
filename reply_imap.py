import imaplib
import socket
import email
import email.utils
import ssl
import time
import os
from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

PROVIDER_DEFAULT = ('imap.gmail.com', 993)


def load_prospect_emails():
    rows = sb.table('enrollments').select('email').execute().data or []
    return set((r.get('email') or '').lower() for r in rows if r.get('email'))


def get_body(msg):
    text, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition') or '')
            if 'attachment' in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or 'utf-8'
                decoded = payload.decode(charset, errors='replace')
            except Exception:
                continue
            if ctype == 'text/plain' and not text:
                text = decoded
            elif ctype == 'text/html' and not html:
                html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            text = (payload or b'').decode(charset, errors='replace')
        except Exception:
            text = ''
    return text, html


def already_have(message_id):
    if not message_id:
        return False
    res = sb.table('replies').select('id').eq('message_id', message_id).limit(1).execute()
    return bool(res.data)


def process_inbox(ib, prospects):
    email_addr = ib.get('email', '')
    host = ib.get('imap_host') or PROVIDER_DEFAULT[0]
    port = ib.get('imap_port') or PROVIDER_DEFAULT[1]
    password = ib.get('imap_password', '')

    if not email_addr or not password:
        print(f"  Skipping {email_addr} — no IMAP password set")
        return

    print(f"\n→ {email_addr} [{host}:{port}]")
    try:
        ctx = ssl.create_default_context()
        M = imaplib.IMAP4_SSL(host, int(port), ssl_context=ctx)
        M.login(email_addr, password)
    except Exception as e:
        print(f"  IMAP connect failed: {e}")
        return

    captured = 0
    try:
        M.select('INBOX')
        # Look at the last 3 days regardless of read state; dedup by Message-ID
        since = time.strftime('%d-%b-%Y', time.gmtime(time.time() - 3 * 86400))
        _, nums = M.search(None, f'(SINCE {since})')
        ids = nums[0].split() if nums[0] else []

        for num in ids[-100:]:
            try:
                _, data = M.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])

                _, from_addr = email.utils.parseaddr(msg.get('From', ''))
                from_addr = (from_addr or '').lower()
                if from_addr not in prospects:
                    continue

                message_id = msg.get('Message-ID', '') or ''
                if already_have(message_id):
                    continue

                from_name = email.utils.parseaddr(msg.get('From', ''))[0] or ''
                subject = str(email.header.make_header(email.header.decode_header(msg.get('Subject', ''))))
                text, html = get_body(msg)
                date_hdr = msg.get('Date', '')
                try:
                    received = email.utils.parsedate_to_datetime(date_hdr).isoformat()
                except Exception:
                    received = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

                sb.table('replies').insert({
                    'from_name': from_name,
                    'from_email': from_addr,
                    'to_email': email_addr,
                    'inbox_email': email_addr,
                    'subject': subject,
                    'body_text': text,
                    'body_html': html,
                    'message_id': message_id,
                    'received_at': received,
                    'read': False,
                }).execute()
                captured += 1
                print(f"    + reply from {from_addr}: {subject[:50]}")
            except Exception as e:
                print(f"    error on message: {e}")

        print(f"  Captured: {captured}")
    finally:
        try:
            M.logout()
        except Exception:
            pass


def main():
    print("=== Reply catcher ===")
    prospects = load_prospect_emails()
    print(f"Known prospects: {len(prospects)}")

    inboxes = sb.table('inboxes').select('*').eq('active', True).execute().data or []
    if not inboxes:
        print("No active inboxes.")
        return

    for ib in inboxes:
        process_inbox(ib, prospects)

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
