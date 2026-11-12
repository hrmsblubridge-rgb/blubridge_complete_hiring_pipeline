// Consent Editor (Settings → Consent Configuration). Any admin may edit/save drafts & preview.
// ONLY the designated top-level admin (enforced server-side) may publish a new version.
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Note, Eye, UploadSimple, Spinner, Clock } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';

export const ConsentEditorPanel = () => {
    const [draft, setDraft] = useState({ title: '', text: '' });
    const [latest, setLatest] = useState(null);
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [previewOpen, setPreviewOpen] = useState(false);
    const [publishOpen, setPublishOpen] = useState(false);
    const [confirmation, setConfirmation] = useState('');
    const [publishing, setPublishing] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [e, v] = await Promise.all([aiApi.get('/consent/editor'), aiApi.get('/consent/versions')]);
            setDraft({ title: e.data.draft.title || '', text: e.data.draft.text || '' });
            setLatest(e.data.latest_published); setVersions(v.data.items);
        } catch (e) { toast.error(errMsg(e, 'Failed to load consent editor')); } finally { setLoading(false); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const save = async () => {
        setSaving(true);
        try { await aiApi.post('/consent/editor/draft', { title: draft.title, text: draft.text });
            toast.success('Draft saved'); }
        catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
    };
    const publish = async () => {
        setPublishing(true);
        try {
            const r = (await aiApi.post('/consent/publish', { confirmation })).data;
            toast.success('Published ' + r.version_id); setPublishOpen(false); setConfirmation(''); load();
        } catch (e) { toast.error(errMsg(e, 'Publish failed')); } finally { setPublishing(false); }
    };

    return (
        <Card data-testid="consent-editor-panel">
            <SectionTitle icon={Note}>Consent Configuration</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-3">
                Candidate-facing wording. Only the designated top-level admin can publish. Published versions are
                immutable and existing candidate consents keep the version they originally accepted.
            </p>

            {loading ? <p className="text-sm text-[#6b7280] flex items-center gap-2"><Spinner size={14} className="animate-spin" /> Loading…</p> : (
                <>
                    <label className="block mb-3">
                        <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase block mb-1">Title</span>
                        <input value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))}
                            data-testid="consent-draft-title" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                    </label>
                    <label className="block mb-3">
                        <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase block mb-1">Draft wording</span>
                        <textarea rows={8} value={draft.text} onChange={e => setDraft(d => ({ ...d, text: e.target.value }))}
                            data-testid="consent-draft-text" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm font-mono" />
                    </label>
                    <div className="flex flex-wrap gap-2">
                        <button onClick={save} disabled={saving} data-testid="consent-save-draft-btn"
                            className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {saving ? <><Spinner size={14} className="animate-spin" /> Saving…</> : 'Save Draft'}
                        </button>
                        <button onClick={() => setPreviewOpen(true)} data-testid="consent-preview-btn"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold flex items-center gap-2"><Eye size={14} /> Preview</button>
                        <button onClick={() => setPublishOpen(true)} data-testid="consent-publish-btn"
                            className="px-4 py-2 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold flex items-center gap-2"><UploadSimple size={14} /> Publish New Version</button>
                    </div>
                    {latest && (
                        <div className="mt-4 bg-[#faf9f1] border border-[#e5e3d8] rounded-xl p-3 text-xs">
                            <p className="font-semibold text-[#1a2332] mb-1"><Clock size={12} className="inline" /> Latest published: {latest.version_id}</p>
                            <p className="text-[#6b7280]">by {latest.published_by} · {new Date(latest.published_at).toLocaleString()}</p>
                        </div>
                    )}
                    {versions.length > 0 && (
                        <details className="mt-3 text-xs" data-testid="consent-versions-details">
                            <summary className="cursor-pointer font-semibold">Version history ({versions.length})</summary>
                            <ul className="mt-2 space-y-1">
                                {versions.map(v => <li key={v.version_id} data-testid={`consent-version-${v.version_id}`}><b>{v.version_id}</b> · {v.published_by} · {new Date(v.published_at).toLocaleString()}</li>)}
                            </ul>
                        </details>
                    )}
                </>
            )}

            <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                <DialogContent data-testid="consent-preview-dialog" className="bg-[#fffdf7] max-w-2xl">
                    <DialogHeader><DialogTitle>Candidate preview</DialogTitle></DialogHeader>
                    <h3 className="text-lg font-bold text-[#1a2332]">{draft.title || '(no title)'}</h3>
                    <div className="text-sm text-[#1a2332] whitespace-pre-line border border-[#e5e3d8] bg-white rounded-xl p-4 max-h-80 overflow-auto" data-testid="consent-preview-body">
                        {draft.text || '(empty)'}
                    </div>
                </DialogContent>
            </Dialog>

            <Dialog open={publishOpen} onOpenChange={o => { setPublishOpen(o); if (!o) setConfirmation(''); }}>
                <DialogContent data-testid="consent-publish-dialog" className="bg-[#fffdf7]">
                    <DialogHeader>
                        <DialogTitle>Publish new consent version?</DialogTitle>
                        <DialogDescription>
                            Only the top-level admin may publish. Published versions are immutable. Existing consents
                            retain the version originally accepted; withdrawn consents and Do-Not-Call records are not affected.
                        </DialogDescription>
                    </DialogHeader>
                    <label className="block text-sm">
                        <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Type: PUBLISH CONSENT VERSION</span>
                        <input value={confirmation} onChange={e => setConfirmation(e.target.value)} autoFocus data-testid="consent-publish-confirm"
                            className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm font-mono" />
                    </label>
                    <DialogFooter>
                        <button onClick={() => setPublishOpen(false)} disabled={publishing} data-testid="consent-publish-cancel"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={publish} disabled={publishing || confirmation !== 'PUBLISH CONSENT VERSION'} data-testid="consent-publish-confirm-btn"
                            className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {publishing ? <><Spinner size={14} className="animate-spin" /> Publishing…</> : 'Publish'}
                        </button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
};
