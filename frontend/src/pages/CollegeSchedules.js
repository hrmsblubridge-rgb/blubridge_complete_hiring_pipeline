import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, ArrowCounterClockwise } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function CollegeSchedules() {
    const navigate = useNavigate();
    const [schedules, setSchedules] = useState([]);
    const [showInactive, setShowInactive] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    // Iter56 — job_roles is an array of chips; legacy single-string rows split on edit
    const [form, setForm] = useState({ college_name: '', job_roles: [], schedule_date: '', schedule_time: '', notes: '' });
    const [roleInput, setRoleInput] = useState('');
    const [loading, setLoading] = useState(false);

    const fetchSchedules = useCallback(async (incInactive = false) => {
        setLoading(true);
        try {
            const r = await axios.get(`${API}/api/bb/college-schedules`, {
                params: incInactive ? { includeInactive: true } : {},
                withCredentials: true,
            });
            setSchedules(r.data.schedules || []);
        } catch { toast.error('Failed to load'); }
        finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchSchedules(showInactive); }, [fetchSchedules, showInactive]);

    const openCreate = () => {
        setEditId(null);
        setForm({ college_name: '', job_roles: [], schedule_date: '', schedule_time: '', notes: '' });
        setRoleInput('');
        setShowModal(true);
    };

    const openEdit = (s) => {
        setEditId(s.id);
        // Iter56 — load job_roles array; fall back to splitting legacy job_role string
        const roles = Array.isArray(s.job_roles) && s.job_roles.length
            ? s.job_roles
            : (s.job_role ? s.job_role.split(',').map(r => r.trim()).filter(Boolean) : []);
        setForm({
            college_name: s.college_name || '',
            job_roles: roles,
            schedule_date: s.schedule_date || '',
            schedule_time: (s.schedule_time || '').slice(0, 5),
            notes: s.notes || '',
        });
        setRoleInput('');
        setShowModal(true);
    };

    // Iter56 — chip helpers
    const addRoleChip = (raw) => {
        const v = (raw || '').trim();
        if (!v) return;
        setForm(p => {
            const exists = p.job_roles.some(r => r.toLowerCase() === v.toLowerCase());
            if (exists) return p;
            return { ...p, job_roles: [...p.job_roles, v] };
        });
        setRoleInput('');
    };
    const removeRoleChip = (idx) => {
        setForm(p => ({ ...p, job_roles: p.job_roles.filter((_, i) => i !== idx) }));
    };
    const onRoleKey = (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            addRoleChip(roleInput);
        } else if (e.key === 'Backspace' && !roleInput && form.job_roles.length) {
            setForm(p => ({ ...p, job_roles: p.job_roles.slice(0, -1) }));
        }
    };

    const save = async () => {
        // Iter56 — flush any text still in the input as a final chip
        const pending = roleInput.trim();
        const roles = pending ? [...form.job_roles, pending] : [...form.job_roles];
        // de-dupe (case-insensitive) preserving first-seen casing
        const seen = new Set();
        const deduped = [];
        for (const r of roles) {
            const k = r.toLowerCase();
            if (!seen.has(k)) { seen.add(k); deduped.push(r); }
        }
        if (!form.college_name.trim() || deduped.length === 0 || !form.schedule_date || !form.schedule_time) {
            toast.error('College, at least one Job Role, Date and Time are required');
            return;
        }
        const payload = {
            college_name: form.college_name,
            job_roles: deduped,
            schedule_date: form.schedule_date,
            schedule_time: form.schedule_time,
            notes: form.notes,
        };
        try {
            if (editId) {
                await axios.put(`${API}/api/bb/college-schedules/${editId}`, payload, { withCredentials: true });
                toast.success('Updated');
            } else {
                await axios.post(`${API}/api/bb/college-schedules`, payload, { withCredentials: true });
                toast.success('Created');
            }
            setShowModal(false);
            fetchSchedules(showInactive);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed');
        }
    };

    const disable = async (s) => {
        if (!window.confirm(`Disable schedule for ${s.college_name} – ${s.job_role}? It can be restored later.`)) return;
        try {
            await axios.delete(`${API}/api/bb/college-schedules/${s.id}`, { withCredentials: true });
            toast.success('Disabled');
            fetchSchedules(showInactive);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };

    const restore = async (s) => {
        try {
            await axios.post(`${API}/api/bb/college-schedules/${s.id}/restore`, {}, { withCredentials: true });
            toast.success('Restored');
            fetchSchedules(showInactive);
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };

    const formatTime = (t) => {
        if (!t) return '-';
        const parts = t.split(':');
        if (parts.length < 2) return t;
        const h = parseInt(parts[0], 10);
        const m = parts[1];
        const period = h < 12 ? 'AM' : 'PM';
        const h12 = h % 12 || 12;
        return `${String(h12).padStart(2, '0')}:${m} ${period}`;
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="college-schedules-page">
            <header className="border-b border-zinc-800 px-6 py-4 flex items-center gap-4">
                <button onClick={() => navigate('/home')} data-testid="back-btn" className="text-zinc-400 hover:text-white"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold">College Interview Schedules</h1>
                <button onClick={openCreate} data-testid="add-schedule-btn" className="ml-auto flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">
                    <Plus size={16} /> Add Schedule
                </button>
            </header>

            <div className="px-6 py-4 flex items-center gap-3 text-sm">
                <span className="text-zinc-400">{schedules.filter(s => s.active !== false).length} active{showInactive ? ` · ${schedules.filter(s => s.active === false).length} inactive` : ''}</span>
                <button onClick={() => setShowInactive(!showInactive)} data-testid="toggle-inactive-btn" className="text-cyan-400 hover:text-cyan-300">
                    {showInactive ? 'Hide inactive' : 'Show inactive'}
                </button>
                <a href="/register/college" target="_blank" rel="noreferrer" className="ml-auto text-cyan-400 hover:text-cyan-300 underline" data-testid="public-form-link">
                    Public registration form ↗
                </a>
            </div>

            <div className="px-6 pb-12 overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-zinc-900 border-b border-zinc-800">
                            {['College', 'Job Role', 'Schedule Date', 'Schedule Time', 'Notes', 'Status', 'Actions'].map(h => (
                                <th key={h} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider">{h}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {loading && <tr><td colSpan={7} className="text-center py-8 text-zinc-500">Loading…</td></tr>}
                        {!loading && schedules.length === 0 && <tr><td colSpan={7} className="text-center py-12 text-zinc-500">No schedules yet. Click "Add Schedule" to create the first mapping.</td></tr>}
                        {!loading && schedules.map(s => {
                            const inactive = s.active === false;
                            return (
                                <tr key={s.id} data-testid={`schedule-row-${s.id}`} className={`border-b border-zinc-900 hover:bg-zinc-900/50 ${inactive ? 'opacity-60' : ''}`}>
                                    <td className="px-4 py-3 font-medium">{s.college_name}</td>
                                    <td className="px-4 py-3">
                                        {Array.isArray(s.job_roles) && s.job_roles.length > 0 ? (
                                            <div className="flex flex-wrap gap-1">
                                                {s.job_roles.map((r, i) => (
                                                    <span key={`${r}-${i}`} className="inline-block bg-cyan-900/40 border border-cyan-700/50 text-cyan-200 px-1.5 py-0.5 text-[11px] rounded">{r}</span>
                                                ))}
                                            </div>
                                        ) : (s.job_role || '-')}
                                    </td>
                                    <td className="px-4 py-3">{s.schedule_date}</td>
                                    <td className="px-4 py-3">{formatTime(s.schedule_time)}</td>
                                    <td className="px-4 py-3 text-zinc-400 text-xs">{s.notes || '-'}</td>
                                    <td className="px-4 py-3">
                                        <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${inactive ? 'bg-zinc-800 text-zinc-500' : 'bg-emerald-900/40 text-emerald-300'}`}>
                                            {inactive ? 'Inactive' : 'Active'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-2">
                                            {inactive ? (
                                                <button onClick={() => restore(s)} data-testid={`restore-${s.id}`} className="p-1 text-zinc-400 hover:text-emerald-400" title="Restore"><ArrowCounterClockwise size={14} /></button>
                                            ) : (
                                                <>
                                                    <button onClick={() => openEdit(s)} data-testid={`edit-${s.id}`} className="p-1 text-zinc-500 hover:text-white" title="Edit"><PencilSimple size={14} /></button>
                                                    <button onClick={() => disable(s)} data-testid={`disable-${s.id}`} className="p-1 text-zinc-500 hover:text-red-400" title="Disable"><Trash size={14} /></button>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" data-testid="schedule-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md p-6 space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold">{editId ? 'Edit Schedule' : 'Add College Schedule'}</h2>
                            <button onClick={() => setShowModal(false)} className="text-zinc-500 hover:text-white"><X size={20} /></button>
                        </div>

                        <div className="space-y-3">
                            <div>
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">College Name</label>
                                <input type="text" value={form.college_name} onChange={e => setForm(p => ({ ...p, college_name: e.target.value }))}
                                    placeholder="e.g. Anna University" data-testid="college-input"
                                    className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                            </div>
                            <div>
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role(s)</label>
                                <div data-testid="role-chip-container"
                                    className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm focus-within:border-zinc-500 flex flex-wrap items-center gap-1 min-h-[40px]"
                                    onClick={() => document.getElementById('role-chip-input')?.focus()}>
                                    {form.job_roles.map((r, i) => (
                                        <span key={`${r}-${i}`} data-testid={`role-chip-${i}`}
                                            className="inline-flex items-center gap-1 bg-cyan-900/40 border border-cyan-700/50 text-cyan-200 px-2 py-0.5 text-xs rounded">
                                            {r}
                                            <button type="button" onClick={(e) => { e.stopPropagation(); removeRoleChip(i); }}
                                                data-testid={`role-chip-remove-${i}`}
                                                className="text-cyan-400 hover:text-white" aria-label={`Remove ${r}`}>
                                                <X size={12} />
                                            </button>
                                        </span>
                                    ))}
                                    <input id="role-chip-input" type="text" value={roleInput}
                                        onChange={e => setRoleInput(e.target.value)}
                                        onKeyDown={onRoleKey}
                                        onBlur={() => roleInput.trim() && addRoleChip(roleInput)}
                                        placeholder={form.job_roles.length === 0 ? 'Type a role and press Enter (e.g. AI/ML)' : 'Add another…'}
                                        data-testid="role-input"
                                        className="flex-1 min-w-[120px] bg-transparent outline-none text-sm py-0.5" />
                                </div>
                                <p className="text-[11px] text-zinc-500 mt-1">Press <b>Enter</b> or <b>,</b> to add. Backspace removes the last chip.</p>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs text-zinc-500 uppercase tracking-wider">Date</label>
                                    <input type="date" value={form.schedule_date} onChange={e => setForm(p => ({ ...p, schedule_date: e.target.value }))} data-testid="date-input"
                                        className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                                </div>
                                <div>
                                    <label className="text-xs text-zinc-500 uppercase tracking-wider">Time</label>
                                    <input type="time" value={form.schedule_time} onChange={e => setForm(p => ({ ...p, schedule_time: e.target.value }))} data-testid="time-input"
                                        className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Notes (optional)</label>
                                <input type="text" value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                                    placeholder="e.g. Drive at college campus" data-testid="notes-input"
                                    className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 pt-2">
                            <button onClick={() => setShowModal(false)} data-testid="cancel-modal-btn" className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={save} data-testid="save-modal-btn" className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">{editId ? 'Update' : 'Create'}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
