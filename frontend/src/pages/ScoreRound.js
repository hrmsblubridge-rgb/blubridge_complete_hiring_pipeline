/**
 * Iter55 — Score & Round table module.
 * Excel-like read-write table for managing per-round scores, commands, status
 * and the three induction dates per candidate.
 *
 * Backed by GET /api/bb/score-round/table, POST /save-scores, PUT /save-dates,
 * plus existing /api/bb/rounds CRUD for round management.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, Plus, X, PencilSimple, Trash, Eye, Sliders, MagnifyingGlass,
    ArrowCounterClockwise, CaretDown,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_OPTIONS = [
    'Scheduled', 'Rescheduled', 'Not Interested', 'No Response', 'Rejected',
    'Shortlisted', 'On-Hold', 'OnBoard', 'Terminated', 'Active/On-track',
    'Confirmed For Exam', 'Doubtfull/Monitor', 'Inactive/Dropout',
];

const fmtDDMMYYYY = (iso) => {
    if (!iso) return '';
    const [y, m, d] = String(iso).split('-');
    if (!y || !m || !d) return iso;
    return `${d}-${m}-${y}`;
};

// --- Manage Rounds Modal (Add / Edit / Logical Delete / Restore) ---
function ManageRoundsModal({ onClose, onChanged }) {
    const [rounds, setRounds] = useState([]);
    const [loading, setLoading] = useState(false);
    const [newName, setNewName] = useState('');
    const [editId, setEditId] = useState(null);
    const [editName, setEditName] = useState('');
    const [showInactive, setShowInactive] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await axios.get(`${API}/api/bb/rounds`, {
                params: { includeInactive: true },
                withCredentials: true,
            });
            setRounds(r.data.rounds || []);
        } catch { toast.error('Failed to load rounds'); }
        finally { setLoading(false); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const create = async () => {
        const n = newName.trim();
        if (!n) return;
        try {
            await axios.post(`${API}/api/bb/rounds`, { name: n }, { withCredentials: true });
            setNewName('');
            await load();
            onChanged?.();
            toast.success(`Round "${n}" added`);
        } catch (e) { toast.error(e.response?.data?.detail || 'Add failed'); }
    };
    const saveEdit = async () => {
        const n = editName.trim();
        if (!n || !editId) return;
        try {
            await axios.put(`${API}/api/bb/rounds/${editId}`, { name: n }, { withCredentials: true });
            setEditId(null); setEditName('');
            await load(); onChanged?.();
            toast.success('Round renamed');
        } catch (e) { toast.error(e.response?.data?.detail || 'Update failed'); }
    };
    const remove = async (r) => {
        if (!window.confirm(`Disable round "${r.name}"? Existing scores remain queryable; restore anytime.`)) return;
        try {
            await axios.delete(`${API}/api/bb/rounds/${r.id}`, { withCredentials: true });
            await load(); onChanged?.();
            toast.success('Round disabled');
        } catch (e) { toast.error(e.response?.data?.detail || 'Delete failed'); }
    };
    const restore = async (r) => {
        try {
            await axios.post(`${API}/api/bb/rounds/${r.id}/restore`, {}, { withCredentials: true });
            await load(); onChanged?.();
            toast.success('Round restored');
        } catch (e) { toast.error(e.response?.data?.detail || 'Restore failed'); }
    };

    const visible = showInactive ? rounds : rounds.filter(r => r.active !== false);
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" data-testid="manage-rounds-modal">
            <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-white">Manage Rounds</h2>
                    <button onClick={onClose} data-testid="manage-rounds-close" className="text-zinc-500 hover:text-white"><X size={20} /></button>
                </div>
                <div className="flex gap-2">
                    <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && create()}
                        placeholder="New round name (e.g. Final Discussion)" data-testid="round-new-name"
                        className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-600" />
                    <button onClick={create} data-testid="round-add-btn"
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium flex items-center gap-1">
                        <Plus size={16} /> Add
                    </button>
                </div>
                <div className="flex justify-between items-center text-xs">
                    <span className="text-zinc-500">{visible.length} {showInactive ? 'total' : 'active'}</span>
                    <button onClick={() => setShowInactive(!showInactive)} data-testid="toggle-inactive-rounds"
                        className="text-cyan-400 hover:text-cyan-300">{showInactive ? 'Hide inactive' : 'Show inactive'}</button>
                </div>
                <div className="border border-zinc-800 divide-y divide-zinc-800">
                    {loading && <div className="p-4 text-center text-zinc-500 text-sm">Loading…</div>}
                    {!loading && visible.length === 0 && <div className="p-4 text-center text-zinc-500 text-sm">No rounds yet.</div>}
                    {!loading && visible.map(r => {
                        const inactive = r.active === false;
                        const isEditing = editId === r.id;
                        return (
                            <div key={r.id} className={`flex items-center gap-2 px-3 py-2 ${inactive ? 'opacity-60' : ''}`}>
                                {isEditing ? (
                                    <input type="text" value={editName} onChange={e => setEditName(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && saveEdit()}
                                        className="flex-1 bg-zinc-800 border border-cyan-600 px-2 py-1 text-sm text-white focus:outline-none" />
                                ) : (
                                    <span className="flex-1 text-sm text-white">{r.name}</span>
                                )}
                                {inactive && <span className="text-[10px] uppercase bg-zinc-800 text-zinc-500 px-1.5 py-0.5">Inactive</span>}
                                {isEditing ? (
                                    <>
                                        <button onClick={saveEdit} className="px-2 py-1 bg-cyan-600 text-white text-xs">Save</button>
                                        <button onClick={() => { setEditId(null); setEditName(''); }} className="px-2 py-1 bg-zinc-700 text-white text-xs">Cancel</button>
                                    </>
                                ) : inactive ? (
                                    <button onClick={() => restore(r)} title="Restore" className="p-1 text-zinc-400 hover:text-emerald-400"><ArrowCounterClockwise size={14} /></button>
                                ) : (
                                    <>
                                        <button onClick={() => { setEditId(r.id); setEditName(r.name); }} title="Edit" className="p-1 text-zinc-400 hover:text-white"><PencilSimple size={14} /></button>
                                        <button onClick={() => remove(r)} title="Disable" className="p-1 text-zinc-400 hover:text-red-400"><Trash size={14} /></button>
                                    </>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

// --- Update Score Modal (per row, multi-round Add More + Save all) ---
function UpdateScoreModal({ row, rounds, onClose, onSaved }) {
    const initialEntries = useMemo(() => {
        const list = [];
        Object.values(row.rounds_map || {}).forEach(r => {
            list.push({
                round_name: r.round_name || '',
                date: r.date || '',
                score: r.score === null || r.score === undefined ? '' : String(r.score),
                command: r.command || '',
                status: r.status || '',
            });
        });
        if (list.length === 0) list.push({ round_name: '', date: '', score: '', command: '', status: '' });
        return list;
    }, [row]);
    const [entries, setEntries] = useState(initialEntries);
    const [saving, setSaving] = useState(false);

    const setEntry = (i, patch) => setEntries(prev => prev.map((e, idx) => idx === i ? { ...e, ...patch } : e));
    const addMore = () => setEntries(prev => [...prev, { round_name: '', date: '', score: '', command: '', status: '' }]);
    const removeAt = (i) => setEntries(prev => prev.length === 1 ? prev : prev.filter((_, idx) => idx !== i));

    const save = async () => {
        const cleaned = entries.filter(e => (e.round_name || '').trim()).map(e => ({
            round_name: e.round_name.trim(),
            date: e.date || '',
            score: e.score === '' ? null : Number(e.score),
            command: e.command || '',
            status: e.status || '',
        }));
        if (cleaned.length === 0) { toast.warning('Add at least one round'); return; }
        setSaving(true);
        try {
            await axios.post(`${API}/api/bb/score-round/save-scores`, {
                email: row.email, entries: cleaned,
            }, { withCredentials: true });
            toast.success(`${cleaned.length} round(s) saved`);
            onSaved?.();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed');
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" data-testid="update-score-modal">
            <div className="bg-zinc-900 border border-zinc-700 w-full max-w-3xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold text-white">Update Score — {row.name || row.email}</h2>
                        <p className="text-xs text-zinc-500 mt-0.5">{row.email}</p>
                    </div>
                    <button onClick={onClose} data-testid="update-score-close" className="text-zinc-500 hover:text-white"><X size={20} /></button>
                </div>
                <div className="space-y-3">
                    {entries.map((e, i) => (
                        <div key={i} className="border border-zinc-800 p-3 space-y-2 bg-zinc-950" data-testid={`score-entry-${i}`}>
                            <div className="flex justify-between items-center">
                                <span className="text-xs text-zinc-500 uppercase tracking-wider">Round #{i + 1}</span>
                                {entries.length > 1 && (
                                    <button onClick={() => removeAt(i)} className="text-zinc-500 hover:text-red-400" title="Remove"><Trash size={14} /></button>
                                )}
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-[11px] text-zinc-500">Round Name</label>
                                    <select value={e.round_name} onChange={ev => setEntry(i, { round_name: ev.target.value })}
                                        data-testid={`score-round-${i}`}
                                        className="w-full mt-0.5 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600">
                                        <option value="">— select —</option>
                                        {rounds.map(rn => <option key={rn} value={rn}>{rn}</option>)}
                                        {/* Allow legacy round names not currently in dropdown */}
                                        {e.round_name && !rounds.includes(e.round_name) && (
                                            <option value={e.round_name}>{e.round_name} (legacy)</option>
                                        )}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[11px] text-zinc-500">Date</label>
                                    <input type="date" value={e.date} onChange={ev => setEntry(i, { date: ev.target.value })}
                                        data-testid={`score-date-${i}`}
                                        className="w-full mt-0.5 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600" />
                                </div>
                                <div>
                                    <label className="text-[11px] text-zinc-500">Score</label>
                                    <input type="number" step="0.01" value={e.score} onChange={ev => setEntry(i, { score: ev.target.value })}
                                        data-testid={`score-value-${i}`}
                                        className="w-full mt-0.5 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600" />
                                </div>
                                <div>
                                    <label className="text-[11px] text-zinc-500">Status</label>
                                    <select value={e.status} onChange={ev => setEntry(i, { status: ev.target.value })}
                                        data-testid={`score-status-${i}`}
                                        className="w-full mt-0.5 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600">
                                        <option value="">— select —</option>
                                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-[11px] text-zinc-500">Command</label>
                                <textarea rows={2} value={e.command} onChange={ev => setEntry(i, { command: ev.target.value })}
                                    data-testid={`score-command-${i}`}
                                    placeholder="Round-related notes / comments"
                                    className="w-full mt-0.5 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-600" />
                            </div>
                        </div>
                    ))}
                </div>
                <div className="flex items-center justify-between pt-2">
                    <button onClick={addMore} data-testid="add-more-round-btn"
                        className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm text-white">
                        <Plus size={14} /> Add More
                    </button>
                    <div className="flex gap-2">
                        <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm text-white">Cancel</button>
                        <button onClick={save} disabled={saving} data-testid="save-scores-btn"
                            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-sm text-white font-medium">
                            {saving ? 'Saving…' : 'Save'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// --- Update Date Modal (3 dates) ---
function UpdateDateModal({ row, onClose, onSaved }) {
    const [doj, setDoj] = useState(row.date_of_joining || '');
    const [dod, setDod] = useState(row.date_of_documentation || '');
    const [doi, setDoi] = useState(row.date_of_induction || '');
    const [saving, setSaving] = useState(false);

    const save = async () => {
        setSaving(true);
        try {
            await axios.put(`${API}/api/bb/score-round/save-dates`, {
                email: row.email,
                date_of_joining: doj,
                date_of_documentation: dod,
                date_of_induction: doi,
            }, { withCredentials: true });
            toast.success('Dates updated');
            onSaved?.();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed');
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" data-testid="update-date-modal">
            <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md p-6 space-y-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold text-white">Update Dates — {row.name || row.email}</h2>
                        <p className="text-xs text-zinc-500 mt-0.5">{row.email}</p>
                    </div>
                    <button onClick={onClose} data-testid="update-date-close" className="text-zinc-500 hover:text-white"><X size={20} /></button>
                </div>
                <div className="space-y-3">
                    <div>
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Date of Joining</label>
                        <input type="date" value={doj} onChange={e => setDoj(e.target.value)} data-testid="doj-input"
                            className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-600" />
                    </div>
                    <div>
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Date of Documentation</label>
                        <input type="date" value={dod} onChange={e => setDod(e.target.value)} data-testid="dod-input"
                            className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-600" />
                    </div>
                    <div>
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Date of Induction</label>
                        <input type="date" value={doi} onChange={e => setDoi(e.target.value)} data-testid="doi-input"
                            className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-600" />
                    </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm text-white">Cancel</button>
                    <button onClick={save} disabled={saving} data-testid="save-dates-btn"
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-sm text-white font-medium">
                        {saving ? 'Saving…' : 'Save'}
                    </button>
                </div>
            </div>
        </div>
    );
}

// --- Main Page ---
export default function ScoreRound() {
    const navigate = useNavigate();
    const [rows, setRows] = useState([]);
    const [rounds, setRounds] = useState([]);
    const [loading, setLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [limit] = useState(50);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [search, setSearch] = useState('');
    const [searchInput, setSearchInput] = useState('');
    const [showManage, setShowManage] = useState(false);
    const [scoreRow, setScoreRow] = useState(null);
    const [dateRow, setDateRow] = useState(null);
    const [actionMenuFor, setActionMenuFor] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await axios.get(`${API}/api/bb/score-round/table`, {
                params: { page, limit, q: search || undefined },
                withCredentials: true,
            });
            setRows(r.data.data || []);
            setRounds(r.data.rounds || []);
            setTotal(r.data.total || 0);
            setTotalPages(r.data.totalPages || 1);
        } catch (e) { toast.error('Failed to load'); }
        finally { setLoading(false); }
    }, [page, limit, search]);
    useEffect(() => { load(); }, [load]);

    const onSearch = () => { setPage(1); setSearch(searchInput.trim()); };

    const cellForRound = (row, roundName) => {
        const canon = roundName.replace(/\s+/g, ' ').trim().toLowerCase();
        const entry = row.rounds_map?.[canon];
        if (!entry || (entry.score === null || entry.score === undefined || entry.score === '')) {
            return <span className="text-zinc-700">—</span>;
        }
        const tooltip = [
            entry.date ? `Date: ${fmtDDMMYYYY(entry.date)}` : null,
            entry.status ? `Status: ${entry.status}` : null,
            entry.command ? `Command: ${entry.command}` : null,
        ].filter(Boolean).join('\n') || 'No additional info';
        return (
            <span className="group relative inline-flex items-center gap-1 cursor-help" data-testid={`round-cell-${row.email}-${canon}`}>
                <span className="font-medium">{entry.score}</span>
                <Eye size={11} className="opacity-0 group-hover:opacity-100 transition-opacity text-cyan-400" />
                <span className="absolute left-0 top-full mt-1 hidden group-hover:block z-30 bg-zinc-950 border border-zinc-700 px-2 py-1 text-[11px] text-white whitespace-pre-wrap min-w-[180px] shadow-lg">{tooltip}</span>
            </span>
        );
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="score-round-page">
            <header className="border-b border-zinc-800 px-6 py-4 flex items-center gap-4 flex-wrap">
                <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={18} /></button>
                <h1 className="text-lg font-semibold tracking-tight">Score &amp; Round</h1>
                <span className="text-xs text-zinc-500">{total} candidate{total === 1 ? '' : 's'}</span>
                <div className="ml-auto flex items-center gap-2">
                    <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 px-2">
                        <MagnifyingGlass size={14} className="text-zinc-500" />
                        <input value={searchInput} onChange={e => setSearchInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && onSearch()}
                            placeholder="Search name / email / phone"
                            data-testid="search-input"
                            className="bg-transparent text-sm py-1.5 px-1 w-64 focus:outline-none placeholder-zinc-600" />
                        <button onClick={onSearch} className="text-cyan-400 hover:text-cyan-300 text-xs px-1">Go</button>
                    </div>
                    <button onClick={() => setShowManage(true)} data-testid="manage-rounds-btn"
                        className="flex items-center gap-2 px-3 py-2 bg-cyan-700 hover:bg-cyan-600 text-sm font-medium">
                        <Sliders size={16} /> Add Rounds
                    </button>
                </div>
            </header>

            <div className="overflow-auto" style={{ maxHeight: 'calc(100vh - 130px)' }}>
                <table className="text-xs whitespace-nowrap" data-testid="score-round-table">
                    <thead className="sticky top-0 z-20 bg-zinc-900 shadow-md">
                        <tr className="border-b border-zinc-800">
                            <th className="sticky left-0 z-30 bg-zinc-900 text-left px-3 py-2 font-medium text-zinc-400 uppercase tracking-wider">Action</th>
                            {['Name', 'Schedule Date', 'College', 'Degree', 'Course', 'YOG', 'Email', 'Phone', 'Job Role', 'Status'].map(h => (
                                <th key={h} className="text-left px-3 py-2 font-medium text-zinc-400 uppercase tracking-wider">{h}</th>
                            ))}
                            {rounds.map(rn => (
                                <th key={rn} className="text-left px-3 py-2 font-medium text-cyan-400 uppercase tracking-wider" title={rn}>{rn}</th>
                            ))}
                            <th className="text-left px-3 py-2 font-medium text-amber-400 uppercase tracking-wider">DOJ</th>
                            <th className="text-left px-3 py-2 font-medium text-amber-400 uppercase tracking-wider">DOD</th>
                            <th className="text-left px-3 py-2 font-medium text-amber-400 uppercase tracking-wider">DOI</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && <tr><td colSpan={11 + rounds.length + 3} className="text-center py-8 text-zinc-500">Loading…</td></tr>}
                        {!loading && rows.length === 0 && <tr><td colSpan={11 + rounds.length + 3} className="text-center py-12 text-zinc-500">No candidates found.</td></tr>}
                        {!loading && rows.map((row, idx) => (
                            <tr key={`${row.email}-${idx}`} className="border-b border-zinc-900 hover:bg-zinc-900/50" data-testid={`row-${idx}`}>
                                <td className="sticky left-0 bg-[#0a0a0a] hover:bg-zinc-900 px-2 py-1.5 z-10">
                                    <div className="relative">
                                        <button onClick={() => setActionMenuFor(actionMenuFor === idx ? null : idx)}
                                            data-testid={`action-btn-${idx}`}
                                            className="flex items-center gap-1 px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-[11px]">
                                            Action <CaretDown size={10} />
                                        </button>
                                        {actionMenuFor === idx && (
                                            <div className="absolute left-0 top-full mt-1 z-40 bg-zinc-900 border border-zinc-700 min-w-[160px] shadow-xl">
                                                <button onClick={() => { setScoreRow(row); setActionMenuFor(null); }}
                                                    data-testid={`action-update-score-${idx}`}
                                                    className="block w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800">1. Update Score</button>
                                                <button onClick={() => { setDateRow(row); setActionMenuFor(null); }}
                                                    data-testid={`action-update-date-${idx}`}
                                                    className="block w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800">2. Update Date</button>
                                            </div>
                                        )}
                                    </div>
                                </td>
                                <td className="px-3 py-1.5 font-medium">{row.name || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{fmtDDMMYYYY(row.schedule_date) || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.college || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.degree || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.course || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.year_of_graduation || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.email || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.phone || '—'}</td>
                                <td className="px-3 py-1.5 text-zinc-400">{row.job_role || '—'}</td>
                                <td className="px-3 py-1.5"><span className="text-[10px] uppercase bg-zinc-800 text-zinc-300 px-1.5 py-0.5">{row.status || '—'}</span></td>
                                {rounds.map(rn => (
                                    <td key={rn} className="px-3 py-1.5 text-zinc-300">{cellForRound(row, rn)}</td>
                                ))}
                                <td className="px-3 py-1.5 text-amber-200">{fmtDDMMYYYY(row.date_of_joining) || '—'}</td>
                                <td className="px-3 py-1.5 text-amber-200">{fmtDDMMYYYY(row.date_of_documentation) || '—'}</td>
                                <td className="px-3 py-1.5 text-amber-200">{fmtDDMMYYYY(row.date_of_induction) || '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="border-t border-zinc-800 px-6 py-3 flex items-center justify-between text-xs">
                <span className="text-zinc-500">Page {page} of {totalPages}</span>
                <div className="flex gap-2">
                    <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || loading}
                        data-testid="page-prev"
                        className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 disabled:opacity-40">Prev</button>
                    <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages || loading}
                        data-testid="page-next"
                        className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 disabled:opacity-40">Next</button>
                </div>
            </div>

            {showManage && <ManageRoundsModal onClose={() => setShowManage(false)} onChanged={load} />}
            {scoreRow && <UpdateScoreModal row={scoreRow} rounds={rounds} onClose={() => setScoreRow(null)} onSaved={load} />}
            {dateRow && <UpdateDateModal row={dateRow} onClose={() => setDateRow(null)} onSaved={load} />}
        </div>
    );
}
