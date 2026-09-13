"""RBI policy rates provider.

The policy corridor changes only on MPC announcement days, so we ship a
curated snapshot (cross-checked against RBI press releases, Aug 2026 policy:
repo held at 5.25%) and stamp it with a valid-as-of date. Users can always
override via ECO_* env or check the reference URL.

TODO(phase-2): scrape rbi.org.in directly for live confirmation.
"""

from __future__ import annotations

from datetime import date

from ..models import envelope

# Current policy corridor (as of the August 2026 MPC meeting; repo held at 5.25%)
SNAPSHOT_AS_OF = date(2026, 8, 5)  # RBI policy announcement, Aug 2026
SNAPSHOT = {
    "policy_repo_rate": 5.25,
    "standing_deposit_facility_sdf": 5.00,
    "marginal_standing_facility_msf": 5.50,
    "bank_rate": 5.50,
    "cash_reserve_ratio_crr": 3.00,
    "statutory_liquidity_ratio_slr": 18.00,
    "stance": "Neutral",
}


def get_policy_rates() -> dict:
    data = {
        **SNAPSHOT,
        "rates_effective_from": SNAPSHOT_AS_OF.isoformat(),
        "unit": "percent per annum (CRR/SLR: percent of NDTL/deposits)",
    }
    return envelope(
        data,
        source="RBI monetary policy statement (curated snapshot)",
        reference="https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        note=f"Curated offline snapshot, current as of RBI policy dated {SNAPSHOT_AS_OF.isoformat()}. Verify at rbi.org.in before acting on it.",
        as_of=None,
    )
