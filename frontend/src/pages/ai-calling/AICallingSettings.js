import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { GearSix, Siren, Key } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { BolnaConfigPanel } from '../../components/ai-calling/BolnaConfigPanel';

const inputCls = 'w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-teal-500';
const FIELDS = [
    ['daily_call_limit', 'Daily test call limit', 'number'],
    ['max_concurrent_calls', 'Max concurrent calls', 'number'],
    ['call_window_start', 'Call window start', 'time'],
    ['call_window_end', 'Call window end', 'time'],
    ['default_company_name', 'Default company name', 'text'],
    ['default_office_address', 'Default office address', 'text'],
];

export default function AICallingSettings() {
    const [s, setS] = useState(null);
    const [f, setF] = useState({});
    const apply = (d) => { setS(d); setF(Object.fromEntries(FIELDS.map(([k]) => [k, d[k] ?? '']))); };
    useEffect(() => { aiApi.get('/settings').then(r => apply(r.data)).catch(e => toast.error(errMsg(e))); }, []);

    const save = async () => {
        const body = { ...f, daily_call_limit: Number(f.daily_call_limit), max_concurrent_calls: Number(f.max_concurrent_calls) };
        try { apply((await aiApi.put('/settings', body)).data); toast.success('Settings saved'); } catch (e) { toast.error(errMsg(e)); }
    };
    const estop = async () => {
        try { apply((await aiApi.post('/emergency-stop', { active: !s.emergency_stop })).data); } catch (e) { toast.error(errMsg(e)); }
    };

    return (
        <div className="min-h-screen" data-testid="ai-settings-page">
            <AICallingHeader title="AI Calling Settings" subtitle="Limits, defaults and safety switches" mode={s?.mode} emergencyStop={s?.emergency_stop} />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <Card>
                    <SectionTitle icon={Siren}>Emergency stop</SectionTitle>
                    <div className="flex flex-wrap items-center gap-3">
                        <p className="flex-1 text-sm text-[#1a2332]">When active, every call is blocked, pending jobs are cancelled and running batches stop.</p>
                        <button onClick={estop} data-testid="estop-toggle-btn" className={`px-4 py-2.5 rounded-lg text-sm font-bold ${s?.emergency_stop ? 'bg-white border border-rose-300 text-rose-700' : 'bg-rose-700 text-white hover:bg-rose-800'}`}>
                            {s?.emergency_stop ? 'Release emergency stop' : 'Activate emergency stop'}
                        </button>
                    </div>
                </Card>
                <Card>
                    <SectionTitle icon={GearSix}>Limits & defaults</SectionTitle>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {FIELDS.map(([k, label, type]) => (
                            <label key={k} className="block">
                                <span className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</span>
                                <input type={type} value={f[k] ?? ''} onChange={e => setF(p => ({ ...p, [k]: e.target.value }))} data-testid={`setting-${k}`} className={inputCls} />
                            </label>
                        ))}
                    </div>
                    <div className="flex justify-end mt-4"><button onClick={save} data-testid="settings-save-btn" className="px-5 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold">Save settings</button></div>
                </Card>
                <BolnaConfigPanel />
                <Card>
                    <SectionTitle icon={Key}>Calling switches</SectionTitle>
                    <p className="text-xs text-[#6b7280]">Integration approval: <b>{s?.bolna_integration_approved ? 'approved' : 'not approved'}</b> · Server calling: <b>{s?.server_calling_enabled ? 'enabled' : 'disabled'}</b></p>
                </Card>
            </main>
        </div>
    );
}
