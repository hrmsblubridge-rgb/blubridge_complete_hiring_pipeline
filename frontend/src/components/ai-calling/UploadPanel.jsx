import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { DownloadSimple, UploadSimple, FileXls } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const download = async (format) => {
    try {
        const r = await aiApi.get(`/template?format=${format}`, { responseType: 'blob' });
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ai_test_candidates_template.${format}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) { toast.error('Template download failed'); }
};

export const UploadPanel = ({ onImported }) => {
    const inputRef = useRef(null);
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(false);

    const send = async (commit, f = file) => {
        const fd = new FormData();
        fd.append('file', f);
        setBusy(true);
        try {
            const r = await aiApi.post(`/test-candidates/upload?commit=${commit}`, fd);
            if (commit) {
                toast.success(`Imported ${r.data.imported} candidate(s). They still need admin approval.`);
                setPreview(null); setFile(null); onImported();
            } else setPreview(r.data);
        } catch (e) { toast.error(errMsg(e, 'Upload failed')); setPreview(null); }
        finally { setBusy(false); if (inputRef.current) inputRef.current.value = ''; }
    };

    const pick = (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        if (!/\.(xlsx|csv)$/i.test(f.name)) { toast.error('Only .xlsx or .csv files'); return; }
        setFile(f); send(false, f);
    };

    return (
        <Card data-testid="upload-panel">
            <SectionTitle icon={FileXls}>Upload test candidates (Excel / CSV)</SectionTitle>
            <div className="flex flex-wrap gap-2">
                <button onClick={() => download('xlsx')} data-testid="download-template-xlsx" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold text-[#1a2332] hover:bg-[#efede5] flex items-center gap-2"><DownloadSimple size={16} /> Sample Excel sheet</button>
                <button onClick={() => download('csv')} data-testid="download-template-csv" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold text-[#1a2332] hover:bg-[#efede5] flex items-center gap-2"><DownloadSimple size={16} /> Sample CSV</button>
                <button onClick={() => inputRef.current?.click()} disabled={busy} data-testid="upload-file-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-60"><UploadSimple size={16} /> {busy ? 'Reading…' : 'Choose .xlsx / .csv'}</button>
                <input ref={inputRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={pick} data-testid="upload-file-input" />
            </div>
            <p className="text-xs text-[#6b7280] mt-2">Uploading only previews and stores rows. It never approves recipients or starts calls.</p>
            {preview && (
                <div className="mt-4" data-testid="upload-preview">
                    <p className="text-sm text-[#1a2332] mb-2"><b>{file?.name}</b> — {preview.total} rows · <span className="text-emerald-700">{preview.valid} valid</span> · <span className="text-rose-700">{preview.invalid} invalid</span></p>
                    <div className="overflow-x-auto max-h-72 border border-[#e5e3d8] rounded-xl">
                        <table className="w-full text-xs">
                            <thead className="bg-[#faf9f1] text-[#6b7280] sticky top-0"><tr>{['Row', 'Name', 'Phone', 'Role', 'Date', 'Time', 'Lang', 'Sheet flag', 'Status'].map(h => <th key={h} className="text-left px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
                            <tbody>
                                {preview.rows.map(r => (
                                    <tr key={r.row} className="border-t border-[#efede5]" data-testid={`preview-row-${r.row}`}>
                                        <td className="px-3 py-2">{r.row}</td><td className="px-3 py-2">{r.candidate_name}</td><td className="px-3 py-2">{r.phone_masked}</td>
                                        <td className="px-3 py-2">{r.job_role}</td><td className="px-3 py-2">{r.interview_date}</td><td className="px-3 py-2">{r.interview_time}</td>
                                        <td className="px-3 py-2">{r.language}</td><td className="px-3 py-2">{r.sheet_approved_flag ? 'yes' : 'no'}</td>
                                        <td className="px-3 py-2">{r.valid ? <span className="text-emerald-700 font-semibold">Valid</span> : <span className="text-rose-700">{r.errors.join('; ')}</span>}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="flex gap-2 mt-3">
                        <button onClick={() => send(true)} disabled={busy || !preview.valid} data-testid="upload-import-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Import {preview.valid} valid row(s)</button>
                        <button onClick={() => { setPreview(null); setFile(null); }} data-testid="upload-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                    </div>
                </div>
            )}
        </Card>
    );
};
