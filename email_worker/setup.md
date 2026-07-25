# Email Worker — Setup Checklist

This folder is a separate, self-contained Flask app, deployed
independently from the main Streamlit app. QStash calls it whenever
someone requests the full reading by email.

## 1. Push this folder to GitHub

Add `email_worker/` (this whole folder — `app.py`, `requirements.txt`,
`Procfile`, and all the copied `.py` modules) to your `astro-app`
repo, same as everything else.

## 2. Create the Render Web Service

- New → Web Service → connect your `astro-app` repo
- **Root Directory**: `email_worker`
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: leave blank (Render reads the `Procfile`
  automatically) — or explicitly `gunicorn app:app` if you'd rather
  set it directly
- **Instance Type**: Free is fine to start

## 3. Set these environment variables in Render

Render dashboard → your service → Environment:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | Same key already used by the main Streamlit app |
| `RESEND_API_KEY` | resend.com → API Keys |
| `RESEND_FROM_ADDRESS` | An address on a domain you've verified in Resend, e.g. `readings@yourdomain.com` |
| `QSTASH_CURRENT_SIGNING_KEY` | Upstash console → QStash tab → Signing Keys |
| `QSTASH_NEXT_SIGNING_KEY` | Same page, the other key |

## 4. Deploy, then copy the live URL

Once deployed, Render gives you a URL like
`https://your-worker-name.onrender.com`. The actual endpoint the
Streamlit app needs to point at is:

```
https://your-worker-name.onrender.com/generate-and-email
```

Test it's alive by visiting `https://your-worker-name.onrender.com/health`
in a browser — should return `{"status": "ok"}`.

## 5. Add secrets to the main Streamlit app

Back in `astro-app` (the main app, not this worker), add two new
entries to Streamlit's secrets — same place `ANTHROPIC_API_KEY`
already lives:

```toml
QSTASH_TOKEN = "your QStash token from the Upstash console"
EMAIL_WORKER_URL = "https://your-worker-name.onrender.com/generate-and-email"
```

## 6. Test end to end

1. In the main app, select "🪙📧 Quick summary + email me the full
   reading", enter a real email address you can check, and hit
   Compute Chart.
2. You should see the quick summary appear immediately, plus a
   message confirming the full reading was queued.
3. Check Render's logs for the worker — you should see the
   `/generate-and-email` request come in.
4. The full reading should land in your inbox within a few minutes.

## A note on reliability

This uses Render's **free tier**, which spins down after periods of
inactivity and takes 30–60 seconds to wake back up on the next
request. QStash will retry automatically if the first attempt times
out while the worker is waking up, so this should still work — just
with an occasional extra delay on the first email after a quiet
period. If this becomes a real annoyance, upgrading to Render's
cheapest paid tier removes the spin-down entirely.

## Keeping this folder in sync

The `.py` files in this folder are **copies**, not imports, from the
main app — Render deploys this as a fully independent service. If you
change chart computation or prompt logic in the main app later,
remember to copy the updated file(s) here too, or the emailed full
reading will drift out of sync with what the main app produces.
