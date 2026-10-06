import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from '@phosphor-icons/react';
import CandidateJourneyModal from '../components/CandidateJourneyModal';
import ApplicantSearchCards from '../components/ApplicantSearchCards';

export default function CandidateJourney() {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [candidate, setCandidate] = useState(null);

    const handleSelect = (card) => {
        // iter95 — Card click opens the modal with the exact email+phone
        // bound to that applicant. The modal still drives the detailed
        // /api/bb/candidate-journey read.
        const payload = {};
        if (card.email) payload.email = String(card.email).toLowerCase();
        if (card.phone) payload.phone = String(card.phone).replace(/\D/g, '').slice(-10);
        setCandidate(payload);
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
                    <ApplicantSearchCards
                        value={query}
                        onChange={setQuery}
                        onSelect={handleSelect}
                        onCancel={() => setQuery('')}
                        testIdPrefix="journey-search"
                        placeholder="Type name, email, or phone (min 2 chars)…"
                    />
                </section>
            </main>
            {candidate && (
                <CandidateJourneyModal candidate={candidate} onClose={() => setCandidate(null)} />
            )}
        </div>
    );
}
