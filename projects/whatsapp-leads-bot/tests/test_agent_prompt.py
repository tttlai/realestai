from datetime import UTC, datetime

from app.agent.prompt import (
    build_system,
    format_business_hours,
    format_lead,
    format_now,
    format_properties,
)
from app.db import Broker, Lead, Property

BROKER = Broker(
    id="b",
    name="Ravi",
    agency_name="Ravi Realty",
    phone_number_id="1",
    access_token_enc="x",
    alert_number="919800000000",
    business_hours={"mon": ["10:00", "19:00"], "sat": ["10:00", "14:00"]},
)


def test_properties_are_listed_with_prices_and_notes() -> None:
    text = format_properties(
        [
            Property(
                id="1",
                broker_id="b",
                title="Green Arc",
                area="Wakad",
                bhk="2 BHK",
                type="rent",
                price_min=28_000,
                price_max=28_000,
                notes="Semi-furnished",
            ),
            Property(id="2", broker_id="b", title="Plots", area="Wagholi"),
        ]
    )
    assert text == (
        "- Green Arc | Wakad | 2 BHK | for rent | ₹28,000/month\n"
        "  Notes: Semi-furnished\n"
        "- Plots | Wagholi | price on request"
    )


def test_no_properties_says_so() -> None:
    assert "None listed" in format_properties([])


def test_lead_details_show_what_is_known() -> None:
    text = format_lead(
        Lead(id="l", broker_id="b", phone="91", name="Asha", intent="buy", needs_loan=False)
    )
    assert "- Name: Asha" in text
    assert "- Buy or rent: buy" in text
    assert "- Needs home loan: no" in text
    assert "- Budget: not known yet" in text


def test_business_hours_and_local_time() -> None:
    assert format_business_hours(BROKER.business_hours).startswith("Mon 10:00-19:00, Tue closed")
    assert format_business_hours(None) == "not set"
    now = datetime(2026, 11, 16, 18, 45, tzinfo=UTC)
    assert format_now(now, "Asia/Kolkata") == "Tuesday 17 November 2026, 00:15 (Asia/Kolkata)"


def test_cached_block_is_the_same_for_every_lead_of_a_broker() -> None:
    props = [Property(id="1", broker_id="b", title="A", area="Wakad")]
    now = datetime(2026, 11, 16, tzinfo=UTC)
    first = build_system(BROKER, props, Lead(id="1", broker_id="b", phone="1", name="Asha"), now)
    second = build_system(BROKER, props, Lead(id="2", broker_id="b", phone="2", name="Vikram"), now)
    assert first[0] == second[0]
    assert "Ravi Realty" in first[0]["text"]
    assert first[1] != second[1]
