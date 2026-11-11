import { useState } from 'react';
import { CaretRight, ShieldCheck } from '@phosphor-icons/react';
import { aiApi } from '../../pages/ai-calling/aiApi';
import { ConsentCard } from './ConsentCard';

// Admin-only AI Calling consent & Do Not Call, per exact registration ID. Never places calls.
export const ProfileConsentPanel = ({ email }) => {
    const [open, setOpen] = useState(false);
    const [state, setState] = useState({ loading: false, error: '', items: null });
    const load = async () => {
        setState({ loading: true, error: '', items: null });
        try {
            const ids = (await aiApi.get('/registrations/lookup', { params: { email } })).data.registration_ids;
            const items = await Promise.all(ids.map(id => aiApi.get(`/consent/admin/${id}`).then(r => r.data)));
            setState({ loading: false, error: '', items });
        } catch { setState({ loading: false, error: 'AI calling consent is unavailable right now.', items: null }); }
    };
    const toggle = () => { const next = !open; setOpen(next); if (next && !state.items && !state.loading) load(); };
    const update = (c) => setState(s => ({ ...s, items: s.items.map(x => (x.registration_id === c.registration_id ? c : x)) }));

    return (
        <section data-testid="journey-ai-consent">
            <button onClick={toggle} aria-expanded={open} data-testid="journey-ai-consent-toggle"
                className="w-full flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 hover:text-zinc-300 mb-3">
                <CaretRight size={12} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
                <ShieldCheck size={14} /> AI Calling Consent &amp; Do Not Call
            </button>
            {open && (
                <div className="space-y-2" data-testid="journey-ai-consent-body">
                    {state.loading && <p className="text-sm text-zinc-500 px-3 py-4">Loading…</p>}
                    {state.error && <p className="text-sm text-red-400 px-3 py-4" data-testid="journey-ai-consent-error">{state.error}</p>}
                    {state.items?.length === 0 && <p className="text-sm text-zinc-500 italic px-3 py-4 border border-dashed border-zinc-800" data-testid="journey-ai-consent-empty">No interview registration found for this candidate.</p>}
                    {state.items?.map(c => <ConsentCard key={c.registration_id} c={c} onChange={update} />)}
                </div>
            )}
        </section>
    );
};
