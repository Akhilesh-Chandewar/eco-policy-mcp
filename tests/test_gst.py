"""GST provider tests: split, inclusive, RCM, GSTIN checksum (envelope format)."""

from __future__ import annotations

import pytest

from eco_policy_mcp.errors import ValidationError
from eco_policy_mcp.providers import gst


def test_split_intra_state_cgst_sgst():
    out = gst.gst_split(10_000, 18, intra_state=True)["data"]
    assert out["tax_type"] == "CGST+SGST"
    assert out["cgst"] == 900.0
    assert out["sgst"] == 900.0
    assert out["igst"] == 0.0
    assert out["total_tax"] == 1800.0
    assert out["total_invoice_value"] == 11_800.0


def test_split_inter_state_igst():
    out = gst.gst_split(10_000, 18, intra_state=False)["data"]
    assert out["tax_type"] == "IGST"
    assert out["igst"] == 1800.0
    assert out["cgst"] == 0.0
    assert out["total_invoice_value"] == 11_800.0


def test_split_envelope_has_provenance():
    out = gst.gst_split(10_000, 18, intra_state=True)
    assert out["provenance"]["source"]
    assert out["provenance"]["as_of"] is not None


def test_split_penny_rounding_balances():
    out = gst.gst_split(250.05, 18, intra_state=True)["data"]
    assert round(out["cgst"] + out["sgst"], 2) == out["total_tax"]


def test_split_rejects_bad_rate_and_negative():
    with pytest.raises(ValidationError):
        gst.gst_split(100, 17, intra_state=True)
    with pytest.raises(ValidationError):
        gst.gst_split(-1, 18, intra_state=False)


def test_from_inclusive():
    out = gst.gst_from_inclusive(1180, 18)["data"]
    assert out["base_amount"] == 1000.0
    assert out["gst_amount"] == 180.0
    assert out["gross_amount"] == 1180.0


def test_reverse_charge_note():
    out = gst.gst_reverse_charge(5000, 5)
    data = out["data"]
    assert "reverse charge" in data["tax_type"].lower()
    assert data["igst"] == 250.0
    assert "rcm_note" in data
    assert "reverse charge" in out["provenance"]["note"].lower()


def test_gstin_canonical_example_valid():
    # Canonical worked example: 14 chars 27AAPFU0939F1Z -> checksum V
    assert gst.validate_gstin("27AAPFU0939F1ZV") is True


def test_gstin_rejects_bad_checksum_and_format():
    assert gst.validate_gstin("27AAPFU0939F1ZA") is False  # wrong checksum
    assert gst.validate_gstin("27AAPFU0939F1") is False  # too short
    assert gst.validate_gstin("XXAAPFU0939F1ZV") is False  # state code not digits
    assert gst.validate_gstin("27aapfu0939f1zv") is True  # case-insensitive


def test_state_code_extracted():
    assert gst.state_code_from_gstin("27AAPFU0939F1ZV") == "27"
