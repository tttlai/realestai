-- WhatsApp messages between the bot and a broker's alert number: alerts about leads, and anything
-- the broker sends back. Kept apart from `messages`, which is each lead's own conversation and is
-- what the agent reads.

create table broker_messages (
  id uuid primary key default gen_random_uuid(),
  broker_id uuid not null references brokers(id) on delete cascade,
  lead_id uuid references leads(id) on delete set null,  -- the lead an alert is about
  direction text not null,                -- inbound / outbound
  kind text not null default 'text',      -- template for alerts, else as WhatsApp sent it
  reason text,                            -- hot_lead / question / complaint / other / assistant_failed
  body text,
  wa_message_id text unique,
  status text not null,                   -- sent / failed / skipped (alerts); received (inbound)
  detail text,                            -- why an alert failed or was skipped
  created_at timestamptz default now()
);

create index on broker_messages (lead_id, created_at);

alter table broker_messages enable row level security;
