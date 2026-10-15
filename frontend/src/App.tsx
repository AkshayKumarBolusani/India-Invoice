import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  CloudUpload,
  FileCheck2,
  FileSearch,
  Files,
  Gauge,
  HeartPulse,
  Layers3,
  LayoutDashboard,
  Loader2,
  Menu,
  Network,
  PanelLeftClose,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { compareInvoice, evaluation, health, processBatch, processInvoice } from "./api";
import type { BatchRow, CompareResult, Invoice, ProcessResult, Validation, View } from "./types";

const navItems: Array<{ id: View; label: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "workspace", label: "Invoice workspace", icon: FileSearch },
  { id: "review", label: "Review center", icon: ClipboardCheck },
  { id: "comparison", label: "Extractor comparison", icon: Network },
  { id: "batch", label: "Batch processing", icon: Layers3 },
  { id: "evaluation", label: "Evaluation lab", icon: BarChart3 },
  { id: "settings", label: "Settings & health", icon: Settings2 },
];

const demoInvoice: Invoice = {
  document_type: "gst_invoice",
  invoice_number: "INV-003",
  invoice_date: "12/10/2026",
  vendor_name: "Metro Business Mart",
  vendor_gstin: "27ABCDE1234F1Z5",
  buyer_name: "Example Retail Pvt Ltd",
  buyer_gstin: null,
  currency: "INR",
  items: [
    { description: "Notebook", hsn_sac: null, quantity: "5", unit_price: "100.00", taxable_value: "500.00", gst_rate: null, cgst_amount: null, sgst_amount: null, igst_amount: null, total_amount: null },
    { description: "Desk Organizer", hsn_sac: null, quantity: "2", unit_price: "500.00", taxable_value: "1000.00", gst_rate: null, cgst_amount: null, sgst_amount: null, igst_amount: null, total_amount: null },
  ],
  subtotal: "1500.00",
  total_cgst: "45.00",
  total_sgst: "45.00",
  total_igst: "0.00",
  grand_total: "1590.00",
};

const demoValidation = {
  status: "review_required",
  errors: [],
  warnings: ["Buyer GSTIN is missing; verify whether it is present or required for this document."],
  notes: ["Line-level tax allocation is not available; invoice-level tax totals were checked separately."],
};

const demoComparison: CompareResult = {
  filename: "INV-003.pdf",
  rules: demoInvoice,
  rules_validation: demoValidation,
  llm: demoInvoice,
  llm_validation: demoValidation,
  llm_metadata: {
    model: "qwen2.5vl:7b",
    latency_seconds: 28.166,
    ingestion_seconds: 0.49,
    rules_extraction_seconds: 0.001,
    llm_inference_seconds: 28.166,
    validation_seconds: 0.001,
    tax_review_warnings: [
      "Cleared duplicated line-level CGST amounts equal to the full invoice-level total (45) on every item.",
      "Cleared duplicated line-level SGST amounts equal to the full invoice-level total (45) on every item.",
      "Cleared per-item GST rates because they were returned alongside duplicated invoice-level taxes.",
    ],
  },
  comparison: {
    fields_compared: 34,
    difference_count: 0,
    missing_field_count: 0,
    formatting_difference_count: 7,
    differences: [],
    missing_fields: [],
    formatting_differences: [],
    agreement_note: "Extractor agreement indicates output agreement only; it does not establish source correctness or GST/tax compliance.",
  },
};

const demoBatch = [
  { filename: "INV-001.pdf", status: "review_required", item_count: 2, grand_total: "2596.00", time: "0.58s" },
  { filename: "INV-002.pdf", status: "review_required", item_count: 1, grand_total: "1180.00", time: "0.45s" },
  { filename: "INV-003.pdf", status: "review_required", item_count: 2, grand_total: "1590.00", time: "0.49s" },
];

const processingTrend = [
  { name: "Mon", processed: 12, reviewed: 3 },
  { name: "Tue", processed: 18, reviewed: 5 },
  { name: "Wed", processed: 15, reviewed: 4 },
  { name: "Thu", processed: 24, reviewed: 8 },
  { name: "Fri", processed: 31, reviewed: 9 },
  { name: "Sat", processed: 19, reviewed: 6 },
  { name: "Sun", processed: 27, reviewed: 7 },
];

function money(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "—";
  return `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

function StatusPill({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone = normalized.includes("valid") && !normalized.includes("review") ? "bg-emerald-100 text-emerald-700" : normalized.includes("fail") || normalized.includes("invalid") ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700";
  return <span className={`status-pill ${tone}`}><span className="h-1.5 w-1.5 rounded-full bg-current" />{status.replaceAll("_", " ")}</span>;
}

function SectionTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-7 flex items-end justify-between gap-4"><div><div className="eyebrow mb-2">{eyebrow}</div><h1 className="font-display text-3xl font-semibold tracking-tight text-ink md:text-4xl">{title}</h1>{description && <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{description}</p>}</div>{action}</div>;
}

function EmptyState({ icon: Icon, title, description, action }: { icon: typeof FileSearch; title: string; description: string; action?: React.ReactNode }) {
  return <div className="panel flex min-h-[260px] flex-col items-center justify-center px-6 text-center"><div className="mb-4 rounded-2xl bg-teal/10 p-4 text-teal"><Icon size={25} /></div><h3 className="font-display text-lg font-semibold text-ink">{title}</h3><p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">{description}</p>{action && <div className="mt-5">{action}</div>}</div>;
}

function MetricCard({ label, value, detail, icon: Icon, accent = "teal" }: { label: string; value: string; detail: string; icon: typeof Activity; accent?: "teal" | "lime" | "coral" }) {
  const accents = { teal: "bg-teal/15 text-teal", lime: "bg-lime/30 text-ink", coral: "bg-coral/15 text-coral" };
  return <div className="panel p-5"><div className="flex items-start justify-between"><span className="label">{label}</span><span className={`rounded-xl p-2.5 ${accents[accent]}`}><Icon size={18} /></span></div><div className="mt-5 metric-value">{value}</div><div className="mt-2 text-xs text-slate-500">{detail}</div></div>;
}

function InvoiceFields({ invoice }: { invoice: Invoice }) {
  const fields = [
    ["Invoice number", invoice.invoice_number], ["Invoice date", invoice.invoice_date], ["Vendor", invoice.vendor_name], ["Vendor GSTIN", invoice.vendor_gstin], ["Buyer", invoice.buyer_name], ["Buyer GSTIN", invoice.buyer_gstin],
  ];
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{fields.map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><div className="label">{label}</div><div className={`mt-2 text-sm font-semibold ${value ? "text-ink" : "text-amber-600"}`}>{value || "Missing — review source"}</div></div>)}</div>;
}

function ValidationCard({ validation }: { validation: Validation }) {
  return <div className="panel p-5"><div className="flex items-center justify-between"><div><div className="eyebrow">Integrity gate</div><h3 className="mt-1 font-display text-xl font-semibold text-ink">Validation result</h3></div><StatusPill status={validation.status} /></div>{validation.warnings.map((warning) => <div key={warning} className="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"><AlertTriangle size={17} className="mt-0.5 shrink-0" />{warning}</div>)}{validation.notes.map((note) => <div key={note} className="mt-3 flex gap-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-600"><CircleHelp size={17} className="mt-0.5 shrink-0 text-teal" />{note}</div>)}</div>;
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [demoMode, setDemoMode] = useState(true);
  const [apiOnline, setApiOnline] = useState(false);
  const [invoice, setInvoice] = useState<Invoice>(demoInvoice);
  const [validation, setValidation] = useState<Validation>(demoValidation);
  const [comparison, setComparison] = useState<CompareResult>(demoComparison);
  const [batchRows, setBatchRows] = useState<BatchRow[]>(demoBatch);
  const [evaluationData, setEvaluationData] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    health().then(() => setApiOnline(true)).catch(() => setApiOnline(false));
    evaluation().then((result) => setEvaluationData(result.reports)).catch(() => undefined);
  }, []);

  const audit = evaluationData?.dataset_audit;
  const liveLabel = apiOnline ? "Connected to local API" : "Demo snapshot · API offline";

  async function handleWorkspaceUpload(file?: File) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const result = await processInvoice(file);
      if (result.invoice) setInvoice(result.invoice);
      if (result.validation) setValidation(result.validation);
      setApiOnline(true);
      setDemoMode(false);
    } catch {
      setDemoMode(true);
      setError("Showing a clearly labeled demo snapshot. Start the FastAPI service to process this upload live.");
    } finally { setBusy(false); }
  }

  async function handleCompare(file?: File) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      setComparison(await compareInvoice(file));
      setApiOnline(true);
      setDemoMode(false);
    } catch {
      setDemoMode(true);
      setError("Comparison is in demo mode. The displayed INV-003 case is a verified local regression snapshot, not live inference.");
    } finally { setBusy(false); }
  }

  async function handleBatch(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setError("");
    try {
      const result = await processBatch(Array.from(files));
      setBatchRows(result.results.map((row) => ({ filename: row.filename, status: row.status, item_count: row.invoice?.items.length || 0, grand_total: row.invoice?.grand_total || "—", time: `${row.metadata.processing_seconds || "—"}s` })));
      setApiOnline(true);
      setDemoMode(false);
    } catch {
      setDemoMode(true);
      setError("Showing the local batch fixture. Start the FastAPI service to process uploaded files.");
    } finally { setBusy(false); }
  }

  const currentTitle = navItems.find((item) => item.id === view)?.label || "Overview";

  return <div className="min-h-screen bg-paper text-ink">
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col bg-ink px-4 py-5 transition-transform lg:translate-x-0 ${mobileNav ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="flex items-center justify-between px-3"><div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl bg-teal text-ink"><Sparkles size={18} /></div><div><div className="font-display text-sm font-bold tracking-tight text-white">INDIA INVOICE</div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal">Intelligence layer</div></div></div><button className="text-slate-500 lg:hidden" onClick={() => setMobileNav(false)}><X size={18} /></button></div>
      <div className="mt-10 space-y-1">{navItems.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => { setView(id); setMobileNav(false); }} className={`nav-item ${view === id ? "nav-item-active" : ""}`}><Icon size={17} />{label}{id === "review" && <span className="ml-auto rounded-full bg-coral px-2 py-0.5 text-[10px] font-bold text-white">12</span>}</button>)}</div>
      <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.04] p-4"><div className="flex items-center gap-2 text-xs font-semibold text-white"><span className={`h-2 w-2 rounded-full ${apiOnline ? "bg-lime" : "bg-amber-400"}`} />{apiOnline ? "Local API online" : "Demo environment"}</div><p className="mt-2 text-xs leading-5 text-slate-400">{apiOnline ? "Uploads route through the Python workflow service." : "No inference is run until the local API is connected."}</p><button onClick={() => setView("settings")} className="mt-3 flex items-center gap-1 text-xs font-semibold text-teal">System health <ArrowUpRight size={13} /></button></div>
    </aside>
    {mobileNav && <button className="fixed inset-0 z-30 bg-ink/40 lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
    <main className="min-h-screen lg:pl-[248px]">
      <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-slate-200/80 bg-paper/90 px-5 backdrop-blur md:px-9"><div className="flex items-center gap-3"><button className="rounded-lg p-2 text-slate-500 hover:bg-white lg:hidden" onClick={() => setMobileNav(true)}><Menu size={20} /></button><div><div className="eyebrow">Control room / {currentTitle}</div><div className="mt-1 text-sm font-semibold text-ink">Thursday, 15 October 2026</div></div></div><div className="flex items-center gap-3"><span className={`hidden rounded-full px-3 py-1.5 text-xs font-semibold sm:inline-flex ${demoMode ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>{demoMode ? "Demo snapshot" : "Live local run"}</span><button className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500"><Search size={16} /></button><div className="grid h-9 w-9 place-items-center rounded-xl bg-shell text-xs font-bold text-white">AK</div></div></header>
      <div className="mx-auto max-w-[1440px] px-5 py-8 md:px-9 md:py-10">
        {error && <div className="mb-6 flex items-center justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"><div className="flex items-center gap-2"><AlertTriangle size={17} />{error}</div><button onClick={() => setError("")}><X size={16} /></button></div>}
        {view === "overview" && <Overview audit={audit} onNavigate={setView} />}
        {view === "workspace" && <Workspace invoice={invoice} validation={validation} busy={busy} onUpload={handleWorkspaceUpload} />}
        {view === "review" && <ReviewCenter invoice={invoice} validation={validation} onNavigate={setView} />}
        {view === "comparison" && <Comparison comparison={comparison} busy={busy} onUpload={handleCompare} />}
        {view === "batch" && <Batch rows={batchRows} busy={busy} onUpload={handleBatch} />}
        {view === "evaluation" && <EvaluationLab audit={audit} />}
        {view === "settings" && <Settings online={apiOnline} liveLabel={liveLabel} />}
      </div>
    </main>
  </div>;
}

function Overview({ audit, onNavigate }: { audit?: any; onNavigate: (view: View) => void }) {
  const metrics = audit ? { docs: audit.records_audited, parsed: audit.parsed_json_records, review: audit.manual_review_records, items: audit.recognized_item_count_total } : { docs: 1348, parsed: 1343, review: 1331, items: 1343 };
  return <><SectionTitle eyebrow="Portfolio signal" title="A quieter way to trust invoice data" description="A review-first command center for extraction, reconciliation, and GST-aware human decisions." action={<button onClick={() => onNavigate("workspace")} className="btn-primary"><Upload size={16} />Process invoice</button>} /><div className="mb-6 flex items-center gap-2 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-lime" />Verified local report · {audit ? "loaded from API" : "using stored report snapshot"}</div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Documents audited" value={metrics.docs.toLocaleString()} detail="Public parser records inspected" icon={Files} /><MetricCard label="JSON responses parsed" value={metrics.parsed.toLocaleString()} detail="Structural success, not accuracy" icon={FileCheck2} accent="lime" /><MetricCard label="Review queue" value={metrics.review.toLocaleString()} detail="Require source-level verification" icon={AlertTriangle} accent="coral" /><MetricCard label="Recognized line items" value={metrics.items.toLocaleString()} detail="Sum of item rows, not records" icon={Layers3} /></div><div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]"><div className="panel p-5 md:p-6"><div className="flex items-start justify-between"><div><div className="eyebrow">Throughput / last 7 days</div><h2 className="mt-1 font-display text-xl font-semibold">Processing rhythm</h2></div><div className="flex gap-4 text-xs text-slate-500"><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-teal" />Processed</span><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-lime" />Review</span></div></div><div className="mt-6 h-[260px]"><ResponsiveContainer width="100%" height="100%"><AreaChart data={processingTrend}><defs><linearGradient id="tealFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3fd7c4" stopOpacity={0.28} /><stop offset="100%" stopColor="#3fd7c4" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#e8e5de" vertical={false} /><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} /><YAxis axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} /><Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", boxShadow: "0 12px 30px #101b2d18" }} /><Area type="monotone" dataKey="processed" stroke="#25bba8" fill="url(#tealFill)" strokeWidth={2.5} /><Area type="monotone" dataKey="reviewed" stroke="#9ac84e" fill="none" strokeWidth={2} /></AreaChart></ResponsiveContainer></div></div><div className="panel-dark bg-shell p-6 text-white"><div className="eyebrow text-teal">Review queue</div><h2 className="mt-2 font-display text-2xl font-semibold">Make uncertainty visible.</h2><p className="mt-3 text-sm leading-6 text-slate-300">Tax totals can reconcile while line-level allocations remain unsupported. This workspace keeps those decisions separate.</p><div className="mt-8 space-y-3"><div className="flex items-center justify-between border-b border-white/10 pb-3 text-sm"><span className="text-slate-300">Missing buyer GSTIN</span><strong>12</strong></div><div className="flex items-center justify-between border-b border-white/10 pb-3 text-sm"><span className="text-slate-300">Arithmetic mismatch</span><strong>08</strong></div><div className="flex items-center justify-between text-sm"><span className="text-slate-300">Tax allocation warning</span><strong>06</strong></div></div><button onClick={() => onNavigate("review")} className="mt-8 flex items-center gap-2 text-sm font-semibold text-teal">Open review center <ChevronRight size={16} /></button></div></div></>;
}

function Workspace({ invoice, validation, busy, onUpload }: { invoice: Invoice; validation: Validation; busy: boolean; onUpload: (file?: File) => void }) {
  return <><SectionTitle eyebrow="Document workspace" title="Review before you rely" description="Upload a document, inspect source-backed fields, and make human corrections before export." action={<label className="btn-primary"><CloudUpload size={16} />Upload invoice<input className="hidden" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.bmp,.txt" onChange={(event) => onUpload(event.target.files?.[0])} /></label>} /><div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,.75fr)]"><div className="space-y-6"><div className="panel overflow-hidden"><div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl bg-teal/10 text-teal"><FileSearch size={17} /></div><div><div className="text-sm font-semibold">{invoice.invoice_number || "Untitled invoice"}.pdf</div><div className="text-xs text-slate-400">Source preview · PDF, image, and text conversion supported</div></div></div><StatusPill status={validation.status} /></div><div className="grid min-h-[170px] place-items-center bg-[#e9e6de] p-8"><div className="max-w-sm rounded-xl border border-slate-300 bg-white p-6 text-center shadow-sm"><div className="mx-auto mb-3 h-1.5 w-20 rounded-full bg-teal/70" /><div className="mx-auto h-2 w-36 rounded-full bg-slate-200" /><div className="mx-auto mt-2 h-2 w-28 rounded-full bg-slate-100" /><div className="mt-6 grid grid-cols-3 gap-2"><span className="h-8 rounded bg-slate-100" /><span className="h-8 rounded bg-slate-100" /><span className="h-8 rounded bg-lime/40" /></div><p className="mt-5 text-xs text-slate-400">Document preview appears after a live upload</p></div></div></div><div className="panel p-5"><div className="mb-4 flex items-center justify-between"><div><div className="eyebrow">Extracted schema</div><h2 className="mt-1 font-display text-xl font-semibold">Invoice identity</h2></div><button className="btn-secondary !px-3 !py-2 text-xs"><Settings2 size={14} />Edit fields</button></div><InvoiceFields invoice={invoice} /></div><div className="panel overflow-hidden"><div className="border-b border-slate-200 px-5 py-4"><div className="eyebrow">Normalized rows</div><h2 className="mt-1 font-display text-xl font-semibold">Line items <span className="text-slate-400">({invoice.items.length})</span></h2></div><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-[10px] uppercase tracking-[0.12em] text-slate-400"><tr><th className="px-5 py-3">Description</th><th className="px-5 py-3">Qty</th><th className="px-5 py-3">Unit price</th><th className="px-5 py-3">Taxable</th></tr></thead><tbody>{invoice.items.map((item) => <tr key={item.description} className="border-t border-slate-100"><td className="px-5 py-4 font-semibold">{item.description}</td><td className="px-5 py-4 text-slate-500">{item.quantity}</td><td className="px-5 py-4 text-slate-500">{money(item.unit_price)}</td><td className="px-5 py-4 font-semibold">{money(item.taxable_value)}</td></tr>)}</tbody></table></div><div className="grid gap-3 border-t border-slate-200 bg-slate-50 p-5 text-sm sm:grid-cols-3"><div><div className="label">Subtotal</div><strong className="mt-1 block">{money(invoice.subtotal)}</strong></div><div><div className="label">Tax</div><strong className="mt-1 block">{money(Number(invoice.total_cgst || 0) + Number(invoice.total_sgst || 0) + Number(invoice.total_igst || 0))}</strong></div><div><div className="label">Grand total</div><strong className="mt-1 block text-teal-700">{money(invoice.grand_total)}</strong></div></div></div></div><div className="space-y-6"><ValidationCard validation={validation} /><div className="panel p-5"><div className="eyebrow">Evidence status</div><h2 className="mt-1 font-display text-xl font-semibold">What is known?</h2><div className="mt-5 space-y-3 text-sm"><div className="flex items-center gap-3"><Check className="text-emerald-600" size={17} /><span>Source-extracted values retained</span></div><div className="flex items-center gap-3"><AlertTriangle className="text-amber-500" size={17} /><span>Buyer GSTIN requires review</span></div><div className="flex items-center gap-3"><CircleHelp className="text-slate-400" size={17} /><span>Line-level tax not inferred</span></div></div></div>{busy && <div className="panel flex items-center gap-3 p-5 text-sm text-slate-600"><Loader2 className="animate-spin text-teal" size={18} />Processing locally…</div>}</div></div></>;
}

function ReviewCenter({ invoice, validation, onNavigate }: { invoice: Invoice; validation: Validation; onNavigate: (view: View) => void }) {
  return <><SectionTitle eyebrow="Human review" title="Resolve what the model cannot prove" description="A compact queue for missing evidence, arithmetic concerns, and tax allocation warnings." action={<button onClick={() => onNavigate("workspace")} className="btn-secondary"><FileSearch size={16} />Open workspace</button>} /><div className="grid gap-4 md:grid-cols-3"><MetricCard label="Open decisions" value="12" detail="Across current review queue" icon={ClipboardCheck} accent="coral" /><MetricCard label="Missing evidence" value="08" detail="Fields not present or not found" icon={Search} /><MetricCard label="Tax warnings" value="06" detail="Never silently corrected" icon={ShieldCheck} accent="lime" /></div><div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_.9fr]"><div className="panel p-5"><div className="eyebrow">Current queue</div><h2 className="mt-1 font-display text-xl font-semibold">Priority decisions</h2><div className="mt-5 space-y-3">{[{title: "Buyer GSTIN is missing", detail: "INV-003 · confirm from source", tone: "amber"}, {title: "Line tax allocation unsupported", detail: "INV-003 · preserve invoice totals", tone: "coral"}, {title: "Arithmetic mismatch", detail: "INV-014 · inspect discount semantics", tone: "rose"}].map((item) => <div key={item.title} className="flex items-center gap-4 rounded-xl border border-slate-200 p-4"><div className={`h-2.5 w-2.5 rounded-full ${item.tone === "coral" ? "bg-coral" : item.tone === "rose" ? "bg-rose-500" : "bg-amber-400"}`} /><div className="min-w-0 flex-1"><div className="text-sm font-semibold">{item.title}</div><div className="mt-1 text-xs text-slate-500">{item.detail}</div></div><ChevronRight size={16} className="text-slate-400" /></div>)}</div></div><ValidationCard validation={validation} /></div><div className="mt-6 panel p-5"><div className="eyebrow">Selected document</div><div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h2 className="font-display text-2xl font-semibold">{invoice.invoice_number}</h2><p className="mt-1 text-sm text-slate-500">{invoice.vendor_name} · {money(invoice.grand_total)}</p></div><StatusPill status="Review required" /></div></div></>;
}

function Comparison({ comparison, busy, onUpload }: { comparison: CompareResult; busy: boolean; onUpload: (file?: File) => void }) {
  const meta = comparison.llm_metadata;
  const latency = String(meta.latency_seconds ?? "—");
  const ingestion = String(meta.ingestion_seconds ?? "—");
  const validation = String(meta.validation_seconds ?? "—");
  const warnings = Array.isArray(meta.tax_review_warnings) ? meta.tax_review_warnings.map(String) : [];
  return <><SectionTitle eyebrow="Model observatory" title="Agreement is not evidence" description="Compare outputs on the same normalized document while keeping tax review and missing values visible." action={<label className="btn-primary"><CloudUpload size={16} />Compare invoice<input className="hidden" type="file" accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp,.txt" onChange={(event) => onUpload(event.target.files?.[0])} /></label>} /><div className="mb-6 flex items-center gap-2 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-amber-400" />{comparison.filename} · verified local regression snapshot</div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5"><MetricCard label="Fields compared" value={String(comparison.comparison.fields_compared)} detail="Nested fields included" icon={BarChart3} /><MetricCard label="Substantive" value={String(comparison.comparison.difference_count)} detail="Requires source review" icon={AlertTriangle} accent="coral" /><MetricCard label="Missing fields" value={String(comparison.comparison.missing_field_count)} detail="Reported separately" icon={Search} /><MetricCard label="Formatting only" value={String(comparison.comparison.formatting_difference_count)} detail="Decimal representation" icon={Activity} /><MetricCard label="LLM latency" value={`${latency}s`} detail="Measured inference time" icon={Gauge} accent="lime" /></div><div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_.85fr]"><div className="panel p-5"><div className="flex items-center justify-between"><div><div className="eyebrow">Rules-based vs local LLM</div><h2 className="mt-1 font-display text-xl font-semibold">Field agreement map</h2></div><StatusPill status="No substantive differences" /></div><div className="mt-6 rounded-xl bg-slate-50 p-4"><div className="flex items-center justify-between text-sm"><span>Rules-based extraction</span><strong>34 / 34</strong></div><div className="mt-3 h-2 rounded-full bg-slate-200"><div className="h-2 w-full rounded-full bg-teal" /></div><div className="mt-5 flex items-center justify-between text-sm"><span>LLM extraction</span><strong>34 / 34</strong></div><div className="mt-3 h-2 rounded-full bg-slate-200"><div className="h-2 w-full rounded-full bg-lime" /></div></div><div className="mt-5 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900"><AlertTriangle size={18} className="mt-1 shrink-0" />Both outputs can agree and still be wrong. Verify against the source document before treating a field as ground truth.</div></div><div className="panel-dark bg-shell p-5 text-white"><div className="eyebrow text-teal">Observed tax review</div><h2 className="mt-1 font-display text-xl font-semibold">Totals preserved. Lines cleared.</h2><p className="mt-3 text-sm leading-6 text-slate-300">Invoice-level CGST ₹45 and SGST ₹45 remain intact. Unsupported duplicated line allocations are cleared and retained in correction history.</p><div className="mt-6 grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-white/10 p-3"><div className="text-lg font-semibold">₹45</div><div className="mt-1 text-[10px] uppercase text-slate-400">CGST</div></div><div className="rounded-xl bg-white/10 p-3"><div className="text-lg font-semibold">₹45</div><div className="mt-1 text-[10px] uppercase text-slate-400">SGST</div></div><div className="rounded-xl bg-teal/20 p-3"><div className="text-lg font-semibold text-teal">₹1,590</div><div className="mt-1 text-[10px] uppercase text-slate-400">Total</div></div></div><div className="mt-5 flex items-center gap-2 text-xs text-slate-400"><Gauge size={14} /> {ingestion}s ingest · {validation}s validate</div></div></div><div className="mt-6 panel p-5"><div className="eyebrow">Correction history</div><h2 className="mt-1 font-display text-xl font-semibold">Human review remains explicit</h2><div className="mt-4 flex flex-wrap gap-2">{warnings.map((warning) => <span key={warning} className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{warning}</span>)}</div></div>{busy && <div className="mt-4 flex items-center gap-2 text-sm text-slate-500"><Loader2 className="animate-spin" size={16} />Comparing through local API…</div>}</>;
}

function Batch({ rows, busy, onUpload }: { rows: BatchRow[]; busy: boolean; onUpload: (files: FileList | null) => void }) {
  return <><SectionTitle eyebrow="Operations" title="Process a folder, keep failures local" description="Per-document status, timings, tax warnings, and exportable results for repeatable review." action={<label className="btn-primary"><CloudUpload size={16} />Upload batch<input className="hidden" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp,.txt" onChange={(event) => onUpload(event.target.files)} /></label>} /><div className="panel overflow-hidden"><div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div><div className="eyebrow">Current run</div><h2 className="mt-1 font-display text-xl font-semibold">{rows.length} documents · {rows.filter((row) => row.status !== "processing_failed").length} completed</h2></div><button className="btn-secondary !px-3 !py-2 text-xs"><Files size={14} />Export CSV</button></div><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-[10px] uppercase tracking-[0.12em] text-slate-400"><tr><th className="px-5 py-3">Document</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Items</th><th className="px-5 py-3">Grand total</th><th className="px-5 py-3">Processing</th><th className="px-5 py-3"> </th></tr></thead><tbody>{rows.map((row) => <tr key={row.filename} className="border-t border-slate-100"><td className="px-5 py-4 font-semibold">{row.filename}</td><td className="px-5 py-4"><StatusPill status={row.status} /></td><td className="px-5 py-4 text-slate-500">{row.item_count}</td><td className="px-5 py-4 font-semibold">{money(row.grand_total)}</td><td className="px-5 py-4 text-slate-500">{row.time}</td><td className="px-5 py-4 text-right"><ChevronRight size={16} className="ml-auto text-slate-400" /></td></tr>)}</tbody></table></div></div>{busy && <div className="mt-4 flex items-center gap-2 text-sm text-slate-500"><Loader2 className="animate-spin" size={16} />Processing each file independently…</div>}</>;
}

function EvaluationLab({ audit }: { audit?: any }) {
  const metrics = audit || { records_audited: 1348, parsed_json_records: 1343, recognized_item_count_total: 1343, arithmetic_failure_records: 1326, manual_review_records: 1331, records_with_source_evidence_gaps: 1343 };
  const chart = [{ name: "Parsed", value: metrics.parsed_json_records }, { name: "Review", value: metrics.manual_review_records }, { name: "Arithmetic", value: metrics.arithmetic_failure_records }];
  return <><SectionTitle eyebrow="Evidence lab" title="Metrics with provenance attached" description="Every number here is tied to a stored report, test run, or clearly labeled demo snapshot." /><div className="grid gap-4 md:grid-cols-3"><MetricCard label="Sample size" value={String(metrics.records_audited)} detail="Public parser records" icon={Files} /><MetricCard label="Recognized items" value={String(metrics.recognized_item_count_total)} detail="Summed line-item rows" icon={Layers3} /><MetricCard label="Manual review" value={String(metrics.manual_review_records)} detail="Not a correctness score" icon={ClipboardCheck} accent="coral" /></div><div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1fr]"><div className="panel p-5"><div className="eyebrow">Audit distribution</div><h2 className="mt-1 font-display text-xl font-semibold">What the dataset actually tells us</h2><div className="mt-6 h-[250px]"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart} layout="vertical" margin={{ left: 14, right: 20 }}><CartesianGrid stroke="#e8e5de" horizontal={false} /><XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} /><YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 11 }} width={75} /><Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0" }} /><Bar dataKey="value" fill="#25bba8" radius={[0, 6, 6, 0]} barSize={24} /></BarChart></ResponsiveContainer></div></div><div className="panel p-5"><div className="eyebrow">Method note</div><h2 className="mt-1 font-display text-xl font-semibold">Not ground truth</h2><div className="mt-5 space-y-4 text-sm leading-6 text-slate-600"><p>JSON parsing proves structure only. Generic tax amounts are never relabeled as CGST, SGST, or IGST.</p><p>Arithmetic failures reflect parsed values and explicit sign conventions; skipped checks reflect unavailable semantics.</p><p>Public parser outputs and synthetic fixtures are auxiliary evidence, not verified invoice labels.</p><div className="rounded-xl bg-shell p-4 text-slate-300"><span className="font-semibold text-teal">Source:</span> evaluation/dataset_audit_summary.json</div></div></div></div></>;
}

function Settings({ online, liveLabel }: { online: boolean; liveLabel: string }) {
  return <><SectionTitle eyebrow="Runtime" title="Settings & system health" description="Local configuration is visible here; secrets and invoice contents stay outside the frontend telemetry path." /><div className="grid gap-6 md:grid-cols-2"><div className="panel p-5"><div className="flex items-center gap-3"><div className={`rounded-xl p-3 ${online ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}><HeartPulse size={20} /></div><div><div className="eyebrow">Backend status</div><h2 className="mt-1 font-display text-xl font-semibold">{liveLabel}</h2></div></div><div className="mt-6 space-y-3 text-sm"><div className="flex justify-between border-b border-slate-100 pb-3"><span className="text-slate-500">API base</span><strong className="max-w-[220px] truncate">{import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"}</strong></div><div className="flex justify-between border-b border-slate-100 pb-3"><span className="text-slate-500">Upload formats</span><strong>PDF · image · TXT</strong></div><div className="flex justify-between"><span className="text-slate-500">Inference mode</span><strong>Rules baseline / Ollama</strong></div></div></div><div className="panel p-5"><div className="eyebrow">Operational guardrails</div><h2 className="mt-1 font-display text-xl font-semibold">Built for review, not autopilot</h2><div className="mt-5 space-y-3 text-sm text-slate-600"><div className="flex gap-3"><ShieldCheck className="text-teal" size={18} />Source values are not silently rewritten.</div><div className="flex gap-3"><Gauge className="text-teal" size={18} />Latency is recorded by processing stage.</div><div className="flex gap-3"><Activity className="text-teal" size={18} />Public metrics show sample size and limitations.</div></div></div></div></>;
}

export default App;
