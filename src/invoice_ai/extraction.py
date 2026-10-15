import re
from decimal import Decimal, InvalidOperation

from invoice_ai.schemas import Invoice, InvoiceItem


def find_field(text: str, pattern: str) -> str | None:
    """Return the first captured field, or None when it is not found."""
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def parse_money(value: str | None) -> Decimal | None:
    """Parse an Indian currency amount without inventing missing values."""
    if value is None:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:INR|Rs\.?)\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", "").replace("₹", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_items(markdown: str) -> list[InvoiceItem]:
    """Extract description, quantity, unit price and taxable value from tables."""
    items: list[InvoiceItem] = []

    for line in markdown.splitlines():
        line = line.strip()
        if "|" not in line:
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue

        description = cells[0].strip()
        header_text = " ".join(cells).casefold()

        # Skip table headings and Markdown separator rows.
        if (
            "description" in header_text
            or "quantity" in header_text
            or all(
                re.fullmatch(r"[\s:.-]+", cell or " ")
                for cell in cells
            )
        ):
            continue

        if not description or re.fullmatch(r"[-:\s]+", description):
            continue

        quantity = parse_money(cells[1])
        unit_price = parse_money(cells[2])
        taxable_value = parse_money(cells[3])
        if quantity is None or unit_price is None or taxable_value is None:
            continue

        try:
            items.append(
                InvoiceItem(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    taxable_value=taxable_value,
                    hsn_sac=None,
                    gst_rate=None,
                    cgst_amount=None,
                    sgst_amount=None,
                    igst_amount=None,
                    total_amount=None,
                )
            )
        except (ValueError, TypeError):
            # Leave malformed rows out rather than fabricating their values.
            continue

    return items


def extract_invoice(markdown: str) -> Invoice:
    """Extract invoice fields from normalized document Markdown."""
    text = markdown.replace("\u00a0", " ")

    # Match Vendor/Supplier regardless of whether GSTIN appears before or after it.
    # Stop at the next known label, even if Docling places fields on one line.
    vendor = find_field(
        text,
        r"(?:Vendor|Supplier)\s*:\s*(.*?)"
        r"(?=\s+(?:GSTIN/UIN|GSTIN|Invoice Number|Invoice No\.?|"
        r"Bill No\.?|Invoice Date|Date|Buyer|Billed To)\s*:|[\r\n]|$)",
    )

    gstin = find_field(
        text,
        r"(?:GSTIN/UIN|GSTIN)\s*:\s*([A-Z0-9]{15})"
    )

    invoice_number = find_field(
        text,
        r"(?:Invoice Number|Invoice No\.?|Bill No\.?)\s*:\s*"
        r"([A-Z0-9/-]+)"
    )

    invoice_date = find_field(
        text,
        r"(?:Invoice Date|Date)\s*:\s*(\d{2}/\d{2}/\d{4})"
    )

    buyer = find_field(
        text,
        r"(?:Buyer|Billed To)\s*:\s*(.*?)"
        r"(?=\s+(?:Subtotal|IGST\s*@|CGST\s*@|SGST\s*@)\s*:|"
        r"[\r\n]|$)"
    )

    subtotal_text = find_field(
        text,
        r"Subtotal\s*:\s*(?:INR|Rs\.?)?\s*([\d,]+\.?\d*)"
    )
    cgst_text = find_field(
        text,
        r"CGST\s*@\s*[\d.]+%\s*:\s*(?:INR|Rs\.?)?\s*([\d,]+\.?\d*)"
    )
    sgst_text = find_field(
        text,
        r"SGST\s*@\s*[\d.]+%\s*:\s*(?:INR|Rs\.?)?\s*([\d,]+\.?\d*)"
    )
    igst_text = find_field(
        text,
        r"IGST\s*@\s*[\d.]+%\s*:\s*(?:INR|Rs\.?)?\s*([\d,]+\.?\d*)"
    )
    total_text = find_field(
        text,
        r"Grand Total\s*:\s*(?:INR|Rs\.?)?\s*([\d,]+\.?\d*)"
    )

    return Invoice(
        document_type="gst_invoice",
        vendor_name=vendor,
        vendor_gstin=gstin,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        buyer_name=buyer,
        items=parse_items(text),
        subtotal=parse_money(subtotal_text),
        total_cgst=parse_money(cgst_text) or Decimal("0"),
        total_sgst=parse_money(sgst_text) or Decimal("0"),
        total_igst=parse_money(igst_text) or Decimal("0"),
        grand_total=parse_money(total_text),
    )
