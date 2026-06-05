import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, PencilSimple, X, Plus, Trash, FloppyDisk, Export, UploadSimple, ArrowCounterClockwise } from '@phosphor-icons/react';
import Pagination from '../components/Pagination';
import { formatDateDDMMYYYY } from '../utils/dateFormat';
import SortableHeader from '../components/SortableHeader';

const API = process.env.REACT_APP_BACKEND_URL;

const COLUMNS = [
    { key: 'name', label: 'NAME', sortable: true },
    { key: 'email', label: 'EMAIL', sortable: true },
    { key: 'phone', label: 'PHONE', sortable: true },
    { key: 'schedule_date', label: 'DATE OF INTERVIEW', sortable: true },
    { key: 'job_role', label: 'JOB ROLE', sortable: true },
    { key: 'result_status', label: 'STATUS', sortable: true },
    { key: '_action', label: '' },
];

export default function UpdateScores() {
    const navigate = useNavigate();
    const [applicants, setApplicants] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(100);
    const [loading, setLoading] = useState(true);
    // iter98 — Default the date filter to TODAY (local) so the page lands on
    // current-day attended applicants only. Recruiters can blank the dates
    // (or pick a wider range) to see historical records — existing UI is
    // untouched, only the initial state changes.
    const _today = (() => {
        const d = new Date();
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${dd}`;
    })();
    const [startDate, setStartDate] = useState(_today);
    const [endDate, setEndDate] = useState(_today);
    // iter141 — Name / Email / Phone filters (combo-box: searchable inputs
    // backed by <datalist> dropdowns).
    const [filterName, setFilterName] = useState('');
    const [filterEmail, setFilterEmail] = useState('');
    const [filterPhone, setFilterPhone] = useState('');
    const [filterOpts, setFilterOpts] = useState({ name: [], email: [], phone: [] });
    const [showUpdate, setShowUpdate] = useState(null);
    const [updateStatus, setUpdateStatus] = useState('On hold');
    const [updateScores, setUpdateScores] = useState([{ round_name: '', score: '' }]);
    const [rounds, setRounds] = useState([]);
    const [showRounds, setShowRounds] = useState(false);
    const [roundName, setRoundName] = useState('');
    const [editRoundId, setEditRoundId] = useState(null);
    const [showInactive, setShowInactive] = useState(false);
    const [sort, setSort] = useState(null);

    const fetchRounds = useCallback(async (includeInactive = false) => {
        try {
            const r = await axios.get(`${API}/api/bb/rounds`, { params: includeInactive ? { includeInactive: true } : {}, withCredentials: true });
            setRounds(r.data.rounds || []);
        } catch {}
    }, []);

    // Active-only list for the score-row dropdown
    const activeRounds = rounds.filter(r => r.active !== false);

    // iter141 — refs let `fetchApplicants` stay reference-stable while still
    // reading the latest filter values when the Apply button fires. This
    // preserves the explicit Apply / Reset UX (changes to the inputs do
    // NOT auto-refetch).
    const filterRefs = useRef({ filterName, filterEmail, filterPhone });
    useEffect(() => {
        filterRefs.current = { filterName, filterEmail, filterPhone };
    }, [filterName, filterEmail, filterPhone]);

    const fetchApplicants = useCallback(async (pg = 1, sz = 100, sortState = null) => {
        setLoading(true);
        try {
            const params = { page: pg, limit: sz };
            if (startDate) params.startDate = startDate;
            if (endDate) params.endDate = endDate;
            const { filterName: fn, filterEmail: fe, filterPhone: fp } = filterRefs.current;
            if (fn.trim()) params.name = fn.trim();
            if (fe.trim()) params.email = fe.trim();
            if (fp.trim()) params.phone = fp.trim();
            if (sortState?.by) { params.sort_by = sortState.by; params.sort_dir = sortState.dir; }
            const r = await axios.get(`${API}/api/bb/attended-for-scores`, { params, withCredentials: true });
            setApplicants(r.data.data || []);
            setTotal(r.data.total || 0);
        } catch { toast.error('Failed to load'); }
        finally { setLoading(false); }
    }, [startDate, endDate]);

    // iter145 — Lazy-fetch the combo-box dropdown options ONLY when the
    // recruiter focuses one of the inputs for the first time. Backend
    // is also hard-capped at 500 entries. Combined, this prevents the
    // page from injecting 100k+ <option> nodes into a <datalist> on
    // mount (the cause of browser blackouts on Score & Round).
    const optsLoadedRef = useRef(false);
    const fetchFilterOpts = useCallback(async () => {
        if (optsLoadedRef.current) return;
        optsLoadedRef.current = true;
        try {
            const params = {};
            if (startDate) params.startDate = startDate;
            if (endDate) params.endDate = endDate;
            const r = await axios.get(`${API}/api/bb/attended-for-scores/filters`, { params, withCredentials: true });
            setFilterOpts({
                name: r.data?.name || [],
                email: r.data?.email || [],
                phone: r.data?.phone || [],
            });
        } catch {
            // Non-fatal — allow retry on next focus.
            optsLoadedRef.current = false;
        }
    }, [startDate, endDate]);
    // Invalidate the cached dropdown when the date range changes.
    useEffect(() => { optsLoadedRef.current = false; }, [startDate, endDate]);

    useEffect(() => { fetchRounds(); }, [fetchRounds]);
    useEffect(() => { fetchApplicants(1, pageSize, sort); setPage(1); }, [fetchApplicants, pageSize, sort]);
    // iter145 — fetchFilterOpts now runs lazily on input focus instead
    // of on mount.

    const applyFilter = () => { setPage(1); fetchApplicants(1, pageSize, sort); };
    const handleSortChange = (next) => { setSort(next); setPage(1); };
    const totalPages = Math.ceil(total / pageSize) || 1;
    const navPage = (pg) => { if (pg >= 1 && pg <= totalPages) { setPage(pg); fetchApplicants(pg, pageSize, sort); } };

    const openUpdate = (app) => {
        setShowUpdate(app);
        setUpdateStatus(app.status || 'On hold');
        // Pre-populate scores from score_sheet data (auto-populated by backend)
        if (app.scores?.length > 0) {
            setUpdateScores(app.scores.map(s => ({ round_name: s.round_name, score: String(s.score) })));
        } else {
            setUpdateScores([{ round_name: '', score: '' }]);
        }
    };

    const addScoreRow = () => setUpdateScores(p => [...p, { round_name: '', score: '' }]);
    const removeScoreRow = (i) => setUpdateScores(p => p.filter((_, idx) => idx !== i));
    const setScoreField = (i, field, val) => setUpdateScores(p => p.map((s, idx) => idx === i ? { ...s, [field]: val } : s));

    const handleSave = async () => {
        const scores = updateScores.filter(s => s.round_name && s.score !== '').map(s => ({ round_name: s.round_name, score: parseFloat(s.score) || 0 }));
        try {
            await axios.put(`${API}/api/bb/applicant-score/${encodeURIComponent(showUpdate.email)}`, { status: updateStatus, scores }, { withCredentials: true });
            toast.success('Updated'); setShowUpdate(null); fetchApplicants(page, pageSize);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };

    // Rounds CRUD
    const saveRound = async () => {
        if (!roundName.trim()) { toast.error('Name required'); return; }
        try {
            if (editRoundId) await axios.put(`${API}/api/bb/rounds/${editRoundId}`, { name: roundName.trim() }, { withCredentials: true });
            else await axios.post(`${API}/api/bb/rounds`, { name: roundName.trim() }, { withCredentials: true });
            toast.success(editRoundId ? 'Updated' : 'Created'); setRoundName(''); setEditRoundId(null); fetchRounds(showInactive);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const deleteRound = async (id) => {
        // Logical delete by default
        if (!window.confirm('Disable this round? Historical scores will be preserved and the round can be restored later.')) return;
        try {
            await axios.delete(`${API}/api/bb/rounds/${id}`, { withCredentials: true });
            toast.success('Round disabled'); fetchRounds(showInactive);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const restoreRound = async (id) => {
        try {
            await axios.post(`${API}/api/bb/rounds/${id}/restore`, {}, { withCredentials: true });
            toast.success('Round restored'); fetchRounds(showInactive);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const toggleShowInactive = () => {
        const next = !showInactive;
        setShowInactive(next);
        fetchRounds(next);
    };

    // Used rounds for current update (prevent duplicate selection)
    const usedRounds = new Set(updateScores.map(s => s.round_name).filter(Boolean));

    const [importPreview, setImportPreview] = useState(null); // {rows, round_columns, errors, total}

    // ---- Iter49: helper to safely format ANY axios error into a string ----
    // FastAPI sometimes returns `detail` as a list/dict (validation errors);
    // passing those directly to toast/React caused the "Script error at
    // handleError..." overlay. We coerce defensively here.
    const errMsg = (err, fallback = 'Operation failed') => {
        try {
            const d = err?.response?.data;
            if (typeof d === 'string') return d;
            if (typeof d?.detail === 'string') return d.detail;
            if (Array.isArray(d?.detail) && d.detail[0]?.msg) return d.detail.map(x => x.msg).join('; ');
            if (typeof d?.message === 'string') return d.message;
            if (err?.response) return `${err.response.status} ${err.response.statusText || fallback}`;
            return err?.message || fallback;
        } catch { return fallback; }
    };

    // Export — calls backend XLSX endpoint (full schema)
    const handleExport = async (fmt = 'xlsx') => {
        const tid = toast.loading(`Exporting ${fmt.toUpperCase()}…`);
        try {
            const params = new URLSearchParams({ format: fmt });
            if (startDate) params.append('startDate', startDate);
            if (endDate) params.append('endDate', endDate);
            const res = await axios.get(`${API}/api/bb/export-scores?${params}`, {
                withCredentials: true, responseType: 'blob',
                timeout: 5 * 60 * 1000, // 5-min cap for very large exports
            });
            const url = URL.createObjectURL(new Blob([res.data]));
            const a = document.createElement('a');
            a.href = url;
            a.download = `applicant_scores_${new Date().toISOString().split('T')[0]}.${fmt}`;
            a.click();
            URL.revokeObjectURL(url);
            toast.success('Export ready', { id: tid });
        } catch (err) {
            toast.error(errMsg(err, 'Export failed'), { id: tid });
        }
    };

    // Import — STEP 1: preview parsed rows
    const handleImport = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        // Reset the input early so re-selecting the same file works on retry
        e.target.value = '';
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await axios.post(
                `${API}/api/bb/import-scores/preview`, formData,
                { withCredentials: true, headers: { 'Content-Type': 'multipart/form-data' }, timeout: 2 * 60 * 1000 },
            );
            const data = res?.data || {};
            // Defensive: ensure shape so the preview modal never crashes on
            // null/undefined access while iterating fields after "Status".
            setImportPreview({
                rows: Array.isArray(data.rows) ? data.rows : [],
                round_columns: Array.isArray(data.round_columns) ? data.round_columns : [],
                errors: Array.isArray(data.errors) ? data.errors : [],
                total: Number.isFinite(data.total) ? data.total : (data.rows?.length || 0),
            });
            const issueCount = (data.errors || []).length;
            if (issueCount) toast.warning(`${issueCount} row(s) had issues`);
            else toast.success(`Parsed ${data.total || 0} rows. Review and confirm.`);
        } catch (err) {
            // Surface the REAL backend error (BOM check, missing column, etc.)
            // so the user can act on it instead of a generic "Script error".
            console.error('Import preview failed:', err);
            toast.error(errMsg(err, 'Import failed'));
        }
    };

    // Import — STEP 2: confirm and save
    const handleImportConfirm = async () => {
        if (!importPreview?.rows?.length) return;
        try {
            const res = await axios.post(
                `${API}/api/bb/import-scores/confirm`,
                { rows: importPreview.rows },
                { withCredentials: true, timeout: 2 * 60 * 1000 },
            );
            const d = res?.data || {};
            const bid = typeof d.batch_id === 'string' ? d.batch_id.slice(0, 8) : 'n/a';
            toast.success(`Imported ${d.imported || 0} records (batch=${bid})`);
            setImportPreview(null);
            fetchApplicants(page, pageSize);
        } catch (err) {
            console.error('Import confirm failed:', err);
            toast.error(errMsg(err, 'Confirm failed'));
        }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="update-scores-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Update Applicants Scores</h1>
                <button onClick={() => { setShowRounds(true); setRoundName(''); setEditRoundId(null); }} data-testid="rounds-btn" className="ml-auto px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium">Rounds</button>
            </header>

            {/* Filters */}
            <div className="px-8 py-5 border-b border-zinc-800">
                <div className="flex items-end gap-4 flex-wrap">
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Start Date</label><input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">End Date</label><input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    {/* iter141 — combo-box (typeahead + dropdown) filters */}
                    <div className="space-y-1">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Name</label>
                        <input list="us-filter-name-list" value={filterName} onChange={e => setFilterName(e.target.value)}
                            onFocus={fetchFilterOpts}
                            placeholder="Type or pick…" data-testid="us-filter-name"
                            className="block w-52 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="us-filter-name-list">
                            {filterOpts.name.map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <div className="space-y-1">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Email</label>
                        <input list="us-filter-email-list" value={filterEmail} onChange={e => setFilterEmail(e.target.value)}
                            onFocus={fetchFilterOpts}
                            placeholder="Type or pick…" data-testid="us-filter-email"
                            className="block w-60 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="us-filter-email-list">
                            {filterOpts.email.map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <div className="space-y-1">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Phone</label>
                        <input list="us-filter-phone-list" value={filterPhone} onChange={e => setFilterPhone(e.target.value)}
                            onFocus={fetchFilterOpts}
                            placeholder="Type or pick…" data-testid="us-filter-phone"
                            className="block w-44 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="us-filter-phone-list">
                            {filterOpts.phone.map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <button onClick={applyFilter} data-testid="apply-btn" className="flex items-center gap-2 px-5 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium"><FunnelSimple size={16} /> Apply</button>
                    {/* iter113 — Reset → today/today | All Records → drop dates */}
                    <button onClick={() => { setStartDate(_today); setEndDate(_today); setFilterName(''); setFilterEmail(''); setFilterPhone(''); setTimeout(applyFilter, 0); }} data-testid="reset-btn"
                        className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium">Reset</button>
                    <button onClick={() => { setStartDate(''); setEndDate(''); setFilterName(''); setFilterEmail(''); setFilterPhone(''); setTimeout(applyFilter, 0); }} data-testid="all-records-btn"
                        className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium border border-zinc-700">All Records</button>
                    <button onClick={() => handleExport('xlsx')} data-testid="export-xlsx-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium"><Export size={16} /> Export XLSX</button>
                    <button onClick={() => handleExport('csv')} data-testid="export-csv-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium"><Export size={16} /> Export CSV</button>
                    <label className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium cursor-pointer" data-testid="import-btn">
                        <UploadSimple size={16} /> Import report
                        <input type="file" accept=".csv,.xlsx,.xls" onChange={handleImport} className="hidden" />
                    </label>
                </div>
            </div>

            {/* Applicant List */}
            <div className="px-8 py-6 pb-24">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                <div className="overflow-x-auto border border-zinc-800" data-testid="scores-table">
                    <table className="w-full text-sm">
                        <thead><tr className="bg-zinc-900 border-b border-zinc-800">
                            {COLUMNS.map(c => (
                                <th key={c.key} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap">
                                    {c.sortable ? (
                                        <SortableHeader label={c.label} sortKey={c.key} sort={sort} onSortChange={handleSortChange} />
                                    ) : c.label}
                                </th>
                            ))}
                        </tr></thead>
                        <tbody>
                            {applicants.length === 0 ? <tr><td colSpan={COLUMNS.length} className="px-4 py-16 text-center text-zinc-500">No attended applicants found.</td></tr> :
                            applicants.map((a, i) => (
                                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50" data-testid={`score-row-${i}`}>
                                    <td className="px-4 py-3 font-medium whitespace-nowrap">{a.name}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap" data-testid={`score-row-${i}-email`}>{a.email || '-'}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap" data-testid={`score-row-${i}-phone`}>{a.phone || '-'}</td>
                                    <td className="px-4 py-3 text-zinc-400">{formatDateDDMMYYYY(a.date_of_interview)}</td>
                                    <td className="px-4 py-3 text-zinc-400">{a.job_role}</td>
                                    <td className="px-4 py-3"><span className={`px-2 py-0.5 text-xs rounded ${a.status === 'Selected' ? 'bg-emerald-900/40 text-emerald-400' : a.status === 'Rejected' ? 'bg-red-900/40 text-red-400' : 'bg-zinc-800 text-zinc-400'}`}>{a.status}</span></td>
                                    <td className="px-4 py-3"><button onClick={() => openUpdate(a)} data-testid={`update-btn-${i}`} className="px-3 py-1 bg-emerald-700 hover:bg-emerald-600 text-xs font-medium">Update</button></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>}
                {/* Pagination */}
                <Pagination
                    page={page}
                    totalPages={totalPages}
                    total={total}
                    pageSize={pageSize}
                    onPageChange={navPage}
                    onPageSizeChange={(s) => { setPageSize(s); setPage(1); }}
                />
            </div>

            {/* Update Modal */}
            {showUpdate && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="update-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg mx-4 p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Update Score</h2><button onClick={() => setShowUpdate(null)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="text-sm text-zinc-400">Employee: <span className="text-white font-medium">{showUpdate.name}</span></div>
                        <div className="space-y-1.5">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Status</label>
                            <select value={updateStatus} onChange={e => setUpdateStatus(e.target.value)} data-testid="status-select" className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                                <option>On hold</option><option>Rejected</option><option>Selected</option>
                            </select>
                        </div>
                        <div className="space-y-2">
                            <div className="flex items-center justify-between"><label className="text-xs text-zinc-500 uppercase tracking-wider">Round Scores</label><button onClick={addScoreRow} className="text-xs text-emerald-400 hover:text-emerald-300"><Plus size={14} className="inline" /> Add round</button></div>
                            {updateScores.map((s, i) => (
                                <div key={i} className="flex gap-2 items-center">
                                    <select value={s.round_name} onChange={e => setScoreField(i, 'round_name', e.target.value)} data-testid={`round-select-${i}`} className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                                        <option value="">Select round</option>
                                        {activeRounds.filter(r => !usedRounds.has(r.name) || r.name === s.round_name).map(r => <option key={r.id} value={r.name}>{r.name}</option>)}
                                        {s.round_name && !activeRounds.find(r => r.name === s.round_name) && (
                                            <option value={s.round_name}>{s.round_name} (inactive)</option>
                                        )}
                                    </select>
                                    <input type="number" value={s.score} onChange={e => setScoreField(i, 'score', e.target.value)} placeholder="Score" data-testid={`score-input-${i}`}
                                        className="w-24 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                                    {updateScores.length > 1 && <button onClick={() => removeScoreRow(i)} className="p-1 text-zinc-500 hover:text-red-400"><Trash size={14} /></button>}
                                </div>
                            ))}
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button onClick={() => setShowUpdate(null)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={handleSave} data-testid="save-score-btn" className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium"><FloppyDisk size={16} /> Save</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Rounds Modal */}
            {showRounds && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="rounds-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md mx-4 p-6 space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold">Rounds</h2>
                            <button onClick={() => setShowRounds(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                            <span className="text-zinc-500">{rounds.filter(r => r.active !== false).length} active{showInactive ? ` · ${rounds.filter(r => r.active === false).length} inactive` : ''}</span>
                            <button onClick={toggleShowInactive} data-testid="toggle-inactive-btn" className="text-cyan-400 hover:text-cyan-300">
                                {showInactive ? 'Hide inactive' : 'Show inactive'}
                            </button>
                        </div>
                        <div className="space-y-2 max-h-72 overflow-y-auto">
                            {rounds.map(r => {
                                const inactive = r.active === false;
                                return (
                                    <div key={r.id} className={`px-4 py-3 flex items-center justify-between border ${inactive ? 'bg-zinc-950 border-zinc-800 opacity-70' : 'bg-zinc-800 border-zinc-700'}`} data-testid={`round-${r.id}`}>
                                        <div className="flex items-center gap-2">
                                            <span className={`text-sm ${inactive ? 'text-zinc-400 line-through' : ''}`}>{r.name}</span>
                                            <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${inactive ? 'bg-zinc-800 text-zinc-500' : 'bg-emerald-900/40 text-emerald-300'}`}>
                                                {inactive ? 'Inactive' : 'Active'}
                                            </span>
                                        </div>
                                        <div className="flex gap-2">
                                            {inactive ? (
                                                <button onClick={() => restoreRound(r.id)} data-testid={`restore-round-${r.id}`} className="p-1 text-zinc-400 hover:text-emerald-400" title="Restore">
                                                    <ArrowCounterClockwise size={14} />
                                                </button>
                                            ) : (
                                                <>
                                                    <button onClick={() => { setEditRoundId(r.id); setRoundName(r.name); }} data-testid={`edit-round-${r.id}`} className="p-1 text-zinc-500 hover:text-white" title="Edit"><PencilSimple size={14} /></button>
                                                    <button onClick={() => deleteRound(r.id)} data-testid={`delete-round-${r.id}`} className="p-1 text-zinc-500 hover:text-red-400" title="Disable (logical delete)"><Trash size={14} /></button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                            {rounds.length === 0 && <p className="text-sm text-zinc-600">No rounds yet.</p>}
                        </div>
                        <div className="border-t border-zinc-800 pt-3 space-y-2">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">{editRoundId ? 'Edit Round' : 'Create New Round'}</label>
                            <div className="flex gap-2">
                                <input type="text" value={roundName} onChange={e => setRoundName(e.target.value)} placeholder="Enter round name" data-testid="round-name-input"
                                    className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" onKeyDown={e => e.key === 'Enter' && saveRound()} />
                                <button onClick={saveRound} data-testid="save-round-btn" className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">{editRoundId ? 'Update' : 'Create'}</button>
                                {editRoundId && <button onClick={() => { setEditRoundId(null); setRoundName(''); }} data-testid="cancel-edit-round-btn" className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Import Preview Modal */}
            {importPreview && (
                <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6" data-testid="import-preview-modal">
                    <div className="bg-zinc-900 border border-zinc-800 w-full max-w-6xl max-h-[85vh] flex flex-col">
                        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
                            <h3 className="text-lg font-semibold">Review Imported Records</h3>
                            <button onClick={() => setImportPreview(null)} data-testid="import-preview-close" className="p-1 hover:bg-zinc-800"><X size={20} /></button>
                        </div>
                        <div className="px-6 py-3 border-b border-zinc-800 text-xs text-zinc-400 flex gap-4">
                            <span data-testid="import-preview-count">Total: {importPreview.total}</span>
                            <span>Round columns: {importPreview.round_columns?.join(', ') || '—'}</span>
                            {importPreview.errors?.length > 0 && (
                                <span className="text-amber-400">Issues: {importPreview.errors.length}</span>
                            )}
                        </div>
                        <div className="flex-1 overflow-auto">
                            <table className="w-full text-xs">
                                <thead className="bg-zinc-800 sticky top-0">
                                    <tr>
                                        <th className="px-3 py-2 text-left">Name</th>
                                        <th className="px-3 py-2 text-left">Email</th>
                                        <th className="px-3 py-2 text-left">Job Role</th>
                                        <th className="px-3 py-2 text-left">Status</th>
                                        {importPreview.round_columns?.map(r => (
                                            <th key={r} className="px-3 py-2 text-left">{r}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {(importPreview.rows || []).map((r, i) => (
                                        <tr key={i} className="border-t border-zinc-800" data-testid={`import-preview-row-${i}`}>
                                            <td className="px-3 py-1.5">{String(r?.name ?? '')}</td>
                                            <td className="px-3 py-1.5">{String(r?.email ?? '')}</td>
                                            <td className="px-3 py-1.5">{String(r?.job_role ?? '')}</td>
                                            <td className={`px-3 py-1.5 ${r?.status === 'Rejected' ? 'text-red-400' : ''}`}>{String(r?.status ?? '')}</td>
                                            {(importPreview.round_columns || []).map(rc => {
                                                const sc = (Array.isArray(r?.scores) ? r.scores : []).find(s => s?.round_name === rc);
                                                const v = sc?.score;
                                                return <td key={rc} className="px-3 py-1.5">{v === undefined || v === null || v === '' ? '-' : String(v)}</td>;
                                            })}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="px-6 py-4 border-t border-zinc-800 flex justify-end gap-3">
                            <button onClick={() => setImportPreview(null)} data-testid="import-cancel-btn" className="px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={handleImportConfirm} data-testid="import-confirm-btn" className="px-5 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">Confirm & Save</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
