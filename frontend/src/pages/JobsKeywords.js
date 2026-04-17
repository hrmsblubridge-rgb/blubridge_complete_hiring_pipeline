import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Trash, PencilSimple, X, FloppyDisk, Tag } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function JobsKeywords() {
    const navigate = useNavigate();
    const [mappings, setMappings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    const [formRole, setFormRole] = useState('');
    const [formKeywords, setFormKeywords] = useState([]);
    const [keywordInput, setKeywordInput] = useState('');

    const fetchMappings = useCallback(async () => {
        setLoading(true);
        try {
            const res = await axios.get(`${API}/api/job-keyword-mappings`, { withCredentials: true });
            setMappings(res.data.mappings || []);
        } catch {
            toast.error('Failed to load keyword mappings');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchMappings(); }, [fetchMappings]);

    const openAdd = () => {
        setEditId(null);
        setFormRole('');
        setFormKeywords([]);
        setKeywordInput('');
        setShowModal(true);
    };

    const openEdit = (mapping) => {
        setEditId(mapping.id);
        setFormRole(mapping.job_role);
        setFormKeywords([...mapping.keywords]);
        setKeywordInput('');
        setShowModal(true);
    };

    const addKeyword = () => {
        const kw = keywordInput.trim();
        if (kw && !formKeywords.includes(kw)) {
            setFormKeywords(prev => [...prev, kw]);
        }
        setKeywordInput('');
    };

    const removeKeyword = (idx) => {
        setFormKeywords(prev => prev.filter((_, i) => i !== idx));
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            addKeyword();
        }
    };

    const handleSave = async () => {
        if (!formRole.trim()) {
            toast.error('Job role name is required');
            return;
        }
        if (formKeywords.length === 0) {
            toast.error('Add at least one keyword');
            return;
        }
        try {
            if (editId) {
                await axios.put(`${API}/api/job-keyword-mappings/${editId}`, {
                    job_role: formRole.trim(),
                    keywords: formKeywords,
                }, { withCredentials: true });
                toast.success('Mapping updated');
            } else {
                await axios.post(`${API}/api/job-keyword-mappings`, {
                    job_role: formRole.trim(),
                    keywords: formKeywords,
                }, { withCredentials: true });
                toast.success('Mapping created');
            }
            setShowModal(false);
            fetchMappings();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Save failed');
        }
    };

    const handleDelete = async (id) => {
        try {
            await axios.delete(`${API}/api/job-keyword-mappings/${id}`, { withCredentials: true });
            toast.success('Mapping deleted');
            fetchMappings();
        } catch {
            toast.error('Delete failed');
        }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="jobs-keywords-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/dashboard')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="text-xl font-semibold tracking-tight">Jobs & Keywords</h1>
                <button onClick={openAdd} data-testid="add-mapping-btn"
                    className="ml-auto flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium transition-colors">
                    <Plus size={16} /> Add Mapping
                </button>
            </header>

            <main className="max-w-4xl mx-auto px-6 py-8 space-y-4">
                {loading ? (
                    <div className="text-center py-20 text-zinc-500">Loading...</div>
                ) : mappings.length === 0 ? (
                    <div className="text-center py-20" data-testid="empty-state">
                        <Tag size={48} className="mx-auto mb-4 text-zinc-600" />
                        <p className="text-zinc-500 mb-2">No keyword mappings yet.</p>
                        <p className="text-zinc-600 text-sm">Create mappings to group job title variations under canonical roles.</p>
                    </div>
                ) : (
                    mappings.map((m) => (
                        <div key={m.id} className="bg-zinc-900 border border-zinc-800 p-5 flex items-start justify-between gap-4" data-testid={`mapping-${m.id}`}>
                            <div className="flex-1 min-w-0">
                                <h3 className="text-base font-medium mb-2" data-testid={`mapping-role-${m.id}`}>{m.job_role}</h3>
                                <div className="flex flex-wrap gap-2">
                                    {m.keywords.map((kw, i) => (
                                        <span key={i} className="inline-block px-2.5 py-1 text-xs font-medium bg-zinc-800 border border-zinc-700 text-zinc-300 rounded-full"
                                            data-testid={`keyword-pill-${m.id}-${i}`}>
                                            {kw}
                                        </span>
                                    ))}
                                </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                <button onClick={() => openEdit(m)} data-testid={`edit-mapping-${m.id}`}
                                    className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors">
                                    <PencilSimple size={16} />
                                </button>
                                <button onClick={() => handleDelete(m.id)} data-testid={`delete-mapping-${m.id}`}
                                    className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 transition-colors">
                                    <Trash size={16} />
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </main>

            {/* Add/Edit Modal */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="mapping-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg mx-4 p-6 space-y-5">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold">{editId ? 'Edit Mapping' : 'Add Mapping'}</h2>
                            <button onClick={() => setShowModal(false)} data-testid="close-modal-btn"
                                className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button>
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Canonical Job Role</label>
                            <input type="text" value={formRole} onChange={e => setFormRole(e.target.value)}
                                placeholder="e.g. AI & ML Engineer"
                                data-testid="role-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Keywords</label>
                            <div className="flex gap-2">
                                <input type="text" value={keywordInput} onChange={e => setKeywordInput(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    placeholder="Type keyword and press Enter"
                                    data-testid="keyword-input"
                                    className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                                <button onClick={addKeyword} data-testid="add-keyword-btn"
                                    className="px-3 py-2 bg-zinc-700 hover:bg-zinc-600 text-sm transition-colors">
                                    <Plus size={16} />
                                </button>
                            </div>
                            {formKeywords.length > 0 && (
                                <div className="flex flex-wrap gap-2 mt-2" data-testid="keyword-pills">
                                    {formKeywords.map((kw, i) => (
                                        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-emerald-900/30 border border-emerald-800/50 text-emerald-400 rounded-full">
                                            {kw}
                                            <button onClick={() => removeKeyword(i)} data-testid={`remove-keyword-${i}`}
                                                className="hover:text-white"><X size={12} /></button>
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="flex justify-end gap-3 pt-2">
                            <button onClick={() => setShowModal(false)} data-testid="cancel-btn"
                                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors">Cancel</button>
                            <button onClick={handleSave} data-testid="save-mapping-btn"
                                className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium transition-colors">
                                <FloppyDisk size={16} /> {editId ? 'Update' : 'Save'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
