# Deploying BriefPay to Render (free plan, PayPal sandbox)

Nothing here is automatic: it needs accounts and secrets only a human can create. Do the steps in order. Never paste a secret into a chat, an issue or a commit.

## What the code already does for you

* `render.yaml` describes the API service. It runs `alembic upgrade head` and then the API on `$PORT`, health-checks `/api/healthz`, generates `JWT_SECRET` for you, and fixes `APP_ENV=prod`, `PAYPAL_ENV=sandbox`, `IMAGE_PROVIDER=cloudinary`.
* **The API refuses to start in production with an unsafe configuration** (`backend/app/startup_checks.py`): a default or short `JWT_SECRET`, a SQLite database, a non-sandbox PayPal environment, half a set of PayPal credentials, or Cloudinary selected without `CLOUDINARY_URL`. The reason is in the deploy log (the message never contains a secret). Weaker problems are logged as warnings (no Gemini key, no webhook id, localhost URLs, demo mode on).
* A sleeping free service wakes in about a minute. PayPal retries webhooks, and the API also polls PayPal every 30 seconds while awake, so a missed webhook still confirms.

## Steps for the human

1. **Database (Aiven free PostgreSQL).** Create the service, download its CA certificate. Copy the connection string and change the prefix to `postgresql+psycopg://`. Keep `?sslmode=require`.
2. **Cloudinary (free plan).** Note the `cloudinary://<key>:<secret>@<cloud>` URL.
3. **Gemini.** Create a key in Google AI Studio with billing left OFF. Note the current Flash model name for `AI_MODEL`.
4. **PayPal sandbox.** Create a REST app (sandbox) with Orders, Payments, Payouts and Transaction Search enabled; note the client id and secret. Create the sandbox accounts listed in `docs/STATUS.md` (T-02).
5. **Render.** New > Blueprint > pick this repository. When asked, fill in the `sync: false` values:
   * `DATABASE_URL`, `DATABASE_SSL_CA` (set it to `/etc/secrets/aiven-ca.pem` and add the CA file under *Secret Files* with that name)
   * `APP_BASE_URL` = the API's `https://...onrender.com` URL, `WEB_BASE_URL` = the web app's URL, `CORS_ORIGINS` = the web app's URL (comma-separated, no spaces)
   * `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `GEMINI_API_KEY`, `AI_MODEL`, `CLOUDINARY_URL`, optionally `GITHUB_TOKEN` (raises GitHub's rate limit for the repository checks)
   * leave `PAYPAL_WEBHOOK_ID` empty for the first deploy
6. **Webhook.** In the PayPal developer dashboard add a sandbox webhook to `https://<api>.onrender.com/api/webhooks/paypal` for: `PAYMENT.AUTHORIZATION.CREATED`, `PAYMENT.AUTHORIZATION.VOIDED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DECLINED`, `PAYMENT.CAPTURE.PENDING`, `PAYMENT.CAPTURE.REFUNDED`, `PAYMENT.CAPTURE.REVERSED`, `PAYMENT.PAYOUTS-ITEM.*`, `PAYMENT.PAYOUTSBATCH.*`, `CHECKOUT.ORDER.APPROVED`. Copy the webhook id into `PAYPAL_WEBHOOK_ID` in Render and redeploy.
7. **Load the demo data** (once): in the Render shell for the API run
   `python scripts/seed.py --paypal-email <the freelancer's sandbox email> --repo <sample site repo> --site <sample site URL> --commit-1 <sha> --commit-2 <sha>`
8. **Check:** open `https://<api>.onrender.com/api/healthz` (expect `ok`) and `/docs`. In the Render log look for `startup` warnings and fix any you do not accept.
9. **Before recording the video:** open the health URL and the web app two minutes earlier so both services are awake, and run `backend/scripts/sandbox_check.py` locally once with the same sandbox keys.

## Things that will bite

* The free plan has **no persistent disk**: that is why production needs PostgreSQL and Cloudinary.
* `DEMO_MODE=true` leaves persona switching, the reconcile report and the tamper simulation open to any signed-in user. That is intended for the hackathon demo and flagged in the log.
* Pledge holds last about three days at PayPal; campaigns are capped at 72 hours. Authorize fresh live pledges within two days of recording.
