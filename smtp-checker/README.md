# SMTP Checker (Railway service)

Standalone worker that verifies emails in the `email_contacts` table of the
Listmonk Supabase project via MX lookup + SMTP RCPT, then writes back
`smtp_checked` / `smtp_valid`. Feeds the Valid/Invalid badges in
`email-cleaner.html`.

## Railway setup (fresh service)

1. New Project (or new service in an existing project) → **Deploy from GitHub repo** → `blubalences`.
2. **Settings → Source → Root Directory:** `smtp-checker`
   (this isolates it from the drip service; Railway only sees this folder).
3. **Variables:**
   - `SUPABASE_URL` = `https://xbwuvaxtnylqvagdvpxp.supabase.co`
   - `SUPABASE_SERVICE_KEY` = service-role key (needs write)
   - optional: `CHECK_BATCH` (default 200), `MAIL_FROM`, `SMTP_TIMEOUT` (default 15)
4. Start command and cron come from `railway.json` here:
   - start: `python smtp_checker.py`
   - cron: `*/30 * * * *` (every 30 min)
   - restart: NEVER (batch job, exits when done)

## Expected logs

```
N contact(s) to check (batch=200)
  [1/N] someone@domain.com -> VALID (...)
Done. valid=X invalid=Y unknown=Z
```

## ⚠️ Port 25

SMTP verification needs outbound port 25. Many Railway plans block it. If every
contact comes back `unknown`, that's the egress block — not bad data. In that
case run this on a VPS that allows port 25, or switch to a verification API.
