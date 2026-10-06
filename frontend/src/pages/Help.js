/**
 * BluBridge Help Center (iter67)
 * ------------------------------
 * Single-stop help page for every module + downloadable .xlsx templates.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, Book, Question, Download, MagnifyingGlass, CaretRight,
    ChartBar, FileText, CalendarCheck, PencilLine, Table, Briefcase,
    FolderOpen, GraduationCap, CalendarBlank, ShieldCheck, WhatsappLogo,
    Lightbulb, ListChecks, FileXls, FileDoc, EnvelopeSimple, Flask,
    Sparkle,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const ICONS = {
    ChartBar, FileText, CalendarCheck, PencilLine, Table,
    MagnifyingGlass, Briefcase, FolderOpen, GraduationCap,
    CalendarBlank, ShieldCheck, WhatsappLogo, EnvelopeSimple, Flask, Question, Book,
};

const TONE = {
    blue:    { bg: 'bg-blue-50',    fg: 'text-blue-600',    ring: 'ring-blue-100' },
    violet:  { bg: 'bg-violet-50',  fg: 'text-violet-600',  ring: 'ring-violet-100' },
    cyan:    { bg: 'bg-cyan-50',    fg: 'text-cyan-600',    ring: 'ring-cyan-100' },
    emerald: { bg: 'bg-emerald-50', fg: 'text-emerald-600', ring: 'ring-emerald-100' },
    sky:     { bg: 'bg-sky-50',     fg: 'text-sky-600',     ring: 'ring-sky-100' },
    indigo:  { bg: 'bg-indigo-50',  fg: 'text-indigo-600',  ring: 'ring-indigo-100' },
    navy:    { bg: 'bg-[#e8ecf6]',  fg: 'text-[#1d3a8a]',   ring: 'ring-[#dde3f2]' },
    rose:    { bg: 'bg-rose-50',    fg: 'text-rose-600',    ring: 'ring-rose-100' },
    pink:    { bg: 'bg-pink-50',    fg: 'text-pink-600',    ring: 'ring-pink-100' },
    orange:  { bg: 'bg-orange-50',  fg: 'text-orange-600',  ring: 'ring-orange-100' },
    teal:    { bg: 'bg-teal-50',    fg: 'text-teal-600',    ring: 'ring-teal-100' },
    whatsapp:{ bg: 'bg-[#25D366]/10', fg: 'text-[#128C7E]', ring: 'ring-[#25D366]/20' },
};

export default function Help() {
    const navigate = useNavigate();
    const [manifest, setManifest] = useState(null);
    const [activeId, setActiveId] = useState(null);
    const [search, setSearch] = useState('');

    useEffect(() => {
        axios.get(`${API}/api/bb/help/manifest`, { withCredentials: true })
            .then(r => {
                setManifest(r.data);
                if (!activeId && r.data.modules?.length) setActiveId(r.data.modules[0].id);
            })
            .catch(() => toast.error('Failed to load help content'));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const modules = useMemo(() => manifest?.modules || [], [manifest]);
    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return modules;
        return modules.filter(m =>
            m.name.toLowerCase().includes(q) ||
            m.summary.toLowerCase().includes(q) ||
            (m.steps || []).some(s => s.toLowerCase().includes(q))
        );
    }, [modules, search]);

    const active = modules.find(m => m.id === activeId);

    const handleDownload = async (url, filename) => {
        try {
            const resp = await axios.get(`${API}${url}`, { withCredentials: true, responseType: 'blob' });
            const blobUrl = window.URL.createObjectURL(new Blob([resp.data]));
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(blobUrl);
            toast.success(`Downloaded ${filename}`);
        } catch (e) {
            toast.error('Download failed');
        }
    };

    return (
        <div className="min-h-screen" data-testid="help-page">
            {/* Header */}
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
                    <div className="flex items-center gap-3 pl-12 lg:pl-0">
                        <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                            <ArrowLeft size={18} className="text-[#1a2332]" />
                        </button>
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-[#1d3a8a]/10">
                            <Book size={22} weight="duotone" className="text-[#1d3a8a]" />
                        </div>
                        <div>
                            <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Help Center</h1>
                            <p className="text-xs text-[#6b7280] mt-0.5">Guides · Templates · FAQs · Match logic</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => handleDownload('/api/bb/help/documentation/xlsx', 'BluBridge-Documentation.xlsx')}
                            data-testid="help-download-xlsx-btn"
                            className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold flex items-center gap-2"
                        >
                            <FileXls size={16} weight="duotone" /> Full Documentation (.xlsx)
                        </button>
                        <button
                            onClick={() => handleDownload('/api/bb/help/documentation/docx', 'BluBridge-Documentation.docx')}
                            data-testid="help-download-docx-btn"
                            className="px-4 py-2.5 rounded-lg bg-[#1d3a8a] hover:bg-[#162d6e] text-white text-sm font-semibold flex items-center gap-2"
                        >
                            <FileDoc size={16} weight="duotone" /> Full Documentation (.docx)
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-6 lg:px-10 py-6 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
                {/* Sidebar nav */}
                <aside className="lg:sticky lg:top-6 lg:self-start space-y-3">
                    <div className="flex items-center gap-2 bg-[#fffdf7] border border-[#e5e3d8] rounded-lg px-3 py-2">
                        <MagnifyingGlass size={16} className="text-[#9b9787]" />
                        <input
                            data-testid="help-search"
                            placeholder="Search modules / FAQs…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="flex-1 bg-transparent outline-none text-sm text-[#1a2332]"
                        />
                    </div>

                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-2 max-h-[calc(100vh-200px)] overflow-y-auto">
                        <p className="px-3 py-2 text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase">Modules</p>
                        {filtered.map((m) => {
                            const Icon = ICONS[m.icon] || Question;
                            const t = TONE[m.color] || TONE.navy;
                            const isActive = m.id === activeId;
                            return (
                                <button
                                    key={m.id}
                                    data-testid={`help-nav-${m.id}`}
                                    onClick={() => setActiveId(m.id)}
                                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-left transition-colors ${isActive ? 'bg-[#1d3a8a] text-white' : 'text-[#3f4655] hover:bg-[#efede5]'}`}
                                >
                                    <span className={`w-7 h-7 rounded-md flex items-center justify-center ${isActive ? 'bg-white/15' : t.bg}`}>
                                        <Icon size={16} weight="duotone" className={isActive ? 'text-white' : t.fg} />
                                    </span>
                                    <span className="flex-1 truncate">{m.name}</span>
                                    {isActive && <CaretRight size={14} weight="bold" />}
                                </button>
                            );
                        })}
                        {!filtered.length && (
                            <p className="px-3 py-6 text-sm text-[#9b9787] text-center">No matches</p>
                        )}
                    </div>
                </aside>

                {/* Detail panel */}
                <section className="space-y-5">
                    {active ? <ModuleDetail mod={active} onDownload={handleDownload} /> : (
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-10 text-center text-[#9b9787]">
                            Select a module from the left to view its guide.
                        </div>
                    )}

                    {/* What's New */}
                    {manifest?.whats_new?.length > 0 && (
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6" data-testid="help-whats-new">
                            <div className="flex items-center gap-2 mb-4">
                                <Sparkle size={18} weight="duotone" className="text-amber-600" />
                                <h2 className="text-base font-semibold text-[#1a2332]">What's New</h2>
                                <span className="ml-auto text-[10px] font-semibold tracking-[0.16em] text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full uppercase">iter67</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                {manifest.whats_new.map((w, i) => (
                                    <div key={i} className="bg-amber-50/40 border border-amber-100 rounded-lg px-3 py-2 text-sm">
                                        <p className="font-semibold text-[#1a2332]">{w.item}</p>
                                        <p className="text-[#3f4655] text-[12px] leading-relaxed mt-0.5">{w.desc}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Global FAQs */}
                    {manifest?.global_faqs?.length > 0 && (
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6" data-testid="help-global-faqs">
                            <div className="flex items-center gap-2 mb-4">
                                <Question size={18} weight="duotone" className="text-[#1d3a8a]" />
                                <h2 className="text-base font-semibold text-[#1a2332]">Global FAQs</h2>
                            </div>
                            <div className="space-y-3">
                                {manifest.global_faqs.map((f, i) => (
                                    <details key={i} className="rounded-lg border border-[#ece9dc] bg-[#faf9f1] px-4 py-3 group">
                                        <summary className="cursor-pointer text-sm font-semibold text-[#1a2332] list-none flex items-center justify-between">
                                            <span>{f.q}</span>
                                            <CaretRight size={14} className="text-[#9b9787] group-open:rotate-90 transition-transform" />
                                        </summary>
                                        <p className="text-sm text-[#3f4655] mt-2 leading-relaxed">{f.a}</p>
                                    </details>
                                ))}
                            </div>
                        </div>
                    )}
                </section>
            </main>
        </div>
    );
}

function ModuleDetail({ mod, onDownload }) {
    const Icon = ICONS[mod.icon] || Question;
    const t = TONE[mod.color] || TONE.navy;

    return (
        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden" data-testid={`help-detail-${mod.id}`}>
            {/* Hero */}
            <div className="px-6 py-5 border-b border-[#e5e3d8] bg-[#faf9f1] flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl ${t.bg} ring-4 ${t.ring} flex items-center justify-center shrink-0`}>
                    <Icon size={24} weight="duotone" className={t.fg} />
                </div>
                <div className="flex-1">
                    <h2 className="text-lg font-bold text-[#1a2332]">{mod.name}</h2>
                    <p className="text-sm text-[#3f4655] mt-1 leading-relaxed">{mod.summary}</p>
                </div>
            </div>

            {/* Steps */}
            {mod.steps?.length > 0 && (
                <div className="p-6 border-b border-[#e5e3d8]">
                    <div className="flex items-center gap-2 mb-3">
                        <ListChecks size={18} weight="duotone" className="text-[#1d3a8a]" />
                        <h3 className="text-sm font-semibold text-[#1a2332]">How to use</h3>
                    </div>
                    <ol className="space-y-2">
                        {mod.steps.map((s, i) => (
                            <li key={i} className="flex gap-3 text-sm text-[#1a2332]">
                                <span className="w-6 h-6 rounded-full bg-[#1d3a8a]/10 text-[#1d3a8a] text-[11px] font-semibold flex items-center justify-center shrink-0">{i + 1}</span>
                                <span className="flex-1 leading-relaxed">{s}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            )}

            {/* Tips */}
            {mod.tips?.length > 0 && (
                <div className="p-6 border-b border-[#e5e3d8] bg-amber-50/30">
                    <div className="flex items-center gap-2 mb-3">
                        <Lightbulb size={18} weight="duotone" className="text-amber-600" />
                        <h3 className="text-sm font-semibold text-[#1a2332]">Tips</h3>
                    </div>
                    <ul className="space-y-1.5">
                        {mod.tips.map((tip, i) => (
                            <li key={i} className="text-sm text-[#3f4655] leading-relaxed pl-5 relative">
                                <span className="absolute left-0 top-2 w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                                {tip}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Downloads */}
            {mod.downloads?.length > 0 && (
                <div className="p-6">
                    <div className="flex items-center gap-2 mb-3">
                        <FileXls size={18} weight="duotone" className="text-emerald-700" />
                        <h3 className="text-sm font-semibold text-[#1a2332]">Templates</h3>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {mod.downloads.map((d, i) => (
                            <button
                                key={i}
                                data-testid={`help-download-${mod.id}-${i}`}
                                onClick={() => onDownload(d.url, d.label.match(/\((.+?)\)/)?.[1] ? `BluBridge-${mod.name.replace(/\s+/g, '-')}-Template.xlsx` : 'BluBridge-Template.xlsx')}
                                className="flex items-center justify-between gap-3 px-4 py-3 border border-[#e5e3d8] rounded-xl bg-[#faf9f1] hover:bg-[#efede5] hover:border-[#1d3a8a]/40 transition-colors text-left"
                            >
                                <div className="flex items-center gap-2">
                                    <FileXls size={20} weight="duotone" className="text-emerald-700" />
                                    <span className="text-sm font-semibold text-[#1a2332]">{d.label}</span>
                                </div>
                                <Download size={16} className="text-[#1d3a8a]" />
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
