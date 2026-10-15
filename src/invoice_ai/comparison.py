"""Field-level comparison helpers for invoice extractor outputs."""
from decimal import Decimal, InvalidOperation


NUMERIC_FIELD_PARTS = (
    "amount", "total", "subtotal", "price", "value", "quantity", "rate",
    "tax", "shipping", "discount", "round", "fee",
)


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def normalize_value(field, value):
    """Normalize equivalent numeric representations without equating null to zero."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = _decimal(value)
        return number.normalize() if number is not None else value
    if isinstance(value, str):
        stripped = " ".join(value.strip().split())
        number = _decimal(stripped)
        # Only normalize numeric strings in known numeric fields. Avoid converting
        # invoice IDs or other text that happens to contain digits.
        numeric_field = any(token in field.casefold() for token in NUMERIC_FIELD_PARTS)
        if numeric_field and number is not None:
            return number.normalize()
        return stripped.casefold()
    return value


def flatten(value, prefix=""):
    flattened = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flattened.update(flatten(child, f"{prefix}[{index}]"))
        flattened[f"{prefix}.__length__"] = len(value)
    else:
        flattened[prefix] = value
    return flattened


def compare_outputs(rules, ollama):
    """Compare supported nested fields without treating missing values as mismatches."""
    rules_flat, ollama_flat = flatten(rules), flatten(ollama)
    all_fields = sorted(set(rules_flat) | set(ollama_flat))
    differences, formatting_differences, missing_fields = [], [], []
    for field in all_fields:
        rules_present = field in rules_flat
        ollama_present = field in ollama_flat
        rv = rules_flat.get(field)
        ov = ollama_flat.get(field)
        rules_missing = not rules_present or rv is None
        ollama_missing = not ollama_present or ov is None
        if rules_missing or ollama_missing:
            if rules_missing != ollama_missing:
                missing_fields.append({
                    "field": field,
                    "rules_value": rv if rules_present else None,
                    "ollama_value": ov if ollama_present else None,
                    "missing_from": "rules" if rules_missing else "ollama",
                })
            continue
        rn, on = normalize_value(field, rv), normalize_value(field, ov)
        if rn == on:
            if rv != ov and rv is not None and ov is not None:
                formatting_differences.append({"field": field, "rules_value": rv, "ollama_value": ov})
        else:
            differences.append({"field": field, "rules_value": rv, "ollama_value": ov})
    return {
        "fields_compared": len(all_fields),
        "difference_count": len(differences),
        "missing_field_count": len(missing_fields),
        "formatting_difference_count": len(formatting_differences),
        "differences": differences,
        "missing_fields": missing_fields,
        "formatting_differences": formatting_differences,
        "agreement_note": (
            "Extractor agreement indicates only output agreement; it does not establish "
            "source correctness or GST/tax compliance."
        ),
    }
