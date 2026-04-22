import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Plus, PencilSimple, Trash, X, FolderOpen } from '@phosphor-icons/react';

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
    const [formResp, setFormResp] = useState('');
    const [formAdvantages, setFormAdvantages] = useState('');
    const [formOffer, setFormOffer] = useState('');
    const [jobRoles, setJobRoles] = useState([]);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [oRes, rRes] = await Promise.all([
                axios.get(`${API}/api/bb/job-openings`, { withCredentials: true }),
                axios.get(`${API}/api/bb/job-roles`, { withCredentials: true }),
            ]);
            setOpenings(oRes.data.openings || []);
            setJobRoles(rRes.data.roles || []);
        } catch {} finally { setLoading(false); }
    }, []);
    useEffect(() => { fetchAll(); }, [fetchAll]);

    const openAdd = () => { setEditId(null); setFormTitle(''); setFormRole(''); setFormVacancies(''); setFormYears([]); setYearInput(''); setFormEdu([]); setEduInput(''); setFormSalary(''); setFormResp(''); setFormAdvantages(''); setFormOffer(''); setShowModal(true); };
    const openEdit = (o) => { setEditId(o.id); setFormTitle(o.title); setFormRole(o.job_role || ''); setFormVacancies(o.vacancies ? String(o.vacancies) : ''); setFormYears(o.years_of_graduation || []); setYearInput(''); setFormEdu(o.education || []); setEduInput(''); setFormSalary(o.salary_range || ''); setFormResp(o.key_responsibilities || ''); setFormAdvantages(o.added_advantages || ''); setFormOffer(o.what_we_offer || ''); setShowModal(true); };

    const addYear = () => { const v = yearInput.trim(); if (v && !formYears.includes(v)) setFormYears(p => [...p, v]); setYearInput(''); };
    const addEdu = () => { const v = eduInput.trim(); if (v && !formEdu.includes(v)) setFormEdu(p => [...p, v]); setEduInput(''); };

    const handleSave = async () => {
        if (!formTitle.trim()) { toast.error('Title required'); return; }
        try {
            const body = { title: formTitle.trim(), job_role: formRole, vacancies: formVacancies ? Number(formVacancies) : null, years_of_graduation: formYears, education: formEdu, salary_range: formSalary, key_responsibilities: formResp, added_advantages: formAdvantages, what_we_offer: formOffer };
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
                <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
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
                                    <h3 className="font-medium">{o.title}</h3>
                                    <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                                        {o.job_role && <span>Role: {o.job_role}</span>}
                                        {o.vacancies && <span>Vacancies: {o.vacancies}</span>}
                                        {o.salary_range && <span>Salary: {o.salary_range}</span>}
                                    </div>
                                    {o.years_of_graduation?.length > 0 && <div className="flex gap-1 mt-1">{o.years_of_graduation.map((y, i) => <span key={i} className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded">{y}</span>)}</div>}
                                    {o.education?.length > 0 && <div className="flex gap-1 mt-1">{o.education.map((e, i) => <span key={i} className="text-xs bg-zinc-800 px-2 py-0.5 text-zinc-400 rounded">{e}</span>)}</div>}
                                </div>
                                <div className="flex gap-2 shrink-0">
                                    <button onClick={() => openEdit(o)} className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800"><PencilSimple size={16} /></button>
                                    <button onClick={() => handleDelete(o.id)} className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-800"><Trash size={16} /></button>
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
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Key Responsibilities</label><textarea value={formResp} onChange={e => setFormResp(e.target.value)} rows={3} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500 resize-none" /></div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Added Advantages</label><textarea value={formAdvantages} onChange={e => setFormAdvantages(e.target.value)} rows={3} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500 resize-none" /></div>
                        <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">What We Offer</label><textarea value={formOffer} onChange={e => setFormOffer(e.target.value)} rows={3} className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500 resize-none" /></div>
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
