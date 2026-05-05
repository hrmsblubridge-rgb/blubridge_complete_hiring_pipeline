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
    const [form, setForm] = useState({ college_name: '', job_role: '', schedule_date: '', schedule_time: '', notes: '' });
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
        setForm({ college_name: '', job_role: '', schedule_date: '', schedule_time: '', notes: '' });
        setShowModal(true);
    };

    const openEdit = (s) => {
        setEditId(s.id);
        setForm({
            college_name: s.college_name || '',
            job_role: s.job_role || '',
            schedule_date: s.schedule_date || '',
            schedule_time: (s.schedule_time || '').slice(0, 5),  // HH:MM for input
            notes: s.notes || '',
        });
        setShowModal(true);
    };

    const save = async () => {
        if (!form.college_name.trim() || !form.job_role.trim() || !form.schedule_date || !form.schedule_time) {
            toast.error('All fields except Notes are required');
            return;
        }
        try {
            if (editId) {
                await axios.put(`${API}/api/bb/college-schedules/${editId}`, form, { withCredentials: true });
                toast.success('Updated');
            } else {
                await axios.post(`${API}/api/bb/college-schedules`, form, { withCredentials: true });
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
                                    <td className="px-4 py-3">{s.job_role}</td>
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
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role</label>
                                <input type="text" value={form.job_role} onChange={e => setForm(p => ({ ...p, job_role: e.target.value }))}
                                    placeholder="e.g. AI/ML Engineer" data-testid="role-input"
                                    className="w-full mt-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
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
