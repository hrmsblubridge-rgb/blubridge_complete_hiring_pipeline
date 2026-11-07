import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader } from '../../components/ai-calling/AICallingHeader';
import { UploadPanel } from '../../components/ai-calling/UploadPanel';
import { ManualEntryForm } from '../../components/ai-calling/ManualEntryForm';
import { TestCandidateTable } from '../../components/ai-calling/TestCandidateTable';
import { BatchPanel } from '../../components/ai-calling/BatchPanel';

export default function TestingMode() {
    const [settings, setSettings] = useState(null);
    const [items, setItems] = useState([]);
    const [batches, setBatches] = useState([]);
    const [selected, setSelected] = useState([]);

    const load = useCallback(async () => {
        try {
            const [s, c, b] = await Promise.all([aiApi.get('/settings'), aiApi.get('/test-candidates'), aiApi.get('/test-batches')]);
            setSettings(s.data); setItems(c.data.items); setBatches(b.data.items);
            const ok = new Set(c.data.items.filter(x => x.approved && !x.opted_out).map(x => x.id));
            setSelected(sel => sel.filter(id => ok.has(id)));
        } catch (e) { toast.error(errMsg(e, 'Failed to load')); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const activate = async () => {
        try { await aiApi.post('/mode', { mode: settings?.mode === 'testing' ? 'off' : 'testing' }); load(); }
        catch (e) { toast.error(errMsg(e)); }
    };

    return (
        <div className="min-h-screen" data-testid="ai-testing-page">
            <AICallingHeader title="Testing Mode" subtitle="Approved test recipients only — never reads real candidate records" mode={settings?.mode} emergencyStop={settings?.emergency_stop} />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex flex-wrap items-center gap-3 bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4">
                    <p className="flex-1 text-sm text-[#1a2332]">Testing Mode is <b data-testid="testing-mode-state">{settings?.mode === 'testing' ? 'ACTIVE' : 'inactive'}</b>. Activating it does not place calls.</p>
                    <button onClick={activate} data-testid="toggle-testing-mode-btn" className="px-4 py-2 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold hover:bg-teal-100">
                        {settings?.mode === 'testing' ? 'Turn Testing Mode off' : 'Activate Testing Mode'}
                    </button>
                </div>
                <UploadPanel onImported={load} />
                <ManualEntryForm onSaved={load} />
                <TestCandidateTable items={items} selected={selected} setSelected={setSelected} reload={load} />
                <BatchPanel selected={selected} clearSelected={() => setSelected([])} batches={batches} reload={load} startEnabled={!!settings?.bolna_integration_approved} />
            </main>
        </div>
    );
}
