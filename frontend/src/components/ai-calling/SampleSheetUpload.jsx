import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { DownloadSimple, UploadSimple, FileXls } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { UploadPreview } from './UploadPreview';

const download = async (format) => {
    try {
        const r = await aiApi.get(`/template?format=${format}`, { responseType: 'blob' });
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ai_test_candidates_sample.${format}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) { toast.error('Sample sheet download failed'); }
};

export const SampleSheetUpload = ({ onImported }) => {
    const inputRef = useRef(null);
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(false);

    const pick = async (e) => {
        const f = e.target.files?.[0];
        e.target.value = '';
        if (!f) return;
        if (!/\.(xlsx|csv)$/i.test(f.name)) { toast.error('Unsupported file type. Upload .xlsx or .csv only'); return; }
        if (f.size > 2 * 1024 * 1024) { toast.error('File too large (max 2 MB)'); return; }
        const fd = new FormData();
        fd.append('file', f);
        setBusy(true);
        try { setPreview((await aiApi.post('/test-candidates/upload', fd)).data); }
        catch (err) { toast.error(errMsg(err, 'Upload failed')); setPreview(null); }
        finally { setBusy(false); }
    };

    return (
        <Card data-testid="upload-panel">
            <SectionTitle icon={FileXls}>Upload test candidates (Excel / CSV)</SectionTitle>
            <div className="flex flex-wrap gap-2">
                <button onClick={() => download('xlsx')} data-testid="download-sample-sheet-btn" className="px-4 py-2 rounded-lg bg-white border border-teal-300 text-sm font-semibold text-teal-800 hover:bg-teal-50 flex items-center gap-2"><DownloadSimple size={16} /> Download Sample Sheet</button>
                <button onClick={() => download('csv')} data-testid="download-sample-csv-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold text-[#1a2332] hover:bg-[#efede5] flex items-center gap-2"><DownloadSimple size={16} /> CSV sample</button>
                <button onClick={() => inputRef.current?.click()} disabled={busy} data-testid="upload-file-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-60"><UploadSimple size={16} /> {busy ? 'Reading…' : 'Upload .xlsx / .csv'}</button>
                <input ref={inputRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={pick} data-testid="upload-file-input" />
            </div>
            <p className="text-xs text-[#6b7280] mt-2">Uploads are previewed first. Nothing is saved until you import, rows are never auto-approved, and no calls are started.</p>
            {preview && <UploadPreview preview={preview} onClose={() => setPreview(null)} onImported={() => { setPreview(null); onImported(); }} />}
        </Card>
    );
};
