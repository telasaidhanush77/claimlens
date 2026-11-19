"""Shapes shared by the extractor, the engine and the API."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Category = Literal["room", "icu", "surgeon", "ot", "diagnostics", "medicines",
                   "consumables", "implants", "other"]
CATEGORIES: tuple[str, ...] = Category.__args__


class Term[T](BaseModel):
    """One policy rule. `value` is None when the policy doesn't state it (or we couldn't
    prove it does). `verified` means the quote was found in the PDF on `page`."""

    value: T | None = None
    page: int | None = None
    quote: str | None = None
    verified: bool = False


class Limit(BaseModel):
    kind: Literal["per_day", "pct_si"]  # rupees per day, or percent of sum insured per day
    amount: Decimal = Field(gt=0)


class PolicyTerms(BaseModel):
    sum_insured: Term[Decimal] = Term()
    room_limit: Term[Limit] = Term()
    icu_limit: Term[Limit] = Term()
    proportionate: Term[bool] = Term()
    proportionate_categories: Term[list[Category]] = Term()
    copay_pct: Term[Decimal] = Term()
    deductible: Term[Decimal] = Term()
    sublimits: Term[dict[str, Decimal]] = Term()
    non_payable: Term[list[Category]] = Term()


class LineItem(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    category: Category
    amount: Decimal = Field(gt=0, le=Decimal(10**9))
    days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def _days_for_stays(self) -> "LineItem":
        if self.category in ("room", "icu") and self.days is None:
            raise ValueError("room and ICU lines need the number of days")
        return self


class RoomOption(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate_per_day: Decimal = Field(gt=0, le=Decimal(10**7))


class Estimate(BaseModel):
    procedure: str | None = None
    items: list[LineItem] = Field(min_length=1, max_length=200)
    room_options: list[RoomOption] = Field(default=[], max_length=10)


class LineResult(BaseModel):
    description: str
    category: Category
    billed: Decimal
    payable: Decimal
    notes: list[str] = []


class Step(BaseModel):
    label: str
    total_after: Decimal
    page: int | None = None


class RoomChoice(BaseModel):
    name: str
    rate_per_day: Decimal
    insurer_pays: int
    you_pay: int


class Simulation(BaseModel):
    lines: list[LineResult]
    steps: list[Step]
    billed: int
    insurer_pays: int
    you_pay: int
    room_choices: list[RoomChoice] = []
