# Realest AI WhatsApp Lead Bot

WhatsApp lead-qualification service for Indian real estate brokers. The full spec is in
[CLAUDE.md](CLAUDE.md).

**Current state: Phase 1 (echo bot).** Messages sent to a broker's WhatsApp number are stored
in Supabase and the text is sent straight back. Phase 2 replaces the echo with the Claude agent.

## Local development

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed by uv if missing.

```sh
uv sync                                  # install dependencies
uv run pytest                            # run tests (Graph API and database are mocked)
uv run ruff check . && uv run ruff format --check .
cp .env.example .env                     # fill in values to run the server locally
uv run uvicorn app.main:app --reload
```

`tests/test_db_integration.py` checks the real Supabase queries (including duplicate
detection) and is skipped unless you point it at a **throwaway** database:

```sh
supabase start                           # local Supabase via Docker, then apply the migration
TEST_POSTGREST_URL=http://127.0.0.1:54321/rest/v1 TEST_POSTGREST_KEY=<local service key> uv run pytest
```

## Setting up Phase 1

You need accounts on Supabase, Meta for Developers and Railway. Do the steps in order.

### 1. Supabase

1. Create a project. Choose the Mumbai region (closest to your leads).
2. Apply the migration in `supabase/migrations/`: open **SQL Editor**, paste the file's contents
   and run it. (Or with the Supabase CLI from this folder: `supabase link`, then `supabase db push`.)
3. From the project's API settings, copy the **Project URL** and the **service-role / secret
   key**. The secret key bypasses row-level security, so keep it server-side only.

### 2. Encryption key

Broker access tokens are stored encrypted. Generate a key once and keep it safe: if it's lost,
every broker's token must be re-entered.

```sh
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Meta (WhatsApp Cloud API)

1. In the [App Dashboard](https://developers.facebook.com/apps), click **Create App**, select the
   **Connect with customers through WhatsApp** use case, then pick or create a business
   portfolio. WhatsApp is added to the app for you.
2. On WhatsApp → **API Setup**, note the test number's **Phone number ID** and the **WhatsApp
   Business Account ID**. Add your own phone to the allowed recipients and verify it (test
   numbers can only message a handful of verified numbers).
3. App settings → **Basic** → copy the **App secret**.
4. Get an access token. The one on the API Setup page expires within a day; for anything longer,
   create a **System User** in Meta Business Settings and generate a token with
   `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
5. Note the current Graph API version (shown in the sample request on API Setup, e.g. `v24.0`).

### 4. Railway

1. New project → deploy from GitHub → `tttlai/realestai`, branch `whatsapp-lead-bot`.
2. In the service settings:
   - **Root Directory**: `/projects/whatsapp-leads-bot`
   - **Config file path**: `/projects/whatsapp-leads-bot/railway.json` (Railway resolves this from
     the repo root, not the root directory)
3. Add variables:

   | Variable | Value |
   |---|---|
   | `SUPABASE_URL` | Project URL from step 1 |
   | `SUPABASE_SERVICE_ROLE_KEY` | secret key from step 1 |
   | `META_APP_SECRET` | App secret from step 3 |
   | `META_VERIFY_TOKEN` | any long random string you make up |
   | `META_GRAPH_VERSION` | e.g. `v24.0` |
   | `TOKEN_ENCRYPTION_KEY` | key from step 2 |

4. Networking → **Generate Domain**. Check `https://<your-domain>/health` returns `{"status":"ok"}`.

### 5. Add the broker

With the same variables available locally (copy them into `.env`, or use `railway link` then
prefix the command with `railway run`):

```sh
uv run python -m scripts.seed_broker \
  --name "Your Name" --agency-name "Your Agency" \
  --phone-number-id <Phone number ID> --waba-id <WABA ID> \
  --alert-number <your WhatsApp number>
```

It prompts for the access token (or reads `BROKER_ACCESS_TOKEN`). Re-running with the same
phone number ID updates the broker, e.g. to replace an expired token.

### 6. Connect the webhook

In the Meta app: WhatsApp → **Configuration** → Webhook:

- Callback URL: `https://<your-domain>/webhooks/whatsapp`
- Verify token: the `META_VERIFY_TOKEN` value
- Click **Verify and save**, then under webhook fields **subscribe to `messages`**.

### 7. Acceptance check

1. From your phone, send a message to the test number. The same text should come back.
2. In Supabase, `messages` has one inbound and one outbound row, and `leads` has your number.
3. Duplicate deliveries are dropped on `wa_message_id` (enforced by a unique constraint and
   covered by tests). This should return no rows:
   `select wa_message_id, count(*) from messages group by 1 having count(*) > 1;`

If no reply arrives, check the Railway logs: each line is JSON with `broker_id`, `lead_id` and
`wa_message_id`. A `no active broker for phone_number_id` warning means step 5's phone number ID
doesn't match the number Meta is sending from.

## Known Phase 1 limitations

- Messages are handled in-process after Meta gets its 200. If the service restarts mid-way, that
  message may go unanswered (Meta won't resend it, since it already got a 200). It is still in
  `messages` if storing finished.
- If sending a reply fails (after one retry on a Meta server error), the error is logged and the
  message is not retried, so a lead is never sent the same reply twice.
- Only text is echoed. Other message types (images, voice notes) are stored but not answered
  until Phase 6.
