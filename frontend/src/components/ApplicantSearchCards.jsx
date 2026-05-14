/**
 * Shared multi-result applicant search component (iter95).
 * ---------------------------------------------------------
 * Used on Manual Applicant Alerts, Manual OTP Verify, and Candidate Journey.
 *
 * Behavior:
 *   - 300ms debounced fetch against /api/bb/manual/applicant/search
 *   - Renders summary cards (Name, Phone, Email, Job Role, Registered Status)
 *   - Clicking a card → onSelect({name,email,phone,job_role,registered_status})
 *   - Inline; the host page swaps this list for a "back to results" detail view
 *
 * Props:
 *   value        — current search text (controlled by parent)
 *   onChange     — (v: string) => void
 *   onSelect     — (applicant: {...}) => void
 *   placeholder  — input placeholder
 *   testIdPrefix — prefix for data-testid on input + cards (e.g. "manual-alerts")
 *   onCancel     — optional Cancel callback (clears state)
 *   autoFocus    — focus the input on mount (default true)
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { MagnifyingGlass, X, User, EnvelopeSimple, Phone, Briefcase, Spinner } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function ApplicantSearchCards({
    value,
    onChange,
    onSelect,
    placeholder = 'Type name, email, or phone (min 2 chars)…',
    testIdPrefix = 'applicant-search',
    onCancel,
    autoFocus = true,
}) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [truncated, setTruncated] = useState(false);
    const [hasFetched, setHasFetched] = useState(false);
    const timer = useRef(null);
    const inFlight = useRef(0);

    useEffect(() => {
        const q = (value || '').trim();
        if (timer.current) clearTimeout(timer.current);
        if (q.length < 2) {
            setItems([]);
            setLoading(false);
            setHasFetched(false);
            setTruncated(false);
            return;
        }
        setLoading(true);
        timer.current = setTimeout(async () => {
            const ticket = ++inFlight.current;
            try {
                const r = await axios.get(`${API}/api/bb/manual/applicant/search`, {
                    withCredentials: true,
                    params: { q, limit: 25 },
                });
                // Drop stale responses (a newer keystroke fired another fetch).
                if (ticket !== inFlight.current) return;
                setItems(r.data?.items || []);
                setTruncated(!!r.data?.truncated);
                setHasFetched(true);
            } catch {
                if (ticket !== inFlight.current) return;
                setItems([]);
                setTruncated(false);
                setHasFetched(true);
            } finally {
                if (ticket === inFlight.current) setLoading(false);
            }
        }, 300);
        return () => { if (timer.current) clearTimeout(timer.current); };
    }, [value]);

    return (
        <div className="space-y-3" data-testid={`${testIdPrefix}-search-wrap`}>
            {/* Search bar */}
            <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[260px]">
                    <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Search</label>
                    <div className="relative">
                        <input
                            value={value || ''}
                            onChange={(e) => onChange(e.target.value)}
                            placeholder={placeholder}
                            data-testid={`${testIdPrefix}-input`}
                            autoFocus={autoFocus}
                            className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg pl-9 pr-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]"
                        />
                        <MagnifyingGlass size={16} className="absolute left-3 top-2.5 text-[#9b9787]" />
                        {loading && (
                            <Spinner size={16} className="absolute right-3 top-2.5 text-[#1d3a8a] animate-spin" data-testid={`${testIdPrefix}-loading`} />
                        )}
                    </div>
                    <p className="text-[11px] text-[#9b9787] mt-1 italic">
                        Partial match — type any part of name, email, or phone. Min 2 characters.
                    </p>
                </div>
                {onCancel && (
                    <button onClick={onCancel} data-testid={`${testIdPrefix}-cancel-btn`}
                        className="px-4 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                        <X size={16} /> Clear
                    </button>
                )}
            </div>

            {/* Result cards */}
            {hasFetched && items.length === 0 && !loading && (
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6 text-center text-sm text-[#6b7280]" data-testid={`${testIdPrefix}-empty`}>
                    No applicants match "<strong className="text-[#1a2332]">{value}</strong>".
                </div>
            )}

            {items.length > 0 && (
                <div className="space-y-2" data-testid={`${testIdPrefix}-results`}>
                    <div className="flex items-center justify-between px-1">
                        <p className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase">
                            {items.length} match{items.length === 1 ? '' : 'es'}
                        </p>
                        {truncated && (
                            <p className="text-[11px] text-amber-700 italic">Showing first 25 — refine your search</p>
                        )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {items.map((it, i) => (
                            <button
                                key={`${it.email || ''}|${it.phone || ''}|${i}`}
                                onClick={() => onSelect(it)}
                                data-testid={`${testIdPrefix}-card-${i}`}
                                className="text-left bg-[#fffdf7] border border-[#e5e3d8] hover:border-[#1d3a8a] hover:shadow-sm rounded-xl p-3 transition-colors"
                            >
                                <div className="flex items-start justify-between gap-2 mb-1.5">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <User size={16} weight="duotone" className="text-[#1d3a8a] shrink-0" />
                                        <span className="text-sm font-semibold text-[#1a2332] truncate">{it.name || '—'}</span>
                                    </div>
                                    {it.registered_status && (
                                        <span className="text-[10px] font-semibold uppercase tracking-wider text-[#6b7280] bg-[#efede5] px-2 py-0.5 rounded shrink-0">
                                            {it.registered_status}
                                        </span>
                                    )}
                                </div>
                                <div className="text-xs text-[#4b5563] space-y-1 pl-6">
                                    <div className="flex items-center gap-1.5"><EnvelopeSimple size={12} className="text-[#9b9787]" /> <span className="truncate">{it.email || '—'}</span></div>
                                    <div className="flex items-center gap-1.5"><Phone size={12} className="text-[#9b9787]" /> {it.phone || '—'}</div>
                                    {it.job_role && (
                                        <div className="flex items-center gap-1.5"><Briefcase size={12} className="text-[#9b9787]" /> <span className="truncate">{it.job_role}</span></div>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
