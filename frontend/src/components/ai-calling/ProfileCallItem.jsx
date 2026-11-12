import { useState } from 'react';
import { CaretDown } from '@phosphor-icons/react';
import { yesNo, fmtTime } from './callFormat';

const API = process.env.REACT_APP_BACKEND_URL;

const Field = ({ label, value, testid }) => (
    <div className="min-w-0">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">{label}</div>
        <div className="text-sm text-zinc-200 break-words whitespace-pre-wrap" data-testid={testid}>{value ?? 'Not available'}</div>
    </div>
);

const PURPOSE = { interview_confirmation: 'Pre-interview confirmation', missed_interview_followup: 'Missed-interview follow-up' };

export const ProfileCallItem = ({ call }) => {
    const [open, setOpen] = useState(false);
    const r = call.response || {};
    const missed = call.purpose === 'missed_interview_followup';
    const flags = [r.missed_interview_outcome === 'RUNNING_LATE' && 'RUNNING_LATE', r.missed_interview_outcome === 'CLAIMS_ATTENDED' && 'CLAIMS_ATTENDED',
        r.wants_reschedule === true && 'RESCHEDULE_REQUEST_PENDING', call.ui_state === 'Needs Review' && 'NEEDS_REVIEW',
        call.status === 'no-answer' && 'NO_ANSWER', call.status === 'busy' && 'BUSY'].filter(Boolean);
    const qs = r.candidate_questions?.length ? r.candidate_questions.map(q => `• ${q}`).join('\n') : (call.response ? 'None asked' : null);
    return (
        <li className="border border-zinc-800 bg-zinc-900/50" data-testid={`profile-call-${call.id}`}>
            <button onClick={() => setOpen(o => !o)} data-testid={`profile-call-toggle-${call.id}`} className="w-full px-4 py-3 flex flex-wrap items-center gap-3 text-left hover:bg-zinc-900">
                <span className="text-sm text-zinc-200 font-medium flex-1 min-w-[10rem]">{fmtTime(call.dispatched_at || call.created_at) || '—'}</span>
                <span className="text-xs px-2 py-0.5 rounded border border-zinc-700 text-zinc-300 uppercase" data-testid="profile-call-mode">{call.mode === 'live' ? 'Live' : 'Testing'}</span>
                <span className="text-xs px-2 py-0.5 rounded border border-violet-400 bg-violet-100 text-violet-900 font-semibold" data-testid="profile-call-purpose">{PURPOSE[call.purpose] || PURPOSE.interview_confirmation}</span>
                {flags.map(f => <span key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-400 font-semibold" data-testid={`profile-call-flag-${f}`}>{f.replace(/_/g, ' ')}</span>)}
                <span className="text-xs px-2 py-0.5 rounded border border-cyan-800/50 bg-cyan-900/30 text-cyan-300" data-testid="profile-call-status">{call.ui_state} · {call.status || '—'}</span>
                <span className="text-xs text-zinc-400" data-testid="profile-call-attendance">Attendance: <b className="text-zinc-200">{r.attendance_status || 'UNKNOWN'}</b></span>
                <CaretDown size={14} className={`text-zinc-500 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && (
                <div className="px-4 pb-4 pt-1 space-y-4 border-t border-zinc-800" data-testid={`profile-call-details-${call.id}`}>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <Field label="Duration" value={call.duration_seconds != null ? `${Math.round(call.duration_seconds)} s` : null} testid="profile-call-duration" />
                        <Field label="Reschedule request" value={yesNo(r.wants_reschedule)} testid="profile-call-reschedule" />
                        <Field label="Virtual interview request" value={yesNo(r.requested_virtual)} testid="profile-call-virtual" />
                    </div>
                    <Field label="Decline reason" value={r.rejection_reason} testid="profile-call-decline" />
                    {(missed || r.missed_interview_outcome) && (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="profile-call-missed-fields">
                            <Field label="Missed-interview outcome" value={r.missed_interview_outcome} testid="profile-call-missed-outcome" />
                            <Field label="Missed-interview reason" value={r.missed_interview_reason} testid="profile-call-missed-reason" />
                            <Field label="Expected arrival time" value={r.expected_arrival_time} testid="profile-call-arrival" />
                            <Field label="Attendance dispute" value={yesNo(r.attendance_dispute)} testid="profile-call-dispute" />
                        </div>
                    )}
                    <Field label="Preferred reschedule date/time" value={r.preferred_reschedule_datetime} testid="profile-call-preferred" />
                    <Field label="Candidate questions" value={qs} testid="profile-call-questions" />
                    <Field label="Call summary" value={r.call_summary} testid="profile-call-summary" />
                    <div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Recording</div>
                        {call.has_recording
                            ? <audio controls preload="none" className="w-full" data-testid="profile-call-recording" src={`${API}/api/ai-calling/calls/${call.id}/recording`} />
                            : <div className="text-sm text-zinc-500">Not available</div>}
                    </div>
                    <div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Full transcript (questions and AI responses)</div>
                        <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-sans max-h-72 overflow-y-auto border border-zinc-800 bg-zinc-950 p-3" data-testid="profile-call-transcript">{call.transcript || 'Not available'}</pre>
                    </div>
                </div>
            )}
        </li>
    );
};
