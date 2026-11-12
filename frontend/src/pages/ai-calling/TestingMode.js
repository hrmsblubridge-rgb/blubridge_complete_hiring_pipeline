import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader } from '../../components/ai-calling/AICallingHeader';
import { SampleSheetUpload } from '../../components/ai-calling/SampleSheetUpload';
import { ManualCandidateForm } from '../../components/ai-calling/ManualCandidateForm';
import { CandidateList } from '../../components/ai-calling/CandidateList';
import { CallingControls } from '../../components/ai-calling/CallingControls';
import { BatchPanel } from '../../components/ai-calling/BatchPanel';
import { CallNowDialog } from '../../components/ai-calling/CallNowDialog';

const Q0 = { search: '', consent: 'all', source: '', language: '', ready: '', page: 1 };

export default function TestingMode() {
    const [settings, setSettings] = useState(null);
    const [data, setData] = useState({ items: [] });
    const [batches, setBatches] = useState([]);
    const [selected, setSelected] = useState({});
    const [q, setQ] = useState(Q0);
    const [callStatus, setCallStatus] = useState(null);
    const [calling, setCalling] = useState(null);

    const load = useCallback(async () => {
        try {
            const params = new URLSearchParams({ ...q, page_size: 20 }).toString();
            const [s, c, b, cs] = await Promise.all([aiApi.get('/settings'), aiApi.get(`/test-candidates?${params}`), aiApi.get('/test-batches'), aiApi.get('/test-calls/status')]);
            setSettings(s.data); setData(c.data); setBatches(b.data.items); setCallStatus(cs.data);
            if (c.data.page > c.data.pages) setQ(p => ({ ...p, page: c.data.pages }));
            const fresh = Object.fromEntries(c.data.items.map(x => [x.id, x]));
            setSelected(sel => Object.fromEntries(Object.entries(sel).map(([k, v]) => [k, fresh[k] || v])));
        } catch (e) { toast.error(errMsg(e, 'Failed to load')); }
    }, [q]);
    useEffect(() => {
        const t = setTimeout(load, 250);
        return () => clearTimeout(t);
    }, [load]);

    const activate = async () => {
        try { await aiApi.post('/mode', { mode: settings?.mode === 'testing' ? 'off' : 'testing' }); load(); }
        catch (e) { toast.error(errMsg(e)); }
    };

    return (
        <div className="min-h-screen" data-testid="ai-testing-page">
            <AICallingHeader title="Testing Mode" subtitle="Consented test recipients only — never reads real candidate records" mode={settings?.mode} emergencyStop={settings?.emergency_stop} />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex flex-wrap items-center gap-3 bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4">
                    <p className="flex-1 text-sm text-[#1a2332]">AI Test Mode is <b data-testid="testing-mode-state">{settings?.ai_test_enabled ? 'ON' : 'OFF'}</b>. Turning it on never places calls. The AI Live switch is on the Settings page.</p>
                    <button onClick={activate} data-testid="toggle-testing-mode-btn" className="px-4 py-2 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold hover:bg-teal-100">
                        {settings?.ai_test_enabled ? 'Turn AI Test Mode off' : 'Turn AI Test Mode on'}
                    </button>
                </div>
                <SampleSheetUpload onImported={load} />
                <ManualCandidateForm settings={settings} onSaved={load} />
                <CallingControls selected={Object.values(selected)} status={callStatus} onCall={setCalling} />
                <CandidateList data={data} q={q} setQ={setQ} selected={selected} setSelected={setSelected} reload={load} callStatus={callStatus} />
                <BatchPanel selected={Object.keys(selected)} clearSelected={() => setSelected({})} batches={batches} reload={load} startEnabled={!!settings?.bolna_integration_approved} />
                {calling && <CallNowDialog key={calling.id} candidate={calling} onClose={() => setCalling(null)} onDone={() => { setCalling(null); load(); }} />}
            </main>
        </div>
    );
}
