import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, CalendarBlank } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function SetHolidays() {
    const navigate = useNavigate();
    const [holidays, setHolidays] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    const [formName, setFormName] = useState('');
    const [formDate, setFormDate] = useState('');

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try { const r = await axios.get(`${API}/api/bb/holidays`, { withCredentials: true }); setHolidays(r.data.holidays || []); }
        catch {} finally { setLoading(false); }
    }, []);
    useEffect(() => { fetchAll(); }, [fetchAll]);

    const openAdd = () => { setEditId(null); setFormName(''); setFormDate(''); setShowModal(true); };
    const openEdit = (h) => { setEditId(h.id); setFormName(h.name); setFormDate(h.date); setShowModal(true); };

    const handleSave = async () => {
        if (!formName.trim() || !formDate) { toast.error('Name and date required'); return; }
        try {
            if (editId) await axios.put(`${API}/api/bb/holidays/${editId}`, { name: formName.trim(), date: formDate }, { withCredentials: true });
            else await axios.post(`${API}/api/bb/holidays`, { name: formName.trim(), date: formDate }, { withCredentials: true });
            toast.success(editId ? 'Updated' : 'Holiday set'); setShowModal(false); fetchAll();
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };

    const handleDelete = async (id) => {
        try { await axios.delete(`${API}/api/bb/holidays/${id}`, { withCredentials: true }); toast.success('Deleted'); fetchAll(); }
        catch { toast.error('Failed'); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="set-holidays-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Set Holidays</h1>
                <button onClick={openAdd} data-testid="add-holiday-btn" className="ml-auto flex items-center gap-2 px-4 py-2 bg-orange-700 hover:bg-orange-600 text-sm font-medium"><Plus size={16} /> Add Holiday</button>
            </header>
            <main className="max-w-3xl mx-auto px-6 py-8">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                 holidays.length === 0 ? <div className="text-center py-20 text-zinc-600" data-testid="empty-state"><CalendarBlank size={48} className="mx-auto mb-4 text-zinc-700" /><p>No holidays set.</p></div> :
                 <div className="space-y-3" data-testid="holidays-list">
                    {holidays.map(h => (
                        <div key={h.id} className="bg-zinc-900 border border-zinc-800 px-5 py-4 flex items-center justify-between" data-testid={`holiday-${h.id}`}>
                            <div><span className="font-medium">{h.name}</span><span className="ml-3 text-sm text-zinc-500">{h.date}</span></div>
                            <div className="flex gap-2">
                                <button onClick={() => openEdit(h)} className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800"><PencilSimple size={16} /></button>
                                <button onClick={() => handleDelete(h.id)} className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800"><Trash size={16} /></button>
                            </div>
                        </div>
                    ))}
                 </div>}
            </main>
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="holiday-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md mx-4 p-6 space-y-5">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{editId ? 'Edit Holiday' : 'Add Holiday'}</h2><button onClick={() => setShowModal(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Holiday Name</label>
                            <input type="text" value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. Republic Day" data-testid="holiday-name-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Date</label>
                            <input type="date" value={formDate} onChange={e => setFormDate(e.target.value)} data-testid="holiday-date-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowModal(false)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={handleSave} data-testid="save-holiday-btn" className="px-4 py-2 bg-orange-700 hover:bg-orange-600 text-sm font-medium">Set holiday</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
