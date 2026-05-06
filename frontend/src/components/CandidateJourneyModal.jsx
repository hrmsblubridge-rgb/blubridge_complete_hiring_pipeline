import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, CheckCircle, Clock, XCircle, User, EnvelopeSimple, Phone, Buildings, Briefcase } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * Iter52 — Candidate Journey (A–Z) modal.
 * Read-only view of the full hiring lifecycle for a single candidate:
 *   1. Basic info
 *   2. Round timeline (canonical name + UI label like "F2F", status, score, date)
 *   3. Final Outcome (Selected / Rejected / In Progress + Date of Induction)
 *
 * The Date of Induction is the only editable field, surfaces only when status
 * is "Selected". All other fields are sourced from pipeline_data /
 * bb_applicant_updates / score_sheet — no writes here.
 */
export default function CandidateJourneyModal({ candidate, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [editingDate, setEditingDate] = useState(false);
    const [doiInput, setDoiInput] = useState('');

    useEffect(() => {
        if (!candidate) return;
        let alive = true;
        const fetchJourney = async () => {
            setLoading(true);
            setError('');
            try {
                const params = new URLSearchParams();
                if (candidate.email) params.append('email', candidate.email);
                if (candidate.phone) params.append('phone', candidate.phone);
                const res = await axios.get(`${API}/api/bb/candidate-journey?${params}`, { withCredentials: true });
                if (!alive) return;
                setData(res.data);
                setDoiInput(res.data?.final_outcome?.date_of_induction === 'Pending' || res.data?.final_outcome?.date_of_induction === 'Not Applicable' ? '' : (res.data?.final_outcome?.date_of_induction || ''));
            } catch (err) {
                if (!alive) return;
                const detail = err?.response?.data?.detail || err?.message || 'Failed to load candidate';
                setError(typeof detail === 'string' ? detail : 'Failed to load candidate');
            } finally {
                if (alive) setLoading(false);
            }
        };
        fetchJourney();
        return () => { alive = false; };
    }, [candidate]);

    const saveInductionDate = async () => {
        try {
            await axios.put(`${API}/api/bb/candidate-induction-date`, {
                email: data.basic.email,
                date_of_induction: doiInput,
            }, { withCredentials: true });
            toast.success('Date of induction saved');
            setData(prev => ({ ...prev, final_outcome: { ...prev.final_outcome, date_of_induction: doiInput || 'Pending' } }));
            setEditingDate(false);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Save failed');
        }
    };

    if (!candidate) return null;

    const StatusPill = ({ status }) => {
        const variant = {
            Completed: 'bg-emerald-900/40 text-emerald-400 border-emerald-800/50',
            Pending: 'bg-zinc-800/60 text-zinc-400 border-zinc-700/50',
            Rejected: 'bg-red-900/40 text-red-400 border-red-800/50',
            Selected: 'bg-emerald-900/40 text-emerald-400 border-emerald-800/50',
            'In Progress': 'bg-cyan-900/40 text-cyan-400 border-cyan-800/50',
        }[status] || 'bg-zinc-800/60 text-zinc-400 border-zinc-700/50';
        const Icon = status === 'Completed' || status === 'Selected' ? CheckCircle :
                     status === 'Rejected' ? XCircle : Clock;
        return (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded border ${variant}`}>
                <Icon size={12} weight="fill" /> {status}
            </span>
        );
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" data-testid="journey-modal" onClick={onClose}>
            <div className="bg-zinc-950 border border-zinc-800 max-w-3xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between sticky top-0 bg-zinc-950 z-10">
                    <h2 className="text-lg font-semibold tracking-tight">Candidate Journey</h2>
                    <button onClick={onClose} data-testid="journey-close-btn" className="p-1.5 hover:bg-zinc-800 text-zinc-400 hover:text-white"><X size={20} /></button>
                </div>

                {loading && <div className="px-6 py-12 text-center text-zinc-500" data-testid="journey-loading">Loading…</div>}
                {error && <div className="px-6 py-12 text-center text-red-400" data-testid="journey-error">{error}</div>}

                {data && !loading && !error && (
                    <div className="p-6 space-y-6">
                        {/* Section 1 — Basic Info */}
                        <section data-testid="journey-basic">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">Candidate Info</h3>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                                <Detail icon={User} label="Name" value={data.basic.name} />
                                <Detail icon={EnvelopeSimple} label="Email" value={data.basic.email} />
                                <Detail icon={Phone} label="Phone" value={data.basic.phone} />
                                <Detail icon={Buildings} label="College" value={data.basic.college} />
                                <Detail icon={Briefcase} label="Job Role" value={data.basic.job_role} />
                            </div>
                        </section>

                        {/* Section 2 — Round Timeline */}
                        <section data-testid="journey-rounds">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">Round Progress</h3>
                            {data.round_details.length === 0 ? (
                                <div className="text-sm text-zinc-500 italic px-3 py-4 border border-zinc-800 border-dashed">
                                    No rounds completed yet.
                                </div>
                            ) : (
                                <ol className="relative border-l border-zinc-800 ml-2 space-y-4">
                                    {data.round_details.map((r, i) => (
                                        <li key={r.round_name + i} className="ml-4" data-testid={`round-${i}`}>
                                            <div className="absolute -left-1.5 mt-1.5 w-3 h-3 rounded-full bg-cyan-500 border-2 border-zinc-950" />
                                            <div className="flex items-center justify-between gap-3 flex-wrap">
                                                <div>
                                                    <div className="text-sm font-medium">
                                                        {r.round_label}
                                                        {r.round_label !== r.round_name && (
                                                            <span className="text-xs text-zinc-500 ml-2">({r.round_name})</span>
                                                        )}
                                                    </div>
                                                    {r.completed_date && (
                                                        <div className="text-xs text-zinc-500 mt-0.5">{String(r.completed_date).split('T')[0]}</div>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    {r.score !== null && r.score !== undefined && (
                                                        <span className="text-cyan-400 font-medium tabular-nums text-sm">{r.score}</span>
                                                    )}
                                                    <StatusPill status={r.status} />
                                                </div>
                                            </div>
                                        </li>
                                    ))}
                                </ol>
                            )}
                            {(data.latest_round || data.total_score > 0) && (
                                <div className="mt-3 flex items-center gap-4 text-xs text-zinc-500">
                                    {data.latest_round && <span>Latest: <span className="text-zinc-300 font-medium">{data.latest_round}</span> ({data.latest_score})</span>}
                                    <span>Total Score: <span className="text-zinc-300 font-medium tabular-nums">{data.total_score}</span></span>
                                </div>
                            )}
                        </section>

                        {/* Section 3 — Final Outcome */}
                        <section data-testid="journey-outcome">
                            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">Final Outcome</h3>
                            <div className="border border-zinc-800 px-4 py-3 bg-zinc-900/50 space-y-2.5">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-zinc-400">Status</span>
                                    <StatusPill status={data.final_outcome.status} />
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-zinc-400">Date of Induction</span>
                                    {!editingDate ? (
                                        <div className="flex items-center gap-2">
                                            <span className={`text-sm ${data.final_outcome.date_of_induction === 'Pending' ? 'text-orange-400' : data.final_outcome.date_of_induction === 'Not Applicable' ? 'text-zinc-500' : 'text-zinc-300 font-medium'}`} data-testid="journey-doi">
                                                {data.final_outcome.date_of_induction || 'Pending'}
                                            </span>
                                            {data.final_outcome.status === 'Selected' && (
                                                <button onClick={() => setEditingDate(true)} data-testid="journey-edit-doi" className="text-xs text-cyan-400 hover:text-cyan-300">Edit</button>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="date"
                                                value={doiInput}
                                                onChange={e => setDoiInput(e.target.value)}
                                                data-testid="journey-doi-input"
                                                className="bg-zinc-900 border border-zinc-700 px-2 py-1 text-sm focus:outline-none focus:border-cyan-600"
                                            />
                                            <button onClick={saveInductionDate} data-testid="journey-doi-save" className="text-xs px-2 py-1 bg-emerald-900/40 border border-emerald-800/50 text-emerald-400 hover:bg-emerald-900/60">Save</button>
                                            <button onClick={() => setEditingDate(false)} data-testid="journey-doi-cancel" className="text-xs px-2 py-1 text-zinc-400 hover:text-white">Cancel</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </section>
                    </div>
                )}
            </div>
        </div>
    );
}

function Detail({ icon: Icon, label, value }) {
    return (
        <div className="flex items-start gap-2.5">
            <Icon size={16} className="text-zinc-500 mt-0.5 flex-shrink-0" />
            <div className="min-w-0 flex-1">
                <div className="text-xs text-zinc-500 uppercase tracking-wider">{label}</div>
                <div className="text-sm text-zinc-200 break-words">{value || '—'}</div>
            </div>
        </div>
    );
}
