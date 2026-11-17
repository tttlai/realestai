# Realest AI WhatsApp Lead Bot

WhatsApp lead-qualification service for Indian real estate brokers. The full spec is in
[CLAUDE.md](CLAUDE.md).

**Current state: Phase 3 (lead intake) built; Phase 2 (agent) live.** Messages sent to a broker's WhatsApp number are stored in
Supabase and answered by a Claude agent that qualifies the lead (buy or rent, budget, area, BHK,
timeline, home loan), quotes only the broker's listed properties, and hands hot or tricky leads
to the broker. Every agent run is logged to `agent_logs`. Leads from Facebook/Instagram lead
forms and from property-portal emails get a WhatsApp opener template, and the agent takes over
when they reply.

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

## Setting up

You need accounts on Supabase, Meta for Developers and Railway. Do the steps in order.

### 1. Supabase

1. Create a project. Choose the Mumbai region (closest to your leads).
2. Apply the migrations in `supabase/migrations/`, oldest first: open **SQL Editor**, paste each
   file's contents and run it. (Or with the Supabase CLI from this folder: `supabase link`, then
   `supabase db push`.) When a new migration is added later, run just that file.
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

1. New project → deploy from GitHub → `tttlai/realestai`, branch `main`.
2. In the service's **Settings** (Railway no longer reads config files for new services, so
   everything is set here):
   - **Source → Root Directory**: `/projects/whatsapp-leads-bot`
   - **Source → Watch Paths**: `/projects/whatsapp-leads-bot/**`
   - **Build**: the Dockerfile is picked up automatically
   - **Deploy → Healthcheck Path**: `/health`
   - **Deploy → Restart Policy**: On Failure, 5 retries

   A service created before 2026-08-28 may still point at `railway.json` under **Config-as-code
   → Railway Config File**. Railway stops reading that file on 2026-12-01: enter the values
   above, then clear that field so the dashboard settings apply.
3. Add variables:

   | Variable | Value |
   |---|---|
   | `SUPABASE_URL` | Project URL from step 1 |
   | `SUPABASE_SERVICE_ROLE_KEY` | secret key from step 1 |
   | `META_APP_SECRET` | App secret from step 3 |
   | `META_VERIFY_TOKEN` | any long random string you make up |
   | `META_GRAPH_VERSION` | e.g. `v24.0` |
   | `TOKEN_ENCRYPTION_KEY` | key from step 2 |
   | `ANTHROPIC_API_KEY` | from [console.anthropic.com](https://console.anthropic.com) → API keys (phase 2) |
   | `INBOUND_EMAIL_SECRET` | any long random string; portal emails only (phase 3, step 10) |
   | `INBOUND_EMAIL_ADDRESS` | your Postmark inbound address; portal emails only (step 10) |

   Optional: `DEFAULT_MODEL` (default `claude-haiku-5-5`) and `AGENT_EFFORT` (`low`, `medium`
   (default) or `high`). Without `ANTHROPIC_API_KEY` the bot still stores messages but doesn't
   reply, and logs a warning at startup.

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

To use a different model for one broker (e.g. `claude-sonnet-5-5` if Hinglish replies need it),
set `brokers.model` for that row in Supabase.

### 6. Connect the webhook

In the Meta app: WhatsApp → **Configuration** → Webhook:

- Callback URL: `https://<your-domain>/webhooks/whatsapp`
- Verify token: the `META_VERIFY_TOKEN` value
- Click **Verify and save**, then under webhook fields **subscribe to `messages`**.

### 7. Load the broker's listings

The agent only quotes what is in `properties` with `status = 'available'`. Each listing has an
`id` from its source that never changes; a sync adds or updates listings by that id and marks
any listing that is no longer in the source `removed`. Nothing is deleted, and the source is
always the full list: edit the source, not Supabase, or the next sync will undo the edit.

**From a Google Sheet (recommended for brokers):**

1. In Google Sheets, **File → Import → Upload** `scripts/listings_template.csv` to start from the
   template, then replace the sample rows with the broker's listings. Columns (any order, extra
   columns ignored):

   | Column | Required | Example |
   |---|---|---|
   | `id` | yes, unique, never reused | `P01` |
   | `title` | yes | `Skyline Residency` |
   | `area` | yes | `Wakad` |
   | `bhk` | | `2 BHK` |
   | `type` | | `sale` or `rent` |
   | `price` (or `price_min` + `price_max`) | | `85-95 L`, `1.2 Cr`, `8500000`, `28k` (rent per month) |
   | `status` | | `available` (default), `sold` or `on hold` |
   | `notes` | | size, possession, amenities: anything the agent may tell leads |

2. **Share → General access → Anyone with the link → Viewer.** The bot reads it through its
   export link, so don't put anything private in it (owner numbers, internal notes).
3. Save the sheet for the broker and sync it once:

   ```sh
   uv run python -m app.sync_listings --phone-number-id <Phone number ID> --sheet "<sheet link>"
   ```

   It prints what changed, and any rows it skipped with the reason (e.g. a price typed as `85`
   instead of `85 L`). A skipped row keeps its previous values.

4. Keep it in sync automatically with a second Railway service that runs on a schedule. In the
   project: **+ Create → GitHub Repo** → `tttlai/realestai`, then in its **Settings**:
   - **Source → Branch**: `main`; **Root Directory**: `/projects/whatsapp-leads-bot`; **Watch
     Paths**: `/projects/whatsapp-leads-bot/**`
   - **Deploy → Custom Start Command**: `python -m app.sync_listings`
   - **Deploy → Cron Schedule**: `*/30 * * * *` (every 30 minutes, in UTC)
   - **Deploy → Restart Policy**: Never
   - No healthcheck and no public domain: it isn't a web server.
   - **Variables**: the same six as the bot. To avoid copying secrets, reference them, e.g.
     `SUPABASE_URL` = `${{<bot service name>.SUPABASE_URL}}`.

   Each run syncs every broker that has a sheet, logs what changed, then exits. Its logs are
   under the service's **Deployments** (look for `listings synced` or `listings sync failed`).

If a sheet can't be read (unshared, deleted, or suddenly empty), the sync changes nothing and
reports the problem. To really empty a broker's listings, run once with `--allow-empty`.

**From a JSON file** (one-off loads, or listings from a CRM export):

```sh
uv run python -m scripts.seed_properties --phone-number-id <Phone number ID>    # 10 Pune samples
uv run python -m scripts.seed_properties --phone-number-id <Phone number ID> --file my_listings.json
```

The file uses the same fields as the sheet (see `scripts/sample_properties.json`), with prices
as whole rupees. Use one source per broker: syncing a sheet after a file marks the file's
listings removed, and the other way round.

### 8. Try the agent before going live (optional)

`scripts/eval_agent.py` plays the conversations in `tests/fixtures/conversations.json`
(Hinglish, Hindi, English, typos, off-topic, a complaint, opt-outs, a property that isn't
listed, a discount request, an attempt to change the bot's rules) against the real Claude API
with an in-memory database and the sample listings. Nothing goes to Supabase or WhatsApp. It
prints each chat and flags any rupee amount that isn't a listed price, plus any missed
expectation. Each run costs a little.

```sh
uv run python -m scripts.eval_agent                        # needs ANTHROPIC_API_KEY
uv run python -m scripts.eval_agent --only hinglish_2bhk_wakad --model claude-sonnet-5-5
```

### 9. Acceptance check

1. From your phone, send `2bhk wakad mein kitna hai?` to the broker's number and keep chatting:
   the bot should reply in Hinglish, quote only listed prices, and ask one thing at a time.
2. In Supabase, `leads` fills in (`intent`, `budget`, `area`, `bhk`, `timeline`, `needs_loan`,
   `score`), and `agent_logs` has a row per reply with its tool calls.
3. Ask for a visit: the lead's `status` becomes `handed_off`. Say "stop": `opted_out` becomes
   true and the bot stops replying.
4. Duplicate deliveries are still dropped. This should return no rows:
   `select wa_message_id, count(*) from messages group by 1 having count(*) > 1;`

To read a conversation with the agent's decisions:

```sql
select m.created_at, m.direction, m.body
from messages m join leads l on l.id = m.lead_id
where l.phone = '<lead number>' order by m.created_at;

select created_at, model, tool_calls, reply from agent_logs
where lead_id = '<lead id>' order by created_at;
```

If no reply arrives, check the Railway logs: each line is JSON with `broker_id`, `lead_id` and
`wa_message_id`. A `no active broker for phone_number_id` warning means step 5's phone number ID
doesn't match the number Meta is sending from. An `outbound message failed` warning means Meta
accepted a reply but couldn't deliver it, and `error_code` and `error_title` say why. The reply
still has an outbound row in `messages`. An `agent not configured` warning means
`ANTHROPIC_API_KEY` isn't set. `reply mentions a price that is not listed` means the agent quoted
an amount that matches no listing and wasn't said by the lead: read that conversation.

### 10. Lead intake: lead forms and portal emails (phase 3)

When a lead arrives from a Facebook/Instagram lead form or a portal email, the bot saves the
lead, stores what they asked as the lead's first message, and sends the `lead_opener` template
(the lead hasn't messaged yet, so free text isn't allowed). When they reply, the agent sees the
form answers or the email and carries on. No opener is sent if the lead opted out, is already
chatting with the bot, or got an opener in the last 24 hours. Every submission is recorded in
`intake_events` with what happened:

```sql
select created_at, source, status, detail from intake_events order by created_at desc limit 20;
```

**a. Apply the migration** `supabase/migrations/20261118000000_lead_intake.sql` (SQL Editor,
just that file).

**b. Get the template approved** (start now: approval can take up to a day). In WhatsApp
Manager → **Message templates** → **Create template**, for each broker's WhatsApp account:

- Category **Utility**, name **`lead_opener`**, language **English** (`en`)
- Body, exactly:
  `Hi {{1}}, thanks for your enquiry about {{2}} with {{3}}. Are you looking to buy or rent?`
- Sample values: `Asha`, `2 BHK in Skyline Residency`, `Ravi Realty`

Meta may move it to the Marketing category, which is fine (it changes the per-message price).
Until it's approved, openers fail with a template error and the event shows `failed`.

**c. Facebook / Instagram lead forms**

1. In Meta Business Settings, make sure the broker's **Facebook Page** is in the business
   portfolio, and assign it to your **System User** with access to leads (full control is
   simplest).
2. Generate a System User token that, besides the WhatsApp permissions, has
   `leads_retrieval`, `pages_show_list`, `pages_read_engagement` and `pages_manage_metadata`. If
   the app doesn't offer these, add the lead-ads / Pages use case to the app in the App
   Dashboard first.
3. In the App Dashboard → **Webhooks**, choose the **Page** object, set the callback URL to
   `https://<your-domain>/webhooks/meta-leads` with your `META_VERIFY_TOKEN`, click **Verify and
   save**, and subscribe to **`leadgen`**.
4. Connect the Page to the broker (it asks for the token from step 2):

   ```sh
   uv run python -m scripts.connect_facebook_page --phone-number-id <Phone number ID> --page-id <Page ID>
   ```

5. Name each lead form after the property (e.g. "Skyline Residency 2 BHK"): the form name is
   what the opener says the lead enquired about. A custom question named `property` overrides
   it.

**d. Portal emails** (via [Postmark](https://postmarkapp.com) inbound)

1. In Postmark, open your server → **Default Inbound Stream** → **Settings**. Note the inbound
   address (like `abc123@inbound.postmarkapp.com`) and set the webhook URL to
   `https://postmark:<INBOUND_EMAIL_SECRET>@<your-domain>/webhooks/email-leads`.
2. In Railway, set `INBOUND_EMAIL_SECRET` (the same random string) and `INBOUND_EMAIL_ADDRESS`
   (the inbound address). Put `INBOUND_EMAIL_ADDRESS` in your local `.env` too.
3. Give the broker a key and get their forwarding address:

   ```sh
   uv run python -m scripts.set_inbound_email --phone-number-id <Phone number ID> --key ravi
   ```

4. In the broker's Gmail: **Settings → Forwarding → Add a forwarding address** with that
   address. Gmail emails a confirmation code to it, which shows in the Railway logs as
   `gmail forwarding confirmation received` with `confirmation_code`. Enter it in Gmail, then
   add a filter such as `from:(99acres.com OR magicbricks.com OR housing.com)` → **Forward to**
   that address.

Each email is read by Claude (the same API key as the agent), which pulls out the enquirer's
name, phone, the property and the portal. Emails that aren't enquiries (reports, receipts,
newsletters) are recorded as `skipped_not_a_lead`.

**e. Acceptance check** (use your own phone number in test leads, never a real lead's)

1. [Lead Ads Testing Tool](https://developers.facebook.com/tools/lead-ads-testing): pick the
   Page and form, create a test lead with your number. The opener arrives on WhatsApp within
   seconds and `intake_events` shows `opener_sent` for `meta_ads`.
2. Email yourself a sample enquiry in the style of a 99acres email with your own number in it
   and let the filter forward it (or forward it by hand). Same result, with `portal_email`.
3. Reply to an opener: the agent answers knowing what you enquired about.

## How the agent works

- Each reply: the last 20 messages, the broker's available properties and the lead's saved details
  go to Claude (`app/agent/prompt.py`), with three tools (`app/agent/tools.py`): `update_lead`,
  `handoff_to_broker` and `mark_opted_out`. Up to five rounds of tool calls, then a reply.
- If Claude fails, refuses, or doesn't finish, the lead gets "Thanks for your message! <broker>
  will get back to you shortly." and is handed to the broker. The lead is never left without an
  answer, and never sent a half-written one.
- A plain `STOP` (or `unsubscribe`, `opt out`) opts the lead out without asking the model. Opt-outs
  in other words or languages are left to the model.
- One lead's messages are answered one at a time; a second quick message waits for the first
  reply.
- The 24-hour window is checked before calling Claude, so a stale message costs nothing.

## Known limitations

- **The broker is not alerted yet.** Hand-offs set the lead's `status` to `handed_off` (the reason
  and summary are in `agent_logs`), but the WhatsApp alert to `alert_number` comes in phase 5,
  with calendar booking. Until then, check for handed-off leads:
  `select name, phone, budget, area, timeline from leads where status = 'handed_off';`
- Site visits are not booked yet: the agent asks for a preferred time and hands over (phase 5).
- Leads who never reply to the opener get no follow-ups yet (phase 4).
- If a lead's number isn't on WhatsApp, Meta accepts the opener and then reports it failed: it
  shows as an `outbound message failed` warning (error 131026).

- Messages are handled in-process after Meta gets its 200. If the service restarts mid-way, that
  message may go unanswered (Meta won't resend it, since it already got a 200). It is still in
  `messages` if storing finished.
- If sending a reply fails (after one retry on a Meta server error), the error is logged and the
  message is not retried, so a lead is never sent the same reply twice.
- Only text is answered. Other message types (images, voice notes) are stored but not answered
  until Phase 6.
