"""Income-tax computation (FY 2026-27 / AY 2027-28).

Slab data cross-checked against incometaxindia.gov.in (Sept 2026):
new regime unchanged from Budget 2025 (0-4L nil .. >24L 30%, std deduction
75k, 87A rebate up to 12L taxable income). Old regime retained as option.

THIS IS AN ESTIMATOR: excludes surcharge, cess (added here at 4%), and
special-case deductions. Always cite it as indicative, not advice.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..models import envelope

_TAX_SOURCE = "eco-policy-mcp computation (FY 2026-27 slabs, Finance Act)"
_TAX_REF = "https://www.incometaxindia.gov.in/Pages/charts-and-tables.aspx"

# Slabs: (upper_limit_in_rupees, rate_percent)
NEW_REGIME_FY2627 = [
    (400_000, 0),
    (800_000, 5),
    (1_200_000, 10),
    (1_600_000, 15),
    (2_000_000, 20),
    (2_400_000, 25),
    (float("inf"), 30),
]

OLD_REGIME_FY2627 = [
    (250_000, 0),
    (500_000, 5),
    (1_000_000, 20),
    (float("inf"), 30),
]

NEW_REGIME_STD_DEDUCTION = 75_000.0
OLD_REGIME_STD_DEDUCTION = 50_000.0
REBATE_87A_NEW_LIMIT = 12_00_000.0  # taxable income up to this -> full rebate of tax
CESS_PERCENT = 4.0

REGIMES = ("new", "old")


@dataclass(frozen=True)
class SlabRow:
    lower: float
    upper: float
    rate: float
    tax_at_rate: float


def _slab_breakup(taxable: float, slabs) -> list[SlabRow]:
    """All amounts in rupees; slab limits are absolute rupee upper bounds."""
    rows: list[SlabRow] = []
    lower = 0.0
    for upper, rate in slabs:
        if taxable > lower:
            span = min(taxable, upper) - lower
            rows.append(SlabRow(lower, upper, rate, span * rate / 100))
        lower = upper
    return rows


def income_tax_new_regime(gross_salary: float, age: int = 35) -> dict:
    if gross_salary < 0:
        raise ValidationError("gross_salary must be non-negative")
    if age < 0:
        raise ValidationError("age must be non-negative")

    # New regime: only standard deduction applies
    taxable = max(0.0, gross_salary - NEW_REGIME_STD_DEDUCTION)
    rows = _slab_breakup(taxable, NEW_REGIME_FY2627)
    base_tax = sum(r.tax_at_rate for r in rows)

    rebate = 0.0
    if taxable <= REBATE_87A_NEW_LIMIT and base_tax > 0:
        rebate = base_tax

    after_rebate = base_tax - rebate
    cess = after_rebate * CESS_PERCENT / 100
    total = after_rebate + cess

    return envelope({
        "regime": "new",
        "assessment_year": "2027-28",
        "financial_year": "2026-27",
        "gross_salary": gross_salary,
        "standard_deduction": NEW_REGIME_STD_DEDUCTION,
        "taxable_income": taxable,
        "slab_breakup": [
            {"lower": r.lower, "upper": r.upper, "rate_percent": r.rate, "tax": round(r.tax_at_rate, 2)}
            for r in rows
        ],
        "tax_before_rebate": round(base_tax, 2),
        "section_87a_rebate": round(rebate, 2),
        "health_and_education_cess": round(cess, 2),
        "total_tax_payable": round(max(0.0, total), 2),
        "effective_rate_percent": round((total / gross_salary * 100) if gross_salary else 0.0, 2),
        "marginal_rate_percent": 30.0 if taxable > 2_400_000 else None,
        "notes": [
            "Estimator only: excludes surcharge and capital-gains special rates.",
            f"Section 87A rebate makes income up to Rs {REBATE_87A_NEW_LIMIT:,.0f} (taxable) effectively tax-free under the new regime.",
        ],
    }, source=_TAX_SOURCE, reference=_TAX_REF)


def income_tax_old_regime(
    gross_salary: float,
    deductions_80c: float = 0.0,
    other_deductions: float = 0.0,
    age: int = 35,
) -> dict:
    if gross_salary < 0 or deductions_80c < 0 or other_deductions < 0:
        raise ValidationError("amounts must be non-negative")
    if age < 0:
        raise ValidationError("age must be non-negative")

    # Basic exemption is age-sensitive in the old regime (rupees)
    exemption = 5_00_000.0 if age >= 80 else 3_00_000.0 if age >= 60 else 2_50_000.0
    slabs = [(exemption, 0)] + OLD_REGIME_FY2627[1:]

    capped_80c = min(deductions_80c, 1_50_000.0)
    taxable = max(
        0.0, gross_salary - OLD_REGIME_STD_DEDUCTION - capped_80c - other_deductions
    )
    rows = _slab_breakup(taxable, slabs)
    base_tax = sum(r.tax_at_rate for r in rows)

    # 87A old-regime rebate: taxable income <= 5L -> rebate up to 12,500
    rebate = 0.0
    if taxable <= 5_00_000 and base_tax > 0:
        rebate = min(base_tax, 12_500.0)

    after_rebate = base_tax - rebate
    cess = after_rebate * CESS_PERCENT / 100
    total = after_rebate + cess

    return envelope({
        "regime": "old",
        "assessment_year": "2027-28",
        "financial_year": "2026-27",
        "gross_salary": gross_salary,
        "standard_deduction": OLD_REGIME_STD_DEDUCTION,
        "deductions_80c_allowed": capped_80c,
        "other_deductions": other_deductions,
        "basic_exemption_limit": exemption,
        "taxable_income": taxable,
        "slab_breakup": [
            {"lower": r.lower, "upper": r.upper, "rate_percent": r.rate, "tax": round(r.tax_at_rate, 2)}
            for r in rows
        ],
        "tax_before_rebate": round(base_tax, 2),
        "section_87a_rebate": round(rebate, 2),
        "health_and_education_cess": round(cess, 2),
        "total_tax_payable": round(max(0.0, total), 2),
        "effective_rate_percent": round((total / gross_salary * 100) if gross_salary else 0.0, 2),
        "notes": [
            "Estimator only: excludes surcharge, HRA, home-loan interest and other chapter-VI-A items beyond inputs given.",
            f"Basic exemption {exemption:,.0f} applied for age {age}.",
        ],
    }, source=_TAX_SOURCE, reference=_TAX_REF)


def compare_regimes(
    gross_salary: float,
    deductions_80c: float = 0.0,
    other_deductions: float = 0.0,
    age: int = 35,
) -> dict:
    new = income_tax_new_regime(gross_salary, age)["data"]
    old = income_tax_old_regime(gross_salary, deductions_80c, other_deductions, age)["data"]
    better = "new" if new["total_tax_payable"] <= old["total_tax_payable"] else "old"
    return envelope(
        {
            "new_regime": new,
            "old_regime": old,
            "recommended_regime": better,
            "savings_if_switched": round(
                abs(new["total_tax_payable"] - old["total_tax_payable"]), 2
            ),
            "note": "Mechanical comparison of the two estimators; individual circumstances (capital gains, NPS, HRA) can change the answer.",
        },
        source=_TAX_SOURCE,
        reference=_TAX_REF,
    )
