import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, FolderOpen, Link as LinkIcon, Copy } from '@phosphor-icons/react';
import LifecycleControl, { StatusDot } from '../components/LifecycleControl';

const API = process.env.REACT_APP_BACKEND_URL;

export default function JobOpenings() {
    const navigate = useNavigate();
    const [openings, setOpenings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editId, setEditId] = useState(null);
    const [formTitle, setFormTitle] = useState('');
    const [formRole, setFormRole] = useState('');
    const [formVacancies, setFormVacancies] = useState('');
    const [formYears, setFormYears] = useState([]);
    const [yearInput, setYearInput] = useState('');
    const [formEdu, setFormEdu] = useState([]);
    const [eduInput, setEduInput] = useState('');
    const [formSalary, setFormSalary] = useState('');
    // iter108 — Dynamic descriptive sections replace the 3 fixed textareas.
    // Each section: { title, description }. At least one card always exists.
    const [formSections, setFormSections] = useState([{ title: '', description: '' }]);
    const [jobRoles, setJobRoles] = useState([]);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [oRes, rRes] = await Promise.all([
                axios.get(`${API}/api/bb/job-openings`, { withCredentials: true }),
                axios.get(`${API}/api/bb/job-roles?active_only=true`, { withCredentials: true }),
            ]);
            setOpenings(oRes.data.openings || []);
            setJobRoles(rRes.data.roles || []);
        } catch {} finally { setLoading(false); }
    }, []);
    useEffect(() => { fetchAll(); }, [fetchAll]);

    const openAdd = () => { setEditId(null); setFormTitle(''); setFormRole(''); setFormVacancies(''); setFormYears([]); setYearInput(''); setFormEdu([]); setEduInput(''); setFormSalary(''); setFormSections([{ title: '', description: '' }]); setShowModal(true); };
    const openEdit = (o) => {
        setEditId(o.id);
        setFormTitle(o.title);
        setFormRole(o.job_role || '');
        setFormVacancies(o.vacancies ? String(o.vacancies) : '');
        setFormYears(o.years_of_graduation || []);
        setYearInput('');
        setFormEdu(o.education || []);
        setEduInput('');
        setFormSalary(o.salary_range || '');
        // iter108 — Backend always emits `descriptive_sections` (synthesized
        // from legacy fields for old rows). Guarantee at least one editable card.
        const sections = (Array.isArray(o.descriptive_sections) && o.descriptive_sections.length > 0)
            ? o.descriptive_sections.map(s => ({ title: s.title || '', description: s.description || '' }))
            : [{ title: '', description: '' }];
        setFormSections(sections);
        setShowModal(true);
    };

    const addSection = () => setFormSections(p => [...p, { title: '', description: '' }]);
    const removeSection = (idx) => setFormSections(p => p.length > 1 ? p.filter((_, i) => i !== idx) : p);
    const updateSection = (idx, field, value) => setFormSections(p => p.map((s, i) => i === idx ? { ...s, [field]: value } : s));

    const addYear = () => { const v = yearInput.trim(); if (v && !formYears.includes(v)) setFormYears(p => [...p, v]); setYearInput(''); };
    const addEdu = () => { const v = eduInput.trim(); if (v && !formEdu.includes(v)) setFormEdu(p => [...p, v]); setEduInput(''); };

    const handleSave = async () => {
        if (!formTitle.trim()) { toast.error('Title required'); return; }
        try {
            // iter108 — Strip empty cards before sending; backend auto-mirrors
            // first 3 sections to legacy fields for backward compatibility.
            const cleanedSections = formSections
                .map(s => ({ title: (s.title || '').trim(), description: (s.description || '').trim() }))
                .filter(s => s.title || s.description);
            const body = {
                title: formTitle.trim(),
                job_role: formRole,
                vacancies: formVacancies ? Number(formVacancies) : null,
                years_of_graduation: formYears,
                education: formEdu,
                salary_range: formSalary,
                descriptive_sections: cleanedSections,
            };
            if (editId) await axios.put(`${API}/api/bb/job-openings/${editId}`, body, { withCredentials: true });
            else await axios.post(`${API}/api/bb/job-openings`, body, { withCredentials: true });
            toast.success(editId ? 'Updated' : 'Created'); setShowModal(false); fetchAll();
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };

    const handleDelete = async (id) => {
        try { await axios.delete(`${API}/api/bb/job-openings/${id}`, { withCredentials: true }); toast.success('Deleted'); fetchAll(); } catch { toast.error('Failed'); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="job-openings-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Create Job Openings</h1>
                <button onClick={openAdd} data-testid="add-opening-btn" className="ml-auto flex items-center gap-2 px-4 py-2 bg-rose-700 hover:bg-rose-600 text-sm font-medium"><Plus size={16} /> Add New Job Opening</button>
            </header>
            <main className="max-w-3xl mx-auto px-6 py-8">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                 openings.length === 0 ? <div className="text-center py-20 text-zinc-600" data-testid="empty-state"><FolderOpen size={48} className="mx-auto mb-4 text-zinc-700" /><p>No job openings yet.</p></div> :
                 <div className="space-y-3" data-testid="openings-list">
                    {openings.map(o => (
                        <div key={o.id} className="bg-zinc-900 border border-zinc-800 p-5" data-testid={`opening-${o.id}`}>
                            <div className="flex items-start justify-between">
                                <div className="space-y-1">
                                    <div className="flex items-center gap-2">
                                        <StatusDot status={o.status} testId={`opening-${o.id}-status-dot`} />
                                        <h3 className="font-medium">{o.title}</h3>
                                    </div>
                                    <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                                        {o.job_role && <span>Role: {o.job_role}</span>}
                                        {o.vacancies && <span>Vacancies: {o.vacancies}</span>}
                                        {o.salary_range && <span>Salary: {o.salary_range}</span>}
                                    </div>
                                    {o.years_of_graduation?.length > 0 && <div className="flex gap-1 mt-1">{o.years_of_graduation.map((y, i) => <span key={i} className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded">{y}</span>)}</div>}
                                    {o.education?.length > 0 && <div className="flex gap-1 mt-1">{o.education.map((e, i) => <span key={i} className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded">{e}</span>)}</div>}
                                </div>
                                <div className="flex gap-2 shrink-0">
                                    <LifecycleControl entity="job-openings" id={o.id} name={o.title} status={o.status} onChanged={fetchAll} testIdPrefix={`opening-${o.id}-lifecycle`} />
                                    <a href={`/jobs/view/${o.slug || o.id}`} target="_blank" rel="noreferrer"
                                        data-testid={`opening-link-${o.id}`}
                                        title="Open Public Job Description"
                                        className="p-2 text-zinc-500 hover:text-cyan-400 hover:bg-zinc-800"><LinkIcon size={16} /></a>
                                    <button
                                        onClick={() => {
                                            // iter96/iter100 — Prefer slug for clean shareable URLs;
                                            // fall back to ObjectId for any row whose slug back-fill
                                            // is still in flight (the GET /job-openings listing
                                            // lazy-fills it on first fetch so this is rare).
                                            const url = `${window.location.origin}/jobs/view/${o.slug || o.id}`;
                                            navigator.clipboard.writeText(url)
                                                .then(() => toast.success(`Copied: ${url}`))
                                                .catch(() => toast.error('Clipboard write failed'));
                                        }}
                                        data-testid={`opening-copy-link-${o.id}`}
                                        title="Copy Public Job Description URL"
                                        className="p-2 text-zinc-500 hover:text-emerald-400 hover:bg-zinc-800"><Copy size={16} /></button>
                                    <button onClick={() => openEdit(o)} data-testid={`opening-edit-${o.id}`} className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800"><PencilSimple size={16} /></button>
                                    <button onClick={() => handleDelete(o.id)} data-testid={`opening-delete-${o.id}`} className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800"><Trash size={16} /></button>
                                </div>
                            </div>
                        </div>
                    ))}
                 </div>}
            </main>
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="opening-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-xl mx-4 p-6 space-y-4 max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{editId ? 'Edit Job Opening' : 'Add New Job Opening'}</h2><button onClick={() => setShowModal(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role</label>
                            <select value={formRole} onChange={e => setFormRole(e.target.value)} data-testid="opening-role-select" className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500"><option value="">Select role</option>{jobRoles.map(r => <option key={r.id} value={r.name}>{r.name}</option>)}</select></div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Title</label><input type="text" value={formTitle} onChange={e => setFormTitle(e.target.value)} data-testid="opening-title-input" className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                            <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Vacancies</label><input type="number" value={formVacancies} onChange={e => setFormVacancies(e.target.value)} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                        </div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Year of Graduation</label>
                            <div className="flex gap-2"><input type="text" value={yearInput} onChange={e => setYearInput(e.target.value)} onKeyDown={e => {if(e.key==='Enter'){e.preventDefault();addYear();}}} placeholder="e.g. 2026" className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /><button onClick={addYear} className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-sm"><Plus size={14} /></button></div>
                            {formYears.length > 0 && <div className="flex flex-wrap gap-1.5 mt-1">{formYears.map((y, i) => <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-zinc-800 border border-zinc-700 rounded-full">{y}<button onClick={() => setFormYears(p => p.filter((_,idx) => idx!==i))} className="hover:text-red-400"><X size={10} /></button></span>)}</div>}</div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Education</label>
                            <div className="flex gap-2"><input type="text" value={eduInput} onChange={e => setEduInput(e.target.value)} onKeyDown={e => {if(e.key==='Enter'){e.preventDefault();addEdu();}}} placeholder="e.g. B.Tech" className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /><button onClick={addEdu} className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-sm"><Plus size={14} /></button></div>
                            {formEdu.length > 0 && <div className="flex flex-wrap gap-1.5 mt-1">{formEdu.map((e, i) => <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-zinc-800 border border-zinc-700 rounded-full">{e}<button onClick={() => setFormEdu(p => p.filter((_,idx) => idx!==i))} className="hover:text-red-400"><X size={10} /></button></span>)}</div>}</div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Salary Range</label><input type="text" value={formSalary} onChange={e => setFormSalary(e.target.value)} placeholder="e.g. 5.0-7.0 LPA" className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                        {/* iter108 — Dynamic Descriptive Sections (replaces the 3 fixed textareas). */}
                        <div className="space-y-3" data-testid="descriptive-sections-block">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Descriptive Sections</label>
                            {formSections.map((s, i) => (
                                <div key={i} className="bg-zinc-800/60 border border-zinc-700 p-3 space-y-2" data-testid={`section-card-${i}`}>
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Section {i + 1}</span>
                                        {formSections.length > 1 && (
                                            <button onClick={() => removeSection(i)} data-testid={`section-remove-${i}`}
                                                className="p-1 text-zinc-500 hover:text-red-400" title="Remove section">
                                                <X size={14} />
                                            </button>
                                        )}
                                    </div>
                                    <input type="text" value={s.title} onChange={e => updateSection(i, 'title', e.target.value)}
                                        placeholder="Section title (e.g. Key Responsibilities)"
                                        data-testid={`section-title-${i}`}
                                        className="w-full bg-zinc-900 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" />
                                    <textarea value={s.description} onChange={e => updateSection(i, 'description', e.target.value)}
                                        rows={3}
                                        placeholder="Section description..."
                                        data-testid={`section-description-${i}`}
                                        className="w-full bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500 resize-none" />
                                </div>
                            ))}
                            <button onClick={addSection} data-testid="section-add-btn"
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300">
                                <Plus size={14} /> Add Section
                            </button>
                        </div>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowModal(false)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={handleSave} data-testid="save-opening-btn" className="px-4 py-2 bg-rose-700 hover:bg-rose-600 text-sm font-medium">{editId ? 'Update' : 'Create'}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
