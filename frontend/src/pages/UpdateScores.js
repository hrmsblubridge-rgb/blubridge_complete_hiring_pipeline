import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, PencilSimple, X, Plus, Trash, FloppyDisk, Export, UploadSimple } from '@phosphor-icons/react';
import Pagination from '../components/Pagination';
import { formatDateDDMMYYYY } from '../utils/dateFormat';
import SortableHeader from '../components/SortableHeader';

const API = process.env.REACT_APP_BACKEND_URL;

const COLUMNS = [
    { key: 'name', label: 'NAME', sortable: true },
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
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [showUpdate, setShowUpdate] = useState(null);
    const [updateStatus, setUpdateStatus] = useState('On hold');
    const [updateScores, setUpdateScores] = useState([{ round_name: '', score: '' }]);
    const [rounds, setRounds] = useState([]);
    const [showRounds, setShowRounds] = useState(false);
    const [roundName, setRoundName] = useState('');
    const [editRoundId, setEditRoundId] = useState(null);
    const [sort, setSort] = useState(null);

    const fetchRounds = useCallback(async () => {
        try { const r = await axios.get(`${API}/api/bb/rounds`, { withCredentials: true }); setRounds(r.data.rounds || []); } catch {}
    }, []);

    const fetchApplicants = useCallback(async (pg = 1, sz = 100, sortState = null) => {
        setLoading(true);
        try {
            const params = { page: pg, limit: sz };
            if (startDate) params.startDate = startDate;
            if (endDate) params.endDate = endDate;
            if (sortState?.by) { params.sort_by = sortState.by; params.sort_dir = sortState.dir; }
            const r = await axios.get(`${API}/api/bb/attended-for-scores`, { params, withCredentials: true });
            setApplicants(r.data.data || []);
            setTotal(r.data.total || 0);
        } catch { toast.error('Failed to load'); }
        finally { setLoading(false); }
    }, [startDate, endDate]);

    useEffect(() => { fetchRounds(); }, [fetchRounds]);
    useEffect(() => { fetchApplicants(1, pageSize, sort); setPage(1); }, [fetchApplicants, pageSize, sort]);

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
            toast.success(editRoundId ? 'Updated' : 'Created'); setRoundName(''); setEditRoundId(null); fetchRounds();
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const deleteRound = async (id) => {
        try { await axios.delete(`${API}/api/bb/rounds/${id}`, { withCredentials: true }); toast.success('Deleted'); fetchRounds(); } catch { toast.error('Failed'); }
    };

    // Used rounds for current update (prevent duplicate selection)
    const usedRounds = new Set(updateScores.map(s => s.round_name).filter(Boolean));

    const [importPreview, setImportPreview] = useState(null); // {rows, round_columns, errors, total}

    // Export — calls backend XLSX endpoint (full schema)
    const handleExport = async (fmt = 'xlsx') => {
        try {
            const params = new URLSearchParams({ format: fmt });
            if (startDate) params.append('startDate', startDate);
            if (endDate) params.append('endDate', endDate);
            const res = await axios.get(`${API}/api/bb/export-scores?${params}`, {
                withCredentials: true, responseType: 'blob',
            });
            const url = URL.createObjectURL(new Blob([res.data]));
            const a = document.createElement('a');
            a.href = url;
            a.download = `applicant_scores_${new Date().toISOString().split('T')[0]}.${fmt}`;
            a.click();
            URL.revokeObjectURL(url);
        } catch { toast.error('Export failed'); }
    };

    // Import — STEP 1: preview parsed rows
    const handleImport = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await axios.post(
                `${API}/api/bb/import-scores/preview`, formData,
                { withCredentials: true, headers: { 'Content-Type': 'multipart/form-data' } },
            );
            setImportPreview(res.data);
            if (res.data.errors?.length) toast.warning(`${res.data.errors.length} row(s) had issues`);
            else toast.success(`Parsed ${res.data.total} rows. Review and confirm.`);
        } catch (err) { toast.error(err?.response?.data?.detail || 'Import failed'); }
        e.target.value = '';
    };

    // Import — STEP 2: confirm and save
    const handleImportConfirm = async () => {
        if (!importPreview?.rows?.length) return;
        try {
            const res = await axios.post(
                `${API}/api/bb/import-scores/confirm`,
                { rows: importPreview.rows },
                { withCredentials: true },
            );
            toast.success(`Imported ${res.data.imported} records (batch=${res.data.batch_id.slice(0, 8)})`);
            setImportPreview(null);
            fetchApplicants(page, pageSize);
        } catch { toast.error('Confirm failed'); }
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
                    <button onClick={applyFilter} data-testid="apply-btn" className="flex items-center gap-2 px-5 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium"><FunnelSimple size={16} /> Apply</button>
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
                            {applicants.length === 0 ? <tr><td colSpan={5} className="px-4 py-16 text-center text-zinc-500">No attended applicants found.</td></tr> :
                            applicants.map((a, i) => (
                                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50" data-testid={`score-row-${i}`}>
                                    <td className="px-4 py-3 font-medium whitespace-nowrap">{a.name}</td>
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
                                        {rounds.filter(r => !usedRounds.has(r.name) || r.name === s.round_name).map(r => <option key={r.id} value={r.name}>{r.name}</option>)}
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
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Rounds</h2><button onClick={() => setShowRounds(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="space-y-2">
                            {rounds.map(r => (
                                <div key={r.id} className="bg-zinc-800 border border-zinc-700 px-4 py-3 flex items-center justify-between" data-testid={`round-${r.id}`}>
                                    <span className="text-sm">{r.name}</span>
                                    <div className="flex gap-2">
                                        <button onClick={() => { setEditRoundId(r.id); setRoundName(r.name); }} className="p-1 text-zinc-500 hover:text-white"><PencilSimple size={14} /></button>
                                        <button onClick={() => deleteRound(r.id)} className="p-1 text-zinc-500 hover:text-red-400"><Trash size={14} /></button>
                                    </div>
                                </div>
                            ))}
                            {rounds.length === 0 && <p className="text-sm text-zinc-600">No rounds yet.</p>}
                        </div>
                        <div className="border-t border-zinc-800 pt-3 space-y-2">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">{editRoundId ? 'Edit Round' : 'Create New Round'}</label>
                            <div className="flex gap-2">
                                <input type="text" value={roundName} onChange={e => setRoundName(e.target.value)} placeholder="Enter round name" data-testid="round-name-input"
                                    className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" onKeyDown={e => e.key === 'Enter' && saveRound()} />
                                <button onClick={saveRound} data-testid="save-round-btn" className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">{editRoundId ? 'Update' : 'Create'}</button>
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
                                    {importPreview.rows.map((r, i) => (
                                        <tr key={i} className="border-t border-zinc-800" data-testid={`import-preview-row-${i}`}>
                                            <td className="px-3 py-1.5">{r.name}</td>
                                            <td className="px-3 py-1.5">{r.email}</td>
                                            <td className="px-3 py-1.5">{r.job_role}</td>
                                            <td className={`px-3 py-1.5 ${r.status === 'Rejected' ? 'text-red-400' : ''}`}>{r.status}</td>
                                            {importPreview.round_columns?.map(rc => {
                                                const sc = (r.scores || []).find(s => s.round_name === rc);
                                                return <td key={rc} className="px-3 py-1.5">{sc?.score ?? '-'}</td>;
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
