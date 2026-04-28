import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Trash, PencilSimple, X, FloppyDisk, Tag, MagnifyingGlass } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function JobsKeywords() {
    const navigate = useNavigate();
    const [mappings, setMappings] = useState([]);
    const [unmatchedTitles, setUnmatchedTitles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    const [formRole, setFormRole] = useState('');
    const [selectedKeywords, setSelectedKeywords] = useState(new Set());
    const [modalSearch, setModalSearch] = useState('');

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [mapRes, titlesRes] = await Promise.all([
                axios.get(`${API}/api/job-keyword-mappings`, { withCredentials: true }),
                axios.get(`${API}/api/job-titles/unmatched`, { withCredentials: true }),
            ]);
            setMappings(mapRes.data.mappings || []);
            setUnmatchedTitles(titlesRes.data.titles || []);
        } catch {
            toast.error('Failed to load data');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const openAdd = () => {
        setEditId(null);
        setFormRole('');
        setSelectedKeywords(new Set());
        setModalSearch('');
        setShowModal(true);
    };

    const openEdit = (mapping) => {
        setEditId(mapping.id);
        setFormRole(mapping.job_role);
        setSelectedKeywords(new Set(mapping.keywords));
        setModalSearch('');
        setShowModal(true);
    };

    const toggleKeyword = (kw) => {
        setSelectedKeywords(prev => {
            const next = new Set(prev);
            if (next.has(kw)) next.delete(kw);
            else next.add(kw);
            return next;
        });
    };

    const handleSave = async () => {
        if (!formRole.trim()) {
            toast.error('Canonical job role name is required');
            return;
        }
        if (selectedKeywords.size === 0) {
            toast.error('Select at least one keyword');
            return;
        }
        try {
            const keywords = Array.from(selectedKeywords);
            if (editId) {
                await axios.put(`${API}/api/job-keyword-mappings/${editId}`, {
                    job_role: formRole.trim(), keywords,
                }, { withCredentials: true });
                toast.success('Mapping updated');
            } else {
                await axios.post(`${API}/api/job-keyword-mappings`, {
                    job_role: formRole.trim(), keywords,
                }, { withCredentials: true });
                toast.success('Mapping created');
            }
            setShowModal(false);
            fetchData();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Save failed');
        }
    };

    const handleDelete = async (id) => {
        try {
            await axios.delete(`${API}/api/job-keyword-mappings/${id}`, { withCredentials: true });
            toast.success('Mapping deleted');
            fetchData();
        } catch {
            toast.error('Delete failed');
        }
    };

    // For the modal: show unmatched titles + current mapping's keywords (if editing)
    const editingMapping = editId ? mappings.find(m => m.id === editId) : null;
    const editKeywords = editingMapping ? editingMapping.keywords : [];
    const availableInModal = [...new Set([...unmatchedTitles, ...editKeywords])];
    const filteredInModal = modalSearch.trim()
        ? availableInModal.filter(t => t.toLowerCase().includes(modalSearch.toLowerCase()))
        : availableInModal;

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="jobs-keywords-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="text-xl font-semibold tracking-tight">Jobs & Keywords</h1>
                <button onClick={openAdd} data-testid="add-mapping-btn"
                    className="ml-auto flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium transition-colors">
                    <Plus size={16} /> Add Mapping
                </button>
            </header>

            <main className="max-w-5xl mx-auto px-6 py-8 space-y-8">
                {/* Existing Mappings */}
                <section>
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest mb-4">Mapped Roles</h2>
                    {loading ? (
                        <div className="text-center py-12 text-zinc-500">Loading...</div>
                    ) : mappings.length === 0 ? (
                        <div className="text-center py-12 text-zinc-600 text-sm" data-testid="no-mappings">No mappings created yet.</div>
                    ) : (
                        <div className="space-y-3">
                            {mappings.map((m) => (
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
                            ))}
                        </div>
                    )}
                </section>

                {/* Unmatched Keywords */}
                <section>
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest mb-4">Unmatched Keywords</h2>
                    {loading ? null : unmatchedTitles.length === 0 ? (
                        <div className="text-center py-12 border border-dashed border-zinc-800 rounded" data-testid="no-unmatched">
                            <Tag size={36} className="mx-auto mb-3 text-zinc-700" />
                            <p className="text-zinc-600 text-sm">All job titles are mapped, or no Naukri data uploaded yet.</p>
                        </div>
                    ) : (
                        <div className="flex flex-wrap gap-2" data-testid="unmatched-keywords-list">
                            {unmatchedTitles.map((t, i) => (
                                <span key={i} className="inline-block px-3 py-1.5 text-xs font-medium bg-amber-900/20 border border-amber-800/40 text-amber-400 rounded-full"
                                    data-testid={`unmatched-keyword-${i}`}>
                                    {t}
                                </span>
                            ))}
                        </div>
                    )}
                </section>
            </main>

            {/* Add/Edit Modal */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="mapping-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-lg mx-4 p-6 space-y-5 max-h-[85vh] flex flex-col">
                        <div className="flex items-center justify-between shrink-0">
                            <h2 className="text-lg font-semibold">{editId ? 'Edit Mapping' : 'Add Mapping'}</h2>
                            <button onClick={() => setShowModal(false)} data-testid="close-modal-btn"
                                className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button>
                        </div>

                        <div className="space-y-1.5 shrink-0">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Canonical Job Role</label>
                            <input type="text" value={formRole} onChange={e => setFormRole(e.target.value)}
                                placeholder="e.g. AI ML Engineer"
                                data-testid="role-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        </div>

                        <div className="space-y-2 flex-1 min-h-0 flex flex-col">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider shrink-0">
                                Select Keywords ({selectedKeywords.size} selected)
                            </label>
                            <div className="relative shrink-0">
                                <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                                <input type="text" value={modalSearch} onChange={e => setModalSearch(e.target.value)}
                                    placeholder="Filter keywords..."
                                    data-testid="modal-search-input"
                                    className="w-full bg-zinc-800 border border-zinc-700 pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                            </div>
                            <div className="flex-1 overflow-y-auto border border-zinc-800 bg-zinc-950 min-h-[120px] max-h-[280px]" data-testid="keyword-checkbox-list">
                                {filteredInModal.length === 0 ? (
                                    <div className="p-4 text-center text-zinc-600 text-sm">
                                        {availableInModal.length === 0 ? 'No unmatched keywords available. Upload Naukri data first.' : 'No keywords match your search.'}
                                    </div>
                                ) : (
                                    filteredInModal.map((kw, i) => (
                                        <label key={kw} className="flex items-center gap-3 px-4 py-2.5 hover:bg-zinc-900/80 cursor-pointer border-b border-zinc-800/50 last:border-0"
                                            data-testid={`keyword-option-${i}`}>
                                            <input type="checkbox"
                                                checked={selectedKeywords.has(kw)}
                                                onChange={() => toggleKeyword(kw)}
                                                data-testid={`keyword-checkbox-${i}`}
                                                className="w-4 h-4 rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-600 focus:ring-offset-0 accent-emerald-500" />
                                            <span className="text-sm text-zinc-300">{kw}</span>
                                        </label>
                                    ))
                                )}
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 pt-2 shrink-0">
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
