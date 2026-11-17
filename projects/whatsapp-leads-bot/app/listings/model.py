"""One listing as it comes from a source (Google Sheet or JSON file), checked before saving."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.prices import LAKH

# Below these, a price was almost certainly typed without its unit ("85" meaning 85 lakh).
MIN_SALE_PRICE = LAKH
MIN_RENT = 1_000


class ListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    external_id: str = Field(alias="id", min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    area: str = Field(min_length=1, max_length=200)
    bhk: str | None = None
    type: Literal["sale", "rent"] | None = None
    price_min: int | None = Field(default=None, ge=0)  # rupees; monthly rent for rentals
    price_max: int | None = Field(default=None, ge=0)
    status: Literal["available", "sold", "on_hold"] = "available"
    notes: str | None = None

    @model_validator(mode="after")
    def _check_prices(self) -> "ListingIn":
        if self.price_min is not None and self.price_max is not None:
            if self.price_min > self.price_max:
                raise ValueError("price_min is above price_max")
        floor = MIN_SALE_PRICE if self.type == "sale" else MIN_RENT
        for price in (self.price_min, self.price_max):
            if price is not None and price < floor:
                raise ValueError(
                    f"price {price} looks too low: write it in full or with a unit, "
                    "e.g. 8500000, 85 L, 1.2 Cr or 28000"
                )
        return self

    def to_row(self) -> dict[str, Any]:
        """Every column, so a value cleared in the source is cleared in the database too."""
        return self.model_dump(by_alias=False)
