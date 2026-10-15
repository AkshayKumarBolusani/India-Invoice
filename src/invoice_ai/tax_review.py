"""Conservative post-processing for suspicious LLM line-level tax allocations.

This module does not infer taxes from arithmetic. It only removes line-level
values when a strong duplicate-total pattern is present across multiple items.
Invoice-level totals are never modified.
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

TAX_FIELDS = ("cgst_amount", "sgst_amount", "igst_amount")
RATE_FIELD = "gst_rate"


def _mapping(value):
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump(mode="python")
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


def _decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def review_llm_tax_fields(invoice, tolerance=Decimal("0.01")):
    """Return ``(reviewed_invoice, warnings)`` without mutating the input.

    When 2+ items each contain the *entire* invoice-level amount for a tax,
    clear that tax field from every item. If any such duplication is detected,
    clear populated per-item GST rates too: the rates may have been attached to
    lines by the same unsupported allocation. Keep invoice-level totals intact.

    This deliberately does not clear a tax in a single-item invoice (e.g. the
    valid IGST amount in INV-002) or make any tax calculation-based guesses.
    """
    result = _mapping(invoice)
    result["items"] = [dict(_mapping(item)) for item in (result.get("items") or [])]
    items = result["items"]
    if len(items) < 2:
        return result, []

    duplicated = []
    for field, total_field, label in (
        ("cgst_amount", "total_cgst", "CGST"),
        ("sgst_amount", "total_sgst", "SGST"),
        ("igst_amount", "total_igst", "IGST"),
    ):
        invoice_total = _decimal(result.get(total_field)) or Decimal("0")
        line_values = [_decimal(item.get(field)) for item in items]
        if invoice_total > 0 and all(value is not None for value in line_values):
            if all(abs(value - invoice_total) <= tolerance for value in line_values):
                duplicated.append((field, label, invoice_total))

    warnings = []
    if not duplicated:
        return result, warnings

    for field, label, invoice_total in duplicated:
        for item in items:
            item[field] = None
        warnings.append(
            f"Cleared duplicated line-level {label} amounts equal to the full invoice-level "
            f"total ({invoice_total}) on every item. The invoice-level total was preserved; "
            "verify the source before assigning tax to individual items."
        )

    # Rates on these lines are not safe to retain when the same output duplicated
    # invoice-level taxes into each line; do not alter rates in any other case.
    for item in items:
        if item.get(RATE_FIELD) is not None:
            item[RATE_FIELD] = None
    warnings.append(
        "Cleared per-item GST rates because they were returned alongside duplicated "
        "invoice-level taxes and are not verified as item-specific."
    )
    return result, warnings
