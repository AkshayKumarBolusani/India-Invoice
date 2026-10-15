export type View = "overview" | "workspace" | "review" | "comparison" | "batch" | "evaluation" | "settings";

export type BatchRow = {
  filename: string;
  status: string;
  item_count: number;
  grand_total: string | number | null;
  time: string;
};

export type InvoiceItem = {
  description: string;
  hsn_sac?: string | null;
  quantity: string | number;
  unit_price: string | number;
  taxable_value: string | number;
  gst_rate?: string | number | null;
  cgst_amount?: string | number | null;
  sgst_amount?: string | number | null;
  igst_amount?: string | number | null;
  total_amount?: string | number | null;
};

export type Invoice = {
  document_type: string;
  invoice_number?: string | null;
  invoice_date?: string | null;
  vendor_name?: string | null;
  vendor_gstin?: string | null;
  buyer_name?: string | null;
  buyer_gstin?: string | null;
  currency: string;
  items: InvoiceItem[];
  subtotal?: string | number | null;
  total_cgst?: string | number | null;
  total_sgst?: string | number | null;
  total_igst?: string | number | null;
  grand_total?: string | number | null;
};

export type Validation = {
  status: string;
  errors: string[];
  warnings: string[];
  notes: string[];
  checks?: Record<string, string | null>;
};

export type ProcessResult = {
  filename: string;
  status: string;
  invoice: Invoice | null;
  validation: Validation | null;
  metadata: Record<string, unknown>;
  error?: string | null;
};

export type CompareResult = {
  filename: string;
  rules: Invoice;
  rules_validation: Validation;
  llm: Invoice;
  llm_validation: Validation;
  llm_metadata: Record<string, unknown>;
  comparison: {
    fields_compared: number;
    difference_count: number;
    missing_field_count: number;
    formatting_difference_count: number;
    differences: Array<Record<string, unknown>>;
    missing_fields: Array<Record<string, unknown>>;
    formatting_differences: Array<Record<string, unknown>>;
    agreement_note: string;
  };
};
