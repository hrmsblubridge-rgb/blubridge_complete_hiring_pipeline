/**
 * Bulk Communication Center (iter69)
 * --------------------------------------------
 * Upload candidate list → auto-match against pipeline_data + bb_registrations
 * → preview matched rows → recruiter picks ONE of 5 actions
 *   (Interview Schedule | Schedule Details | OTP | Candidate Follow-up |
 *    Rejection) → bulk send Mail + WhatsApp via centralized notify_*
 *   helpers (TEST MODE gate enforced) → log to bb_resend_history.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, Upload, WhatsappLogo, MagnifyingGlass, Funnel, ArrowsClockwise,
    PaperPlaneTilt, Eye, CheckCircle, XCircle, Warning, ClockCountdown, X,
    FileText, ListChecks, FileXls, FileCsv, Download,
    Calendar, ShieldCheck, Bell, Prohibit, EnvelopeSimple,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;
const WA_GREEN = '#25D366';
const WA_GREEN_DARK = '#128C7E';

// ---------- Action catalog (Bulk Communication Center) ----------
const ACTIONS = [
    {
        key: 'interview_schedule',
        label: 'Send Interview Schedule',
        icon: PaperPlaneTilt,
        bg: '#f0abfc', fg: '#86198f', accent: '#a21caf',
        helper: 'notify_shortlisted',
        requires: ['name'],
        // Auto-creates schedule_token if missing.
    },
    {
        key: 'schedule_details',
        label: 'Send Schedule Details',
        icon: Calendar,
        bg: '#3b82f6', fg: '#ffffff', accent: '#1d4ed8',
        helper: 'notify_schedule_confirmation',
        requires: ['name', 'date', 'time'],
    },
    {
        key: 'otp',
        label: 'Send OTP',
        icon: ShieldCheck,
        bg: '#f97316', fg: '#ffffff', accent: '#c2410c',
        helper: 'notify_otp',
        requires: ['name', 'date', 'time'],
        // OTP reused from bb_registrations or generated.
    },
    {
        key: 'candidate_followup',
        label: 'Send Candidate Follow-up',
        icon: Bell,
        bg: '#7c3aed', fg: '#ffffff', accent: '#5b21b6',
        helper: 'notify_missed_reminder',
        requires: ['name', 'role', 'date', 'time', 'active_schedule'],
    },
    {
        key: 'rejection',
        label: 'Send Rejection',
        icon: Prohibit,
        bg: '#f5d0fe', fg: '#86198f', accent: '#a21caf',
        helper: 'notify_rejected',
        requires: ['name'],
    },
];

const ACTION_BY_KEY = Object.fromEntries(ACTIONS.map(a => [a.key, a]));

// ---------- helpers ----------
const fmtDDMMYYYY = (iso) => {
    if (!iso) return '';
    const s = String(iso);
    if (s.length >= 10 && s[4] === '-' && s[7] === '-') return `${s.slice(8, 10)}-${s.slice(5, 7)}-${s.slice(0, 4)}`;
    return s;
};
const matchTone = {
    'Exact Match':   'bg-emerald-50 text-emerald-700 border-emerald-200',
    'Partial Match': 'bg-amber-50 text-amber-700 border-amber-200',
    'Multiple Match':'bg-blue-50 text-blue-700 border-blue-200',
    'No Match':      'bg-rose-50 text-rose-700 border-rose-200',
};
const waTone = {
    pending: 'bg-zinc-100 text-zinc-700 border-zinc-200',
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    sent:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    failed:  'bg-rose-50 text-rose-700 border-rose-200',
    blocked: 'bg-amber-50 text-amber-700 border-amber-200',
    skipped: 'bg-zinc-100 text-zinc-600 border-zinc-200',
};

// ---------- Upload zone ----------
function UploadZone({ onUploaded }) {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);

    const handleFile = async (file) => {
        if (!file) return;
        if (!/\.(csv|xlsx|xls)$/i.test(file.name)) {
            toast.error('Only .csv or .xlsx files are supported');
            return;
        }
        if (file.size > 5 * 1024 * 1024) { toast.error('File exceeds 5 MB limit'); return; }

        const fd = new FormData();
        fd.append('file', file);
        setUploading(true);
        try {
            const r = await axios.post(`${API}/api/bb/resend/upload`, fd, { withCredentials: true });
            toast.success(`Parsed ${r.data.total_rows} rows · matched ${r.data.matched_rows}`);
            onUploaded(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(false);
            if (inputRef.current) inputRef.current.value = '';
        }
    };

    return (
        <div
            data-testid="resend-upload-zone"
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files?.[0]); }}
            className={`border-2 border-dashed rounded-2xl p-8 transition-colors ${
                dragging ? 'border-[#25D366] bg-[#25D366]/5' : 'border-[#d6d4c8] bg-[#fffdf7]'
            }`}
        >
            <div className="flex flex-col items-center text-center gap-3">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ backgroundColor: '#25D36620' }}>
                    <Upload size={28} weight="duotone" color={WA_GREEN_DARK} />
                </div>
                <div>
                    <p className="text-base font-semibold text-[#1a2332]">Upload candidate list</p>
                    <p className="text-sm text-[#6b7280] mt-1">Drag & drop or click to browse · CSV / XLSX · max 5 MB</p>
                    <p className="text-xs text-[#9b9787] mt-1">Required columns: Name, Email, Phone (auto-mapped)</p>
                </div>
                <button
                    type="button"
                    disabled={uploading}
                    onClick={() => inputRef.current?.click()}
                    data-testid="resend-upload-btn"
                    className="mt-2 px-5 py-2.5 rounded-lg text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60 transition-colors"
                    style={{ backgroundColor: uploading ? WA_GREEN_DARK : WA_GREEN }}
                >
                    {uploading ? (<><div className="spinner w-4 h-4 border-white border-t-transparent" /> Uploading…</>) : (<><Upload size={16} weight="bold" /> Choose File</>)}
                </button>
                <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
            </div>
        </div>
    );
}

// ---------- Message Preview Modal ----------
function MessagePreview({ row, template, action, onClose }) {
    const c = row?.candidate || {};
    const s = row?.schedule || {};
    const office = template?.office_location || '30, Norton Road, Chennai - 600028';
    const body = (template?.body || '')
        .replace(/{{name}}/g, c.name || c.input_name || '—')
        .replace(/{{job_role}}/g, s.job_role || '—')
        .replace(/{{schedule_date}}/g, fmtDDMMYYYY(s.schedule_date))
        .replace(/{{schedule_time}}/g, s.schedule_time || '—')
        .replace(/{{interview_round}}/g, s.interview_round || 'Round 1')
        .replace(/{{schedule_link}}/g, s.schedule_link || `${window.location.origin}/schedule-interview/<token>`)
        .replace(/{{otp}}/g, c.otp || '—')
        .replace(/{{phone}}/g, c.phone || c.input_phone || '—')
        .replace(/{{office_location}}/g, office)
        .replace(/{{hr_name}}/g, s.hr_name || 'BluBridge HR Team');

    const headerColor = action?.accent || WA_GREEN_DARK;
    return (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose} data-testid="resend-message-preview">
            <div className="bg-[#fffdf7] rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between px-5 py-3 border-b border-[#e5e3d8]" style={{ backgroundColor: headerColor }}>
                    <div className="flex items-center gap-2 text-white">
                        <WhatsappLogo size={20} weight="fill" />
                        <span className="font-semibold text-sm">{action?.label || 'WhatsApp Preview'}</span>
                    </div>
                    <button onClick={onClose} className="text-white/80 hover:text-white"><X size={18} /></button>
                </div>
                <div className="p-5" style={{ backgroundColor: '#ECE5DD' }}>
                    <div className="bg-[#DCF8C6] rounded-xl rounded-tl-none p-4 shadow-sm whitespace-pre-wrap text-sm text-[#1f2937] leading-relaxed">
                        {body}
                    </div>
                    <p className="text-[10px] text-[#6b7280] mt-3 text-center">
                        Template: <span className="font-mono">{template?.template || '—'}</span> · Params: {(template?.params || []).length}
                    </p>
                </div>
            </div>
        </div>
    );
}

// ---------- Main page ----------
export default function WhatsAppResend() {
    const navigate = useNavigate();
    const [upload, setUpload] = useState(null);   // result of /upload
    const [rows, setRows] = useState([]);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);
    const [filteredTotal, setFilteredTotal] = useState(0);
    const [matchFilter, setMatchFilter] = useState('');
    const [waFilter, setWaFilter] = useState('');
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState(new Set());
    const [previewRow, setPreviewRow] = useState(null);
    const [template, setTemplate] = useState({ body: '', params: [] });
    const [sending, setSending] = useState(false);
    const [history, setHistory] = useState([]);
    const [showHistory, setShowHistory] = useState(false);
    // iter69 — Bulk Communication Center: recruiter picks 1 of 5 actions.
    const [actionKey, setActionKey] = useState('candidate_followup');
    const action = ACTION_BY_KEY[actionKey];

    // iter71 — Reload preview template whenever action changes so the
    // preview always reflects the active action's body.
    useEffect(() => {
        axios.get(`${API}/api/bb/resend/template-preview`, {
            withCredentials: true,
            params: { action_type: actionKey },
        }).then(r => setTemplate(r.data)).catch(() => {});
    }, [actionKey]);

    const loadPreview = useCallback(async (uploadId, p = 1) => {
        if (!uploadId) return;
        try {
            const r = await axios.get(`${API}/api/bb/resend/preview/${uploadId}`, {
                withCredentials: true,
                params: { page: p, page_size: pageSize, match_status: matchFilter || undefined, whatsapp_status: waFilter || undefined, search: search || undefined },
            });
            setRows(r.data.rows || []);
            setFilteredTotal(r.data.filtered_total || 0);
            setPage(p);
        } catch (e) { toast.error('Failed to load preview'); }
    }, [matchFilter, waFilter, search, pageSize]);

    useEffect(() => {
        if (upload?.upload_id) loadPreview(upload.upload_id, 1);
    }, [upload?.upload_id, loadPreview]);

    const loadHistory = useCallback(async () => {
        try {
            const r = await axios.get(`${API}/api/bb/resend/history`, {
                withCredentials: true,
                params: { page: 1, page_size: 100, upload_id: upload?.upload_id || undefined },
            });
            setHistory(r.data.rows || []);
        } catch (e) { toast.error('Failed to load history'); }
    }, [upload?.upload_id]);

    useEffect(() => { if (showHistory) loadHistory(); }, [showHistory, loadHistory]);

    const toggleSelect = (id) => {
        setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    };
    const toggleSelectAll = () => {
        if (selected.size === rows.length) setSelected(new Set());
        else setSelected(new Set(rows.map(r => r.row_id)));
    };

    const sendRows = async (rowIds, label, onlyFailed = false) => {
        if (!upload?.upload_id) return;
        setSending(true);
        try {
            const r = await axios.post(`${API}/api/bb/resend/send`, {
                upload_id: upload.upload_id,
                row_ids: rowIds,
                only_failed: onlyFailed,
                action_type: actionKey,
            }, { withCredentials: true });
            const { success = 0, failed = 0, blocked = 0, skipped = 0 } = r.data;
            // iter75 — "Submitted" wording: AiSensy 200 = accepted, NOT
            // guaranteed Meta delivery.
            toast.success(`${action.label} → ${label}: ✅ ${success} submitted · ❌ ${failed} failed · 🚫 ${blocked} gated · ⏭ ${skipped}`);
            await loadPreview(upload.upload_id, page);
            setSelected(new Set());
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Send failed');
        } finally { setSending(false); }
    };

    const sendTest = async () => {
        try {
            const r = await axios.post(`${API}/api/bb/resend/test`, {}, { withCredentials: true });
            toast[r.data.success ? 'success' : 'error'](r.data.success ? `Test sent to ${r.data.to}` : 'Test failed (allowlist or AiSensy)');
        } catch (e) { toast.error('Test failed'); }
    };

    const exportResults = async (fmt) => {
        if (!upload?.upload_id) return;
        try {
            const resp = await axios.get(`${API}/api/bb/resend/export/${upload.upload_id}`, {
                withCredentials: true,
                responseType: 'blob',
                params: {
                    fmt,
                    match_status: matchFilter || undefined,
                    whatsapp_status: waFilter || undefined,
                },
            });
            const blobUrl = window.URL.createObjectURL(new Blob([resp.data]));
            const a = document.createElement('a');
            const base = (upload.filename || 'whatsapp-resend').replace(/\.(csv|xlsx?|xls)$/i, '');
            a.href = blobUrl;
            a.download = `${base}-results.${fmt}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(blobUrl);
            toast.success(`Downloaded ${fmt.toUpperCase()}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Export failed');
        }
    };

    // iter69 — Per-action sendability: each action requires different fields.
    const isRowSendable = useCallback((r) => {
        if (r.match_status === 'No Match') return false;
        const s = r.schedule || {};
        const c = r.candidate || {};
        const phone = c.phone || c.input_phone || '';
        const email = c.email || c.input_email || '';
        if (!phone && !email) return false;
        const reqs = action?.requires || [];
        if (reqs.includes('date') && !s.schedule_date) return false;
        if (reqs.includes('time') && !s.schedule_time) return false;
        if (reqs.includes('role') && !s.job_role) return false;
        if (reqs.includes('active_schedule') && !s.has_active_schedule) return false;
        return true;
    }, [action]);

    const sendable = useMemo(() => rows.filter(isRowSendable), [rows, isRowSendable]);
    const sendBulkAll = () => sendRows(sendable.map(r => r.row_id), 'Bulk');
    const sendSelected = () => sendRows([...selected], 'Selected');
    const retryFailed = () => sendRows(rows.filter(r => r.whatsapp?.last_status === 'failed').map(r => r.row_id), 'Retry failed', true);

    const totalPages = Math.max(1, Math.ceil(filteredTotal / pageSize));

    return (
        <div className="min-h-screen" data-testid="whatsapp-resend-page">
            {/* Header */}
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
                    <div className="flex items-center gap-3 pl-12 lg:pl-0">
                        <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                            <ArrowLeft size={18} className="text-[#1a2332]" />
                        </button>
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: '#1d3a8a20' }}>
                            <PaperPlaneTilt size={22} weight="fill" color="#1d3a8a" />
                        </div>
                        <div>
                            <h1 data-testid="bulk-comm-heading" className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Bulk Communication Center</h1>
                            <p className="text-xs text-[#6b7280] mt-0.5">Pick an action — fire Mail + WhatsApp to matched candidates</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button onClick={() => setShowHistory(s => !s)} data-testid="resend-history-btn"
                            className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-sm text-[#1a2332] hover:bg-[#efede5] flex items-center gap-1.5">
                            <ListChecks size={16} weight="duotone" /> {showHistory ? 'Back to Preview' : 'Resend History'}
                        </button>
                        <button onClick={sendTest} data-testid="resend-test-btn"
                            className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-sm text-[#1a2332] hover:bg-[#efede5] flex items-center gap-1.5">
                            <PaperPlaneTilt size={16} weight="duotone" /> Send Test
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                {showHistory ? (
                    <HistoryView history={history} />
                ) : !upload ? (
                    <UploadZone onUploaded={setUpload} />
                ) : (
                    <>
                        {/* iter69 — Action selector: pick one of 5 Mail+WhatsApp actions */}
                        <ActionSelector active={actionKey} onPick={setActionKey} />

                        {/* Stats strip */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <Stat label="Total Rows" value={upload.total_rows} tone="zinc" />
                            <Stat label="Matched" value={upload.matched_rows} tone="emerald" />
                            <Stat label="Unmatched" value={upload.total_rows - upload.matched_rows} tone="rose" />
                            <Stat label={`Sendable · ${action.label.replace('Send ', '')}`} value={sendable.length} tone="green" icon={<EnvelopeSimple size={16} weight="fill" color="#128C7E" />} />
                        </div>

                        {/* Filter + bulk action toolbar */}
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4 flex flex-wrap items-end gap-3" data-testid="resend-toolbar">
                            <div className="flex items-center gap-2 bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 flex-1 min-w-[200px]">
                                <MagnifyingGlass size={16} className="text-[#9b9787]" />
                                <input
                                    placeholder="Search by name, email, phone…" value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && loadPreview(upload.upload_id, 1)}
                                    data-testid="resend-search"
                                    className="flex-1 bg-transparent outline-none text-sm text-[#1a2332]"
                                />
                            </div>
                            <select value={matchFilter} onChange={(e) => { setMatchFilter(e.target.value); }}
                                data-testid="resend-match-filter"
                                className="bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332]">
                                <option value="">All Match Statuses</option>
                                <option>Exact Match</option><option>Partial Match</option><option>Multiple Match</option><option>No Match</option>
                            </select>
                            <select value={waFilter} onChange={(e) => { setWaFilter(e.target.value); }}
                                data-testid="resend-wa-filter"
                                className="bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332]">
                                <option value="">All WhatsApp Statuses</option>
                                <option value="pending">Pending</option><option value="success">Sent</option>
                                <option value="failed">Failed</option><option value="blocked">Blocked</option><option value="skipped">Skipped</option>
                            </select>
                            <button onClick={() => loadPreview(upload.upload_id, 1)} data-testid="resend-apply-filters"
                                className="px-4 py-2 rounded-lg bg-[#1d3a8a] text-white text-sm font-semibold flex items-center gap-1.5 hover:bg-[#162d6e]">
                                <Funnel size={14} weight="bold" /> Apply
                            </button>
                            <button onClick={() => { setMatchFilter(''); setWaFilter(''); setSearch(''); loadPreview(upload.upload_id, 1); }}
                                className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-sm text-[#1a2332] hover:bg-[#efede5] flex items-center gap-1.5">
                                <ArrowsClockwise size={14} weight="duotone" /> Reset
                            </button>

                            <div className="ml-auto flex items-center gap-2">
                                <div className="flex items-center gap-1 mr-1 pl-1 border-l border-[#e5e3d8]">
                                    <button onClick={() => exportResults('xlsx')} data-testid="resend-export-xlsx-btn"
                                        title="Download as Excel"
                                        className="px-3 py-2 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-700 text-sm font-semibold flex items-center gap-1.5 hover:bg-emerald-100">
                                        <FileXls size={14} weight="duotone" /> Excel
                                    </button>
                                    <button onClick={() => exportResults('csv')} data-testid="resend-export-csv-btn"
                                        title="Download as CSV"
                                        className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] text-sm font-semibold flex items-center gap-1.5 hover:bg-[#efede5]">
                                        <FileCsv size={14} weight="duotone" /> CSV
                                    </button>
                                </div>
                                <button disabled={sending || !sendable.length} onClick={sendBulkAll} data-testid="resend-bulk-all-btn"
                                    className="px-4 py-2 rounded-lg text-white text-sm font-semibold flex items-center gap-1.5 disabled:opacity-50"
                                    style={{ backgroundColor: action.accent }}>
                                    <PaperPlaneTilt size={14} weight="bold" /> {action.label} ({sendable.length})
                                </button>
                                <button disabled={sending || !selected.size} onClick={sendSelected} data-testid="resend-selected-btn"
                                    className="px-3 py-2 rounded-lg border text-sm font-semibold disabled:opacity-50"
                                    style={{ borderColor: action.accent, color: action.accent }}>
                                    Send Selected ({selected.size})
                                </button>
                                <button disabled={sending} onClick={retryFailed} data-testid="resend-retry-btn"
                                    className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-sm text-[#1a2332] hover:bg-[#efede5] flex items-center gap-1.5 disabled:opacity-50">
                                    <ArrowsClockwise size={14} weight="duotone" /> Retry Failed
                                </button>
                            </div>
                        </div>

                        {/* Preview table */}
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden">
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead className="bg-[#faf9f1] border-b border-[#e5e3d8] sticky top-0 z-10">
                                        <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-[#6b7280]">
                                            <th className="px-3 py-3 w-10">
                                                <input type="checkbox" data-testid="resend-select-all" onChange={toggleSelectAll}
                                                    checked={rows.length > 0 && selected.size === rows.length} />
                                            </th>
                                            <th className="px-3 py-3">Candidate</th>
                                            <th className="px-3 py-3">Email / Phone</th>
                                            <th className="px-3 py-3">Match</th>
                                            <th className="px-3 py-3">Job Role</th>
                                            <th className="px-3 py-3">Round</th>
                                            <th className="px-3 py-3">Schedule</th>
                                            <th className="px-3 py-3">Link</th>
                                            <th className="px-3 py-3">WhatsApp</th>
                                            <th className="px-3 py-3 sticky right-0 bg-[#faf9f1]">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.length === 0 && (
                                            <tr><td colSpan={10} className="text-center py-12 text-[#9b9787]">No rows match the current filters.</td></tr>
                                        )}
                                        {rows.map((r) => {
                                            const c = r.candidate || {};
                                            const s = r.schedule || {};
                                            const w = r.whatsapp || {};
                                            const sendable = isRowSendable(r);
                                            return (
                                                <tr key={r.row_id} className="border-b border-[#ece9dc] hover:bg-[#faf9f1]" data-testid={`resend-row-${r.row_id}`}>
                                                    <td className="px-3 py-3">
                                                        <input type="checkbox" disabled={!sendable}
                                                            checked={selected.has(r.row_id)}
                                                            onChange={() => toggleSelect(r.row_id)}
                                                            data-testid={`resend-select-${r.row_id}`} />
                                                    </td>
                                                    <td className="px-3 py-3">
                                                        <p className="font-semibold text-[#1a2332]">{c.name || c.input_name || '—'}</p>
                                                        <p className="text-[11px] text-[#9b9787]">conf {r.match_confidence}% · P{r.priority_used || '–'}</p>
                                                    </td>
                                                    <td className="px-3 py-3">
                                                        <p className="text-[#1a2332]">{c.email || c.input_email || '—'}</p>
                                                        <p className="text-[#6b7280] text-xs">{c.phone || c.input_phone || '—'}</p>
                                                    </td>
                                                    <td className="px-3 py-3">
                                                        <span className={`inline-block px-2 py-0.5 text-[11px] font-medium rounded-md border ${matchTone[r.match_status] || 'bg-zinc-100 text-zinc-700 border-zinc-200'}`}>
                                                            {r.match_status}
                                                        </span>
                                                    </td>
                                                    <td className="px-3 py-3 text-[#1a2332]">{s.job_role || '—'}</td>
                                                    <td className="px-3 py-3 text-[#1a2332]">{s.interview_round || '—'}</td>
                                                    <td className="px-3 py-3">
                                                        <p className="text-[#1a2332]">{fmtDDMMYYYY(s.schedule_date) || '—'}</p>
                                                        <p className="text-[#6b7280] text-xs">{s.schedule_time || ''}</p>
                                                    </td>
                                                    <td className="px-3 py-3 max-w-[180px]">
                                                        {s.schedule_link
                                                            ? <a href={s.schedule_link} target="_blank" rel="noreferrer" className="text-[#1d3a8a] underline truncate inline-block max-w-[160px]">{s.schedule_link.slice(-22)}</a>
                                                            : <span className="text-[#9b9787]">—</span>}
                                                    </td>
                                                    <td className="px-3 py-3">
                                                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-md border ${waTone[w.last_status || 'pending'] || waTone.pending}`}>
                                                            {w.last_status === 'success' && <CheckCircle size={12} weight="fill" />}
                                                            {w.last_status === 'failed' && <XCircle size={12} weight="fill" />}
                                                            {w.last_status === 'blocked' && <Warning size={12} weight="fill" />}
                                                            {w.last_status === 'skipped' && <ClockCountdown size={12} weight="fill" />}
                                                            {(w.last_status || 'pending')}
                                                        </span>
                                                        {w.failure_reason && <p className="text-[10px] text-rose-600 mt-1 max-w-[140px] truncate" title={w.failure_reason}>{w.failure_reason}</p>}
                                                    </td>
                                                    <td className="px-3 py-3 sticky right-0 bg-[#fffdf7]">
                                                        <div className="flex items-center gap-1">
                                                            <button onClick={async () => {
                                                                let enriched = r;
                                                                // iter71 — OTP-action preview: fetch live OTP so the
                                                                // preview shows the applicant's actual code.
                                                                if (actionKey === 'otp' && upload?.upload_id) {
                                                                    try {
                                                                        const resp = await axios.get(`${API}/api/bb/resend/row-otp/${upload.upload_id}/${r.row_id}`, { withCredentials: true });
                                                                        enriched = { ...r, candidate: { ...(r.candidate || {}), otp: resp.data?.otp || '' } };
                                                                    } catch { /* keep base row on error */ }
                                                                }
                                                                setPreviewRow(enriched);
                                                            }} title="Preview message"
                                                                data-testid={`resend-preview-${r.row_id}`}
                                                                className="p-1.5 rounded-md border border-[#e5e3d8] hover:bg-[#efede5]">
                                                                <Eye size={14} className="text-[#1a2332]" />
                                                            </button>
                                                            <button disabled={!sendable || sending} onClick={() => sendRows([r.row_id], 'Single send')}
                                                                title={sendable ? `Send ${action.label}` : 'Missing required fields for this action'}
                                                                data-testid={`resend-send-${r.row_id}`}
                                                                className="p-1.5 rounded-md text-white disabled:opacity-40"
                                                                style={{ backgroundColor: action.accent }}>
                                                                <PaperPlaneTilt size={14} weight="bold" />
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Pagination */}
                            <div className="flex items-center justify-between px-4 py-3 border-t border-[#e5e3d8] text-sm bg-[#faf9f1]">
                                <span className="text-[#6b7280]">Showing {rows.length} of {filteredTotal}</span>
                                <div className="flex items-center gap-1">
                                    <button onClick={() => loadPreview(upload.upload_id, page - 1)} disabled={page <= 1}
                                        className="px-3 py-1.5 rounded-md border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] disabled:opacity-40">Prev</button>
                                    <span className="px-3 text-[#1a2332]">Page {page} / {totalPages}</span>
                                    <button onClick={() => loadPreview(upload.upload_id, page + 1)} disabled={page >= totalPages}
                                        className="px-3 py-1.5 rounded-md border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] disabled:opacity-40">Next</button>
                                </div>
                                <button onClick={() => setUpload(null)} className="text-[#1d3a8a] hover:underline" data-testid="resend-new-upload">+ Upload new file</button>
                            </div>
                        </div>
                    </>
                )}
            </main>

            {previewRow && <MessagePreview row={previewRow} template={template} action={action} onClose={() => setPreviewRow(null)} />}
        </div>
    );
}

// ---------- Action Selector (Bulk Communication Center) ----------
function ActionSelector({ active, onPick }) {
    return (
        <div data-testid="bulk-action-selector" className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
                <PaperPlaneTilt size={16} weight="duotone" className="text-[#1d3a8a]" />
                <p className="text-[11px] font-semibold tracking-[0.16em] uppercase text-[#6b7280]">Choose Action — Mail + WhatsApp</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {ACTIONS.map((a) => {
                    const Icon = a.icon;
                    const isActive = active === a.key;
                    return (
                        <button
                            key={a.key}
                            onClick={() => onPick(a.key)}
                            data-testid={`action-card-${a.key}`}
                            className={`relative rounded-2xl p-5 text-left transition-all border-2 ${isActive ? 'shadow-lg scale-[1.02]' : 'border-transparent hover:shadow-md hover:scale-[1.01]'}`}
                            style={{
                                backgroundColor: a.bg,
                                color: a.fg,
                                borderColor: isActive ? a.accent : 'transparent',
                            }}
                        >
                            {isActive && (
                                <span className="absolute top-2 right-2 inline-flex items-center justify-center w-5 h-5 rounded-full bg-white">
                                    <CheckCircle size={16} weight="fill" color={a.accent} />
                                </span>
                            )}
                            <Icon size={28} weight="duotone" />
                            <p className="mt-3 font-bold text-[14px] leading-tight">{a.label}</p>
                            <p className="mt-2 text-[11px] opacity-90 flex items-center gap-1">
                                <EnvelopeSimple size={12} weight="fill" />
                                <span>Mail + WhatsApp</span>
                            </p>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

// ---------- Stat card ----------
function Stat({ label, value, tone, icon }) {
    const palette = {
        zinc:    { bg: 'bg-[#fffdf7]', fg: 'text-[#1a2332]' },
        emerald: { bg: 'bg-emerald-50', fg: 'text-emerald-700' },
        rose:    { bg: 'bg-rose-50',    fg: 'text-rose-700' },
        green:   { bg: 'bg-[#25D366]/10', fg: 'text-[#128C7E]' },
    }[tone] || { bg: 'bg-white', fg: 'text-zinc-900' };
    return (
        <div className={`border border-[#e5e3d8] ${palette.bg} rounded-2xl p-4`}>
            <div className="flex items-center gap-2">
                {icon}
                <p className="text-[11px] font-semibold tracking-[0.16em] uppercase text-[#9b9787]">{label}</p>
            </div>
            <p className={`text-2xl font-bold mt-1 ${palette.fg}`}>{value ?? 0}</p>
        </div>
    );
}

// ---------- History view ----------
function HistoryView({ history }) {
    return (
        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden" data-testid="resend-history-view">
            <div className="px-4 py-3 border-b border-[#e5e3d8] bg-[#faf9f1] flex items-center gap-2">
                <FileText size={18} className="text-[#1d3a8a]" />
                <h2 className="text-sm font-semibold text-[#1a2332]">Resend History · last 100</h2>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-[#faf9f1] border-b border-[#e5e3d8]">
                        <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-[#6b7280]">
                            <th className="px-4 py-3">Sent At</th>
                            <th className="px-4 py-3">Sent By</th>
                            <th className="px-4 py-3">Candidate</th>
                            <th className="px-4 py-3">Email / Phone</th>
                            <th className="px-4 py-3">Status</th>
                            <th className="px-4 py-3">Retry</th>
                            <th className="px-4 py-3">Reason</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history.length === 0 && <tr><td colSpan={7} className="text-center py-10 text-[#9b9787]">No resend history yet.</td></tr>}
                        {history.map((h) => (
                            <tr key={h.history_id} className="border-b border-[#ece9dc] hover:bg-[#faf9f1]">
                                <td className="px-4 py-3 text-[#1a2332]">{(h.sent_at || '').replace('T', ' ').slice(0, 19)}</td>
                                <td className="px-4 py-3 text-[#1a2332]">{h.sent_by}</td>
                                <td className="px-4 py-3 text-[#1a2332]">{h.candidate?.name || '—'}</td>
                                <td className="px-4 py-3">
                                    <p className="text-[#1a2332]">{h.candidate?.email || '—'}</p>
                                    <p className="text-[#6b7280] text-xs">{h.candidate?.phone || '—'}</p>
                                </td>
                                <td className="px-4 py-3">
                                    <span className={`inline-block px-2 py-0.5 text-[11px] font-medium rounded-md border ${waTone[h.status] || waTone.pending}`}>{h.status}</span>
                                </td>
                                <td className="px-4 py-3 text-[#1a2332]">{h.retry_count || 1}</td>
                                <td className="px-4 py-3 text-[#6b7280] text-xs max-w-[260px] truncate" title={h.failure_reason || ''}>{h.failure_reason || '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
