"""Validation helpers for India Invoice AI.

These checks are conservative and support human review; they do not certify GST/tax compliance.
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import re


GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _as_mapping(value):
    """Accept dictionaries and Pydantic v1/v2 models, including line items."""
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def validate_invoice(data, tolerance=Decimal("1.00")):
    """Validate invoice structure and arithmetic; return status/errors/warnings/notes."""
    data = _as_mapping(data)
    errors = []
    warnings = []
    notes = []

    # These core fields are hard failures when absent, except invoice identifiers,
    # which are sent to human review so partially extracted documents can be checked.
    for field in ("document_type", "vendor_name", "items", "grand_total"):
        value = data.get(field)
        if value is None or value == "" or (field == "items" and not value):
            errors.append(f"Required field is missing: {field.replace('_', ' ')}.")

    if not data.get("invoice_number"):
        warnings.append("Required field is missing: invoice number.")
    if not data.get("invoice_date"):
        warnings.append("Required field is missing: invoice date.")

    vendor_gstin = str(data.get("vendor_gstin") or "").strip().upper()
    buyer_gstin = str(data.get("buyer_gstin") or "").strip().upper()
    if not vendor_gstin:
        warnings.append("Vendor GSTIN is missing; verify it against the source document.")
    elif not GSTIN_PATTERN.fullmatch(vendor_gstin):
        errors.append("Vendor invalid GSTIN format; verify it against the source document.")
    if not buyer_gstin:
        warnings.append("Buyer GSTIN is missing; verify whether it is present or required for this document.")
    elif not GSTIN_PATTERN.fullmatch(buyer_gstin):
        errors.append("Buyer invalid GSTIN format; verify it against the source document.")

    items = [_as_mapping(item) for item in (data.get("items") or [])]
    item_taxable_values = [
        _decimal(item.get("taxable_value"))
        for item in items
        if item.get("taxable_value") is not None and str(item.get("taxable_value")).strip() != ""
    ]
    subtotal = _decimal(data.get("subtotal"))
    grand_total = _decimal(data.get("grand_total"))
    cgst = _decimal(data.get("total_cgst")) or Decimal("0")
    sgst = _decimal(data.get("total_sgst")) or Decimal("0")
    igst = _decimal(data.get("total_igst")) or Decimal("0")

    if subtotal is not None and len(item_taxable_values) == len(items):
        sum_taxable = sum(item_taxable_values, Decimal("0"))
        if abs(sum_taxable - subtotal) > tolerance:
            errors.append(
                f"Item taxable values total ({sum_taxable}) does not match subtotal ({subtotal})."
            )

    if grand_total is not None and subtotal is not None:
        calculated_total = subtotal + cgst + sgst + igst
        if abs(calculated_total - grand_total) > tolerance:
            errors.append(
                f"Grand total mismatch: extracted total ({grand_total}) does not match subtotal plus invoice-level taxes ({calculated_total})."
            )

    invoice_tax_total = cgst + sgst + igst
    line_tax_values = []
    for index, item in enumerate(items, start=1):
        line_tax_components = [
            _decimal(item.get("cgst_amount")),
            _decimal(item.get("sgst_amount")),
            _decimal(item.get("igst_amount")),
        ]
        known_components = [value for value in line_tax_components if value is not None]
        if known_components:
            line_tax_values.append(sum(known_components, Decimal("0")))

        quantity = _decimal(item.get("quantity"))
        unit_price = _decimal(item.get("unit_price"))
        taxable = _decimal(item.get("taxable_value"))
        if quantity is not None and unit_price is not None and taxable is not None:
            if abs(quantity * unit_price - taxable) > tolerance:
                warnings.append(f"Line {index}: quantity × unit price does not match taxable value.")

    # Detect a common LLM error: copying the full invoice tax total to every line.
    if len(items) > 1:
        for key, invoice_total, label in (
            ("cgst_amount", cgst, "CGST"),
            ("sgst_amount", sgst, "SGST"),
            ("igst_amount", igst, "IGST"),
        ):
            populated = [_decimal(item.get(key)) for item in items]
            if invoice_total > 0 and all(value is not None for value in populated):
                if all(abs(value - invoice_total) <= tolerance for value in populated):
                    warnings.append(
                        f"Each line item has {label} equal to the full invoice-level {label} total "
                        f"({invoice_total}); likely duplicated allocation. Verify against the source."
                    )

    if any(_decimal(item.get("gst_rate")) is not None for item in items):
        notes.append(
            "Line-level GST rates were populated. Confirm each rate is supported by the source; "
            "invoice-level tax totals alone do not establish each item's rate."
        )

    all_lines_have_tax = bool(items) and all(
        any(
            item.get(key) is not None and str(item.get(key)).strip() != ""
            for key in ("cgst_amount", "sgst_amount", "igst_amount")
        )
        for item in items
    )
    if all_lines_have_tax:
        # Recalculate each line's known tax components independently.
        sum_line_tax = sum(line_tax_values, Decimal("0"))
        if abs(sum_line_tax - invoice_tax_total) > tolerance:
            warnings.append(
                f"Sum of line-level tax amounts ({sum_line_tax}) differs from invoice-level tax total "
                f"({invoice_tax_total}). Check for duplicated invoice-level taxes."
            )
    else:
        notes.append("Line-level tax allocation is not available; invoice-level tax totals were checked separately.")

    if errors:
        status = "invalid"
    elif warnings:
        status = "review_required"
    else:
        status = "valid"

    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
        "checks": {
            "subtotal": str(subtotal) if subtotal is not None else None,
            "sum_line_taxable_values": (
                str(sum(item_taxable_values, Decimal("0")))
                if len(item_taxable_values) == len(items) else None
            ),
            "invoice_level_tax_total": str(invoice_tax_total),
            "grand_total": str(grand_total) if grand_total is not None else None,
        },
    }
