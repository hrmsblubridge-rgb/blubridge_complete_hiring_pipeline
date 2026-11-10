import { useState } from 'react';
import { toast } from 'sonner';
import { Waveform, ChatText, ListBullets, ArrowsClockwise, SealWarning } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { StateBadge, yesNo, fmtTime } from './callFormat';

const F = ({ k, v, testid }) => (
    <div className="py-1.5 border-b border-[#efede5] last:border-0">
        <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">{k}</p>
        <p className="text-sm text-[#1a2332] font-medium whitespace-pre-wrap" data-testid={testid}>{v ?? 'Not available'}</p>
    </div>
);

export const CallDetails = ({ call, onUpdated }) => {
    const [busy, setBusy] = useState(false);
    const r = call.response || {};
    const run = async (fn) => {
        setBusy(true);
        try { onUpdated((await fn()).data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    const review = () => {
        const v = window.prompt('Checked this call in the Bolna dashboard? Type REVIEWED to unlock new test calls.');
        if (v) run(() => aiApi.post(`/test-calls/${call.id}/resolve-review`, { confirmation: v }));
    };
    const qs = r.candidate_questions?.length ? r.candidate_questions.map(q => `• ${q}`).join('\n') : (call.response ? 'None asked' : null);
    const err = call.provider_error ? `${call.provider_error.kind}${call.provider_error.http_status ? ` (HTTP ${call.provider_error.http_status})` : ''}${call.provider_error.message ? ` — ${call.provider_error.message}` : ''}` : null;

    return (
        <div className="space-y-5" data-testid="call-details">
            <Card>
                <div className="flex flex-wrap items-center gap-3 mb-3">
                    <h3 className="text-lg font-bold text-[#1a2332] flex-1" data-testid="detail-name">{call.candidate_name} <span className="font-mono text-sm text-[#6b7280]">{call.phone_masked}</span></h3>
                    <StateBadge s={call.ui_state} />
                    <button disabled={busy} onClick={() => run(() => aiApi.post(`/test-calls/${call.id}/check`))} data-testid="check-bolna-btn"
                        className="px-3 py-1.5 rounded-lg border border-[#e5e3d8] bg-white text-xs font-semibold flex items-center gap-1 hover:bg-[#efede5] disabled:opacity-40"><ArrowsClockwise size={14} /> Check with Bolna</button>
                    {call.state === 'needs_review' && <button onClick={review} data-testid="resolve-review-btn" className="px-3 py-1.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-xs font-semibold flex items-center gap-1"><SealWarning size={14} /> Mark reviewed</button>}
                </div>
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-x-6">
                    <F k="Call time" v={fmtTime(call.dispatched_at)} />
                    <F k="Interview (IST)" v={`${call.interview_date || ''} ${call.interview_time || ''}`} />
                    <F k="Language" v={call.language} />
                    <F k="Bolna status" v={call.status || '—'} testid="detail-status" />
                    <F k="Duration" v={call.duration_seconds != null ? `${Math.round(call.duration_seconds)} s` : null} testid="detail-duration" />
                    <F k="Hangup reason" v={call.hangup_reason} />
                    <F k="Execution ID" v={call.execution_id} />
                    <F k="Provider error" v={err} testid="detail-error" />
                </div>
            </Card>
            <Card data-testid="extracted-panel">
                <SectionTitle icon={ListBullets}>Extracted response</SectionTitle>
                <div className="grid sm:grid-cols-3 gap-x-6">
                    <F k="Attendance" v={r.attendance_status || 'UNKNOWN'} testid="detail-attendance" />
                    <F k="Wants reschedule" v={yesNo(r.wants_reschedule)} testid="detail-reschedule" />
                    <F k="Virtual interview requested" v={yesNo(r.requested_virtual)} testid="detail-virtual" />
                </div>
                <F k="Rejection reason" v={r.rejection_reason} testid="detail-rejection" />
                <F k="Candidate questions" v={qs} testid="detail-questions" />
                <F k="Call summary" v={r.call_summary} testid="detail-summary" />
            </Card>
            <div className="grid lg:grid-cols-2 gap-5">
                <Card data-testid="recording-panel">
                    <SectionTitle icon={Waveform}>Recording</SectionTitle>
                    {call.has_recording
                        ? <audio controls preload="none" className="w-full" data-testid="recording-player" src={`${process.env.REACT_APP_BACKEND_URL}/api/ai-calling/calls/${call.id}/recording`} />
                        : <p className="text-sm text-[#9b9787]">Not available yet.</p>}
                </Card>
                <Card data-testid="transcript-panel">
                    <SectionTitle icon={ChatText}>Full transcript (questions and AI answers)</SectionTitle>
                    <pre className="text-xs whitespace-pre-wrap max-h-96 overflow-y-auto text-[#1a2332] font-sans" data-testid="detail-transcript">{call.transcript || 'Not available yet.'}</pre>
                </Card>
            </div>
        </div>
    );
};
