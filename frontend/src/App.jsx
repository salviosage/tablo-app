import { useState, useCallback } from "react";
import { uploadFiles, processJob } from "./api";
import { Upload, FileText, AlertTriangle, CheckCircle2, Clock, DollarSign, TrendingUp, BarChart3, Shield, Lightbulb, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const COLORS = ["#0d9488","#0891b2","#6366f1","#d946ef","#f59e0b","#ef4444","#22c55e","#64748b"];
const fmt = (n) => `$${Math.abs(n).toLocaleString("en-CA",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

function UploadZone({ onResult }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState(null);

  const handle = useCallback(async (files) => {
    if (!files.length) return;
    setLoading(true); setError(null);
    try {
      setStage("Uploading & classifying files…");
      const upload = await uploadFiles(files);
      setStage(`Extracting data from ${upload.file_count} files (OCR, PDF, XLSX)…`);
      const result = await processJob(upload.job_id);
      onResult({ ...result, job_id: upload.job_id, upload });
    } catch (e) { setError(e.response?.data?.detail || e.message); }
    finally { setLoading(false); setStage(""); }
  }, [onResult]);

  return (
    <div className="max-w-2xl mx-auto">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handle(Array.from(e.dataTransfer.files)); }}
        className={`border-2 border-dashed rounded-2xl p-16 text-center transition-all cursor-pointer ${dragging ? "border-teal-400 bg-teal-50/50" : "border-gray-300 hover:border-teal-400 hover:bg-gray-50"}`}
        onClick={() => {
          if (loading) return;
          const input = document.createElement("input");
          input.type = "file"; input.multiple = true;
          input.accept = ".zip,.pdf,.xlsx,.csv,.txt,.png,.jpg,.jpeg";
          input.onchange = (e) => handle(Array.from(e.target.files));
          input.click();
        }}
      >
        {loading ? (
          <div className="space-y-4">
            <Loader2 className="w-12 h-12 text-teal-600 mx-auto animate-spin" />
            <p className="text-teal-700 font-medium">{stage}</p>
            <p className="text-sm text-gray-400">This may take a moment for OCR…</p>
          </div>
        ) : (
          <div className="space-y-4">
            <Upload className="w-12 h-12 text-gray-400 mx-auto" />
            <div><p className="text-lg font-medium text-gray-700">Drop your shoebox here</p>
            <p className="text-sm text-gray-400 mt-1">ZIP, PDF, XLSX, images, text — we handle the mess</p></div>
          </div>
        )}
      </div>
      {error && <div className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">{error}</div>}
    </div>
  );
}

function Stat({ label, value, sub, icon: Icon, color = "text-gray-900" }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-1">{Icon && <Icon className="w-4 h-4 text-gray-400" />}<span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span></div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function OverviewTab({ n, r }) {
  const t = n.totals;
  const catData = Object.entries(t.expenses_by_category||{}).map(([name,value])=>({name,value:Math.round(value*100)/100})).sort((a,b)=>b.value-a.value);
  const clientData = Object.entries(t.revenue_by_client||{}).map(([name,value])=>({name,value})).sort((a,b)=>b.value-a.value);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Net Income" value={fmt(t.net_income)} icon={TrendingUp} color="text-emerald-700" />
        <Stat label="Revenue" value={fmt(t.gross_revenue)} icon={DollarSign} sub={`${fmt(t.outstanding_revenue)} outstanding`} />
        <Stat label="Expenses" value={fmt(t.net_expenses)} icon={BarChart3} sub={`${fmt(t.total_refunds)} refunded`} />
        <Stat label="Avg Payment" value={`${t.avg_payment_days}d`} icon={Clock} sub={`${t.invoices_outstanding} outstanding`} />
      </div>
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Expenses by Category</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart><Pie data={catData} cx="50%" cy="50%" innerRadius={45} outerRadius={80} paddingAngle={2} dataKey="value">
              {catData.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip formatter={(v)=>fmt(v)}/></PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-2 gap-1 mt-2">{catData.map((c,i)=>(
            <div key={c.name} className="flex items-center gap-2 text-xs text-gray-600">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{background:COLORS[i%COLORS.length]}}/><span className="truncate">{c.name}</span><span className="ml-auto text-gray-400">{fmt(c.value)}</span>
            </div>))}</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Revenue by Client</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={clientData} layout="vertical" barSize={18}>
              <XAxis type="number" tick={{fontSize:11}} tickFormatter={(v)=>`$${(v/1000).toFixed(0)}k`}/>
              <YAxis type="category" dataKey="name" tick={{fontSize:11}} width={130}/><Tooltip formatter={(v)=>fmt(v)}/>
              <Bar dataKey="value" radius={[0,4,4,0]}>{clientData.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      {r.data_quality && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4"><h3 className="text-sm font-semibold text-gray-700">Data Quality Score</h3>
            <span className={`text-2xl font-bold ${r.data_quality.score>=70?"text-emerald-600":r.data_quality.score>=40?"text-amber-600":"text-red-600"}`}>{r.data_quality.score}/100</span></div>
          <div className="w-full bg-gray-100 rounded-full h-2 mb-4"><div className={`h-2 rounded-full ${r.data_quality.score>=70?"bg-emerald-500":r.data_quality.score>=40?"bg-amber-500":"bg-red-500"}`} style={{width:`${r.data_quality.score}%`}}/></div>
          {r.data_quality.issues.length>0&&<div className="space-y-1">{r.data_quality.issues.map((issue,i)=>(<div key={i} className="flex items-start gap-2 text-sm text-gray-600"><AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5"/><span>{issue}</span></div>))}</div>}
        </div>
      )}
    </div>
  );
}

function ExpensesTab({ n }) {
  const [filter, setFilter] = useState("all");
  const expenses = n.expenses.filter((e) => filter==="flagged"?(e.is_personal||e.is_duplicate||e.is_refund):filter==="business"?(!e.is_personal&&!e.is_duplicate&&!e.is_refund):true);
  const counts = { all:n.expenses.length, business:n.expenses.filter(e=>!e.is_personal&&!e.is_duplicate&&!e.is_refund).length, flagged:n.expenses.filter(e=>e.is_personal||e.is_duplicate||e.is_refund).length };

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="flex gap-1 p-3 border-b border-gray-100">{Object.entries(counts).map(([key,count])=>(
        <button key={key} onClick={()=>setFilter(key)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${filter===key?"bg-teal-700 text-white":"text-gray-500 hover:bg-gray-100"}`}>{key} ({count})</button>))}</div>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-gray-100 text-left">
        <th className="px-4 py-3 text-xs text-gray-500 font-semibold">Date</th><th className="px-4 py-3 text-xs text-gray-500 font-semibold">Description</th>
        <th className="px-4 py-3 text-xs text-gray-500 font-semibold text-right">Amount</th><th className="px-4 py-3 text-xs text-gray-500 font-semibold">Category</th>
        <th className="px-4 py-3 text-xs text-gray-500 font-semibold">Flags</th></tr></thead>
        <tbody>{expenses.map((e,i)=>(<tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
          <td className="px-4 py-2.5 text-gray-500 font-mono text-xs whitespace-nowrap">{e.date}</td>
          <td className="px-4 py-2.5 text-gray-800 max-w-[250px] truncate">{e.description}</td>
          <td className={`px-4 py-2.5 text-right font-mono font-semibold ${e.amount<0?"text-emerald-600":"text-gray-900"}`}>{e.amount<0?`(${fmt(e.amount)})`:fmt(e.amount)}</td>
          <td className="px-4 py-2.5"><span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600">{e.category}</span></td>
          <td className="px-4 py-2.5"><div className="flex gap-1">
            {e.is_personal&&<span className="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium">Personal</span>}
            {e.is_duplicate&&<span className="text-xs px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 font-medium">Duplicate</span>}
            {e.is_refund&&<span className="text-xs px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-medium">Refund</span>}
          </div></td></tr>))}</tbody></table></div>
    </div>
  );
}

function InvoicesTab({ n }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-gray-100 text-left">
      <th className="px-4 py-3 text-xs text-gray-500 font-semibold">Client</th><th className="px-4 py-3 text-xs text-gray-500 font-semibold">Description</th>
      <th className="px-4 py-3 text-xs text-gray-500 font-semibold text-right">Amount</th><th className="px-4 py-3 text-xs text-gray-500 font-semibold">Sent</th>
      <th className="px-4 py-3 text-xs text-gray-500 font-semibold">Paid</th><th className="px-4 py-3 text-xs text-gray-500 font-semibold">Status</th>
      <th className="px-4 py-3 text-xs text-gray-500 font-semibold text-right">Days</th></tr></thead>
      <tbody>{n.invoices.map((inv,i)=>(<tr key={i} className={`border-b border-gray-50 ${inv.status==="Outstanding"?"bg-amber-50/30":""}`}>
        <td className="px-4 py-2.5 font-medium text-gray-800">{inv.client}</td>
        <td className="px-4 py-2.5 text-gray-500 max-w-[200px] truncate">{inv.description}</td>
        <td className="px-4 py-2.5 text-right font-mono font-semibold">{fmt(inv.amount)}</td>
        <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">{inv.date_sent}</td>
        <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">{inv.date_paid||"—"}</td>
        <td className="px-4 py-2.5"><span className={`text-xs px-2 py-0.5 rounded font-medium ${inv.status==="Paid"?"bg-emerald-50 text-emerald-600":"bg-amber-50 text-amber-600"}`}>{inv.status}</span></td>
        <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-400">{inv.days_to_payment!=null?`${inv.days_to_payment}d`:"—"}</td>
      </tr>))}</tbody></table></div>
  );
}

function Collapsible({ title, count, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <button onClick={()=>setOpen(!open)} className="w-full flex items-center gap-3 px-5 py-4 text-left">
        {open?<ChevronDown className="w-4 h-4 text-gray-400"/>:<ChevronRight className="w-4 h-4 text-gray-400"/>}
        <span className="text-sm font-semibold text-gray-700">{title}</span>
        {count!=null&&<span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">{count}</span>}
      </button>
      {open&&<div className="px-5 pb-5 border-t border-gray-100 pt-4">{children}</div>}
    </div>
  );
}

function ReconcileTab({ r }) {
  return (
    <div className="space-y-4">
      <Collapsible title="Refund Matches" count={r.refund_matches.length} defaultOpen>
        {r.refund_matches.length===0?<p className="text-sm text-gray-400">No refunds to match</p>:
        <div className="space-y-3">{r.refund_matches.map((m,i)=>(
          <div key={i} className="flex items-center gap-4 text-sm bg-gray-50 rounded-lg p-3">
            <div className="flex-1"><p className="text-gray-700">{m.refund_description}</p><p className="text-xs text-gray-400">{m.refund_date} · Refund {fmt(m.refund_amount)}</p></div>
            <span className="text-gray-300">→</span>
            <div className="flex-1"><p className="text-gray-700">{m.original_description}</p><p className="text-xs text-gray-400">{m.original_date} · Original {fmt(m.original_amount)}</p></div>
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${m.match_confidence==="high"?"bg-emerald-50 text-emerald-600":m.match_confidence==="medium"?"bg-amber-50 text-amber-600":"bg-gray-100 text-gray-500"}`}>{m.match_confidence}</span>
          </div>))}</div>}
      </Collapsible>
      <Collapsible title="Overdue Invoices" count={r.overdue_invoices.length} defaultOpen>
        {r.overdue_invoices.length===0?<p className="text-sm text-gray-400">All invoices paid</p>:
        <div className="space-y-2">{r.overdue_invoices.map((o,i)=>(
          <div key={i} className="flex items-center gap-4 text-sm bg-gray-50 rounded-lg p-3">
            <div className="flex-1"><p className="font-medium text-gray-800">{o.client}</p><p className="text-xs text-gray-400">Sent {o.date_sent}</p></div>
            <span className="font-mono font-semibold">{fmt(o.amount)}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${o.urgency==="overdue"?"bg-red-50 text-red-600":"bg-amber-50 text-amber-600"}`}>{o.days_outstanding}d</span>
          </div>))}</div>}
      </Collapsible>
      <Collapsible title="Missing Receipts" count={r.missing_receipts.length}>
        <div className="space-y-1 max-h-60 overflow-y-auto">{r.missing_receipts.map((m,i)=>(
          <div key={i} className="flex items-center justify-between text-sm py-1.5 border-b border-gray-50">
            <div><span className="text-gray-700">{m.description}</span><span className="text-xs text-gray-400 ml-2">{m.date}</span></div>
            <span className="font-mono text-gray-500">{fmt(m.amount)}</span></div>))}</div>
      </Collapsible>
      {r.tax_summary&&<Collapsible title="Tax Summary" defaultOpen>
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-4 bg-emerald-50 rounded-lg"><p className="text-xs text-emerald-600 uppercase tracking-wide">Deductible</p><p className="text-xl font-bold text-emerald-700">{fmt(r.tax_summary.net_deductible)}</p><p className="text-xs text-emerald-500 mt-1">(net of {fmt(r.tax_summary.refunds_total)} refunds)</p></div>
          <div className="text-center p-4 bg-red-50 rounded-lg"><p className="text-xs text-red-600 uppercase tracking-wide">Non-Deductible</p><p className="text-xl font-bold text-red-700">{fmt(r.tax_summary.total_non_deductible)}</p></div>
        </div>
      </Collapsible>}
    </div>
  );
}

function ActionsTab({ n }) {
  const todos = n.action_items.filter(a=>!a.done);
  const done = n.action_items.filter(a=>a.done);
  const cc = {"follow-up":"bg-red-50 text-red-600",opportunity:"bg-purple-50 text-purple-600",admin:"bg-gray-100 text-gray-600",tax:"bg-blue-50 text-blue-600"};
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">To Do ({todos.length})</h3>
        <div className="space-y-2">{todos.map((a,i)=>(<div key={i} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
          <div className="w-4 h-4 rounded border-2 border-gray-300 mt-0.5 flex-shrink-0"/>
          <div><p className="text-sm text-gray-800">{a.description}</p><span className={`text-xs px-1.5 py-0.5 rounded font-medium ${cc[a.category]||cc.admin}`}>{a.category}</span></div>
        </div>))}</div>
      </div>
      {done.length>0&&<div className="bg-white rounded-xl border border-gray-200 p-5 opacity-60"><h3 className="text-sm font-semibold text-gray-400 mb-3">Done ({done.length})</h3>
        <div className="space-y-1">{done.map((a,i)=>(<div key={i} className="flex items-center gap-3 py-1.5 text-sm text-gray-400 line-through"><CheckCircle2 className="w-4 h-4 text-emerald-400"/><span>{a.description}</span></div>))}</div>
      </div>}
    </div>
  );
}

function InsightsTab({ r, n }) {
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-6"><h3 className="text-sm font-semibold text-gray-700 mb-4">Key Insights</h3>
        <div className="space-y-3">{r.insights.map((ins,i)=>(<div key={i} className="flex items-start gap-3 text-sm"><Lightbulb className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5"/><span className="text-gray-700">{ins}</span></div>))}</div></div>
      {r.data_quality?.recommendations?.length>0&&<div className="bg-white rounded-xl border border-gray-200 p-6"><h3 className="text-sm font-semibold text-gray-700 mb-4">Recommendations</h3>
        <div className="space-y-3">{r.data_quality.recommendations.map((rec,i)=>(<div key={i} className="flex items-start gap-3 text-sm"><CheckCircle2 className="w-4 h-4 text-teal-500 flex-shrink-0 mt-0.5"/><span className="text-gray-600">{rec}</span></div>))}</div></div>}
      {n.warnings?.length>0&&<div className="bg-white rounded-xl border border-gray-200 p-6"><h3 className="text-sm font-semibold text-gray-700 mb-4">Processing Warnings ({n.warnings.length})</h3>
        <div className="space-y-2 max-h-60 overflow-y-auto">{n.warnings.map((w,i)=>(<div key={i} className="flex items-start gap-2 text-xs text-gray-500"><AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0 mt-0.5"/><span>{w}</span></div>))}</div></div>}
    </div>
  );
}

const TABS = [{key:"overview",label:"Overview",icon:BarChart3},{key:"expenses",label:"Expenses",icon:DollarSign},{key:"invoices",label:"Invoices",icon:FileText},{key:"reconcile",label:"Reconciliation",icon:Shield},{key:"actions",label:"Actions",icon:CheckCircle2},{key:"insights",label:"Insights",icon:Lightbulb}];

export default function App() {
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("overview");

  if (!result) return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-gradient-to-r from-emerald-900 to-teal-800 text-white px-8 py-8">
        <p className="text-xs tracking-widest uppercase opacity-50 mb-1">tablo</p>
        <h1 className="text-3xl font-bold tracking-tight">Your documents talk to each other</h1>
        <p className="text-teal-200/70 mt-2 text-sm">Drop your shoebox. Get your financial overview.</p>
      </header>
      <main className="px-8 py-16"><UploadZone onResult={setResult}/></main>
    </div>
  );

  const n = result.normalized, r = result.reconciliation;
  const content = {overview:<OverviewTab n={n} r={r}/>,expenses:<ExpensesTab n={n}/>,invoices:<InvoicesTab n={n}/>,reconcile:<ReconcileTab r={r}/>,actions:<ActionsTab n={n}/>,insights:<InsightsTab r={r} n={n}/>};

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-gradient-to-r from-emerald-900 to-teal-800 text-white px-8 py-5">
        <div className="flex items-center justify-between max-w-6xl mx-auto"><div><p className="text-xs tracking-widest uppercase opacity-50">tablo</p><h1 className="text-xl font-bold tracking-tight">Financial Overview</h1></div>
          <button onClick={()=>setResult(null)} className="text-xs text-teal-200/70 hover:text-white px-3 py-1.5 rounded-lg border border-teal-600/30 hover:border-teal-400/50 transition">New upload</button></div>
      </header>
      <nav className="bg-emerald-950 border-b border-emerald-900 overflow-x-auto"><div className="flex max-w-6xl mx-auto">{TABS.map(({key,label,icon:Icon})=>(
        <button key={key} onClick={()=>setTab(key)} className={`flex items-center gap-2 px-5 py-3 text-sm font-medium whitespace-nowrap transition ${tab===key?"text-white bg-gray-50/10 border-b-2 border-teal-400":"text-teal-300/60 hover:text-teal-100"}`}><Icon className="w-4 h-4"/>{label}</button>))}</div></nav>
      <main className="max-w-6xl mx-auto px-8 py-8">{content[tab]}</main>
      <footer className="text-center py-6 text-xs text-gray-400">Processed {result.upload?.file_count||"?"} files · {n.expenses.length} expenses · {n.invoices.length} invoices</footer>
    </div>
  );
}
