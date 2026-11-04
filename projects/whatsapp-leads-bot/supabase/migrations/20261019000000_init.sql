-- Initial schema for the WhatsApp leads bot (from CLAUDE.md).

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

-- Row-level security on, with no policies: the public anon key can read nothing.
-- The bot uses the service-role key, which bypasses RLS.
alter table brokers enable row level security;
alter table properties enable row level security;
alter table leads enable row level security;
alter table messages enable row level security;
alter table followups enable row level security;
alter table visits enable row level security;
alter table agent_logs enable row level security;
