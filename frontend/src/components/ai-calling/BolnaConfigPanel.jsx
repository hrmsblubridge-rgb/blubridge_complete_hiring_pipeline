import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Key, PlugsConnected, Trash, Warning } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { inputCls } from './constants';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';

const STATUS = {
    not_configured: ['Not configured', 'bg-zinc-100 text-zinc-700'],
    incomplete: ['Incomplete', 'bg-amber-100 text-amber-800'],
    configured_unverified: ['Saved — not verified', 'bg-sky-50 text-sky-800'],
    verification_failed: ['Verification failed', 'bg-rose-100 text-rose-800'],
    verified: ['Verified', 'bg-emerald-100 text-emerald-800'],
    key_unreadable: ['Stored key unreadable — re-enter API key', 'bg-rose-100 text-rose-800'],
};

const L = ({ label, hint, children }) => (
    <label className="block">
        <span className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</span>
        {children}
        {hint && <span className="text-[11px] text-[#9b9787] mt-1 block">{hint}</span>}
    </label>
);

export const BolnaConfigPanel = () => {
    const [p, setP] = useState(null);
    const [apiKey, setApiKey] = useState('');
    const [agentId, setAgentId] = useState('');
    const [caller, setCaller] = useState('');
    const [busy, setBusy] = useState(false);
    const [clearOpen, setClearOpen] = useState(false);
    const [word, setWord] = useState('');

    const load = useCallback(async () => {
        try { const d = (await aiApi.get('/provider')).data; setP(d); setAgentId(d.agent_id || ''); }
        catch (e) { toast.error(errMsg(e, 'Failed to load Bolna configuration')); }
    }, []);
    useEffect(() => { load(); }, [load]);

    const save = async () => {
        const wantKey = apiKey.trim().length > 0;
        const wantSettings = (agentId.trim() && agentId.trim() !== p?.agent_id) || caller.trim();
        if (!wantKey && !wantSettings) { toast.error('Nothing to save'); return; }
        setBusy(true);
        let keySaved = false;
        try {
            if (wantSettings) {
                const body = {};
                if (agentId.trim() !== p?.agent_id) body.agent_id = agentId.trim();
                if (caller.trim()) body.caller_number = caller.trim();
                await aiApi.put('/provider/settings', body);
                setCaller('');
            }
            if (wantKey) { await aiApi.put('/provider/credentials', { api_key: apiKey.trim() }); keySaved = true; setApiKey(''); }
            toast.success('Bolna configuration saved. Pending call jobs (if any) were paused until validation.');
            load();
        } catch (e) { toast.error(errMsg(e, 'Save failed') + (keySaved ? '' : wantKey ? ' — API key was not saved.' : '')); setApiKey(''); load(); } finally { setBusy(false); }
    };
    const [hookUrl, setHookUrl] = useState('');
    const testConn = async () => {
        setBusy(true);
        try { const r = (await aiApi.post('/provider/test-connection')).data; toast[r.status === 'verified' ? 'success' : 'error'](r.status === 'verified' ? 'Connection verified (read-only checks)' : 'Verification failed — see checks'); load(); }
        catch (e) { toast.error(errMsg(e, 'Test failed')); } finally { setBusy(false); }
    };
    const genHook = async () => {
        if (p?.webhook_configured && !window.confirm('Rotate the webhook URL? The old URL stops working.')) return;
        try { setHookUrl((await aiApi.post('/provider/webhook-token')).data.webhook_url); load(); } catch (e) { toast.error(errMsg(e)); }
    };
    const clear = async () => {
        try { await aiApi.post('/provider/clear', { confirmation: word }); toast.success('Bolna configuration cleared'); setClearOpen(false); setWord(''); load(); }
        catch (e) { toast.error(errMsg(e)); }
    };

    const [sl, sc] = STATUS[p?.status] || STATUS.not_configured;
    const encReady = p?.encryption?.ready;
    return (
        <Card data-testid="bolna-config-panel">
            <SectionTitle icon={Key}>Bolna AI Configuration</SectionTitle>
            <div className="flex flex-wrap items-center gap-2 mb-4">
                <span className="text-xs text-[#6b7280]">Connection status:</span>
                <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold ${sc}`} data-testid="bolna-status">{sl}</span>
                {p?.updated_at && <span className="text-[11px] text-[#9b9787]" data-testid="bolna-updated">v{p.config_version} · {p.updated_by} · {new Date(p.updated_at).toLocaleString()}</span>}
            </div>
            {p && !encReady && (
                <div className="flex items-start gap-2 bg-rose-50 border border-rose-200 rounded-xl px-3 py-2 mb-4 text-sm text-rose-900" data-testid="bolna-encryption-blocker">
                    <Warning size={18} weight="duotone" className="shrink-0 mt-0.5" /> API key cannot be saved: {p.encryption.reason}.
                </div>
            )}
            <div className="grid sm:grid-cols-3 gap-3">
                <L label="Bolna API key" hint={p?.has_api_key ? `Stored: ${p.api_key_masked} — type a new key to replace` : 'Write-only. Never shown after saving.'}>
                    <input type="password" autoComplete="new-password" value={apiKey} onChange={e => setApiKey(e.target.value)} disabled={!encReady}
                        placeholder={p?.has_api_key ? 'Replace stored key' : 'Enter API key'} data-testid="bolna-api-key-input" className={inputCls} />
                </L>
                <L label="Agent ID" hint={p?.agent_id ? `Current: ${p.agent_id_masked}` : ''}>
                    <input value={agentId} onChange={e => setAgentId(e.target.value)} placeholder="Bolna agent ID" data-testid="bolna-agent-id-input" className={inputCls} />
                </L>
                <L label="Calling phone number" hint={p?.caller_number_masked ? `Current: ${p.caller_number_masked}` : 'International format, e.g. +918012345678'}>
                    <input value={caller} onChange={e => setCaller(e.target.value)} placeholder={p?.caller_number_masked ? 'Enter to replace' : '+91XXXXXXXXXX'} data-testid="bolna-caller-input" className={inputCls} />
                </L>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
                <button onClick={save} disabled={busy} data-testid="bolna-save-btn" className="px-5 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Save Configuration</button>
                <button onClick={testConn} disabled={busy || !p?.has_api_key} data-testid="bolna-test-connection-btn" className="px-4 py-2.5 rounded-lg border border-teal-300 bg-teal-50 text-teal-800 text-sm font-semibold flex items-center gap-2 disabled:opacity-40"><PlugsConnected size={16} /> {busy ? 'Testing…' : 'Test Connection'}</button>
                <button onClick={genHook} disabled={busy} data-testid="bolna-webhook-btn" className="px-4 py-2.5 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">{p?.webhook_configured ? 'Rotate webhook URL' : 'Generate webhook URL'}</button>
                <button onClick={() => setClearOpen(true)} disabled={!p || p.status === 'not_configured'} data-testid="bolna-clear-btn" className="px-4 py-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold flex items-center gap-2 disabled:opacity-40"><Trash size={16} /> Clear Configuration</button>
            </div>
            <p className="text-[11px] text-[#9b9787] mt-3">The API key is sent only to the backend, encrypted before storage and never displayed. Any change pauses future call jobs until the configuration is validated.</p>
            {hookUrl && (
                <div className="mt-3 bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs" data-testid="bolna-webhook-url">
                    <p className="font-semibold text-amber-900 mb-1">Webhook URL (shown once — paste into the Bolna agent's webhook setting):</p>
                    <code className="break-all">{hookUrl}</code>
                </div>
            )}
            {p?.last_verification && (
                <div className="mt-4 border border-[#e5e3d8] rounded-xl p-3" data-testid="bolna-verification">
                    <p className="text-xs font-semibold text-[#1a2332] mb-2">Last test: {new Date(p.last_verification.tested_at).toLocaleString()} by {p.last_verification.tested_by}</p>
                    <ul className="space-y-1">
                        {p.last_verification.checks.map(c => (
                            <li key={c.key} className="text-xs flex gap-2" data-testid={`bolna-check-${c.key}`}>
                                <span className={`font-bold uppercase w-24 shrink-0 ${c.state === 'verified' ? 'text-emerald-700' : c.state === 'failed' ? 'text-rose-700' : 'text-amber-700'}`}>{c.state.replace('_', ' ')}</span>
                                <span>{c.label}{c.detail ? <span className="text-[#9b9787]"> — {c.detail}</span> : null}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            <Dialog open={clearOpen} onOpenChange={(o) => { setClearOpen(o); if (!o) setWord(''); }}>
                <DialogContent className="bg-[#fffdf7]" data-testid="bolna-clear-dialog">
                    <DialogHeader><DialogTitle>Clear Bolna configuration?</DialogTitle><DialogDescription>Removes the stored API key, Agent ID and calling number.</DialogDescription></DialogHeader>
                    <label className="block text-sm">Type <b>CLEAR</b> to confirm
                        <input value={word} onChange={e => setWord(e.target.value.toUpperCase())} data-testid="bolna-clear-input" className="mt-1 w-40 bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                    </label>
                    <DialogFooter>
                        <button onClick={() => setClearOpen(false)} data-testid="bolna-clear-cancel" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={clear} disabled={word !== 'CLEAR'} data-testid="bolna-clear-confirm" className="px-4 py-2 rounded-lg bg-rose-700 text-white text-sm font-semibold disabled:opacity-50">Clear</button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
};
