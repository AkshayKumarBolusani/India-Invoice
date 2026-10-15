import json

from scripts.audit_dataset import (
    audit_arithmetic,
    audit_record,
    build_summary,
    normalize_invoice_response,
    write_reports,
)


def make_record(response, source="Invoice INV-1 dated 01/01/2026 for Paper", **metadata):
    return {
        "doc_id": "sensitive-document-id",
        "messages": [
            {"role": "user", "content": source},
            {"role": "assistant", "content": response},
        ],
        **metadata,
    }


def test_real_hugging_face_shape_recognizes_line_items():
    response = json.dumps({
        "invoice_number": "INV-1",
        "invoice_date": "01/01/2026",
        "vendor_name": "Seller",
        "line_items": [{"description": "Paper", "quantity": 2, "unit_price": 5}],
        "subtotal": 10,
        "tax_amount": 1.8,
        "total_amount": 11.8,
        "currency": "INR",
    })

    row = audit_record(make_record(response), 0)

    assert row["response_status"] == "parsed"
    assert row["recognized_item_count"] == 1
    assert row["schema_issue_count"] == 0
    assert row["arithmetic_failure_count"] == 0
    assert row["arithmetic_skipped_count"] >= 1
    assert row["generic_tax_semantics"] == "generic_tax_amount"


def test_items_alias_and_equivalent_total_are_normalized():
    normalized, provenance = normalize_invoice_response({
        "items": [{"description": "Paper", "quantity": 1, "unit_price": 10}],
        "total_amount": 10,
    })

    assert provenance["item_source"] == "items"
    assert normalized["grand_total"] == 10
    assert normalized["items"][0]["description"] == "Paper"


def test_malformed_json_is_not_called_a_schema_failure():
    row = audit_record(make_record("not json"), 0)

    assert row["response_status"] == "malformed_json"
    assert row["schema_issues"] == "malformed_json"
    assert row["recognized_item_count"] == 0


def test_arithmetic_mismatch_is_reported_without_inventing_tax_semantics():
    response = json.dumps({
        "invoice_number": "INV-1",
        "invoice_date": "01/01/2026",
        "vendor_name": "Seller",
        "line_items": [{
            "description": "Paper",
            "quantity": 2,
            "unit_price": 5,
            "taxable_value": 9,
        }],
        "subtotal": 9,
        "tax_amount": 1,
        "total_amount": 10,
    })

    row = audit_record(make_record(response), 0)

    assert row["arithmetic_failure_count"] == 1
    assert "line_quantity_times_unit_price" in row["arithmetic_failures"]
    assert "cgst" not in row["arithmetic_failures"]


def test_generic_total_equation_supports_shipping_discount_and_round_off():
    failures, skipped = audit_arithmetic({
        "subtotal": "100",
        "generic_tax_amount": "18",
        "shipping_fee": "5",
        "discount": "3",
        "round_off": "0.01",
        "grand_total": "120.01",
        "items": [],
    })

    assert failures == []
    assert "subtotal_plus_generic_tax_plus_adjustments_vs_total" not in skipped


def test_rounding_tolerance_allows_small_total_delta():
    failures, _ = audit_arithmetic({
        "subtotal": "100",
        "generic_tax_amount": "18",
        "grand_total": "118.009",
        "items": [],
    })

    assert failures == []


def test_negative_round_off_is_added_with_its_signed_value():
    failures, _ = audit_arithmetic({
        "subtotal": "100",
        "generic_tax_amount": "18",
        "round_off": "-0.01",
        "grand_total": "117.99",
        "items": [],
    })

    assert failures == []


def test_missing_generic_tax_skips_total_check_without_failure():
    failures, skipped = audit_arithmetic({
        "subtotal": "100",
        "grand_total": "100",
        "items": [],
    })

    assert failures == []
    assert "subtotal_plus_generic_tax_plus_adjustments_vs_total:missing_semantic_fields" in skipped


def test_empty_items_are_separate_from_missing_response_fields():
    row = audit_record(make_record(json.dumps({
        "invoice_number": "INV-1",
        "invoice_date": "01/01/2026",
        "vendor_name": "Seller",
        "items": [],
        "subtotal": 0,
        "tax_amount": 0,
        "total_amount": 0,
    })), 0)

    assert row["recognized_item_count"] == 0
    assert row["missing_field_count"] == 0
    assert row["arithmetic_skipped_count"] == 2


def test_summary_matches_row_level_counts_and_skip_reasons():
    rows = [
        audit_record(make_record(json.dumps({
            "invoice_number": "INV-1",
            "invoice_date": "01/01/2026",
            "vendor_name": "Seller",
            "line_items": [{"description": "Paper", "quantity": 1, "unit_price": 10}],
            "subtotal": 10,
            "tax_amount": 0,
            "total_amount": 10,
        })), 0),
        audit_record(make_record("not json"), 1),
    ]
    summary = build_summary(rows, sample_size=2)

    assert summary["records_audited"] == len(rows)
    assert summary["recognized_item_count_total"] == sum(row["recognized_item_count"] for row in rows)
    assert summary["arithmetic_skipped_checks"] == sum(row["arithmetic_skipped_count"] for row in rows)
    assert summary["records_with_source_evidence_gaps"] == sum(
        int(row["source_core_fields_not_found"]) > 0
        or int(row["source_item_descriptions_not_found"]) > 0
        for row in rows
    )


def test_suspicious_metadata_is_classified_and_redacted():
    secret = "INV-1 with a long private invoice fragment " * 5
    row = audit_record(make_record("{}", is_duplicate=secret, all_found=True), 0)

    assert row["suspicious_metadata_count"] == 1
    assert "long_or_multiline_text" in row["metadata_types"]
    assert secret not in json.dumps(row)


def test_reports_are_sanitized_and_empty_reports_work(tmp_path):
    row = audit_record(make_record("{}", is_duplicate="private invoice text"), 0)
    csv_path = tmp_path / "audit.csv"
    summary_path = tmp_path / "summary.json"
    write_reports([row], csv_path, summary_path, 1)

    assert "private invoice text" not in csv_path.read_text(encoding="utf-8")
    assert "private invoice text" not in summary_path.read_text(encoding="utf-8")

    empty_csv = tmp_path / "empty.csv"
    empty_summary = tmp_path / "empty.json"
    write_reports([], empty_csv, empty_summary, 10)
    assert json.loads(empty_summary.read_text(encoding="utf-8"))["records_audited"] == 0