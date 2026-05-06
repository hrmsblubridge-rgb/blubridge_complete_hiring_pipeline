import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, MagnifyingGlass } from '@phosphor-icons/react';
import CandidateJourneyModal from '../components/CandidateJourneyModal';

export default function CandidateJourney() {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [candidate, setCandidate] = useState(null);

    const open = () => {
        const q = (query || '').trim();
        if (!q) { toast.warning('Enter an email or phone'); return; }
        const isEmail = q.includes('@');
        setCandidate(isEmail ? { email: q.toLowerCase() } : { phone: q.replace(/\D/g, '').slice(-10) });
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="candidate-journey-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Candidate Journey</h1>
            </header>
            <main className="max-w-3xl mx-auto px-6 py-12 space-y-6">
                <section className="space-y-4" data-testid="journey-search-section">
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Score and Round</h2>
                    <div className="bg-zinc-900 border border-zinc-800 hover:border-cyan-600 transition-all p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <MagnifyingGlass size={24} className="text-cyan-500" />
                            <div>
                                <div className="text-base font-medium">Look up a candidate</div>
                                <div className="text-sm text-zinc-500 mt-0.5">Full lifecycle — rounds, scores, status, induction date</div>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={query}
                                onChange={e => setQuery(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && open()}
                                placeholder="Email or phone…"
                                data-testid="journey-search-input"
                                className="flex-1 bg-zinc-950 border border-zinc-800 px-4 py-2.5 text-sm focus:outline-none focus:border-cyan-600 placeholder-zinc-600"
                            />
                            <button
                                onClick={open}
                                data-testid="journey-search-btn"
                                className="px-5 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium transition-colors flex items-center gap-2"
                            >
                                <MagnifyingGlass size={16} /> View Journey
                            </button>
                        </div>
                    </div>
                </section>
            </main>
            {candidate && (
                <CandidateJourneyModal candidate={candidate} onClose={() => setCandidate(null)} />
            )}
        </div>
    );
}
