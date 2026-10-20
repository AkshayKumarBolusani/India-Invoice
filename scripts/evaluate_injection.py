"""Error-injection study for the India-Invoice arithmetic consistency checker.

Protocol (v1, 2026-10-20):
  - Input: the repo's 60 synthetic ground-truth invoices
    (evaluation/synthetic_benchmark/ground_truth.jsonl, seed 20261015).
  - Baseline: validate_invoice() on every clean record (expect valid).
  - Injection classes: deterministic field corruptions applied one at a time
    to a copy of each record. For each class we record whether the checker
    fires the INTENDED signal (named error/warning), not just any flag.
  - Controls: benign formatting mutations + one arithmetically-consistent
    invention class that the checker is NOT expected to catch (documented
    blind spot, reported honestly).

This is synthetic-fixture evidence, not real-world accuracy. The identical
protocol applies unchanged to authorized real invoices when available.

Usage: python3 evaluate_injection.py [repo_path] [out_json]
"""
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 else REPO / "evaluation" / "injection_results.json"

sys.path.insert(0, str(REPO / "src"))
from invoice_ai.validation import validate_invoice  # noqa: E402


def D(x):
    return Decimal(str(x)) if x is not None else None


def S(d):
    return f"{d:.2f}"


# ---------------- injection classes ----------------
def m_grand_total(rec):
    rec["grand_total"] = S(D(rec["grand_total"]) + Decimal("50"))
    return "Grand total mismatch"


def m_subtotal(rec):
    rec["subtotal"] = S(D(rec["subtotal"]) + Decimal("100"))
    return "does not match subtotal"


def m_line_taxable(rec):
    rec["items"][0]["taxable_value"] = S(D(rec["items"][0]["taxable_value"]) + Decimal("100"))
    return "does not match subtotal"


def m_tax_total(rec):
    if D(rec.get("total_igst")) and D(rec["total_igst"]) > 0:
        rec["total_igst"] = S(D(rec["total_igst"]) + Decimal("100"))
    else:
        rec["total_cgst"] = S(D(rec.get("total_cgst") or "0") + Decimal("100"))
    return "Grand total mismatch"


def m_gstin_format(rec):
    g = rec["vendor_gstin"]
    rec["vendor_gstin"] = g[:13] + "Q" + g[14:]  # break the fixed 'Z' position
    return "invalid GSTIN format"


def m_missing_total(rec):
    rec["grand_total"] = None
    return "Required field is missing"


def m_duplicated_allocation(rec):
    """Copy the full invoice-level tax onto every line (a known LLM error)."""
    if len(rec["items"]) < 2:
        return None
    heads = [("total_igst", "igst_amount"), ("total_cgst", "cgst_amount"), ("total_sgst", "sgst_amount")]
    applied = False
    for total_key, line_key in heads:
        total = D(rec.get(total_key) or "0")
        if total and total > 0:
            for item in rec["items"]:
                item[line_key] = S(total)
            applied = True
    return "duplicated allocation" if applied else None


def m_invented_split(rec):
    """Arithmetically-consistent invention: distribute invoice IGST across
    lines proportionally (what an LLM did in the fixture comparisons).
    The checker is NOT expected to catch this; it reconciles by construction."""
    igst = D(rec.get("total_igst") or "0")
    if not igst or igst == 0 or len(rec["items"]) < 1:
        return None
    taxable = [D(i["taxable_value"]) for i in rec["items"]]
    tot = sum(taxable)
    parts, acc = [], Decimal("0")
    for j, t in enumerate(taxable):
        if j == len(taxable) - 1:
            parts.append(igst - acc)
        else:
            p = (igst * t / tot).quantize(Decimal("0.01"))
            parts.append(p)
            acc += p
    for item, p in zip(rec["items"], parts):
        item["igst_amount"] = S(p)
    return "CONTROL_no_catch_expected"


def m_benign_comma(rec):
    for k in ("subtotal", "grand_total"):
        v = D(rec[k])
        rec[k] = f"{v:,.2f}"
    return "CONTROL_no_catch_expected"


def m_benign_symbol(rec):
    for k in ("subtotal", "grand_total"):
        rec[k] = "₹" + str(rec[k])
    return "CONTROL_no_catch_expected"


CLASSES = [
    ("grand_total_drift", m_grand_total, "error"),
    ("subtotal_drift", m_subtotal, "error"),
    ("line_taxable_drift", m_line_taxable, "error"),
    ("tax_total_drift", m_tax_total, "error"),
    ("gstin_format_break", m_gstin_format, "error"),
    ("missing_grand_total", m_missing_total, "error"),
    ("duplicated_allocation", m_duplicated_allocation, "warning"),
    ("invented_consistent_split", m_invented_split, "control"),
    ("benign_comma_format", m_benign_comma, "control"),
    ("benign_currency_symbol", m_benign_symbol, "control"),
]


def main():
    records = [json.loads(l) for l in open(REPO / "evaluation" / "synthetic_benchmark" / "ground_truth.jsonl")]
    print(f"loaded {len(records)} synthetic ground-truth records")

    base = [validate_invoice(r) for r in records]
    base_valid = sum(1 for r in base if r["status"] == "valid")
    print(f"baseline: {base_valid}/{len(records)} valid")

    results = {"protocol": "injection v1; intended-signal matching; tolerance=1.00 default",
               "n_documents": len(records), "baseline_valid": base_valid, "classes": {}}
    for name, fn, kind in CLASSES:
        n = caught = flagged_any = 0
        for rec in records:
            mut = copy.deepcopy(rec)
            intended = fn(mut)
            if intended is None:
                continue
            n += 1
            out = validate_invoice(mut)
            msgs = out["errors"] + out["warnings"]
            if kind == "control":
                if out["status"] != "valid":
                    flagged_any += 1  # false flag for controls
            else:
                if out["status"] != "valid":
                    flagged_any += 1
                if any(intended in m for m in msgs):
                    caught += 1
        entry = {"kind": kind, "n_applicable": n}
        if kind == "control":
            entry["false_flagged"] = flagged_any
            entry["false_flag_rate"] = round(flagged_any / n, 4) if n else None
            print(f"{name:28} control  n={n:3}  false-flagged={flagged_any}")
        else:
            entry["caught_intended"] = caught
            entry["catch_rate"] = round(caught / n, 4) if n else None
            entry["flagged_any"] = flagged_any
            print(f"{name:28} {kind:7}  n={n:3}  caught(intended)={caught}  rate={entry['catch_rate']}")
        results["classes"][name] = entry

    # Explicitly exercise the documented Decimal tolerance boundary. These are
    # separate probes, not part of the large-drift injection classes above.
    tolerance_probes = {}
    for probe_name, drift, should_flag in (
        ("grand_total_plus_0_50", Decimal("0.50"), False),
        ("grand_total_plus_2_00", Decimal("2.00"), True),
    ):
        flagged = caught_intended = 0
        for rec in records:
            mut = copy.deepcopy(rec)
            mut["grand_total"] = S(D(mut["grand_total"]) + drift)
            out = validate_invoice(mut)
            msgs = out["errors"] + out["warnings"]
            if out["status"] != "valid":
                flagged += 1
            if any("Grand total mismatch" in msg for msg in out["errors"]):
                caught_intended += 1
        tolerance_probes[probe_name] = {
            "mutation": f"grand_total + {drift:.2f}",
            "expected_flag": should_flag,
            "n_applicable": len(records),
            "flagged_any": flagged,
            "caught_intended": caught_intended,
            "flag_rate": round(flagged / len(records), 4) if records else None,
        }
        print(f"{probe_name:28} expected_flag={should_flag!s:5} n={len(records):3} flagged={flagged:3} intended_error={caught_intended:3}")

    # Fail closed if the documented tolerance behavior ever changes.
    assert len(records) == 60, f"Expected 60 benchmark records, got {len(records)}"
    assert base_valid == len(records), f"Expected all clean records valid, got {base_valid}/{len(records)}"
    assert tolerance_probes["grand_total_plus_0_50"]["flagged_any"] == 0, "₹0.50 probe should not be flagged"
    assert tolerance_probes["grand_total_plus_0_50"]["caught_intended"] == 0, "₹0.50 probe should not trigger grand-total mismatch"
    assert tolerance_probes["grand_total_plus_2_00"]["flagged_any"] == len(records), "₹2.00 probe should flag every record"
    assert tolerance_probes["grand_total_plus_2_00"]["caught_intended"] == len(records), "₹2.00 probe should trigger grand-total mismatch for every record"
    results["tolerance_probes"] = tolerance_probes

    # Write atomically so an interrupted run cannot leave a truncated results file.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp_out = OUT.with_suffix(OUT.suffix + ".tmp")
    temp_out.write_text(json.dumps(results, indent=2) + "\n")
    temp_out.replace(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
