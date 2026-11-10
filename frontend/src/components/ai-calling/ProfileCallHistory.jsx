import { useState } from 'react';
import axios from 'axios';
import { CaretRight, PhoneCall } from '@phosphor-icons/react';
import { ProfileCallItem } from './ProfileCallItem';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/ai-calling`;

// Read-only: Live Mode calls matched ONLY by this candidate's own registration IDs. Never places calls.
export const ProfileCallHistory = ({ email }) => {
    const [open, setOpen] = useState(false);
    const [state, setState] = useState({ loading: false, error: '', items: null });

    const load = async () => {
        setState({ loading: true, error: '', items: null });
        try {
            const ids = (await axios.get(`${API}/registrations/lookup`, { params: { email }, withCredentials: true })).data.registration_ids;
            const pages = await Promise.all(ids.map(id => axios.get(`${API}/calls/by-registration/${id}`, { withCredentials: true })));
            const items = pages.flatMap(p => p.data.items).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
            setState({ loading: false, error: '', items });
        } catch (e) {
            setState({ loading: false, error: 'AI Calling History is unavailable right now.', items: null });
        }
    };
    const toggle = () => { const next = !open; setOpen(next); if (next && !state.items && !state.loading) load(); };

    return (
        <section data-testid="journey-ai-calls">
            <button onClick={toggle} data-testid="journey-ai-calls-toggle" aria-expanded={open}
                className="w-full flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500 hover:text-zinc-300 mb-3">
                <CaretRight size={12} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
                <PhoneCall size={14} /> AI Calling History
            </button>
            {open && (
                <div data-testid="journey-ai-calls-body">
                    {state.loading && <div className="text-sm text-zinc-500 px-3 py-4" data-testid="journey-ai-calls-loading">Loading AI calls…</div>}
                    {state.error && (
                        <div className="text-sm text-red-400 px-3 py-4 border border-red-900/50 flex items-center justify-between" data-testid="journey-ai-calls-error">
                            {state.error}<button onClick={load} className="text-xs text-cyan-400 hover:text-cyan-300" data-testid="journey-ai-calls-retry">Retry</button>
                        </div>
                    )}
                    {state.items && state.items.length === 0 && (
                        <div className="text-sm text-zinc-500 italic px-3 py-4 border border-zinc-800 border-dashed" data-testid="journey-ai-calls-empty">No AI calls recorded.</div>
                    )}
                    {state.items?.length > 0 && <ul className="space-y-2" data-testid="journey-ai-calls-list">{state.items.map(c => <ProfileCallItem key={c.id} call={c} />)}</ul>}
                </div>
            )}
        </section>
    );
};
