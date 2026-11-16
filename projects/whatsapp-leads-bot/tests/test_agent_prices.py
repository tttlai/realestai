import pytest

from app.agent.prices import format_inr, format_price_range, rupee_amounts, unlisted_amounts
from app.db import Property


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (12_500_000, "₹1.25 Cr"),
        (10_000_000, "₹1 Cr"),
        (8_500_000, "₹85 L"),
        (1_234_567, "₹12.35 L"),
        (28_000, "₹28,000"),
        (950, "₹950"),
    ],
)
def test_format_inr(amount: int, expected: str) -> None:
    assert format_inr(amount) == expected


def test_format_price_range() -> None:
    assert format_price_range(8_500_000, 9_500_000) == "₹85 L - ₹95 L"
    assert format_price_range(28_000, 28_000) == "₹28,000"
    assert format_price_range(None, 28_000) == "₹28,000"
    assert format_price_range(None, None) == "price on request"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("₹85 L to ₹95 L", [8_500_000, 9_500_000]),
        ("budget 80-90 lakh", [8_000_000, 9_000_000]),
        ("1.2\u20131.5 cr", [12_000_000, 15_000_000]),  # en dash
        ("Rs.25,000/month", [25_000]),
        ("rent 25k", [25_000]),
        ("₹ 1,20,00,000", [12_000_000]),
        ("सिर्फ 80 लाख", [8_000_000]),
        ("1.5 करोड़", [15_000_000]),
        ("2 BHK, 3 months, 10 to 7 office hours, 850 sq ft", []),
    ],
)
def test_rupee_amounts(text: str, expected: list[int]) -> None:
    assert rupee_amounts(text) == expected


PROPERTIES = [
    Property(
        id="1", broker_id="b", title="A", area="Wakad", price_min=8_500_000, price_max=9_500_000
    ),
    Property(id="2", broker_id="b", title="B", area="Wakad", type="rent", price_max=28_000),
]


@pytest.mark.parametrize(
    ("reply", "lead_texts", "expected"),
    [
        ("2 BHK is ₹85 L - ₹95 L", [], []),
        ("around 90 lakh", [], []),  # inside a listed range
        ("rent is 28k a month", [], []),
        ("we can do 80 lakh for you", [], [8_000_000]),  # made up
        ("within your 80 lakh budget, nothing yet", ["budget 80 lakh"], []),  # the lead said it
        ("2 BHK in Wakad, ready to move", [], []),
    ],
)
def test_unlisted_amounts(reply: str, lead_texts: list[str], expected: list[int]) -> None:
    assert unlisted_amounts(reply, PROPERTIES, lead_texts) == expected
