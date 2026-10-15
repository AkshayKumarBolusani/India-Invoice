import json
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

load_dotenv(ROOT / ".env")

from invoice_ai.schemas import Invoice
from invoice_ai.validation import validate_invoice
from invoice_ai.workflow import process_file, process_batch, compare_file as compare_invoice_file

st.set_page_config(page_title="India Invoice AI", page_icon="🧾", layout="wide")

st.title("🧾 India Invoice AI")
st.caption("Local invoice extraction with rules-based parsing or Ollama. Review all extracted fields before using them.")

with st.sidebar:
    st.header("Extraction settings")
    engine = st.radio("Extractor", ["Rules-based", "Ollama (local LLM)"], index=0, key="single_engine")
    st.caption("Ollama uses the model and endpoint configured in your .env file.")
    st.divider()
    st.caption("Privacy note: rules-based extraction runs locally. Ollama runs locally when pointed at localhost.")

uploaded = st.file_uploader(
    "Upload an invoice",
    type=["pdf", "png", "jpg", "jpeg", "webp", "tiff", "bmp", "txt"],
    help="Supported formats depend on the installed Docling pipeline.",
)

if uploaded is not None:
    if st.button("Extract invoice", type="primary", use_container_width=True):
        suffix = Path(uploaded.name).suffix or ".pdf"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getvalue())
                temp_path = Path(tmp.name)

            with st.spinner("Reading document and extracting fields..."):
                result = process_file(
                    temp_path,
                    engine="rules-based" if engine == "Rules-based" else "llm",
                )
                st.session_state["invoice_ai_original"] = result["invoice"]
                st.session_state["invoice_ai_metadata"] = result["metadata"]
                st.session_state["invoice_ai_source_markdown"] = result["source_markdown"]
                st.session_state["invoice_ai_filename"] = uploaded.name
                st.session_state.pop("invoice_ai_edit", None)

        except Exception as exc:
            st.error(f"Extraction failed: {exc}")
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

if "invoice_ai_original" in st.session_state:
    original = st.session_state["invoice_ai_original"]
    metadata = st.session_state.get("invoice_ai_metadata", {})
    st.divider()
    st.subheader("Extracted fields")
    st.info(f"Source file: {st.session_state.get('invoice_ai_filename', 'Uploaded file')} · Engine: {metadata.get('engine', 'unknown')}")
    if metadata.get("latency_seconds") is not None:
        st.caption(f"LLM latency: {metadata['latency_seconds']} seconds · Model: {metadata.get('model', 'configured model')}")
    timing_fields = (
        "ingestion_seconds", "extraction_seconds", "validation_seconds", "processing_seconds"
    )
    if any(metadata.get(field) is not None for field in timing_fields):
        st.caption(" · ".join(
            f"{field.removesuffix('_seconds')}: {metadata[field]}s"
            for field in timing_fields
            if metadata.get(field) is not None
        ))
    for warning in metadata.get("tax_review_warnings", []):
        st.warning(f"Tax review: {warning}")
    if metadata.get("tax_review_changes"):
        with st.expander("Tax review corrections"):
            st.dataframe(pd.DataFrame(metadata["tax_review_changes"]), use_container_width=True, hide_index=True)

    with st.form("invoice_review_form"):
        left, right = st.columns(2)
        with left:
            document_type = st.selectbox(
                "Document type",
                ["gst_invoice", "purchase_order", "bill", "receipt"],
                index=["gst_invoice", "purchase_order", "bill", "receipt"].index(original.get("document_type", "gst_invoice")),
            )
            invoice_number = st.text_input("Invoice / document number", value=original.get("invoice_number") or "")
            invoice_date = st.text_input("Date (as shown)", value=original.get("invoice_date") or "")
            vendor_name = st.text_input("Vendor name", value=original.get("vendor_name") or "")
            vendor_gstin = st.text_input("Vendor GSTIN", value=original.get("vendor_gstin") or "")
        with right:
            buyer_name = st.text_input("Buyer name", value=original.get("buyer_name") or "")
            buyer_gstin = st.text_input("Buyer GSTIN", value=original.get("buyer_gstin") or "")
            currency = st.text_input("Currency", value=original.get("currency") or "INR")
            subtotal = st.text_input("Subtotal", value=str(original.get("subtotal") or ""))
            total_cgst = st.text_input("Total CGST", value=str(original.get("total_cgst") if original.get("total_cgst") is not None else "0"))
            total_sgst = st.text_input("Total SGST", value=str(original.get("total_sgst") if original.get("total_sgst") is not None else "0"))
            total_igst = st.text_input("Total IGST", value=str(original.get("total_igst") if original.get("total_igst") is not None else "0"))
            grand_total = st.text_input("Grand total", value=str(original.get("grand_total") or ""))

        st.markdown("#### Line items")
        items = original.get("items", [])
        item_df = pd.DataFrame(items)
        if item_df.empty:
            item_df = pd.DataFrame(columns=[
                "description", "hsn_sac", "quantity", "unit_price",
                "taxable_value", "gst_rate", "cgst_amount",
                "sgst_amount", "igst_amount", "total_amount",
            ])
        edited_items_df = st.data_editor(
            item_df,
            num_rows="dynamic",
            use_container_width=True,
            key="invoice_items_editor",
            column_config={
                "description": st.column_config.TextColumn("Description", required=True),
                "quantity": st.column_config.TextColumn("Quantity"),
                "unit_price": st.column_config.TextColumn("Unit price"),
                "taxable_value": st.column_config.TextColumn("Taxable value"),
            },
        )
        submitted = st.form_submit_button("Validate and apply edits", type="primary", use_container_width=True)

    if submitted:
        try:
            def dec_or_none(value, field):
                if value is None or str(value).strip() == "":
                    return None
                try:
                    return Decimal(str(value).replace(",", "").replace("₹", "").strip())
                except InvalidOperation as exc:
                    raise ValueError(f"{field} must be a valid number.") from exc

            def text_or_none(value):
                value = str(value).strip() if value is not None else ""
                return value or None

            edited_items = []
            for row in edited_items_df.to_dict(orient="records"):
                if not str(row.get("description") or "").strip():
                    continue
                edited_items.append({
                    "description": str(row["description"]).strip(),
                    "hsn_sac": text_or_none(row.get("hsn_sac")),
                    "quantity": dec_or_none(row.get("quantity"), "Quantity"),
                    "unit_price": dec_or_none(row.get("unit_price"), "Unit price"),
                    "taxable_value": dec_or_none(row.get("taxable_value"), "Taxable value"),
                    "gst_rate": dec_or_none(row.get("gst_rate"), "GST rate"),
                    "cgst_amount": dec_or_none(row.get("cgst_amount"), "CGST amount"),
                    "sgst_amount": dec_or_none(row.get("sgst_amount"), "SGST amount"),
                    "igst_amount": dec_or_none(row.get("igst_amount"), "IGST amount"),
                    "total_amount": dec_or_none(row.get("total_amount"), "Line total"),
                })

            payload = {
                "document_type": document_type,
                "invoice_number": text_or_none(invoice_number),
                "invoice_date": text_or_none(invoice_date),
                "vendor_name": text_or_none(vendor_name),
                "vendor_gstin": text_or_none(vendor_gstin),
                "buyer_name": text_or_none(buyer_name),
                "buyer_gstin": text_or_none(buyer_gstin),
                "currency": text_or_none(currency) or "INR",
                "items": edited_items,
                "subtotal": dec_or_none(subtotal, "Subtotal"),
                "total_cgst": dec_or_none(total_cgst, "Total CGST") or Decimal("0"),
                "total_sgst": dec_or_none(total_sgst, "Total SGST") or Decimal("0"),
                "total_igst": dec_or_none(total_igst, "Total IGST") or Decimal("0"),
                "grand_total": dec_or_none(grand_total, "Grand total"),
            }
            validated = Invoice.model_validate(payload)
            st.session_state["invoice_ai_edit"] = validated.model_dump(mode="json")
            st.success("Edits applied and schema validation passed.")
        except Exception as exc:
            st.error(f"Could not validate edits: {exc}")

    final_data = st.session_state.get("invoice_ai_edit", original)
    st.divider()
    st.subheader("Validation checks")
    validation = validate_invoice(final_data)

    status = validation["status"].lower().replace(" ", "_")

    if status == "valid":
        st.success(
            "VALID — no configured checks raised warnings. "
            "This is not tax or GST compliance certification."
        )
    elif status == "review_required":
        st.warning(
            "REVIEW REQUIRED — inspect the warnings before using this invoice data."
        )
    else:
        st.error("INVALID — fix the errors before relying on this invoice data.")

    for error in validation["errors"]:
        st.error(error)
    for warning in validation["warnings"]:
        st.warning(warning)
    for note in validation["notes"]:
        st.info(note)

    with st.expander("Validation details"):
        st.json(validation)

    st.subheader("Final structured output")
    st.json(final_data)
    with st.expander("Original extracted output"):
        st.json(original)
    json_bytes = json.dumps(final_data, indent=2, ensure_ascii=False).encode("utf-8")
    st.download_button(
        "Download JSON",
        data=json_bytes,
        file_name="invoice_extraction.json",
        mime="application/json",
    )

    items_df = pd.DataFrame(final_data.get("items", []))
    st.download_button(
        "Download line items CSV",
        data=items_df.to_csv(index=False).encode("utf-8"),
        file_name="invoice_line_items.csv",
        mime="text/csv",
    )

    with st.expander("View normalized document text (debug)"):
        st.text(st.session_state.get("invoice_ai_source_markdown", ""))

else:
    st.markdown(
        "Upload a sample invoice to begin. Start with your existing `data/samples/INV-001.pdf` fixture."
    )


st.divider()
st.header("Batch invoice processing")
st.caption("Upload multiple invoices and export a consolidated result. Review results before relying on them.")

batch_files = st.file_uploader(
    "Upload multiple invoices",
    type=["pdf", "png", "jpg", "jpeg", "webp", "tiff", "bmp", "txt"],
    accept_multiple_files=True,
    help="Each file is processed locally through Docling. Ollama runs locally when configured to localhost.",
    key="batch_invoice_upload",
)

batch_engine = st.radio(
    "Batch extractor",
    ["Rules-based", "Ollama (local LLM)"],
    horizontal=True,
    index=0,
    key="batch_engine",
)

if st.button("Process batch", type="primary", disabled=not batch_files, key="process_batch"):
    batch_results = []
    progress = st.progress(0)
    for index, batch_file in enumerate(batch_files):
        tmp_path = None
        try:
            suffix = Path(batch_file.name).suffix or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(batch_file.getvalue())
                tmp_path = Path(tmp.name)

            result = process_file(
                tmp_path,
                engine="rules-based" if batch_engine == "Rules-based" else "llm",
            )
            payload = result["invoice"]
            validation = result["validation"]
            metadata = result["metadata"]
            batch_results.append({
                "filename": batch_file.name,
                "status": validation["status"],
                "invoice_number": payload.get("invoice_number"),
                "vendor_name": payload.get("vendor_name"),
                "invoice_date": payload.get("invoice_date"),
                "grand_total": payload.get("grand_total"),
                "currency": payload.get("currency", "INR"),
                "item_count": len(payload.get("items", [])),
                "validation_warnings": " | ".join(validation["warnings"]),
                "tax_review_warnings": " | ".join(metadata.get("tax_review_warnings", [])),
                "tax_review_changes": json.dumps(metadata.get("tax_review_changes", []), ensure_ascii=False),
                "validation_errors": " | ".join(validation["errors"]),
                "invoice_json": payload,
                "validation": validation,
                "metadata": metadata,
            })
        except Exception as exc:
            batch_results.append({
                "filename": batch_file.name,
                "status": "Processing failed",
                "invoice_number": None,
                "vendor_name": None,
                "invoice_date": None,
                "grand_total": None,
                "currency": None,
                "item_count": 0,
                "validation_warnings": "",
                "validation_errors": str(exc),
                "invoice_json": None,
                "validation": None,
                "metadata": {},
            })
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        progress.progress((index + 1) / len(batch_files))

    st.session_state["invoice_ai_batch_results"] = batch_results

if "invoice_ai_batch_results" in st.session_state:
    batch_results = st.session_state["invoice_ai_batch_results"]
    st.subheader("Batch results")
    summary_columns = [
        "filename", "status", "invoice_number", "vendor_name",
        "invoice_date", "grand_total", "currency", "item_count",
        "validation_warnings", "validation_errors", "tax_review_warnings",
        "tax_review_changes",
    ]
    summary_df = pd.DataFrame([
        {key: row.get(key) for key in summary_columns}
        for row in batch_results
    ])
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download batch JSON",
        data=json.dumps(batch_results, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name="invoice_batch_results.json",
        mime="application/json",
        key="download_batch_json",
    )
    st.download_button(
        "Download batch summary CSV",
        data=summary_df.to_csv(index=False).encode("utf-8"),
        file_name="invoice_batch_summary.csv",
        mime="text/csv",
        key="download_batch_csv",
    )


st.divider()
st.header("Rules vs. Ollama comparison")
st.caption(
    "Run both extractors on the same invoice. Numeric formatting-only differences are separated from substantive mismatches. "
    "Neither agreement nor disagreement alone measures real-world accuracy."
)

compare_file = st.file_uploader(
    "Choose one invoice to compare",
    type=["pdf", "png", "jpg", "jpeg", "webp", "tiff", "bmp", "txt"],
    key="compare_invoice_upload",
)

if st.button("Compare both extractors", type="primary", disabled=compare_file is None, key="compare_both_extractors"):
    compare_tmp = None
    try:
        compare_suffix = Path(compare_file.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=compare_suffix) as tmp:
            tmp.write(compare_file.getvalue())
            compare_tmp = Path(tmp.name)

        with st.spinner("Extracting once, then running both extractors..."):
            comparison_result = compare_invoice_file(compare_tmp)
            rules_json = comparison_result["rules"]
            llm_json = comparison_result["llm"]
            llm_metadata = comparison_result["llm_metadata"]
            st.session_state["invoice_ai_comparison_source"] = comparison_result["source_markdown"]

            for warning in llm_metadata.get("tax_review_warnings", []):
                st.warning(warning)
            st.session_state["invoice_ai_comparison"] = {
                "filename": compare_file.name,
                "rules": rules_json,
                "ollama": llm_json,
                "ollama_metadata": llm_metadata,
                **comparison_result["comparison"],
            }
    except Exception as exc:
        st.error(f"Comparison failed: {exc}")
    finally:
        if compare_tmp is not None:
            try:
                compare_tmp.unlink(missing_ok=True)
            except OSError:
                pass

if "invoice_ai_comparison" in st.session_state:
    comparison = st.session_state["invoice_ai_comparison"]
    st.subheader(f"Comparison: {comparison['filename']}")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Fields compared", comparison["fields_compared"])
    col_b.metric("Substantive differences", comparison["difference_count"])
    col_c.metric("Missing fields", comparison.get("missing_field_count", 0))
    col_d.metric("Formatting-only differences", comparison.get("formatting_difference_count", 0))
    latency = comparison["ollama_metadata"].get("latency_seconds")
    st.caption(f"Ollama latency: {latency} s" if latency is not None else "Ollama latency not reported")
    timing = comparison["ollama_metadata"]
    st.caption(" · ".join(
        f"{field.removesuffix('_seconds')}: {timing[field]}s"
        for field in (
            "ingestion_seconds", "rules_extraction_seconds", "llm_inference_seconds",
            "validation_seconds", "processing_seconds",
        )
        if timing.get(field) is not None
    ))

    if comparison["differences"]:
        st.warning("Substantive mismatches need review against the source document.")
        st.dataframe(pd.DataFrame(comparison["differences"]), use_container_width=True, hide_index=True)
    else:
        st.success("No substantive differences after normalization. This does not prove either output is correct.")

    formatting = comparison.get("formatting_differences", [])
    if formatting:
        with st.expander(f"Formatting-only differences ({len(formatting)})"):
            st.dataframe(pd.DataFrame(formatting), use_container_width=True, hide_index=True)

    missing_fields = comparison.get("missing_fields", [])
    if missing_fields:
        with st.expander(f"Missing fields ({len(missing_fields)})"):
            st.dataframe(pd.DataFrame(missing_fields), use_container_width=True, hide_index=True)
    if comparison["ollama_metadata"].get("tax_review_changes"):
        with st.expander("Tax review corrections"):
            st.dataframe(pd.DataFrame(comparison["ollama_metadata"]["tax_review_changes"]), use_container_width=True, hide_index=True)
    st.info(comparison.get("agreement_note", "Agreement does not establish correctness."))
    with st.expander("Source evidence for review"):
        st.text(st.session_state.get("invoice_ai_comparison_source", ""))

    # Validate both outputs independently, including line-tax duplication safeguards.
    from invoice_ai.validation import validate_invoice
    val_a, val_b = st.columns(2)
    for col, label, payload in (
        (val_a, "Rules-based validation", comparison["rules"]),
        (val_b, "Ollama validation", comparison["ollama"]),
    ):
        with col:
            st.markdown(f"#### {label}")
            result = validate_invoice(payload)
            st.write(f"Status: **{result['status']}**")
            for warning in result["warnings"]:
                st.warning(warning)
            for note in result["notes"]:
                st.info(note)
            for error in result["errors"]:
                st.error(error)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Rules-based output")
        st.json(comparison["rules"])
    with right:
        st.markdown("#### Ollama output")
        st.json(comparison["ollama"])

    st.download_button(
        "Download comparison JSON",
        data=json.dumps(comparison, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name="extractor_comparison.json",
        mime="application/json",
        key="download_extractor_comparison",
    )
