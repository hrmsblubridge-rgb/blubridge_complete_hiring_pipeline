import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, Briefcase } from '@phosphor-icons/react';
import LifecycleControl, { StatusDot } from '../components/LifecycleControl';

const API = process.env.REACT_APP_BACKEND_URL;

export default function ManageJobRoles() {
    const navigate = useNavigate();
    const [roles, setRoles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    const [formName, setFormName] = useState('');

    const fetch_ = useCallback(async () => {
        setLoading(true);
        try {
            const res = await axios.get(`${API}/api/bb/job-roles`, { withCredentials: true });
            setRoles(res.data.roles || []);
        } catch { toast.error('Failed to load'); }
        finally { setLoading(false); }
    }, []);
    useEffect(() => { fetch_(); }, [fetch_]);

    const openAdd = () => { setEditId(null); setFormName(''); setShowModal(true); };
    const openEdit = (r) => { setEditId(r.id); setFormName(r.name); setShowModal(true); };

    const handleSave = async () => {
        if (!formName.trim()) { toast.error('Name required'); return; }
        try {
            if (editId) {
                await axios.put(`${API}/api/bb/job-roles/${editId}`, { name: formName.trim() }, { withCredentials: true });
                toast.success('Updated');
            } else {
                await axios.post(`${API}/api/bb/job-roles`, { name: formName.trim() }, { withCredentials: true });
                toast.success('Created');
            }
            setShowModal(false); fetch_();
        } catch (err) { toast.error(err.response?.data?.detail || 'Failed'); }
    };

    const handleDelete = async (id) => {
        try { await axios.delete(`${API}/api/bb/job-roles/${id}`, { withCredentials: true }); toast.success('Deleted'); fetch_(); }
        catch { toast.error('Failed'); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="manage-job-roles-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800 transition-colors"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Create Job Roles</h1>
                <button onClick={openAdd} data-testid="add-role-btn" className="ml-auto flex items-center gap-2 px-4 py-2 bg-blue-700 hover:bg-blue-600 text-sm font-medium transition-colors"><Plus size={16} /> Add Job Role</button>
            </header>
            <main className="max-w-3xl mx-auto px-6 py-8">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                 roles.length === 0 ? <div className="text-center py-20 text-zinc-600" data-testid="empty-state"><Briefcase size={48} className="mx-auto mb-4 text-zinc-700" /><p>No job roles yet.</p></div> :
                 <div className="space-y-3" data-testid="roles-list">
                    {roles.map(r => (
                        <div key={r.id} className="bg-zinc-900 border border-zinc-800 px-5 py-4 flex flex-wrap items-center justify-between gap-3 relative" data-testid={`role-${r.id}`}>
                            {/* iter132 — flex-wrap + min-w-0 so long role
                                names wrap inside the row and never crush
                                the action buttons off-screen. */}
                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                <StatusDot status={r.status} testId={`role-${r.id}-status-dot`} />
                                <span className="font-medium break-words">{r.name}</span>
                            </div>
                            <div className="flex gap-2 shrink-0 flex-wrap justify-end ml-auto">
                                <LifecycleControl entity="job-roles" id={r.id} name={r.name} status={r.status} onChanged={fetch_} testIdPrefix={`role-${r.id}-lifecycle`} />
                                <button onClick={() => openEdit(r)} data-testid={`edit-${r.id}`} className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors"><PencilSimple size={16} /></button>
                                <button onClick={() => handleDelete(r.id)} data-testid={`delete-${r.id}`} className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors"><Trash size={16} /></button>
                            </div>
                        </div>
                    ))}
                 </div>}
            </main>
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="role-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md mx-4 p-6 space-y-5">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{editId ? 'Edit Job Role' : 'Add Job Role'}</h2><button onClick={() => setShowModal(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="space-y-1.5">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Job Title</label>
                            <input type="text" value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. AI ML Engineer" data-testid="role-name-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" onKeyDown={e => e.key === 'Enter' && handleSave()} />
                        </div>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowModal(false)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={handleSave} data-testid="save-role-btn" className="px-4 py-2 bg-blue-700 hover:bg-blue-600 text-sm font-medium">{editId ? 'Update' : 'Add job role'}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
