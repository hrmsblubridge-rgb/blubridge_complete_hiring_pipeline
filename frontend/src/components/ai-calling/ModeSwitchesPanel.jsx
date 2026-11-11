import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ToggleRight, Warning, CheckCircle, XCircle } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const OnOff = ({ on }) => <b className={on ? 'text-emerald-700' : 'text-zinc-500'}>{on ? 'ON' : 'OFF'}</b>;

const Switch = ({ label, help, on, onToggle, testid, busy }) => (
    <div className="flex items-start gap-3 bg-white border border-[#e5e3d8] rounded-xl p-4">
        <div className="flex-1">
            <p className="text-sm font-semibold text-[#1a2332]">{label} <OnOff on={on} /></p>
            <p className="text-xs text-[#6b7280] mt-1">{help}</p>
        </div>
        <button role="switch" aria-checked={on} disabled={busy} onClick={onToggle} data-testid={testid}
            className={`w-12 h-7 rounded-full relative transition-colors disabled:opacity-50 ${on ? 'bg-teal-600' : 'bg-zinc-300'}`}>
            <span className={`absolute top-1 w-5 h-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
    </div>
);

const Source = ({ name, d, testid }) => (
    <div className="bg-white border border-[#e5e3d8] rounded-xl p-4" data-testid={testid}>
        <p className="text-sm font-semibold flex items-center gap-2">
            {d?.can_call ? <CheckCircle size={16} className="text-emerald-600" /> : <XCircle size={16} className="text-rose-600" />}
            {name}: {d?.can_call ? 'can call' : 'blocked'}
        </p>
        {d?.blockers?.length > 0 && <ul className="mt-2 text-xs text-[#6b7280] list-disc pl-5 space-y-0.5">{d.blockers.map(b => <li key={b}>{b}</li>)}</ul>}
    </div>
);

export const ModeSwitchesPanel = () => {
    const [st, setSt] = useState(null);
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => aiApi.get('/switches').then(r => setSt(r.data)).catch(e => toast.error(errMsg(e))), []);
    useEffect(() => { load(); }, [load]);
    const flip = async (key) => {
        setBusy(true);
        try { setSt((await aiApi.post('/switches', { [key]: !st[key], expected_version: st.switch_version })).data); toast.success('Switch updated. No calls were started.'); }
        catch (e) { toast.error(errMsg(e)); load(); } finally { setBusy(false); }
    };
    const warn = st && ((st.ai_live_enabled && !st.live.can_call) || (st.ai_test_enabled && !st.test.can_call));

    return (
        <Card data-testid="mode-switches-panel">
            <SectionTitle icon={ToggleRight}>AI calling switches</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-4">
                Overall Website Test Mode (read-only here): <OnOff on={st?.overall_test_mode} /> <span data-testid="overall-test-mode" className="hidden">{String(st?.overall_test_mode)}</span>.
                Both AI switches may be ON together. The emergency stop overrides everything.
            </p>
            <div className="grid md:grid-cols-2 gap-3 mb-4">
                <Switch label="AI Test Mode" on={!!st?.ai_test_enabled} busy={busy || !st} onToggle={() => flip('ai_test_enabled')} testid="switch-ai-test"
                    help="Manual Call Now calls to saved, consented test recipients only. Works whatever the Overall Test Mode is." />
                <Switch label="AI Live Mode" on={!!st?.ai_live_enabled} busy={busy || !st} onToggle={() => flip('ai_live_enabled')} testid="switch-ai-live"
                    help="Scheduled calls to existing eligible candidates. Blocked while Overall Test Mode is OFF. Turning it ON never starts dialling by itself." />
            </div>
            <div className="bg-[#faf9f1] border border-[#e5e3d8] rounded-xl p-4 mb-4" data-testid="effective-status">
                <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">Effective calling (switch policy)</p>
                <p className="text-lg font-bold text-[#1a2332]" data-testid="effective-label">{st?.effective?.label || '—'}</p>
            </div>
            {warn && (
                <div className="flex gap-2 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-xl px-3 py-2 mb-4" data-testid="switch-blocked-warning">
                    <Warning size={18} weight="fill" className="shrink-0 mt-0.5" /> A switch is ON, but calling is still blocked by the requirements listed below.
                </div>
            )}
            <div className="grid md:grid-cols-2 gap-3 mb-4">
                <Source name="Test-list calls" d={st?.test} testid="source-test" />
                <Source name="Live candidate calls" d={st?.live} testid="source-live" />
            </div>
            <p className="text-xs text-[#6b7280] mb-2" data-testid="live-dispatch-status">
                Live Dispatch Authorization: <b className="text-rose-700">{st?.live_dispatch_authorized ? 'GRANTED' : 'OFF'}</b>. It is a separate, explicit approval (typed phrase "{st?.live_auth_phrase}") and cannot be activated in this phase.
                Live limits: <b data-testid="live-limits">{st?.live_limits?.daily} calls/day · {st?.live_limits?.concurrent} at a time</b>.
            </p>
            <button disabled title="Activation is disabled in this phase" data-testid="live-authorize-btn"
                className="mb-3 px-4 py-2 rounded-lg bg-rose-700 text-white text-xs font-semibold opacity-40 cursor-not-allowed">Authorize Live Dispatch (disabled)</button>
            <details className="text-xs" data-testid="policy-table">
                <summary className="cursor-pointer font-semibold text-[#1a2332]">Show all 8 switch combinations</summary>
                <table className="mt-2 w-full">
                    <thead className="text-[#9b9787] uppercase"><tr><th className="text-left py-1">Overall Test</th><th className="text-left">AI Test</th><th className="text-left">AI Live</th><th className="text-left">Effective</th></tr></thead>
                    <tbody>{st?.policy?.map((r, i) => (
                        <tr key={i} className="border-t border-[#efede5]"><td className="py-1">{r.overall_test ? 'ON' : 'OFF'}</td><td>{r.ai_test ? 'ON' : 'OFF'}</td><td>{r.ai_live ? 'ON' : 'OFF'}</td><td>{r.label}</td></tr>
                    ))}</tbody>
                </table>
            </details>
        </Card>
    );
};
