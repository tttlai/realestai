# CLAUDE.md — Realest AI WhatsApp Lead Bot

## What we're building

A multi-tenant WhatsApp lead-qualification service for Indian real estate brokers and small builders.

When a lead comes in (Meta Lead Ads, portal email from 99acres / MagicBricks / Housing.com, website form, or a direct WhatsApp message), the service:

1. Replies on WhatsApp within seconds (approved template if the lead hasn't messaged first).
2. Qualifies the lead in conversation: buy/rent, budget, area, BHK, timeline, home loan.
3. Saves structured lead data to Supabase.
4. Alerts the broker on WhatsApp when a lead is hot.
5. Books a site visit into the broker's calendar.
6. Sends template follow-ups if the lead goes quiet (day 1, day 3, then stop).

One codebase serves every broker. Each broker is a row in `brokers`.

## Current status

| Phase | State |
|---|---|
| 1. Echo bot | ✅ Passed 2026-11-16 on a registered business number (Meta business verified, app Live) |
| 2. Agent | ✅ Built and tested 2026-11-17. Listings sync from Google Sheets added on top |
| 3. Lead intake | Built 2026-11-18 (Meta Lead Ads + portal emails via Postmark, English `lead_opener`). Awaiting setup and acceptance: template approval, Page connection, Postmark |
| 4. Templates and follow-ups | Next |
| 5-7 | Not started |

What phase 2 left for later: hand-offs set `leads.status = 'handed_off'` but the broker isn't
alerted yet, and the calendar tools (`get_visit_slots`, `book_visit`) aren't exposed: both come in
phase 5. Non-text messages are stored but not answered until phase 6.

**Setup and operating steps live in [README.md](README.md)** (Supabase, Meta, Railway, adding a
broker, loading listings, the eval script, acceptance checks). Keep them there, not here; this
file is the spec and the rules.

## Stack

| Layer | Choice |
|---|---|
| Language / framework | Python 3.12, FastAPI, Uvicorn |
| Hosting | Railway: the web service, plus cron services (listings sync now, follow-ups in phase 4). Configured in the Railway dashboard, not config files (see Deployment) |
| Database | Supabase Postgres (`supabase-py` or `asyncpg`) |
| LLM | Claude API via the `anthropic` Python SDK, tool use |
| Messaging | WhatsApp Cloud API (Graph API), official only |
| Voice notes | Whisper API or Sarvam AI speech-to-text |
| Calendar | Google Calendar API (cal.com API as an alternative) |
| Portal email intake | Postmark or Mailgun inbound parse → webhook |

Models: default `claude-haiku-5-5` for conversation turns; make the model configurable per broker so `claude-sonnet-5-5` can be tried where Hinglish quality needs it.

## Hard rules

- **Official WhatsApp Cloud API only.** No WhatsApp Web automation, no unofficial libraries.
- **Keep the bot narrowly scoped** to property enquiries, qualification and site visits. Meta's January 2026 terms block general-purpose AI assistants on the Business API. The system prompt must refuse off-topic requests politely and steer back.
- **Never invent prices, availability or property details.** The agent may only state facts present in the broker's `properties` rows. If unsure, hand off to the broker.
- **24-hour window:** free-form messages only within 24 hours of the lead's last inbound message. Outside it, send approved templates only. Enforce this in code, not just in the prompt.
- **Opt-outs are final.** "STOP", "not interested" or equivalent (any language) → `mark_opted_out`, cancel pending follow-ups, never message again.
- **Respond to Meta webhooks with 200 immediately**, process in the background, and de-duplicate on WhatsApp message ID (Meta retries).
- **Verify `X-Hub-Signature-256`** on every WhatsApp webhook using the app secret. Reject on mismatch.
- **Encrypt broker access tokens at rest** (Fernet with a key from env). Never log tokens.
- **Secrets only in environment variables.** Nothing secret in the repo.
- **Log every inbound message, outbound message, Claude call and tool call** to Supabase so any bot decision can be explained to a broker.
- Phone numbers are always stored as E.164 without `+`, e.g. `919876543210`. Numbers from WhatsApp (`wa_id`) already include the country code and are stored unchanged; only numbers typed by people (forms, emails) are normalised.
- **Listings come from the broker's source** (Google Sheet or JSON file), matched on `properties.external_id`. A sync never deletes: listings missing from the source get `status = 'removed'`, so rows (and visits pointing at them) survive. Edits belong in the source, not in Supabase.

## Project structure

```
app/
  main.py              # FastAPI app, route registration
  config.py            # env var loading (pydantic-settings)
  db.py                # Supabase client / queries
  crypto.py            # token encrypt/decrypt
  webhooks/
    whatsapp.py        # GET verify, POST inbound
    meta_leads.py      # Facebook Lead Ads
    email_leads.py     # inbound-parse portal emails
  whatsapp/
    client.py          # send text, send template, download media
    templates.py       # template names + parameter builders
    window.py          # 24h window check
  agent/
    prompt.py          # system prompt builder (broker + inventory + lead)
    tools.py           # tool schemas
    handlers.py        # tool execution
    run.py             # agent loop
    prices.py          # ₹ formatting (L / Cr) and the unlisted-price check
  listings/
    model.py           # one listing from a source, validated
    sheet.py           # read a Google Sheet (CSV export) into listings
    sync.py            # upsert by external_id, mark missing 'removed'
  sync_listings.py     # cron entrypoint: sync every broker with a sheet
  intake/
    normalise.py       # phone normalisation (wa_id kept as is; typed numbers get +91)
    leads.py           # shared intake: intake_events dedupe, lead upsert, lead_opener
    email_parser.py    # Claude-based extraction from portal emails (structured output)
  calendar/
    google.py
  transcription.py
  followups.py         # cron entrypoint (phase 4)
scripts/               # run locally, not deployed (the Docker image holds app/ only)
  seed_broker.py       # add or update a broker (encrypts the token)
  seed_properties.py   # load listings from a JSON file
  connect_facebook_page.py  # subscribe the app to a broker's Page, save its Page token
  set_inbound_email.py # give a broker an inbound email key, print their forwarding address
  eval_agent.py        # play tests/fixtures/conversations.json against the real API
  sample_properties.json
  listings_template.csv  # Google Sheet template
tests/
  fixtures/conversations.json
supabase/migrations/   # applied by hand in the Supabase SQL editor, new files only
```

## Environment variables

```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
DEFAULT_MODEL=claude-haiku-5-5
AGENT_EFFORT=medium           # low / medium / high
LOG_LEVEL=INFO
META_APP_SECRET=
META_VERIFY_TOKEN=
META_GRAPH_VERSION=           # pin a current Graph API version
TOKEN_ENCRYPTION_KEY=         # Fernet key
TRANSCRIPTION_PROVIDER=whisper   # or sarvam
OPENAI_API_KEY=               # if whisper
SARVAM_API_KEY=               # if sarvam
GOOGLE_SERVICE_ACCOUNT_JSON=
INBOUND_EMAIL_SECRET=         # basic-auth password the email provider sends; unset = endpoint off
INBOUND_EMAIL_ADDRESS=        # provider's inbound address, to print forwarding addresses
```

## Database schema (Supabase migration)

The migrations in `supabase/migrations/` are the source of truth; this is the original design.
Added since: `properties.external_id` (unique per broker), `properties.status` may be
`removed`, and `brokers.listings_sheet_url` (`20261117000000_listing_sync.sql`);
`brokers.fb_page_id`, `brokers.leads_access_token_enc`, `brokers.inbound_email_key` and the
`intake_events` table: one row per form submission or email, unique on source + external ID,
with the outcome (`20261118000000_lead_intake.sql`).

```sql
create table brokers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  agency_name text,
  phone_number_id text unique not null,   -- WhatsApp Cloud API
  waba_id text,
  access_token_enc text not null,         -- encrypted
  alert_number text not null,             -- hot-lead alerts go here
  calendar_id text,
  timezone text default 'Asia/Kolkata',
  business_hours jsonb,                   -- {"mon":["10:00","19:00"], ...}
  model text,                             -- null = DEFAULT_MODEL
  active boolean default true,
  created_at timestamptz default now()
);

create table properties (
  id uuid primary key default gen_random_uuid(),
  broker_id uuid references brokers(id) on delete cascade,
  title text not null,
  area text not null,
  bhk text,
  price_min bigint,                       -- rupees
  price_max bigint,
  type text,                              -- sale / rent
  status text default 'available',        -- available / sold / on_hold
  notes text,
  updated_at timestamptz default now()
);

create table leads (
  id uuid primary key default gen_random_uuid(),
  broker_id uuid references brokers(id) on delete cascade,
  phone text not null,
  name text,
  source text,                            -- meta_ads / portal_email / website / whatsapp
  source_detail text,                     -- portal name, ad name, property enquired
  intent text,                            -- buy / rent
  budget text,
  area text,
  bhk text,
  timeline text,
  needs_loan boolean,
  score text,                             -- hot / warm / cold
  status text default 'new',              -- new / qualifying / qualified / visit_booked / handed_off / closed
  opted_out boolean default false,
  last_inbound_at timestamptz,            -- drives the 24h window
  created_at timestamptz default now(),
  unique (broker_id, phone)
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  direction text not null,                -- inbound / outbound
  kind text default 'text',               -- text / template / audio / interactive
  body text,
  wa_message_id text unique,              -- dedupe Meta retries
  created_at timestamptz default now()
);

create table followups (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  due_at timestamptz not null,
  template text not null,
  sent boolean default false,
  cancelled boolean default false
);

create table visits (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  property_id uuid references properties(id),
  starts_at timestamptz not null,
  calendar_event_id text,
  status text default 'booked'            -- booked / cancelled / done
);

create table agent_logs (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  model text,
  input_tokens int,
  output_tokens int,
  tool_calls jsonb,
  reply text,
  created_at timestamptz default now()
);

create index on followups (due_at) where sent = false and cancelled = false;
create index on messages (lead_id, created_at);
```

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| GET | `/webhooks/whatsapp` | Meta verification: echo `hub.challenge` if `hub.verify_token` matches |
| POST | `/webhooks/whatsapp` | Verify signature → 200 → background: route by `phone_number_id` to broker, dedupe, store, transcribe audio, run agent, send reply |
| POST | `/webhooks/meta-leads` | Fetch lead details from Graph API, upsert lead, send opener template, schedule follow-ups |
| POST | `/webhooks/email-leads` | Postmark inbound JSON, basic auth with `INBOUND_EMAIL_SECRET`, broker from the `+key` in the address; Claude extracts `{name, phone, property, portal}`, upsert lead, send opener template |
| GET | `/health` | Liveness check for Railway |

Cron (Railway cron service, every 15 minutes): `python -m app.followups` sends due follow-ups that are not sent, not cancelled, and whose lead is not opted out and has not replied since scheduling.

## Agent

### Per-turn context
Build the system prompt from: broker name and agency, business hours, current date/time in the broker's timezone, the broker's available `properties` (compact table), the lead record, and the last ~20 messages.

### System prompt requirements
- You are the WhatsApp assistant for {agency}. You only help with property enquiries and site visits for this agency.
- Reply in the language the lead uses: English, Hindi or Hinglish. Short WhatsApp-style messages, one question at a time.
- Qualify: buy or rent, budget, preferred area, BHK, timeline, home loan.
- Only mention properties and prices from the inventory provided. Never guess.
- Call `update_lead` whenever you learn something new.
- Score: hot = budget + area + timeline within 3 months and wants a visit; warm = partially qualified; cold = browsing or no budget fit.
- When hot, offer a site visit (`get_visit_slots` → `book_visit`) and call `handoff_to_broker`.
- If the lead asks something you can't answer from the inventory, or is upset, call `handoff_to_broker`.
- Off-topic requests: politely decline and steer back to property.
- Opt-out phrases in any language → `mark_opted_out` and send one short confirmation.

### Tools

```python
TOOLS = [
  {
    "name": "update_lead",
    "description": "Save qualification details learned from the conversation.",
    "input_schema": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "intent": {"type": "string", "enum": ["buy", "rent"]},
        "budget": {"type": "string"},
        "area": {"type": "string"},
        "bhk": {"type": "string"},
        "timeline": {"type": "string"},
        "needs_loan": {"type": "boolean"},
        "score": {"type": "string", "enum": ["hot", "warm", "cold"]}
      }
    }
  },
  {
    "name": "get_visit_slots",
    "description": "Get free site-visit slots from the broker's calendar.",
    "input_schema": {
      "type": "object",
      "properties": {
        "from_date": {"type": "string", "description": "YYYY-MM-DD"},
        "to_date": {"type": "string", "description": "YYYY-MM-DD"}
      },
      "required": ["from_date", "to_date"]
    }
  },
  {
    "name": "book_visit",
    "description": "Book a site visit after the lead confirms a slot.",
    "input_schema": {
      "type": "object",
      "properties": {
        "slot_start": {"type": "string", "description": "ISO 8601"},
        "property_id": {"type": "string"}
      },
      "required": ["slot_start"]
    }
  },
  {
    "name": "handoff_to_broker",
    "description": "Alert the broker with a summary when the lead is hot or needs a human.",
    "input_schema": {
      "type": "object",
      "properties": {
        "summary": {"type": "string"},
        "reason": {"type": "string", "enum": ["hot_lead", "question", "complaint", "other"]}
      },
      "required": ["summary", "reason"]
    }
  },
  {
    "name": "mark_opted_out",
    "description": "The lead asked not to be contacted again.",
    "input_schema": {"type": "object", "properties": {}}
  }
]
```

### Loop
Call Claude with tools → execute any tool calls in `agent/handlers.py` → return tool results → repeat until a final text reply (max 5 iterations) → send reply via WhatsApp → log to `agent_logs` and `messages`.

## WhatsApp templates (submit for approval early)

| Name | Category | Use |
|---|---|---|
| `lead_opener` | Utility | First touch for portal / ad leads: thanks for enquiring about {{property}}, buy or rent? |
| `visit_confirmation` | Utility | Visit booked: {{date}} {{time}}, {{address}} |
| `visit_reminder` | Utility | Morning-of reminder |
| `followup_day1` | Marketing | Gentle nudge |
| `followup_day3` | Marketing | Final nudge, then stop |

Keep template names and parameter builders in `whatsapp/templates.py`.

## Build phases

Work through these in order. Each phase must pass its acceptance check before moving on.

1. **Echo bot.** Migration applied, FastAPI on Railway, webhook verified with Meta's test number, inbound messages stored and echoed back.
   ✅ Messaging the test number returns the same text; rows appear in `messages`; duplicate deliveries don't create duplicate rows.
2. **Agent.** One seeded broker and ~10 sample properties. Claude agent with tools replaces the echo.
   ✅ A Hinglish conversation ("2bhk wakad mein kitna hai?") gets qualified, `leads` fields fill in, no invented prices.
3. **Lead intake.** Meta Lead Ads webhook, then portal email webhook.
   ✅ A test lead form submission and a forwarded sample 99acres email each create a lead and trigger `lead_opener`.
4. **Templates and follow-ups.** 24h window enforcement, follow-up scheduling, cron job.
   ✅ A lead who never replies gets day 1 and day 3 follow-ups and nothing more; a lead who replies has follow-ups cancelled; an opted-out lead gets nothing.
5. **Calendar and alerts.** Google Calendar slots and booking, hot-lead alerts to `alert_number`, visit confirmation and reminder.
   ✅ A hot lead books a visit end to end; the event appears in the calendar; the broker receives the summary.
6. **Voice notes.** Download media, transcribe, feed to the agent.
   ✅ A Hindi voice note is answered correctly.
7. **Multi-tenancy hardening.** Broker onboarding script (insert broker, encrypt token), per-broker model setting, rate limiting per lead, error alerts.
   ✅ Two brokers on two numbers run side by side with no data crossover.

## Deployment

- **Railway**, deploying `main` of `tttlai/realestai` with root directory `/projects/whatsapp-leads-bot`. Service settings (healthcheck `/health`, restart policy, cron schedule, start command) are set in the dashboard: Railway deprecated config files (`railway.json` is read only until 2026-12-01, and new services can't use one). Railway's replacement is Infrastructure as Code (`.railway/railway.ts` via the Railway CLI), if the project outgrows the dashboard.
- **Migrations** are applied by hand: paste only the new file into the Supabase SQL editor. Re-running the init migration fails with `relation "brokers" already exists`.
- **Pull requests target `main`.** GitHub has defaulted new PRs to the stale `whatsapp-lead-bot` branch before; check the base.
- **The marketing site** is in `website/` at the repo root, published to realestai.in by `.github/workflows/deploy-website.yml`. Its `public/` holds the privacy and data-deletion pages Meta links to and a Meta domain-verification file that must stay.
- **Local runs on OneDrive** need `UV_LINK_MODE=copy` (uv's default hardlinks fail there).
- **Secrets** go only in `.env` (gitignored) and Railway variables, never in `.env.example`.

## Testing

- `pytest` for everything. Mock the WhatsApp Graph API, Claude API and Google Calendar (`tests/fakes.py` has an in-memory database and a scripted Claude client). `tests/test_db_integration.py` runs only against a throwaway database.
- Fixture conversations in `tests/fixtures/conversations.json`: English, Hindi, Hinglish, typos, off-topic, rude, opt-out, asks for a property not in inventory, discount pressure, prompt injection (voice note to add in phase 6). `python -m scripts.eval_agent` runs them against the real API with an in-memory database and flags unlisted prices.
- Unit-test the 24h window, phone normalisation, signature verification and dedupe directly.
- Before each pilot: run 20+ real conversations from the test number and review `agent_logs`.

## Conventions

- Type hints everywhere; `ruff` for lint and format.
- Async I/O (`httpx.AsyncClient`) for all outbound calls, with timeouts and one retry on 5xx.
- Structured JSON logging; include `broker_id` and `lead_id` in every log line; never log tokens or full message bodies at info level.
- Small, focused commits per phase.
