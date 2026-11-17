-- Listings are synced from a broker's source (a Google Sheet, or a JSON file) and matched on the
-- source's own ID, so a property keeps its row (and anything linked to it, like visits) across
-- syncs. Listings that disappear from the source are marked 'removed', never deleted.

alter table properties add column external_id text;
alter table properties
  add constraint properties_broker_external_id_key unique (broker_id, external_id);
comment on column properties.external_id is 'ID of the listing in its source, e.g. the sheet''s id column';
comment on column properties.status is 'available / sold / on_hold / removed (no longer in the source)';

-- The Google Sheet a broker's listings are synced from. Null: not synced.
alter table brokers add column listings_sheet_url text;
