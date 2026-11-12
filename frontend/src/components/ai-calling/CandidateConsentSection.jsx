// Candidate AI Voice Call Consent — merged section (A2).
//
// Reuses the existing editor/version backend. No new storage. Shows the currently published
// wording as the live text, the editable draft, and a candidate booking-form preview.
// Publish is gated server-side to Admin User.
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Note, Eye, UploadSimple, Spinner, Clock, Megaphone, CheckCircle } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';

const BookingFormPreview = ({ title, text }) => (
    <div className="bg-white border border-[#e5e3d8] rounded-xl p-4" data-testid="consent-booking-preview">
        <p className="text-[11px] uppercase tracking-wider text-[#9b9787] mb-2">Candidate booking-form appearance</p>
        <label className="flex items-start gap-2 cursor-not-allowed">
            <input type="checkbox" disabled className="mt-1" />
            <div>
                <p className="text-sm font-semibold text-[#1a2332]">{title || '(no title)'}</p>
                <p className="text-xs text-[#6b7280] whitespace-pre-line mt-1">{text || '(empty)'}</p>
            </div>
        </label>
        <p className="text-[10px] text-[#9b9787] mt-2">Optional, unchecked by default. Candidates can book without consenting.</p>
    </div>
);

export const CandidateConsentSection = () => {
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
        } catch (e) { toast.error(errMsg(e, 'Failed to load consent')); } finally { setLoading(false); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const save = async () => {
        setSaving(true);
        try { await aiApi.post('/consent/editor/draft', { title: draft.title, text: draft.text }); toast.success('Draft saved'); }
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
        <Card data-testid="candidate-consent-section">
            <SectionTitle icon={Megaphone}>Candidate AI Voice Call Consent</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-3">
                The wording below is used on the candidate booking form. Consent remains optional and
                unchecked by default. Only the designated top-level admin can publish a new version;
                published versions are immutable and never retroactively applied to prior consents.
            </p>

            {loading ? <p className="text-sm text-[#6b7280] flex items-center gap-2"><Spinner size={14} className="animate-spin" /> Loading…</p> : (
                <div className="grid lg:grid-cols-2 gap-4">
                    {/* LEFT: current published + editable draft */}
                    <div className="space-y-3">
                        <div className="border border-emerald-200 bg-emerald-50 rounded-xl p-3" data-testid="consent-current-published">
                            <p className="text-[10px] uppercase tracking-wider text-emerald-800 mb-1 flex items-center gap-1"><CheckCircle size={12} weight="fill" /> Currently published (live on booking form)</p>
                            {latest ? (
                                <>
                                    <p className="text-sm font-bold text-[#1a2332]">{latest.title}</p>
                                    <p className="text-xs text-[#1a2332]/80 whitespace-pre-line mt-1">{latest.text}</p>
                                    <p className="text-[10px] text-[#6b7280] mt-2">{latest.version_id} · published by {latest.published_by} · {new Date(latest.published_at).toLocaleString()}</p>
                                </>
                            ) : (
                                <p className="text-sm text-[#6b7280]" data-testid="consent-no-published">No version published yet — the booking form uses the existing default wording.</p>
                            )}
                        </div>

                        <label className="block">
                            <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase block mb-1 flex items-center gap-1"><Note size={12} /> Draft title</span>
                            <input value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))}
                                data-testid="consent-draft-title" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        </label>
                        <label className="block">
                            <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase block mb-1">Draft wording (not live)</span>
                            <textarea rows={6} value={draft.text} onChange={e => setDraft(d => ({ ...d, text: e.target.value }))}
                                data-testid="consent-draft-text" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm font-mono" />
                        </label>
                        <div className="flex flex-wrap gap-2">
                            <button onClick={save} disabled={saving} data-testid="consent-save-draft-btn"
                                className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                                {saving ? <><Spinner size={14} className="animate-spin" /> Saving…</> : 'Save Draft'}
                            </button>
                            <button onClick={() => setPreviewOpen(true)} data-testid="consent-preview-btn"
                                className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold flex items-center gap-2"><Eye size={14} /> Expand Preview</button>
                            <button onClick={() => setPublishOpen(true)} data-testid="consent-publish-btn"
                                className="px-4 py-2 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold flex items-center gap-2"><UploadSimple size={14} /> Publish New Version</button>
                        </div>
                    </div>

                    {/* RIGHT: inline candidate preview + version history */}
                    <div className="space-y-3">
                        <BookingFormPreview title={draft.title} text={draft.text} />
                        <p className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1" data-testid="consent-draft-warning">
                            This is a <b>DRAFT PREVIEW</b> — candidates still see the currently-published wording until a new version is published.
                        </p>
                        {versions.length > 0 && (
                            <details className="text-xs" data-testid="consent-versions-details">
                                <summary className="cursor-pointer font-semibold text-[#1a2332]"><Clock size={12} className="inline mr-1" /> Version history ({versions.length})</summary>
                                <ul className="mt-2 space-y-1">
                                    {versions.map(v => <li key={v.version_id} data-testid={`consent-version-${v.version_id}`}><b>{v.version_id}</b> · {v.published_by} · {new Date(v.published_at).toLocaleString()}</li>)}
                                </ul>
                            </details>
                        )}
                    </div>
                </div>
            )}

            <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                <DialogContent data-testid="consent-preview-dialog" className="bg-[#fffdf7] max-w-2xl">
                    <DialogHeader><DialogTitle>Draft preview (not live)</DialogTitle></DialogHeader>
                    <BookingFormPreview title={draft.title} text={draft.text} />
                </DialogContent>
            </Dialog>

            <Dialog open={publishOpen} onOpenChange={o => { setPublishOpen(o); if (!o) setConfirmation(''); }}>
                <DialogContent data-testid="consent-publish-dialog" className="bg-[#fffdf7]">
                    <DialogHeader>
                        <DialogTitle>Publish new consent version?</DialogTitle>
                        <DialogDescription>
                            Only the top-level admin may publish. Published versions are immutable. Candidates who already
                            accepted an older version keep their original consent. Withdrawn consents and Do-Not-Call remain in force.
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
