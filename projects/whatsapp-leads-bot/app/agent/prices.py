"""Rupee amounts: writing them the Indian way, and spotting ones the agent should not have said.

The agent may only quote prices from the broker's listed properties. `unlisted_amounts` finds
rupee amounts in a reply that match no listed price and that the lead did not say first, so a
made-up price shows up in the logs and in the evaluation script.
"""

import re
from collections.abc import Iterable

from app.db import Property

LAKH = 100_000
CRORE = 10_000_000

_UNITS = {
    "crore": CRORE,
    "crores": CRORE,
    "cr": CRORE,
    "करोड़": CRORE,
    "करोड": CRORE,
    "lakh": LAKH,
    "lakhs": LAKH,
    "lac": LAKH,
    "lacs": LAKH,
    "l": LAKH,
    "लाख": LAKH,
    "k": 1_000,
    "thousand": 1_000,
    "hazar": 1_000,
    "hazaar": 1_000,
    "हज़ार": 1_000,
    "हजार": 1_000,
}

# An amount is a number after a currency marker (unit optional), or a number followed by a unit.
# Units are matched longest first so "lakhs" is not read as "l".
_UNIT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
_NUM = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT = re.compile(
    rf"(?:(?:₹|\b(?:rs\.?|inr))\s*(?P<num1>{_NUM})\s*(?P<unit1>{_UNIT})?"
    rf"|(?<![\w.,])(?P<num2>{_NUM})\s*(?P<unit2>{_UNIT}))(?!\w)",
    re.IGNORECASE,
)
# "80-90 lakh" / "85 to 95 L": the unit belongs to both numbers.
_RANGE = re.compile(
    rf"(?P<a>{_NUM})\s*(?P<sep>-|\u2013|to)\s*(?P<b>{_NUM})\s*(?P<unit>{_UNIT})(?!\w)",
    re.IGNORECASE,
)

# Listed prices are matched with a little slack for rounding ("~95 lakh" for 94.5 lakh).
_TOLERANCE = 0.02


def format_inr(amount: int) -> str:
    """Write rupees as people in India say them: ₹1.25 Cr, ₹85 L, ₹28,000."""
    if amount >= CRORE:
        return f"₹{_trim(amount / CRORE)} Cr"
    if amount >= LAKH:
        return f"₹{_trim(amount / LAKH)} L"
    return f"₹{_group_indian(amount)}"


def format_price_range(price_min: int | None, price_max: int | None) -> str:
    if price_min is None and price_max is None:
        return "price on request"
    if price_min is None or price_max is None or price_min == price_max:
        return format_inr(price_min if price_min is not None else price_max)  # type: ignore[arg-type]
    return f"{format_inr(price_min)} - {format_inr(price_max)}"


def rupee_amounts(text: str) -> list[int]:
    """Rupee amounts in the text. Bare numbers ("2 BHK", "3 months") are not amounts."""
    amounts = []
    text = _RANGE.sub(r"\g<a> \g<unit> \g<sep> \g<b> \g<unit>", text)
    for m in _AMOUNT.finditer(text):
        num = m.group("num1") or m.group("num2")
        unit = m.group("unit1") or m.group("unit2")
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        multiplier = _UNITS[unit.lower()] if unit else 1
        amounts.append(round(value * multiplier))
    return amounts


def unlisted_amounts(
    reply: str, properties: Iterable[Property], lead_texts: Iterable[str] = ()
) -> list[int]:
    """Amounts in the reply that are not a listed price and were not first said by the lead."""
    ranges = [
        (p.price_min if p.price_min is not None else p.price_max, p.price_max or p.price_min)
        for p in properties
        if p.price_min is not None or p.price_max is not None
    ]
    said_by_lead = {a for text in lead_texts for a in rupee_amounts(text)}

    def listed(amount: int) -> bool:
        return any(
            lo is not None
            and hi is not None
            and lo * (1 - _TOLERANCE) <= amount <= hi * (1 + _TOLERANCE)
            for lo, hi in ranges
        )

    def from_lead(amount: int) -> bool:
        return any(abs(amount - a) <= a * _TOLERANCE for a in said_by_lead)

    return [a for a in rupee_amounts(reply) if not listed(a) and not from_lead(a)]


def _trim(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _group_indian(amount: int) -> str:
    """12,34,567 style grouping."""
    digits = str(amount)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])
