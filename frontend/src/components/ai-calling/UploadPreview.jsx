import { useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { COLS, CATEGORY_LABELS } from './constants';

const Summary = ({ res, excluded, fileTotal }) => (
    <div className="flex flex-wrap gap-2 mb-3" data-testid="upload-summary">
        <span className="px-2.5 py-1 rounded-full bg-zinc-100 text-xs font-semibold">Rows in file {fileTotal} · Checked {res.total}</span>
        <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-semibold" data-testid="summary-valid">Valid {res.valid}</span>
        <span className="px-2.5 py-1 rounded-full bg-rose-100 text-rose-800 text-xs font-semibold" data-testid="summary-invalid">Invalid {res.invalid}</span>
        {excluded > 0 && <span className="px-2.5 py-1 rounded-full bg-zinc-200 text-xs font-semibold">Excluded {excluded}</span>}
        {Object.entries(res.by_category || {}).filter(([, n]) => n).map(([k, n]) => (
            <span key={k} className="px-2.5 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200 text-xs" data-testid={`summary-${k}`}>{CATEGORY_LABELS[k]}: {n}</span>
        ))}
    </div>
);

export const UploadPreview = ({ preview, onClose, onImported }) => {
    const [rows, setRows] = useState(preview.rows);
    const [res, setRes] = useState(preview);
    const [excluded, setExcluded] = useState(new Set());
    const [dirty, setDirty] = useState(false);
    const [busy, setBusy] = useState(false);

    const included = rows.filter(r => !excluded.has(r.row));
    const payload = () => ({ filename: preview.filename, excluded_count: excluded.size, rows: included.map(r => ({ row: r.row, values: r.values })) });
    const edit = (row, k, v) => { setRows(rs => rs.map(r => r.row === row ? { ...r, values: { ...r.values, [k]: v } } : r)); setDirty(true); };
    const toggle = (row) => { setExcluded(s => { const n = new Set(s); n.has(row) ? n.delete(row) : n.add(row); return n; }); setDirty(true); };
    const excludeInvalid = () => { setExcluded(new Set(rows.filter(r => !r.valid).map(r => r.row))); setDirty(true); };

    const revalidate = async () => {
        if (!included.length) { toast.error('All rows are excluded'); return; }
        setBusy(true);
        try {
            const r = (await aiApi.post('/test-candidates/validate-rows', payload())).data;
            const byRow = Object.fromEntries(r.rows.map(x => [x.row, x]));
            setRows(rs => rs.map(x => byRow[x.row] ? { ...x, ...byRow[x.row] } : x));
            setRes(r); setDirty(false);
        } catch (e) { toast.error(errMsg(e, 'Validation failed')); } finally { setBusy(false); }
    };
    const doImport = async () => {
        setBusy(true);
        try {
            const r = (await aiApi.post('/test-candidates/import', payload())).data;
            toast.success(`Imported ${r.imported} test candidate(s). Each still needs admin approval.`);
            onImported();
        } catch (e) { toast.error(errMsg(e, 'Import failed')); } finally { setBusy(false); }
    };
    const canImport = !dirty && included.length > 0 && included.every(r => r.valid);

    return (
        <div className="mt-4" data-testid="upload-preview">
            <p className="text-sm text-[#1a2332] mb-2"><b>{preview.filename}</b> — edit cells to correct errors or exclude rows, then re-validate.</p>
            <Summary res={res} excluded={excluded.size} fileTotal={preview.total} />
            <div className="overflow-x-auto max-h-96 border border-[#e5e3d8] rounded-xl">
                <table className="w-full text-xs">
                    <thead className="bg-[#faf9f1] text-[#6b7280] sticky top-0 z-10">
                        <tr><th className="px-2 py-2 text-left">Exclude</th><th className="px-2 py-2 text-left">Row</th>{COLS.map(([, l]) => <th key={l} className="px-2 py-2 text-left whitespace-nowrap">{l}</th>)}<th className="px-2 py-2 text-left">Status</th></tr>
                    </thead>
                    <tbody>
                        {rows.map(r => {
                            const ex = excluded.has(r.row);
                            const bad = new Set((r.errors || []).map(e => e.field));
                            return (
                                <tr key={r.row} className={`border-t border-[#efede5] ${ex ? 'opacity-40' : ''}`} data-testid={`preview-row-${r.row}`}>
                                    <td className="px-2 py-1.5"><input type="checkbox" checked={ex} onChange={() => toggle(r.row)} data-testid={`preview-exclude-${r.row}`} className="accent-teal-700" /></td>
                                    <td className="px-2 py-1.5">{r.row}</td>
                                    {COLS.map(([k]) => (
                                        <td key={k} className="px-1 py-1">
                                            <input value={r.values[k] ?? ''} disabled={ex} onChange={e => edit(r.row, k, e.target.value)} data-testid={`preview-cell-${r.row}-${k}`}
                                                className={`w-32 px-2 py-1 rounded border text-xs ${bad.has(k) ? 'border-rose-400 bg-rose-50' : 'border-[#e5e3d8] bg-white'}`} />
                                        </td>
                                    ))}
                                    <td className="px-2 py-1.5 min-w-[220px]">{ex ? 'Excluded' : r.valid ? <span className="text-emerald-700 font-semibold">Valid</span> : <span className="text-rose-700">{r.errors.map(e => e.message).join('; ')}</span>}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
                <button onClick={revalidate} disabled={busy} data-testid="preview-revalidate-btn" className="px-4 py-2 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold disabled:opacity-50">Re-validate</button>
                <button onClick={excludeInvalid} disabled={busy} data-testid="preview-exclude-invalid-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Exclude invalid rows</button>
                <button onClick={doImport} disabled={busy || !canImport} data-testid="preview-import-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Import {included.length} row(s)</button>
                <button onClick={onClose} data-testid="preview-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
            </div>
            {!canImport && <p className="text-xs text-[#6b7280] mt-2" data-testid="preview-import-hint">{dirty ? 'Re-validate after changes to enable import.' : 'All included rows must be valid before importing.'}</p>}
        </div>
    );
};
