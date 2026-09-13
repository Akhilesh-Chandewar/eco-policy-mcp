"""RBI provider and error-envelope tests."""

from __future__ import annotations

from eco_policy_mcp.errors import ValidationError
from eco_policy_mcp.providers import rbi


def test_policy_rates_envelope():
    out = rbi.get_policy_rates()
    assert set(out.keys()) == {"data", "provenance"}
    assert out["data"]["policy_repo_rate"] == 5.25
    assert out["data"]["cash_reserve_ratio_crr"] == 3.00
    assert out["provenance"]["as_of"] is not None
    assert "curated" in out["provenance"]["note"].lower()


def test_validation_error_payload_shape():
    payload = ValidationError("bad input").to_payload()
    assert payload == {"error": {"code": "invalid_input", "message": "bad input"}}


def test_error_payload_with_details():
    err = ValidationError("bad", hint="try x", details={"field": "amount"})
    payload = err.to_payload()
    assert payload["error"]["hint"] == "try x"
    assert payload["error"]["details"] == {"field": "amount"}
