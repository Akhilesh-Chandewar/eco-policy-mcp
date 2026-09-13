"""GST computation provider (pure math, no network).

Rates as per CGST Act, 2017. GSTIN checksum per GSTN spec (mod-36-36).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from ..errors import ValidationError
from ..models import envelope

GST_RATES = (0.25, 3, 5, 12, 18, 28)

_GST_SOURCE = "eco-policy-mcp computation (GST rates per CGST Act, 2017)"
_GST_REF = "https://taxinformation.cbic.gov.in/"

# GSTIN: 2-digit state code + 10-char PAN + entity code + 'Z' + checksum
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_gstin(gstin: str) -> bool:
    """Validate via the mod-36 checksum (verified against the canonical
    worked example GSTIN 27AAPFU0939F1Z -> checksum 'V', sum 221).

    Algorithm (GSTN spec): for the first 14 chars, multiply the char code by
    an alternating multiplier starting at 1 (1,2,1,2,...), take
    quotient+remainder of the product divided by 36 and sum them; the
    expected 15th char is lookup((36 - sum % 36) % 36).
    """
    gstin = gstin.strip().upper()
    if len(gstin) != 15 or not gstin[:2].isdigit():
        return False
    try:
        total = 0
        for i, ch in enumerate(gstin[:14]):
            factor = (i % 2) + 1  # 1,2,1,2,...
            product = _CHARS.index(ch) * factor
            total += product // 36 + product % 36
        expected = (36 - (total % 36)) % 36
        return expected == _CHARS.index(gstin[14])
    except ValueError:
        return False


def state_code_from_gstin(gstin: str) -> str:
    return gstin.strip()[:2]


def gst_split(amount: float, rate_percent: float, intra_state: bool) -> dict:
    """Split GST into CGST/SGST (intra-state) or IGST (inter-state)."""
    if rate_percent not in GST_RATES:
        raise ValidationError(
            f"rate_percent must be one of {list(GST_RATES)}",
            hint="Standard GST slabs are 0.25, 3, 5, 12, 18 and 28 percent.",
        )
    if amount < 0:
        raise ValidationError("amount must be non-negative")

    rate = Decimal(str(rate_percent))
    base = Decimal(str(amount))
    total_tax = _round2(base * rate / 100)

    if intra_state:
        half = total_tax / 2
        cgst = _round2(half)
        sgst = total_tax - cgst  # keep pennies balanced
        data = {
            "tax_type": "CGST+SGST",
            "base_amount": float(_round2(base)),
            "rate_percent": float(rate),
            "cgst": float(cgst),
            "sgst": float(sgst),
            "igst": 0.0,
            "total_tax": float(total_tax),
            "total_invoice_value": float(_round2(base + total_tax)),
        }
    else:
        data = {
            "tax_type": "IGST",
            "base_amount": float(_round2(base)),
            "rate_percent": float(rate),
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": float(total_tax),
            "total_tax": float(total_tax),
            "total_invoice_value": float(_round2(base + total_tax)),
        }
    return envelope(data, source=_GST_SOURCE, reference=_GST_REF)


def gst_reverse_charge(amount: float, rate_percent: float) -> dict:
    """RCM: recipient pays tax directly; invoice shows tax payable in cash."""
    if amount < 0:
        raise ValidationError("amount must be non-negative")
    result = gst_split(amount, rate_percent, intra_state=False)["data"]
    result["tax_type"] = "IGST (reverse charge)"
    result["rcm_note"] = "Under reverse charge (Section 9(3)/9(4)), the recipient deposits this tax in cash, not via supplier invoice."
    return envelope(
        result,
        source=_GST_SOURCE,
        reference=_GST_REF,
        note="Reverse charge per Section 9(3)/9(4), CGST Act, 2017.",
    )


def gst_from_inclusive(amount: float, rate_percent: float) -> dict:
    """Extract GST out of a tax-inclusive amount."""
    if rate_percent not in GST_RATES:
        raise ValidationError(f"rate_percent must be one of {list(GST_RATES)}")
    if amount < 0:
        raise ValidationError("amount must be non-negative")
    base = Decimal(str(amount)) * 100 / (100 + Decimal(str(rate_percent)))
    base_r = _round2(base)
    tax = Decimal(str(amount)) - base_r
    return envelope(
        {
            "gross_amount": float(_round2(Decimal(str(amount)))),
            "base_amount": float(base_r),
            "gst_amount": float(_round2(tax)),
            "rate_percent": float(rate_percent),
        },
        source=_GST_SOURCE,
        reference=_GST_REF,
    )
