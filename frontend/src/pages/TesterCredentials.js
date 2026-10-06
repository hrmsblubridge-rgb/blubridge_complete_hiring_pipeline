/**
 * Tester Credentials (iter67 — Module #5)
 * ---------------------------------------
 * Manage `bb_test_credentials`. Any (email, phone) pair OR-matched here
 * bypasses the 4-month registration cooldown.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, X, PencilSimple, Trash, Flask, ShieldCheck } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function TesterCredentials() {
    const navigate = useNavigate();
    const [items, setItems] = useState([]);
    const [email, setEmail] = useState('');
    const [phone, setPhone] = useState('');
    const [editId, setEditId] = useState(null);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            const r = await axios.get(`${API}/api/bb/manual/test-credentials`, { withCredentials: true });
            setItems(r.data.items || []);
        } catch (e) { toast.error('Failed to load testers'); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const reset = () => { setEmail(''); setPhone(''); setEditId(null); };

    const submit = async () => {
        if (!email || !phone) { toast.error('Both email and phone are required'); return; }
        setBusy(true);
        try {
            if (editId) {
                await axios.put(`${API}/api/bb/manual/test-credentials/${editId}`, { email, phone }, { withCredentials: true });
                toast.success('Tester updated');
            } else {
                await axios.post(`${API}/api/bb/manual/test-credentials`, { email, phone }, { withCredentials: true });
                toast.success('Tester added');
            }
            reset();
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed');
        } finally { setBusy(false); }
    };

    const startEdit = (it) => {
        setEditId(it.id);
        setEmail(it.email);
        setPhone(it.phone);
    };

    const remove = async (it) => {
        if (!window.confirm(`Delete tester ${it.email} / ${it.phone}?`)) return;
        try {
            await axios.delete(`${API}/api/bb/manual/test-credentials/${it.id}`, { withCredentials: true });
            toast.success('Tester deleted');
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Delete failed');
        }
    };

    return (
        <div className="min-h-screen" data-testid="tester-credentials-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-4xl mx-auto flex items-center gap-3 pl-12 lg:pl-0">
                    <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                        <ArrowLeft size={18} className="text-[#1a2332]" />
                    </button>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-pink-100">
                        <Flask size={22} weight="duotone" className="text-pink-700" />
                    </div>
                    <div>
                        <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Add Tester Credentials</h1>
                        <p className="text-xs text-[#6b7280] mt-0.5">Bypass the 4-month registration cooldown for QA recipients</p>
                    </div>
                </div>
            </header>

            <main className="max-w-4xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 flex flex-wrap items-end gap-3">
                    <Field label="Email" value={email} onChange={setEmail} placeholder="tester@example.com" testid="tester-email" />
                    <Field label="Phone" value={phone} onChange={setPhone} placeholder="9876543210" testid="tester-phone" />
                    <button onClick={submit} disabled={busy} data-testid="tester-add-btn"
                        className="px-5 py-2.5 rounded-lg bg-pink-600 hover:bg-pink-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                        <Plus size={16} weight="bold" /> {editId ? 'Update' : 'Add'}
                    </button>
                    <button onClick={reset} data-testid="tester-cancel-btn"
                        className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                        <X size={16} /> Cancel
                    </button>
                </div>

                <div>
                    <div className="flex items-center gap-2 mb-3">
                        <ShieldCheck size={18} weight="duotone" className="text-pink-700" />
                        <h2 className="text-sm font-semibold text-[#1a2332]">Existing Testing Credentials ({items.length})</h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {items.length === 0 && (
                            <p className="text-sm text-[#9b9787] col-span-full">No testers yet. Add one above.</p>
                        )}
                        {items.map((it) => (
                            <div key={it.id} className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4 flex items-center gap-3" data-testid={`tester-row-${it.id}`}>
                                <div className="w-10 h-10 rounded-full bg-pink-100 flex items-center justify-center shrink-0">
                                    <Flask size={18} weight="duotone" className="text-pink-700" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold text-[#1a2332] truncate">{it.email}</p>
                                    <p className="text-xs text-[#6b7280]">{it.phone} {it.is_default && <span className="ml-1 text-[10px] uppercase tracking-wider text-pink-700 font-bold">Default</span>}</p>
                                </div>
                                <button onClick={() => startEdit(it)} title="Edit"
                                    data-testid={`tester-edit-${it.id}`}
                                    className="p-2 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] hover:bg-[#efede5]">
                                    <PencilSimple size={14} className="text-[#1a2332]" />
                                </button>
                                <button onClick={() => remove(it)} title="Delete"
                                    data-testid={`tester-delete-${it.id}`}
                                    className="p-2 rounded-lg border border-rose-200 bg-rose-50 hover:bg-rose-100">
                                    <Trash size={14} className="text-rose-700" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </main>
        </div>
    );
}

function Field({ label, value, onChange, placeholder, testid }) {
    return (
        <div className="flex-1 min-w-[200px]">
            <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</label>
            <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid}
                className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]" />
        </div>
    );
}
