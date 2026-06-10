import imaplib
import email
import email.utils
import email.header
import ssl
import time
import os
import random
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
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

REPLY_TEMPLATES = [
    "Yep, got it!", "Thanks, received it.", "Got it, thanks!",
    "Perfect, thank you.", "Yes, came through.", "Thanks so much!",
    "Awesome, got it.", "Received it, thanks!", "Yep, looks good.",
    "Thanks, all set!", "Got it — thanks!", "Yes, received. Thanks!",
]

def load_settings():
    rows = sb.table('settings').select('key,value').execute().data or []
    cfg = {}
    for r in rows:
        v = r.get('value', '') or ''
        if isinstance(v, list): v = v[0] if v else ''
        if isinstance(v, str): v = v.strip('"')
        cfg[r['key']] = v
    return cfg

def load_warmup_emails():
    rows = sb.table('warmup_mailboxes').select('email').eq('active', True).execute().data or []
    return set((r.get('email') or '').lower() for r in rows if r.get('email'))

def get_body(msg):
    text, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition') or '')
            if 'attachment' in disp: continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None: continue
                charset = part.get_content_charset() or 'utf-8'
                decoded = payload.decode(charset, errors='replace')
            except Exception: continue
            if ctype == 'text/plain' and not text: text = decoded
            elif ctype == 'text/html' and not html: html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            text = (payload or b'').decode(charset, errors='replace')
        except Exception: text = ''
    return text, html

def already_have(message_id):
    if not message_id: return False
    res = sb.table('replies').select('id').eq('message_id', message_id).limit(1).execute()
    return bool(res.data)

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
        print(f"    Gmail token {e.code}: {body}")
        raise

def send_reply_gmail_api(client_id, client_secret, refresh_token,
                         from_addr, to_addr, subject, body,
                         in_reply_to=None, thread_id=None):
    if not (client_id and client_secret and refresh_token):
        print("    Gmail API not configured for this inbox")
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

def outlook_access_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        'client_id': client_id, 'client_secret': client_secret,
        'refresh_token': refresh_token, 'grant_type': 'refresh_token',
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
        print("    Outlook Graph API not configured for this inbox")
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

def send_reply_brevo(brevo_api_key, from_addr, from_name,
                     to_addr, subject, body, in_reply_to=None):
    if not brevo_api_key:
        print("    Brevo API key not configured for this inbox")
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

def send_reply(ib, cfg, to_addr, subject, body, in_reply_to=None, thread_id=None):
    prov = (ib.get('provider') or 'gmail').lower()

    if prov == 'gmail':
        return send_reply_gmail_api(
            ib.get('gmail_client_id', ''),
            ib.get('gmail_client_secret', ''),
            ib.get('gmail_refresh_token', ''),
            from_addr=ib.get('email', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to, thread_id=thread_id,
        )
    elif prov in ('outlook', 'office365', 'microsoft'):
        return send_reply_outlook_graph(
            ib.get('outlook_client_id', '') or ib.get('gmail_client_id', ''),
            ib.get('outlook_client_secret', '') or ib.get('gmail_client_secret', ''),
            ib.get('outlook_refresh_token', '') or ib.get('gmail_refresh_token', ''),
            from_addr=ib.get('email', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to,
        )
    else:
        brevo_key = ib.get('brevo_api_key') or cfg.get('brevo_api_key', '')
        return send_reply_brevo(
            brevo_key,
            from_addr=ib.get('email', ''),
            from_name=ib.get('name', ''),
            to_addr=to_addr, subject=subject, body=body,
            in_reply_to=in_reply_to,
        )

def count_warmup_sent_today(inbox_id, day_start_iso):
    try:
        res = sb.table('send_log').select('id').eq('inbox_id', inbox_id)\
            .eq('kind', 'warmup').gte('sent_at', day_start_iso).execute()
        return len(res.data or [])
    except Exception:
        return 0

def process_inbox(ib, warmup_emails, cfg):
    email_addr = ib.get('email', '')
    host = ib.get('imap_host') or 'imap.gmail.com'
    port = ib.get('imap_port') or 993
    password = ib.get('imap_password', '')
    if not email_addr or not password:
        print(f"  Skipping {email_addr} — no IMAP password set")
        return
    print(f"\n→ {email_addr} [{host}:{port}]")

    daily_limit = int(ib.get('warmup_daily_limit') or 0)
    day_start = time.strftime('%Y-%m-%dT00:00:00Z', time.gmtime())
    warmup_sent_today = count_warmup_sent_today(ib['id'], day_start) if daily_limit > 0 else 0

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
        since = time.strftime('%d-%b-%Y', time.gmtime(time.time() - 1 * 86400))
        _, nums = M.search(None, f'(SINCE {since})')
        ids = nums[0].split() if nums[0] else []
        print(f"  Scanning {len(ids)} emails from last 1 day")
        for num in ids[-200:]:
            try:
                _, data = M.fetch(num, '(RFC822)')
                msg = email.message_from_bytes(data[0][1])
                from_name, from_addr = email.utils.parseaddr(msg.get('From', ''))
                from_addr = (from_addr or '').lower()

                if from_addr == email_addr.lower(): continue
                if not from_addr or '@' not in from_addr: continue

                message_id = msg.get('Message-ID', '') or ''
                if already_have(message_id): continue

                kind = 'warmup' if from_addr in warmup_emails else 'prospect'

                subject = str(email.header.make_header(email.header.decode_header(msg.get('Subject', ''))))
                text, html = get_body(msg)
                in_reply_to = msg.get('In-Reply-To', '') or ''
                date_hdr = msg.get('Date', '')
                try: received = email.utils.parsedate_to_datetime(date_hdr).isoformat()
                except Exception: received = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

                sb.table('replies').insert({
                    'kind': kind,
                    'direction': 'in',
                    'from_name': from_name or '',
                    'from_email': from_addr,
                    'to_email': email_addr,
                    'inbox_email': email_addr,
                    'subject': subject,
                    'body_text': text,
                    'body_html': html,
                    'message_id': message_id,
                    'thread_id': in_reply_to or None,
                    'received_at': received,
                    'read': False,
                }).execute()
                captured += 1
                print(f"    + [{kind}] reply from {from_addr}: {subject[:50]}")

                if kind == 'warmup':
                    if daily_limit > 0:
                        warmup_sent_today = count_warmup_sent_today(ib['id'], day_start)
                    if daily_limit > 0 and warmup_sent_today >= daily_limit:
                        print(f"    ! auto-reply to {from_addr} skipped — inbox at daily limit ({warmup_sent_today}/{daily_limit})")
                    else:
                        reply_subj = f"Re: {subject}" if not subject.lower().startswith('re:') else subject
                        reply_body = random.choice(REPLY_TEMPLATES)
                        ok = send_reply(
                            ib, cfg,
                            to_addr=from_addr,
                            subject=reply_subj,
                            body=reply_body,
                            in_reply_to=message_id or None,
                        )
                        if ok:
                            try:
                                sb.table('send_log').insert({
                                    'inbox_id': ib['id'],
                                    'recipient_email': from_addr,
                                    'status': 'sent',
                                    'kind': 'warmup',
                                    'sent_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                }).execute()
                                warmup_sent_today += 1
                            except Exception as e:
                                print(f"    ! send_log insert failed: {e}")
                        else:
                            print(f"    ! auto-reply to {from_addr} failed")

            except Exception as e:
                print(f"    error on message: {e}")
        print(f"  Captured: {captured}")
    finally:
        try: M.logout()
        except Exception: pass

def main():
    print("=== Reply catcher ===")
    cfg = load_settings()
    warmup_emails = load_warmup_emails()
    print(f"Known warm-up addresses: {len(warmup_emails)}")
    inboxes = sb.table('inboxes').select('*').eq('active', True).execute().data or []
    if not inboxes:
        print("No active inboxes.")
        return
    for ib in inboxes:
        process_inbox(ib, warmup_emails, cfg)
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
