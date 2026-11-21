-- Phase 3: leads from Facebook/Instagram lead forms and from property-portal emails.

-- Where each broker's leads arrive from.
alter table brokers add column fb_page_id text unique;            -- Facebook Page running Lead Ads
alter table brokers add column leads_access_token_enc text;       -- Page token for reading leads, encrypted
alter table brokers add column inbound_email_key text unique;     -- e.g. 'ravi' in <inbound>+ravi@...

-- One row per lead-form submission or portal email, so Meta's and the email provider's retries
-- are handled once, and so every intake can be traced (what came in, what was sent, why not).
create table intake_events (
  id uuid primary key default gen_random_uuid(),
  broker_id uuid references brokers(id) on delete cascade,
  source text not null,                   -- meta_ads / portal_email
  external_id text not null,              -- leadgen_id / email Message-ID
  lead_id uuid references leads(id) on delete set null,
  status text not null default 'received',  -- received / opener_sent / skipped_* / failed
  detail text,                            -- why it was skipped or failed
  created_at timestamptz default now(),
  unique (source, external_id)
);

create index on intake_events (lead_id, created_at);

alter table intake_events enable row level security;
