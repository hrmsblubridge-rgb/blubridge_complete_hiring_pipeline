import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, Link as LinkIcon, Copy, CaretDown, CaretRight } from '@phosphor-icons/react';
import LifecycleControl, { StatusDot } from '../components/LifecycleControl';
import ConfirmDeleteModal from '../components/ConfirmDeleteModal';

const API = process.env.REACT_APP_BACKEND_URL;

export default function HiringForms() {
    const navigate = useNavigate();
    const [formTypes, setFormTypes] = useState([]);
    const [forms, setForms] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showTypeModal, setShowTypeModal] = useState(false);
    const [showFormModal, setShowFormModal] = useState(false);
    const [editTypeId, setEditTypeId] = useState(null);
    const [typeName, setTypeName] = useState('');
    const [editFormId, setEditFormId] = useState(null);
    const [formName, setFormName] = useState('');
    const [formTypeId, setFormTypeId] = useState('');
    const [formJobRole, setFormJobRole] = useState('');
    const [cond, setCond] = useState({ age_min: '', age_max: '', grad_year_min: '', grad_year_max: '', locations: [], location_change: 'NA', attend_in_person: 'NA', college_limit: 'Both' });
    const [locInput, setLocInput] = useState('');
    const [jobRoles, setJobRoles] = useState([]);
    const [jdAttached, setJdAttached] = useState(false);
    const [jdOpeningId, setJdOpeningId] = useState('');
    const [jobOpenings, setJobOpenings] = useState([]);
    const [showInstructionPage, setShowInstructionPage] = useState(false);
    const [instructionContent, setInstructionContent] = useState('');
    // iter146 — delete-confirmation target (forms only; form-types not in scope this iter).
    const [deleteFormTarget, setDeleteFormTarget] = useState(null); // {id, name} | null
    // iter146b — Hiring Forms page form-types deletion modal.
    const [deleteTypeTarget, setDeleteTypeTarget] = useState(null); // {id, name} | null
    // iter150 — Forms section now groups by form type. Each section header
    // expands to reveal that type's cards. The set of headers is derived
    // live from `formTypes`, so adding/removing a type from the database
    // adds/removes its header automatically on the next refresh.
    // Map<form_type_id, boolean> — `true` = expanded.
    const [expandedTypes, setExpandedTypes] = useState({});
    const toggleType = (typeId) => setExpandedTypes(p => ({ ...p, [typeId]: !p[typeId] }));

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [tRes, fRes, rRes, oRes] = await Promise.all([
                axios.get(`${API}/api/bb/form-types`, { withCredentials: true }),
                axios.get(`${API}/api/bb/hiring-forms`, { withCredentials: true }),
                axios.get(`${API}/api/bb/job-roles?active_only=true`, { withCredentials: true }),
                axios.get(`${API}/api/bb/job-openings?active_only=true`, { withCredentials: true }),
            ]);
            setFormTypes(tRes.data.form_types || []);
            setForms(fRes.data.forms || []);
            setJobRoles(rRes.data.roles || []);
            setJobOpenings(oRes.data.openings || []);
        } catch {} finally { setLoading(false); }
    }, []);
    useEffect(() => { fetchAll(); }, [fetchAll]);

    // Form Types
    const openAddType = () => { setEditTypeId(null); setTypeName(''); setShowTypeModal(true); };
    const openEditType = (t) => { setEditTypeId(t.id); setTypeName(t.name); setShowTypeModal(true); };
    const saveType = async () => {
        if (!typeName.trim()) { toast.error('Name required'); return; }
        try {
            if (editTypeId) await axios.put(`${API}/api/bb/form-types/${editTypeId}`, { name: typeName.trim() }, { withCredentials: true });
            else await axios.post(`${API}/api/bb/form-types`, { name: typeName.trim() }, { withCredentials: true });
            toast.success(editTypeId ? 'Updated' : 'Created'); setShowTypeModal(false); fetchAll();
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const deleteType = async (id) => {
        try { await axios.delete(`${API}/api/bb/form-types/${id}`, { withCredentials: true }); toast.success('Deleted'); setDeleteTypeTarget(null); fetchAll(); } catch { toast.error('Failed'); }
    };

    // Hiring Forms
    const resetFormModal = () => {
        setEditFormId(null); setFormName(''); setFormTypeId(''); setFormJobRole('');
        setCond({ age_min: '', age_max: '', grad_year_min: '', grad_year_max: '', locations: [], location_change: 'NA', attend_in_person: 'NA', college_limit: 'Both' });
        setLocInput(''); setJdAttached(false); setJdOpeningId('');
        setShowInstructionPage(false); setInstructionContent('');
    };
    const openAddForm = () => { resetFormModal(); setShowFormModal(true); };
    const openEditForm = (f) => {
        setEditFormId(f.id); setFormName(f.name); setFormTypeId(f.form_type_id); setFormJobRole(f.job_role);
        const c = f.conditions || {};
        setCond({ age_min: c.age_min ?? '', age_max: c.age_max ?? '', grad_year_min: c.grad_year_min ?? '', grad_year_max: c.grad_year_max ?? '',
            locations: c.locations || [], location_change: c.location_change || 'NA', attend_in_person: c.attend_in_person || 'NA', college_limit: c.college_limit || 'Both' });
        setLocInput(''); setJdAttached(f.job_description_attached || false); setJdOpeningId(f.job_opening_id || '');
        setShowInstructionPage(f.show_instruction_page || false); setInstructionContent(f.instruction_content || '');
        setShowFormModal(true);
    };
    const addLocation = () => { const v = locInput.trim(); if (v && !cond.locations.includes(v)) setCond(p => ({ ...p, locations: [...p.locations, v] })); setLocInput(''); };
    const removeLocation = (i) => setCond(p => ({ ...p, locations: p.locations.filter((_, idx) => idx !== i) }));

    const saveForm = async () => {
        if (!formName.trim() || !formTypeId || !formJobRole.trim()) { toast.error('Name, type, and job role are required'); return; }
        const conditions = {
            age_min: cond.age_min ? Number(cond.age_min) : null, age_max: cond.age_max ? Number(cond.age_max) : null,
            grad_year_min: cond.grad_year_min ? Number(cond.grad_year_min) : null, grad_year_max: cond.grad_year_max ? Number(cond.grad_year_max) : null,
            locations: cond.locations, location_change: cond.location_change, attend_in_person: cond.attend_in_person, college_limit: cond.college_limit,
        };
        try {
            const body = { name: formName.trim(), form_type_id: formTypeId, job_role: formJobRole.trim(), conditions, job_description_attached: jdAttached, job_opening_id: jdAttached ? jdOpeningId : null, show_instruction_page: showInstructionPage, instruction_content: showInstructionPage ? instructionContent : '' };
            if (editFormId) await axios.put(`${API}/api/bb/hiring-forms/${editFormId}`, body, { withCredentials: true });
            else await axios.post(`${API}/api/bb/hiring-forms`, body, { withCredentials: true });
            toast.success(editFormId ? 'Updated' : 'Created'); setShowFormModal(false); fetchAll();
        } catch (e) { toast.error(e.response?.data?.detail || 'Failed'); }
    };
    const deleteForm = async (id) => {
        try { await axios.delete(`${API}/api/bb/hiring-forms/${id}`, { withCredentials: true }); toast.success('Deleted'); setDeleteFormTarget(null); fetchAll(); } catch { toast.error('Failed'); }
    };

    // iter150 — Bucket forms by their form_type_id so each section header
    // can render only its own cards. Orphan forms (whose form_type_id no
    // longer matches a current type — e.g. the type was just deleted) land
    // in a dedicated "Uncategorized" bucket so they never disappear silently.
    const formsByType = useMemo(() => {
        const buckets = {};
        const knownIds = new Set(formTypes.map(t => t.id));
        for (const f of forms) {
            const key = knownIds.has(f.form_type_id) ? f.form_type_id : '__uncategorized__';
            (buckets[key] = buckets[key] || []).push(f);
        }
        return buckets;
    }, [forms, formTypes]);
    const uncategorizedCount = (formsByType['__uncategorized__'] || []).length;

    // iter150 — Single card renderer reused inside each grouped section.
    // Kept inline (closes over the page's handlers/state) instead of a
    // separate component so the existing event wiring stays intact.
    const renderFormCard = (f) => (
        <div key={f.id} className="bg-zinc-900 border border-zinc-800 p-5" data-testid={`form-${f.id}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <StatusDot status={f.status} testId={`form-${f.id}-status-dot`} />
                        <h3 className="font-medium break-words">{f.name}</h3>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1 break-words">Type: {f.form_type_name} | Role: {f.job_role}</p>
                    {f.conditions && Object.keys(f.conditions).length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-2">
                            {f.conditions.age_min != null && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">Age: {f.conditions.age_min}-{f.conditions.age_max}</span>}
                            {f.conditions.grad_year_min != null && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">Grad: {f.conditions.grad_year_min}-{f.conditions.grad_year_max}</span>}
                            {f.conditions.locations?.length > 0 && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">Locations: {f.conditions.locations.join(', ')}</span>}
                            {f.conditions.location_change !== 'NA' && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">Loc Change: {f.conditions.location_change}</span>}
                            {f.conditions.attend_in_person !== 'NA' && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">In Person: {f.conditions.attend_in_person}</span>}
                            {f.conditions.college_limit !== 'Both' && <span className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded whitespace-nowrap">College: {f.conditions.college_limit}</span>}
                        </div>
                    )}
                </div>
                <div className="flex gap-2 shrink-0 flex-wrap justify-end ml-auto">
                    <LifecycleControl entity="hiring-forms" id={f.id} name={f.name} status={f.status} onChanged={fetchAll} testIdPrefix={`form-${f.id}-lifecycle`} />
                    <a href={`/register/${f.slug || f.id}`} target="_blank" rel="noreferrer" data-testid={`link-${f.id}`} className="p-2 text-zinc-500 hover:text-cyan-400 hover:bg-zinc-800" title="Open Registration Link"><LinkIcon size={16} /></a>
                    <button
                        onClick={() => {
                            const url = `${window.location.origin}/register/${f.slug || f.id}`;
                            navigator.clipboard.writeText(url)
                                .then(() => toast.success(`Copied: ${url}`))
                                .catch(() => toast.error('Clipboard write failed'));
                        }}
                        data-testid={`copy-link-${f.id}`}
                        title="Copy Registration URL"
                        className="p-2 text-zinc-500 hover:text-emerald-400 hover:bg-zinc-800"
                    ><Copy size={16} /></button>
                    <button onClick={() => openEditForm(f)} className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800"><PencilSimple size={16} /></button>
                    <button onClick={() => setDeleteFormTarget({ id: f.id, name: f.name })} data-testid={`form-delete-${f.id}`} className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800"><Trash size={16} /></button>
                </div>
            </div>
        </div>
    );

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="hiring-forms-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Hiring Forms</h1>
                <div className="ml-auto flex gap-2">
                    <button onClick={openAddType} data-testid="add-form-type-btn" className="flex items-center gap-2 px-4 py-2 bg-violet-700 hover:bg-violet-600 text-sm font-medium"><Plus size={16} /> Add Form Type</button>
                    <button onClick={openAddForm} data-testid="add-new-form-btn" className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium"><Plus size={16} /> Add New Form</button>
                </div>
            </header>
            <main className="max-w-5xl mx-auto px-6 py-8 space-y-10">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> : <>
                {/* Form Types */}
                <section>
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest mb-4">Form Types</h2>
                    {formTypes.length === 0 ? <p className="text-zinc-600 text-sm" data-testid="no-form-types">No form types yet.</p> :
                    <div className="flex flex-wrap gap-3" data-testid="form-types-list">
                        {formTypes.map(t => (
                            <div key={t.id} className="bg-zinc-900 border border-zinc-800 px-4 py-3 flex items-center gap-3" data-testid={`form-type-${t.id}`}>
                                <span className="text-sm font-medium">{t.name}</span>
                                <button onClick={() => openEditType(t)} className="p-1 text-zinc-500 hover:text-white"><PencilSimple size={14} /></button>
                                <button onClick={() => setDeleteTypeTarget({ id: t.id, name: t.name })} data-testid={`form-type-delete-${t.id}`} className="p-1 text-zinc-500 hover:text-red-400"><Trash size={14} /></button>
                            </div>
                        ))}
                    </div>}
                </section>
                {/* Forms — iter150: grouped by Form Type with collapsible
                    section headers. Headers are derived from `formTypes`
                    so they stay in sync with the DB automatically. */}
                <section>
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest mb-4">Forms</h2>
                    {forms.length === 0 ? <p className="text-zinc-600 text-sm" data-testid="no-forms">No forms yet.</p> :
                    formTypes.length === 0 && uncategorizedCount === 0 ? <p className="text-zinc-600 text-sm">Add a Form Type to organise your forms.</p> :
                    <div className="space-y-3" data-testid="forms-list">
                        {formTypes.map(t => {
                            const list = formsByType[t.id] || [];
                            const isOpen = !!expandedTypes[t.id];
                            return (
                                <div key={t.id} className="border border-zinc-800 bg-zinc-950" data-testid={`forms-group-${t.id}`}>
                                    <button
                                        type="button"
                                        onClick={() => toggleType(t.id)}
                                        data-testid={`forms-group-header-${t.id}`}
                                        aria-expanded={isOpen}
                                        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-900 focus:outline-none"
                                    >
                                        {isOpen ? <CaretDown size={14} className="text-zinc-400" /> : <CaretRight size={14} className="text-zinc-400" />}
                                        <span className="text-sm font-semibold text-white">{t.name}</span>
                                        <span className="text-xs text-zinc-500" data-testid={`forms-group-count-${t.id}`}>{list.length} form{list.length === 1 ? '' : 's'}</span>
                                    </button>
                                    {isOpen && (
                                        <div className="border-t border-zinc-800 p-3 space-y-3" data-testid={`forms-group-body-${t.id}`}>
                                            {list.length === 0
                                                ? <p className="text-xs text-zinc-600 px-2 py-1">No forms of this type yet.</p>
                                                : list.map(f => renderFormCard(f))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                        {uncategorizedCount > 0 && (
                            <div className="border border-amber-900/60 bg-zinc-950" data-testid="forms-group-uncategorized">
                                <button
                                    type="button"
                                    onClick={() => toggleType('__uncategorized__')}
                                    data-testid="forms-group-header-uncategorized"
                                    aria-expanded={!!expandedTypes['__uncategorized__']}
                                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-900 focus:outline-none"
                                >
                                    {expandedTypes['__uncategorized__'] ? <CaretDown size={14} className="text-amber-400" /> : <CaretRight size={14} className="text-amber-400" />}
                                    <span className="text-sm font-semibold text-amber-300">Uncategorized</span>
                                    <span className="text-xs text-amber-500/80">{uncategorizedCount} form{uncategorizedCount === 1 ? '' : 's'} — type was deleted</span>
                                </button>
                                {expandedTypes['__uncategorized__'] && (
                                    <div className="border-t border-amber-900/40 p-3 space-y-3" data-testid="forms-group-body-uncategorized">
                                        {(formsByType['__uncategorized__'] || []).map(f => renderFormCard(f))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>}
                </section>
                </>}
            </main>

            {/* Form Type Modal */}
            {showTypeModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="form-type-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md mx-4 p-6 space-y-5">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{editTypeId ? 'Edit Form Type' : 'Add Form Type'}</h2><button onClick={() => setShowTypeModal(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="space-y-1.5">
                            <label className="text-xs text-zinc-500 uppercase tracking-wider">Type of Form</label>
                            <input type="text" value={typeName} onChange={e => setTypeName(e.target.value)} placeholder="e.g. Registration" data-testid="type-name-input"
                                className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" onKeyDown={e => e.key === 'Enter' && saveType()} />
                        </div>
                        <div className="flex justify-end gap-3">
                            <button onClick={() => setShowTypeModal(false)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={saveType} data-testid="save-type-btn" className="px-4 py-2 bg-violet-700 hover:bg-violet-600 text-sm font-medium">Create form type</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Hiring Form Modal */}
            {showFormModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="hiring-form-modal">
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-xl mx-4 p-6 space-y-4 max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{editFormId ? 'Edit Form' : 'Add New Form'}</h2><button onClick={() => setShowFormModal(false)} className="p-1 text-zinc-500 hover:text-white"><X size={20} /></button></div>
                        <div className="grid grid-cols-1 gap-4">
                            <div className="space-y-1.5">
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Name of Form</label>
                                <input type="text" value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. 2026 Batch Hiring" data-testid="form-name-input"
                                    className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Type of Form</label>
                                <select value={formTypeId} onChange={e => setFormTypeId(e.target.value)} data-testid="form-type-select"
                                    className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                                    <option value="">Select form type</option>
                                    {formTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                                </select>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role</label>
                                <select value={formJobRole} onChange={e => setFormJobRole(e.target.value)} data-testid="form-job-role-select"
                                    className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                                    <option value="">Select job role</option>
                                    {jobRoles.map(r => <option key={r.id} value={r.name}>{r.name}</option>)}
                                </select>
                            </div>
                        </div>
                        {/* Conditions */}
                        <div className="border-t border-zinc-800 pt-4">
                            <h3 className="text-sm font-medium text-zinc-400 mb-3">Conditions</h3>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Min Age</label><input type="number" value={cond.age_min} onChange={e => setCond(p => ({ ...p, age_min: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /></div>
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Max Age</label><input type="number" value={cond.age_max} onChange={e => setCond(p => ({ ...p, age_max: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /></div>
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Min Grad Year</label><input type="number" value={cond.grad_year_min} onChange={e => setCond(p => ({ ...p, grad_year_min: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /></div>
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Max Grad Year</label><input type="number" value={cond.grad_year_max} onChange={e => setCond(p => ({ ...p, grad_year_max: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" /></div>
                            </div>
                            <div className="mt-3 space-y-1.5">
                                <label className="text-xs text-zinc-500">Location Limit</label>
                                <div className="flex gap-2">
                                    <input type="text" value={locInput} onChange={e => setLocInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addLocation(); } }} placeholder="Add location"
                                        className="flex-1 bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500" />
                                    <button onClick={addLocation} className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-sm"><Plus size={14} /></button>
                                </div>
                                {cond.locations.length > 0 && <div className="flex flex-wrap gap-1.5 mt-1">{cond.locations.map((l, i) => (
                                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-zinc-800 border border-zinc-700 rounded-full">{l}<button onClick={() => removeLocation(i)} className="hover:text-red-400"><X size={10} /></button></span>
                                ))}</div>}
                            </div>
                            <div className="grid grid-cols-3 gap-3 mt-3">
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Location Change</label>
                                    <select value={cond.location_change} onChange={e => setCond(p => ({ ...p, location_change: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500"><option>NA</option><option>Yes</option><option>No</option></select></div>
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Attend in Person</label>
                                    <select value={cond.attend_in_person} onChange={e => setCond(p => ({ ...p, attend_in_person: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500"><option>NA</option><option>Yes</option><option>No</option></select></div>
                                <div className="space-y-1"><label className="text-xs text-zinc-500">College Limit</label>
                                    <select value={cond.college_limit} onChange={e => setCond(p => ({ ...p, college_limit: e.target.value }))} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm focus:outline-none focus:border-zinc-500"><option>Both</option><option>NIRF</option><option>Non NIRF</option></select></div>
                            </div>
                        </div>
                        {/* Job Description Attached */}
                        <div className="border-t border-zinc-800 pt-4 space-y-3">
                            <h3 className="text-sm font-medium text-zinc-400">Job description attached?</h3>
                            <div className="flex gap-4">
                                {[true, false].map(v => <label key={String(v)} className="flex items-center gap-1.5 text-sm cursor-pointer"><input type="radio" checked={jdAttached === v} onChange={() => setJdAttached(v)} className="accent-emerald-500" />{v ? 'Yes' : 'No'}</label>)}
                            </div>
                            {jdAttached && (
                                <div className="space-y-1"><label className="text-xs text-zinc-500">Job Description Type</label>
                                    <select value={jdOpeningId} onChange={e => setJdOpeningId(e.target.value)} data-testid="jd-opening-select" className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                                        <option value="">Select job opening</option>
                                        {jobOpenings.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}
                                    </select>
                                </div>
                            )}
                        </div>
                        {/* Show Instruction Page */}
                        <div className="border-t border-zinc-800 pt-4 space-y-3" data-testid="instruction-page-section">
                            <h3 className="text-sm font-medium text-zinc-400">Show Instruction Page?</h3>
                            <div className="flex gap-4">
                                {[true, false].map(v => (
                                    <label key={String(v)} className="flex items-center gap-1.5 text-sm cursor-pointer">
                                        <input type="radio" checked={showInstructionPage === v} onChange={() => setShowInstructionPage(v)} className="accent-emerald-500" data-testid={`instruction-page-radio-${v ? 'yes' : 'no'}`} />
                                        {v ? 'Yes' : 'No'}
                                    </label>
                                ))}
                            </div>
                            {showInstructionPage && (
                                <div className="space-y-1">
                                    <label className="text-xs text-zinc-500">Instruction Content (HTML allowed)</label>
                                    <textarea
                                        value={instructionContent}
                                        onChange={e => setInstructionContent(e.target.value)}
                                        rows={6}
                                        placeholder="Enter the instructions candidates will see after submitting the form. You can use basic HTML (e.g., <h2>, <p>, <ul>, <li>, <strong>, <a>)."
                                        className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500 font-mono"
                                        data-testid="instruction-content-textarea"
                                    />
                                </div>
                            )}
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button onClick={() => setShowFormModal(false)} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm">Cancel</button>
                            <button onClick={saveForm} data-testid="save-form-btn" className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium">{editFormId ? 'Update' : 'Create Form'}</button>
                        </div>
                    </div>
                </div>
            )}
            <ConfirmDeleteModal
                open={!!deleteFormTarget}
                title="Delete Hiring Form?"
                itemLabel={deleteFormTarget?.name}
                description="The form will be removed and any public links pointing to it will stop working."
                testId="delete-hiring-form"
                onConfirm={() => deleteForm(deleteFormTarget.id)}
                onClose={() => setDeleteFormTarget(null)}
            />
            <ConfirmDeleteModal
                open={!!deleteTypeTarget}
                title="Delete Form Type?"
                itemLabel={deleteTypeTarget?.name}
                description="Existing forms referencing this type may lose their categorization."
                testId="delete-form-type"
                onConfirm={() => deleteType(deleteTypeTarget.id)}
                onClose={() => setDeleteTypeTarget(null)}
            />
        </div>
    );
}
