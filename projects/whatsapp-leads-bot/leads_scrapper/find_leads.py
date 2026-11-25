#!/usr/bin/env python3
"""
Realest AI lead finder
======================
Builds a list of real estate brokers and developers in one Indian city from:
  1. Meta Ad Library  - businesses running property ads right now (hottest leads)
  2. Google Maps      - real estate agents, consultants and developers in the city

Both are scraped through Apify (apify.com). Results are merged, de-duplicated
by phone number / website / name, scored, and saved as an Excel file you can
work through as an outreach tracker.

Usage
-----
    pip install requests openpyxl
    copy .env.example to .env and fill in APIFY_TOKEN, CITY etc.
    python find_leads.py                      # uses everything in .env
    python find_leads.py --city Mumbai        # any flag overrides .env for one run
    python find_leads.py --no-emails          # switch off a yes/no setting from .env

Re-build the spreadsheet from a previous run without spending Apify credit:
    python find_leads.py --city Pune --from-raw leads_pune_2026-11-23
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

APIFY = "https://api.apify.com/v2"
META_ACTOR = "apify~facebook-ads-scraper"
MAPS_ACTOR = "compass~crawler-google-places"

# Search phrases. {city} / {area} are filled in.
META_KEYWORDS = [
    "flats for sale {city}",
    "2 BHK {city}",
    "3 BHK {city}",
    "apartments {city}",
    "plots {city}",
    "new launch {city}",
    "villa {city}",
]
MAPS_QUERIES = [
    "real estate agent",
    "real estate consultant",
    "property dealer",
    "real estate developer",
]

# Portals and national brands: not your customers. Edit freely.
EXCLUDE = [
    "99acres", "magicbricks", "housing.com", "nobroker", "squareyards", "square yards",
    "makaan", "commonfloor", "proptiger", "olx", "quikr", "nestaway", "anarock",
    "godrej properties", "lodha", "dlf", "prestige group", "sobha", "tata housing",
    "brigade group", "mahindra lifespaces", "puravankara", "oberoi realty",
]
DEVELOPER_WORDS = re.compile(
    r"\b(builders?|developers?|constructions?|infra\w*|projects|promoters|estates? pvt|"
    r"homes pvt|realty pvt|ltd|limited)\b", re.I)

PHONE_RE = re.compile(r"(?:\+?91[\s-]?|0)?([6-9]\d{4}[\s-]?\d{5})\b")
WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)\+?(\d{10,13})", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


# --------------------------------------------------------------------------- Apify

MAX_COST_USD = None  # set from --max-cost


def run_actor(actor, run_input, token, label):
    """Start an Apify actor, wait for it, return its dataset items."""
    params = {"token": token}
    if MAX_COST_USD:
        params["maxTotalChargeUsd"] = MAX_COST_USD  # Apify stops charging at this amount
    print(f"-> {label}: starting {actor}"
          + (f" (cost cap {MAX_COST_USD:.2f} USD)" if MAX_COST_USD else ""))
    r = requests.post(f"{APIFY}/acts/{actor}/runs", params=params,
                      json=run_input, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"Apify refused the {label} run ({r.status_code}): {r.text[:500]}")
    run = r.json()["data"]
    run_id, dataset = run["id"], run["defaultDatasetId"]
    status = run["status"]
    while status in ("READY", "RUNNING"):
        time.sleep(15)
        run = requests.get(f"{APIFY}/actor-runs/{run_id}", params={"token": token},
                           timeout=60).json()["data"]
        status = run["status"]
        print(f"   {label}: {status} ... {run.get('usageTotalUsd', 0) or 0:.2f} USD so far")
    if status != "SUCCEEDED":
        print(f"   WARNING: {label} run ended as {status}; using whatever it collected.")
    print(f"   {label}: cost {run.get('usageTotalUsd', 0) or 0:.2f} USD (dataset {dataset})")
    return fetch_dataset(dataset, token, label)


def last_run_items(actor, token, label):
    """Reuse the results of your most recent successful run of an actor (no new cost)."""
    r = requests.get(f"{APIFY}/acts/{actor}/runs/last", params={"token": token,
                     "status": "SUCCEEDED"}, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"No earlier successful {label} run found ({r.status_code}): {r.text[:300]}")
    run = r.json()["data"]
    print(f"-> {label}: reusing run from {run.get('startedAt', '')[:16]} (no new cost)")
    return fetch_dataset(run["defaultDatasetId"], token, label)


def fetch_dataset(dataset, token, label):
    items, offset = [], 0
    while True:
        page = requests.get(f"{APIFY}/datasets/{dataset}/items",
                            params={"token": token, "offset": offset, "limit": 1000,
                                    "clean": "true"}, timeout=120).json()
        items += page
        if len(page) < 1000:
            break
        offset += 1000
    print(f"   {label}: {len(items)} records")
    return items


def ad_library_url(query):
    params = {
        "active_status": "active", "ad_type": "all", "country": "IN",
        "is_targeted_country": "false", "media_type": "all",
        "q": query, "search_type": "keyword_unordered",
    }
    return "https://www.facebook.com/ads/library/?" + urllib.parse.urlencode(params)


def scrape_meta(city, areas, limit, token):
    queries = [k.format(city=city) for k in META_KEYWORDS]
    queries += [f"flats {a}" for a in areas]
    return run_actor(META_ACTOR, {
        "startUrls": [{"url": ad_library_url(q)} for q in queries],
        "resultsLimit": limit,
        "activeStatus": "active",
        "includeAboutPage": True,
    }, token, "Meta Ad Library")


def scrape_maps(city, areas, limit, emails, token):
    searches = list(MAPS_QUERIES) + [f"real estate agent in {a}" for a in areas]
    run_input = {
        "searchStringsArray": searches,
        "locationQuery": f"{city}, India",
        "maxCrawledPlacesPerSearch": limit,
        "language": "en",
        "skipClosedPlaces": True,
    }
    if emails:
        run_input["scrapeContacts"] = True  # paid add-on: emails + socials from websites
    return run_actor(MAPS_ACTOR, run_input, token, "Google Maps")


# --------------------------------------------------------------------------- helpers

def norm_phone(p):
    digits = re.sub(r"\D", "", str(p or ""))
    if len(digits) >= 10 and digits[-10] in "6789":
        return digits[-10:]
    if len(digits) >= 10:  # landline: keep last 10-11 for matching
        return digits[-10:]
    return ""


def domain(url):
    if not url:
        return ""
    host = urllib.parse.urlparse(url if "://" in url else "http://" + url).netloc.lower()
    host = host.removeprefix("www.").removeprefix("m.")
    if any(s in host for s in ("facebook.com", "instagram.com", "fb.me", "wa.me",
                               "whatsapp.com", "google.", "goo.gl", "bit.ly", "linktr.ee")):
        return ""
    return host


def norm_name(n):
    n = re.sub(r"[^a-z0-9 ]", " ", (n or "").lower())
    n = re.sub(r"\b(pvt|private|ltd|limited|llp|the|and|co|india)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def walk_strings(obj, keys=None):
    """Yield (key, string) pairs from nested JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                yield k, v
            else:
                yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def first(*vals):
    for v in vals:
        if v:
            return v
    return ""


def excluded(name, site=""):
    text = f"{name} {site}".lower()
    return any(x in text for x in EXCLUDE)


# --------------------------------------------------------------------------- parsing

def parse_meta(items):
    """Group ads by advertiser page."""
    pages = {}
    for ad in items:
        snap = ad.get("snapshot") or {}
        page_id = str(first(ad.get("pageID"), ad.get("pageId"), snap.get("page_id")))
        name = first(ad.get("pageName"), snap.get("page_name"))
        if not (page_id or name):
            continue
        key = page_id or name
        p = pages.setdefault(key, {
            "name": name, "page_id": page_id, "ads": 0, "phones": set(), "wa": set(),
            "emails": set(), "sites": set(), "sample": "", "first_seen": "",
            "fb": first(snap.get("page_profile_uri"),
                        f"https://www.facebook.com/{page_id}" if page_id else ""),
            "likes": snap.get("page_like_count") or "",
        })
        p["ads"] += 1
        body = (snap.get("body") or {}).get("text", "") if isinstance(snap.get("body"), dict) \
            else str(snap.get("body") or "")
        if body and len(body) > len(p["sample"]):
            p["sample"] = body[:300]
        start = first(ad.get("startDateFormatted"), ad.get("startDate"))
        if start and (not p["first_seen"] or str(start) < p["first_seen"]):
            p["first_seen"] = str(start)[:10]
        for k, s in walk_strings(ad):
            kl = k.lower()
            for m in WA_RE.findall(s):
                p["wa"].add(m[-10:])
            if "phone" in kl or kl in ("text", "caption", "title", "link_description"):
                for m in PHONE_RE.findall(s):
                    p["phones"].add(re.sub(r"\D", "", m))
            if "email" in kl or kl == "text":
                p["emails"].update(e.lower() for e in EMAIL_RE.findall(s)
                                   if not e.lower().endswith((".png", ".jpg")))
            if kl in ("link_url", "website", "websites") or kl.endswith("_url"):
                d = domain(s)
                if d:
                    p["sites"].add(d)
    return list(pages.values())


def parse_maps(items):
    out = []
    for pl in items:
        if pl.get("permanentlyClosed"):
            continue
        out.append({
            "name": pl.get("title", ""),
            "category": pl.get("categoryName", ""),
            "phone": norm_phone(first(pl.get("phoneUnformatted"), pl.get("phone"))),
            "site": domain(pl.get("website")),
            "website": pl.get("website") or "",
            "address": pl.get("address", ""),
            "area": first(pl.get("neighborhood"), pl.get("city")),
            "rating": pl.get("totalScore") or "",
            "reviews": pl.get("reviewsCount") or 0,
            "maps_url": pl.get("url", ""),
            "emails": set(e.lower() for e in (pl.get("emails") or [])),
            "instagram": ", ".join(pl.get("instagrams") or []),
            "facebook": ", ".join(pl.get("facebooks") or []),
        })
    return out


# --------------------------------------------------------------------------- merge

def merge(meta, maps):
    leads = []
    by_phone, by_site, by_name = {}, {}, {}

    def index(lead):
        for ph in lead["_phones"]:
            by_phone.setdefault(ph, lead)
        if lead["_site"]:
            by_site.setdefault(lead["_site"], lead)
        if lead["_name"]:
            by_name.setdefault(lead["_name"], lead)

    for m in meta:
        site = sorted(m["sites"])[0] if m["sites"] else ""
        if excluded(m["name"], site):
            continue
        phones = {norm_phone(p) for p in m["phones"] | m["wa"]} - {""}
        lead = {
            "Business": m["name"], "Sources": {"Meta ads"},
            "Phone": ", ".join(sorted(phones)),
            "WhatsApp": ", ".join(f"https://wa.me/91{w}" for w in sorted(m["wa"])),
            "Email": ", ".join(sorted(m["emails"])),
            "Website": site, "Instagram": "", "Facebook": m["fb"],
            "Area": "", "Category": "", "Google rating": "", "Google reviews": "",
            "Active Meta ads": m["ads"], "Advertising since": m["first_seen"],
            "Sample ad text": m["sample"].replace("\n", " "),
            "Ad Library": (f"https://www.facebook.com/ads/library/?active_status=active"
                           f"&ad_type=all&country=IN&view_all_page_id={m['page_id']}"
                           if m["page_id"] else ""),
            "Maps link": "",
            "_phones": phones, "_site": site, "_name": norm_name(m["name"]),
        }
        leads.append(lead)
        index(lead)

    for g in maps:
        if excluded(g["name"], g["site"]):
            continue
        match = (by_phone.get(g["phone"]) if g["phone"] else None) \
            or (by_site.get(g["site"]) if g["site"] else None) \
            or by_name.get(norm_name(g["name"]))
        if match:
            match["Sources"].add("Google Maps")
            for col, val in (("Website", g["site"]), ("Area", g["area"]),
                             ("Category", g["category"]), ("Google rating", g["rating"]),
                             ("Google reviews", g["reviews"]), ("Maps link", g["maps_url"]),
                             ("Instagram", g["instagram"])):
                if val and not match[col]:
                    match[col] = val
            if g["phone"] and g["phone"] not in match["_phones"]:
                match["_phones"].add(g["phone"])
                match["Phone"] = ", ".join(sorted(match["_phones"]))
            if g["emails"]:
                match["Email"] = ", ".join(sorted(set(filter(None, match["Email"].split(", ")))
                                                  | g["emails"]))
            continue
        lead = {
            "Business": g["name"], "Sources": {"Google Maps"},
            "Phone": g["phone"], "WhatsApp": "", "Email": ", ".join(sorted(g["emails"])),
            "Website": g["site"], "Instagram": g["instagram"], "Facebook": g["facebook"],
            "Area": g["area"], "Category": g["category"], "Google rating": g["rating"],
            "Google reviews": g["reviews"], "Active Meta ads": 0, "Advertising since": "",
            "Sample ad text": "", "Ad Library": "", "Maps link": g["maps_url"],
            "_phones": {g["phone"]} - {""}, "_site": g["site"], "_name": norm_name(g["name"]),
        }
        leads.append(lead)
        index(lead)

    for l in leads:
        dev = "developer" in str(l["Category"]).lower() or DEVELOPER_WORDS.search(l["Business"] or "")
        l["Type"] = "Developer" if dev else "Broker"
        l["Best channel"] = ("Email + LinkedIn" if dev and l["Email"] else
                             "WhatsApp" if l["Phone"] else
                             "Instagram / Facebook DM")
        score = 0
        if l["Active Meta ads"]:
            score += 50 + min(l["Active Meta ads"], 10) * 3   # paying for leads now
        score += min(int(l["Google reviews"] or 0), 100) // 5  # established business
        score += 10 if l["Phone"] else 0
        score += 5 if l["Email"] else 0
        score += 5 if l["Website"] else 0
        l["Score"] = score
        l["Priority"] = "Hot" if score >= 60 else "Warm" if score >= 15 else "Cold"
        l["Sources"] = " + ".join(sorted(l["Sources"], reverse=True))
    leads.sort(key=lambda l: -l["Score"])
    return leads


# --------------------------------------------------------------------------- Excel

COLUMNS = [
    ("Priority", 9), ("Score", 7), ("Business", 32), ("Type", 10), ("Best channel", 18),
    ("Phone", 14), ("WhatsApp", 26), ("Email", 28), ("Website", 24), ("Instagram", 24),
    ("Facebook", 26), ("Area", 16), ("Category", 20), ("Google rating", 8),
    ("Google reviews", 9), ("Active Meta ads", 9), ("Advertising since", 12),
    ("Sample ad text", 50), ("Ad Library", 26), ("Maps link", 26), ("Sources", 22),
    ("Status", 16), ("Last contact", 12), ("Notes", 40),
]
STATUSES = ["Not contacted", "DM sent", "WhatsApp sent", "Email sent", "Replied",
            "Call booked", "Pilot started", "Not interested"]
FILLS = {"Hot": "F8D7D3", "Warm": "FBEBCB", "Cold": "E8EDF2"}


def write_excel(leads, meta_raw, maps_raw, path, city):
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    head_fill = PatternFill("solid", fgColor="1F2A37")
    for c, (name, width) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[1].height = 30
    for r, lead in enumerate(leads, 2):
        for c, (name, _) in enumerate(COLUMNS, 1):
            val = lead.get(name, "")
            if name == "Status":
                val = "Not contacted"
            cell = ws.cell(row=r, column=c, value=val)
            if isinstance(val, str) and val.startswith("http"):
                cell.hyperlink = val.split(", ")[0]
                cell.font = Font(color="1D4ED8", underline="single")
        ws.cell(row=r, column=1).fill = PatternFill("solid", fgColor=FILLS[lead["Priority"]])
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(leads) + 1, 2)}"
    status_col = get_column_letter([n for n, _ in COLUMNS].index("Status") + 1)
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{status_col}2:{status_col}{len(leads) + 500}")

    s = wb.create_sheet("Summary")
    hot = sum(l["Priority"] == "Hot" for l in leads)
    rows = [
        ("City", city), ("Built on", date.today().isoformat()),
        ("Total leads", len(leads)), ("Hot (running Meta ads)", hot),
        ("Warm", sum(l["Priority"] == "Warm" for l in leads)),
        ("Cold", sum(l["Priority"] == "Cold" for l in leads)),
        ("Brokers", sum(l["Type"] == "Broker" for l in leads)),
        ("Developers", sum(l["Type"] == "Developer" for l in leads)),
        ("With phone", sum(bool(l["Phone"]) for l in leads)),
        ("With email", sum(bool(l["Email"]) for l in leads)),
        ("Raw Meta ads scraped", len(meta_raw)), ("Raw Google Maps places", len(maps_raw)),
        ("", ""),
        ("How to use", "Work top-down. Hot = paying for Meta leads right now: open their "
                       "Ad Library link, mention a specific ad in your first message."),
        ("", "Brokers -> Instagram DM first, then WhatsApp. Developers with email -> Instantly."),
        ("", "Update Status and Last contact as you go; filter on Status to see follow-ups."),
    ]
    for r, (a, b) in enumerate(rows, 1):
        s.cell(row=r, column=1, value=a).font = Font(bold=True)
        s.cell(row=r, column=2, value=b)
    s.column_dimensions["A"].width = 26
    s.column_dimensions["B"].width = 90

    # Instantly-ready sheet: only leads with an email
    e = wb.create_sheet("Instantly import")
    cols = ["email", "company_name", "website", "phone", "city", "type", "active_meta_ads"]
    e.append(cols)
    for l in leads:
        for em in filter(None, l["Email"].split(", ")):
            e.append([em, l["Business"], l["Website"], l["Phone"], city, l["Type"],
                      l["Active Meta ads"]])
    wb.save(path)


GENERIC = ("info@", "contact@", "enquiry@", "enquiries@", "sales@", "admin@", "support@",
           "hello@", "office@", "mail@")


def write_instantly_csv(leads, path, city):
    """One row per company, best email first, headers Instantly maps automatically."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Email", "Company Name", "Website", "Phone", "City", "Type",
                    "Priority", "Opener"])
        n = 0
        for l in leads:
            emails = [e for e in l["Email"].split(", ") if e]
            if not emails:
                continue
            emails.sort(key=lambda e: e.startswith(GENERIC))  # personal-looking first
            if l["Active Meta ads"]:
                opener = f"Saw you're running Meta ads for property in {city}"
            elif l["Area"]:
                opener = f"Came across {l['Business']} while looking at brokers in {l['Area']}"
            else:
                opener = f"Came across {l['Business']} on Google Maps"
            w.writerow([emails[0], l["Business"], l["Website"], l["Phone"], city,
                        l["Type"], l["Priority"], opener])
            n += 1
    return n


# --------------------------------------------------------------------------- main

def load_env():
    """Read KEY=value lines from .env (next to this script, then the current folder).
    Real environment variables win over the file; command-line flags win over both."""
    for path in (Path(__file__).resolve().parent / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            val = val.split(" #")[0].strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


def env(key, default=""):
    return os.environ.get(key, "").strip() or default


def env_bool(key):
    return env(key).lower() in ("1", "true", "yes", "y", "on")


def main():
    load_env()
    flag = argparse.BooleanOptionalAction  # gives --emails / --no-emails etc.
    ap = argparse.ArgumentParser(
        description="Find real estate broker leads in an Indian city. "
                    "Every option can also be set in a .env file (see .env.example).")
    ap.add_argument("--city", default=env("CITY"), help="e.g. Pune, Bengaluru  [.env CITY]")
    ap.add_argument("--areas", default=env("AREAS"),
                    help='Comma-separated localities, e.g. "Baner,Wakad"  [.env AREAS]')
    ap.add_argument("--meta-limit", type=int, default=int(env("META_LIMIT", "100")),
                    help="Max ads per Meta search  [.env META_LIMIT, default 100]")
    ap.add_argument("--maps-limit", type=int, default=int(env("MAPS_LIMIT", "60")),
                    help="Max places per Maps search  [.env MAPS_LIMIT, default 60]")
    ap.add_argument("--emails", action=flag, default=env_bool("EMAILS"),
                    help="Pull emails/socials from websites, paid add-on  [.env EMAILS]")
    ap.add_argument("--skip-meta", action=flag, default=env_bool("SKIP_META"))
    ap.add_argument("--skip-maps", action=flag, default=env_bool("SKIP_MAPS"))
    ap.add_argument("--reuse-meta", action=flag, default=env_bool("REUSE_META"),
                    help="Reuse your last successful Meta run on Apify, no new cost  [.env REUSE_META]")
    ap.add_argument("--reuse-maps", action=flag, default=env_bool("REUSE_MAPS"),
                    help="Reuse your last successful Maps run on Apify, no new cost  [.env REUSE_MAPS]")
    ap.add_argument("--from-raw", help="Folder from an earlier run: rebuild the sheet, no scraping")
    ap.add_argument("--max-cost", type=float, default=float(env("MAX_COST_USD", "2.0")),
                    help="Max USD each Apify run may charge, 0 = no cap  [.env MAX_COST_USD, default 2]")
    ap.add_argument("--token", default=env("APIFY_TOKEN"), help="[.env APIFY_TOKEN]")
    a = ap.parse_args()
    if not a.city:
        ap.error("no city: add CITY=Pune to your .env file or pass --city Pune")
    global MAX_COST_USD
    MAX_COST_USD = a.max_cost or None

    areas = [x.strip() for x in a.areas.split(",") if x.strip()]
    slug = re.sub(r"\W+", "_", a.city.lower()).strip("_")
    folder = Path(a.from_raw or f"leads_{slug}_{date.today().isoformat()}")
    folder.mkdir(exist_ok=True)
    meta_file, maps_file = folder / "meta_ads_raw.json", folder / "google_maps_raw.json"

    if a.from_raw:
        meta_raw = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else []
        maps_raw = json.loads(maps_file.read_text(encoding="utf-8")) if maps_file.exists() else []
    else:
        if not a.token:
            sys.exit("No Apify token: add APIFY_TOKEN=apify_api_... to your .env file "
                     "(Apify Console > Settings > API & Integrations)")
        meta_raw = ([] if a.skip_meta else
                    last_run_items(META_ACTOR, a.token, "Meta Ad Library") if a.reuse_meta else
                    scrape_meta(a.city, areas, a.meta_limit, a.token))
        meta_file.write_text(json.dumps(meta_raw, ensure_ascii=False), encoding="utf-8")
        maps_raw = ([] if a.skip_maps else
                    last_run_items(MAPS_ACTOR, a.token, "Google Maps") if a.reuse_maps else
                    scrape_maps(a.city, areas, a.maps_limit, a.emails, a.token))
        maps_file.write_text(json.dumps(maps_raw, ensure_ascii=False), encoding="utf-8")

    leads = merge(parse_meta(meta_raw), parse_maps(maps_raw))
    out = folder / f"Leads_{a.city.title()}_{date.today().isoformat()}.xlsx"
    write_excel(leads, meta_raw, maps_raw, out, a.city.title())
    csv_out = folder / f"Instantly_{a.city.title()}_{date.today().isoformat()}.csv"
    n_email = write_instantly_csv(leads, csv_out, a.city.title())
    hot = sum(l["Priority"] == "Hot" for l in leads)
    print(f"\nDone: {len(leads)} leads ({hot} hot) -> {out.resolve()}")
    print(f"Instantly CSV: {n_email} companies with email -> {csv_out.resolve()}")
    if n_email < 20:
        print("Few emails found. Re-run with --emails to pull them from business websites.")


if __name__ == "__main__":
    main()
