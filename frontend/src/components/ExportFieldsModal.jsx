import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, CheckSquare, Square } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;
const STORAGE_KEY = 'exportFields:interviewReports';

/**
 * Export Fields Modal — dynamic field selection for Interview Reports export.
 * Loads catalog from /api/bb/interview-reports/export-fields with current filters.
 */
export default function ExportFieldsModal({ open, onClose, filterParams, onDownload }) {
    const [sections, setSections] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState(new Set());
    const [downloading, setDownloading] = useState(false);

    const allKeys = useMemo(() => {
        const s = [];
        sections.forEach(sec => sec.fields.forEach(f => s.push(f.key)));
        return s;
    }, [sections]);

    useEffect(() => {
        if (!open) return;
        setLoading(true);
        axios.get(`${API}/api/bb/interview-reports/export-fields`, {
            params: filterParams || {}, withCredentials: true,
        }).then(r => {
            const secs = r.data.sections || [];
            setSections(secs);
            const allInOrder = [];
            secs.forEach(s => s.fields.forEach(f => allInOrder.push(f.key)));
            // Restore last selection from localStorage if it intersects with current catalog
            try {
                const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
                if (Array.isArray(saved) && saved.length) {
                    const valid = saved.filter(k => allInOrder.includes(k));
                    setSelected(new Set(valid.length ? valid : allInOrder));
                } else {
                    setSelected(new Set(allInOrder)); // pre-select all
                }
            } catch {
                setSelected(new Set(allInOrder));
            }
        }).catch(() => {
            toast.error('Failed to load export fields');
        }).finally(() => setLoading(false));
    }, [open, filterParams]);

    if (!open) return null;

    const toggle = (key) => {
        const next = new Set(selected);
        if (next.has(key)) next.delete(key); else next.add(key);
        setSelected(next);
    };
    const sectionAll = (sec, on) => {
        const next = new Set(selected);
        sec.fields.forEach(f => on ? next.add(f.key) : next.delete(f.key));
        setSelected(next);
    };
    const globalAll = (on) => {
        setSelected(on ? new Set(allKeys) : new Set());
    };

    const handleDownload = async () => {
        if (selected.size === 0) {
            toast.error('Please select at least one field');
            return;
        }
        // Persist selection (only valid keys, ordered by catalog)
        const ordered = allKeys.filter(k => selected.has(k));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(ordered));
        setDownloading(true);
        try {
            await onDownload(ordered.join(','));
            onClose();
        } finally {
            setDownloading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="export-fields-modal">
            <div className="bg-zinc-900 border border-zinc-700 rounded w-full max-w-2xl max-h-[85vh] flex flex-col">
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
                    <h2 className="text-lg font-semibold text-white">Select Fields to Export</h2>
                    <button onClick={onClose} data-testid="close-modal-btn" className="text-zinc-400 hover:text-white"><X size={20} /></button>
                </div>

                <div className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 bg-zinc-950">
                    <span className="text-xs text-zinc-400">{selected.size} of {allKeys.length} fields selected</span>
                    <div className="flex gap-2">
                        <button onClick={() => globalAll(true)} data-testid="select-all-btn" className="text-xs text-cyan-400 hover:text-cyan-300 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded">Select All</button>
                        <button onClick={() => globalAll(false)} data-testid="clear-all-btn" className="text-xs text-zinc-300 hover:text-white px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded">Clear All</button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                    {loading && <div className="text-zinc-400 text-sm">Loading fields…</div>}
                    {!loading && sections.length === 0 && <div className="text-zinc-500 text-sm">No exportable fields found.</div>}
                    {!loading && sections.map(sec => {
                        const total = sec.fields.length;
                        const inSec = sec.fields.filter(f => selected.has(f.key)).length;
                        return (
                            <div key={sec.id} data-testid={`section-${sec.id}`}>
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-300">{sec.label}</h3>
                                    <button onClick={() => sectionAll(sec, inSec !== total)} data-testid={`section-toggle-${sec.id}`} className="text-xs text-cyan-400 hover:text-cyan-300">
                                        {inSec === total ? 'Clear Section' : 'Select All'}
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    {sec.fields.map(f => {
                                        const on = selected.has(f.key);
                                        return (
                                            <label key={f.key} data-testid={`field-${f.key}`} className={`flex items-center gap-2 px-3 py-2 rounded border cursor-pointer text-sm select-none ${on ? 'bg-cyan-950/40 border-cyan-700 text-white' : 'bg-zinc-950 border-zinc-800 text-zinc-300 hover:border-zinc-700'}`}>
                                                <input type="checkbox" checked={on} onChange={() => toggle(f.key)} className="hidden" />
                                                {on ? <CheckSquare size={18} className="text-cyan-400" weight="fill" /> : <Square size={18} className="text-zinc-500" />}
                                                <span>{f.label}</span>
                                            </label>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>

                <div className="flex justify-end gap-3 px-6 py-4 border-t border-zinc-800 bg-zinc-950">
                    <button onClick={onClose} data-testid="cancel-btn" className="px-5 py-2 text-sm font-medium text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded">Cancel</button>
                    <button onClick={handleDownload} disabled={downloading || selected.size === 0} data-testid="download-btn" className="px-5 py-2 text-sm font-medium text-white bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed rounded">
                        {downloading ? 'Generating…' : 'Download'}
                    </button>
                </div>
            </div>
        </div>
    );
}
