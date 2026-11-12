import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { BellRinging } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { fmtTime } from './callFormat';

export const ALERT_LABEL = { RUNNING_LATE: 'Running late', CLAIMS_ATTENDED: 'Says they attended (dispute)',
    RESCHEDULE_REQUEST_PENDING: 'Reschedule request pending', WRONG_NUMBER: 'Wrong number — calls blocked' };

const detailText = (a) => [a.detail?.expected_arrival_time && `arrival ${a.detail.expected_arrival_time}`,
    a.detail?.preferred_reschedule_datetime && `preferred ${a.detail.preferred_reschedule_datetime}`,
    a.detail?.reason].filter(Boolean).join(' · ');

// HR review alerts raised by AI call outcomes. Resolving an alert never edits the booking or OTP.
export const AlertsPanel = ({ registrationId, dark }) => {
    const [rows, setRows] = useState(null);
    const load = () => aiApi.get('/alerts', { params: registrationId ? { registration_id: registrationId } : {} })
        .then(r => setRows(r.data.alerts)).catch(() => setRows([]));
    useEffect(() => { load(); }, [registrationId]); // eslint-disable-line react-hooks/exhaustive-deps
    const resolve = async (id) => {
        try { await aiApi.post(`/alerts/${id}/resolve`, { note: 'Reviewed' }); load(); toast.success('Alert resolved'); } catch (e) { toast.error(errMsg(e)); }
    };
    if (!rows) return null;
    const list = (
        <ul className="space-y-2" data-testid="ai-alerts-list">
            {rows.length === 0 && <li className={`text-sm ${dark ? 'text-zinc-500' : 'text-[#9b9787]'}`} data-testid="ai-alerts-empty">No open alerts.</li>}
            {rows.map(a => (
                <li key={a.id} className={`flex flex-wrap items-center gap-2 text-sm border rounded-lg px-3 py-2 ${dark ? 'border-amber-800/60 bg-amber-900/20 text-amber-200' : 'border-amber-200 bg-amber-50 text-amber-900'}`} data-testid={`ai-alert-${a.id}`}>
                    <b>{ALERT_LABEL[a.type] || a.type}</b>
                    <span className="text-xs">{a.purpose === 'missed_interview_followup' ? 'Missed-interview follow-up' : 'Pre-interview confirmation'} · {fmtTime(a.created_at)}</span>
                    {detailText(a) && <span className="text-xs">{detailText(a)}</span>}
                    <button onClick={() => resolve(a.id)} data-testid={`ai-alert-resolve-${a.id}`} className="ml-auto text-xs underline">Mark reviewed</button>
                </li>
            ))}
        </ul>
    );
    if (dark) return list;
    return <Card data-testid="ai-alerts-panel"><SectionTitle icon={BellRinging}>HR review alerts</SectionTitle>{list}</Card>;
};
