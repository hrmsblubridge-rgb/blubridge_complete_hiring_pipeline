import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CalendarCheck } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const Num = ({ label, value, onChange, min, max, testid, suffix }) => (
    <label className="text-xs text-[#6b7280] flex flex-col gap-1">
        {label}
        <span className="flex items-center gap-2">
            <input type="number" min={min} max={max} value={value} onChange={e => onChange(Number(e.target.value))} data-testid={testid}
                className="w-28 border border-[#e5e3d8] rounded-lg px-2 py-1.5 text-sm text-[#1a2332]" />
            {suffix && <span>{suffix}</span>}
        </span>
    </label>
);

const Toggle = ({ on, onChange, testid }) => (
    <button type="button" onClick={() => onChange(!on)} data-testid={testid}
        className={`px-3 py-1 rounded-full text-xs font-bold border ${on ? 'bg-emerald-50 border-emerald-300 text-emerald-800' : 'bg-zinc-100 border-zinc-300 text-zinc-600'}`}>
        {on ? 'ON' : 'OFF'}
    </button>
);

// AI Calling → Settings → Call Scheduling (both purposes + queue capacity). Saving never places a call.
export const SchedulingPanel = () => {
    const [d, setD] = useState(null);
    const [f, setF] = useState(null);
    const [busy, setBusy] = useState(false);
    const load = () => aiApi.get('/scheduling').then(r => {
        setD(r.data);
        const c = r.data.interview_confirmation, m = r.data.missed_interview_followup;
        setF({ confirm_enabled: c.enabled, confirm_offset_days: c.offset_days, missed_enabled: m.enabled,
            missed_offset_minutes: m.offset_minutes, ...r.data.capacity });
    }).catch(e => toast.error(errMsg(e)));
    useEffect(() => { load(); }, []);
    const set = (k) => (v) => setF(x => ({ ...x, [k]: v }));
    const save = async () => {
        setBusy(true);
        try { const r = await aiApi.put('/scheduling', f); toast.success('Call scheduling saved. Pending jobs were recalculated; no call was placed.'); setD(r.data); }
        catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    if (!d || !f) return null;
    const c = d.interview_confirmation, m = d.missed_interview_followup;
    return (
        <Card data-testid="scheduling-panel">
            <SectionTitle icon={CalendarCheck}>Call Scheduling</SectionTitle>
            <div className="grid md:grid-cols-2 gap-5">
                <div className="border border-[#e5e3d8] rounded-xl p-4 space-y-3" data-testid="scheduling-confirmation">
                    <div className="flex items-center justify-between"><p className="font-bold text-sm">Pre-Interview Confirmation</p><Toggle on={f.confirm_enabled} onChange={set('confirm_enabled')} testid="confirm-enabled-toggle" /></div>
                    <Num label="Call this many days before the interview (1–7)" value={f.confirm_offset_days} onChange={set('confirm_offset_days')} min={1} max={7} testid="confirm-offset-input" suffix="days" />
                    <p className="text-xs text-[#6b7280]">One retry after {c.retry_minutes} min, only after a no-answer or busy. Calling window {c.window[0]}–{c.window[1]} IST. Needs at least 2 h before the interview.</p>
                </div>
                <div className="border border-[#e5e3d8] rounded-xl p-4 space-y-3" data-testid="scheduling-missed">
                    <div className="flex items-center justify-between"><p className="font-bold text-sm">Missed-Interview Follow-up</p><Toggle on={f.missed_enabled} onChange={set('missed_enabled')} testid="missed-enabled-toggle" /></div>
                    <Num label="Call this many minutes after the interview (60–10080 = 1 h–7 days)" value={f.missed_offset_minutes} onChange={set('missed_offset_minutes')} min={60} max={10080} testid="missed-offset-input" suffix="min" />
                    <p className="text-xs text-[#6b7280]">One retry after {m.retry_minutes} min, only after a no-answer or busy. Calling window {m.window[0]}–{m.window[1]} IST. Attendance source: <b>{m.attendance_source}</b>.</p>
                </div>
            </div>
            <div className="flex flex-wrap gap-4 mt-4" data-testid="scheduling-capacity">
                <Num label="Max calls per day" value={f.live_daily_call_limit} onChange={set('live_daily_call_limit')} min={0} max={100000} testid="cap-daily-input" />
                <Num label="Pilot daily cap" value={f.live_pilot_daily_cap} onChange={set('live_pilot_daily_cap')} min={0} max={100000} testid="cap-pilot-input" />
                <Num label="Max calls at once" value={f.live_max_concurrent_calls} onChange={set('live_max_concurrent_calls')} min={1} max={50} testid="cap-concurrent-input" />
                <Num label="Jobs per worker run" value={f.live_queue_capacity} onChange={set('live_queue_capacity')} min={1} max={1000} testid="cap-queue-input" />
            </div>
            <p className="text-xs text-[#6b7280] mt-2">The effective daily limit is the lower of the two daily values. Jobs that don't fit stay queued; none are deleted. Set these to your verified Bolna capacity.</p>
            <button onClick={save} disabled={busy} data-testid="scheduling-save-btn" className="mt-4 px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50">{busy ? 'Saving…' : 'Save call scheduling'}</button>
        </Card>
    );
};
