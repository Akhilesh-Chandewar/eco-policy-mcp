"""Income-tax estimator tests with hand-computed expectations (FY 2026-27)."""

from __future__ import annotations

import pytest

from eco_policy_mcp.errors import ValidationError
from eco_policy_mcp.providers import income_tax as it


def test_12_lakh_new_regime_is_zero_after_rebate():
    out = it.income_tax_new_regime(12_00_000 + 75_000)["data"]  # taxable exactly 12,00,000
    assert out["taxable_income"] == 12_00_000.0
    assert out["tax_before_rebate"] > 0
    assert out["section_87a_rebate"] == out["tax_before_rebate"]
    assert out["total_tax_payable"] == 0.0


def test_new_regime_15_lakh_slab_breakup():
    out = it.income_tax_new_regime(15_00_000 + 75_000)["data"]
    assert out["taxable_income"] == 15_00_000.0
    # 0-4L nil, 4-8L 5% (20k), 8-12L 10% (40k), 12-15L 15% (45k) = 1,05,000
    assert out["tax_before_rebate"] == 1_05_000.0
    assert out["section_87a_rebate"] == 0.0
    cess = round(1_05_000 * 0.04, 2)
    assert out["total_tax_payable"] == round(1_05_000 + cess, 2)


def test_old_regime_senior_exemption():
    out = it.income_tax_old_regime(6_00_000, age=66)["data"]
    assert out["basic_exemption_limit"] == 3_00_000.0
    # taxable = 6L - 50k std = 5.5L; 0-3L nil, 3-5L 5% (10k), 5-5.5L 20% (10k) = 20k
    assert out["tax_before_rebate"] == 20_000.0
    assert out["section_87a_rebate"] == 0.0


def test_old_regime_80c_cap():
    out = it.income_tax_old_regime(10_00_000, deductions_80c=2_00_000)["data"]
    assert out["deductions_80c_allowed"] == 1_50_000.0


def test_old_regime_rebate_at_5_lakh():
    out = it.income_tax_old_regime(5_00_000 + 50_000)["data"]  # taxable exactly 5L
    assert out["tax_before_rebate"] == 12_500.0
    assert out["section_87a_rebate"] == 12_500.0
    assert out["total_tax_payable"] == 0.0


def test_compare_regimes_recommends():
    out = it.compare_regimes(15_00_000, deductions_80c=1_50_000)
    data = out["data"]
    assert data["recommended_regime"] in ("new", "old")
    assert data["savings_if_switched"] >= 0
    assert {"new_regime", "old_regime"} <= set(data.keys())


def test_negative_input_rejected():
    with pytest.raises(ValidationError):
        it.income_tax_new_regime(-5)
