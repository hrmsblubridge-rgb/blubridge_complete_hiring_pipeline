/**
 * iter96 — Public View-Only Job Opening page.
 * --------------------------------------------
 * Route: /jobs/view/:openingId  (no auth required)
 * Renders ONLY the job description block. Intentionally:
 *   - NO Apply button
 *   - NO registration form
 *   - NO admin / edit / delete controls
 *
 * Pulls from public endpoint GET /api/pub/job-opening/:id which returns
 * only public-safe fields (no `_id`, no `created_at`, no internal metadata).
 *
 * Matches the existing JD-step styling inside PublicRegistration.js so the
 * branding is consistent for any recruiter sharing the link externally.
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PublicJobView() {
    const { openingId } = useParams();
    const [jo, setJo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let alive = true;
        (async () => {
            try {
                const r = await axios.get(`${API}/api/pub/job-opening/${openingId}`);
                if (!alive) return;
                setJo(r.data);
            } catch (e) {
                if (!alive) return;
                if (e.response?.status === 404) setError('Job opening not found');
                else setError('Unable to load job opening. Please try again later.');
            } finally {
                if (alive) setLoading(false);
            }
        })();
        return () => { alive = false; };
    }, [openingId]);

    return (
        <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid="public-job-view-page">
            <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                <img src="/blubridge-logo.webp" alt="Blubridge" />
            </header>
            <div className="flex-1 flex items-start justify-center px-4 py-10">
                <div className="w-full max-w-2xl">
                    {loading && (
                        <div className="text-center py-20 text-gray-500" data-testid="public-job-loading">Loading job description…</div>
                    )}
                    {!loading && error && (
                        <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden" data-testid="public-job-error">
                            <div className="bg-rose-700 h-3 rounded-t-xl"></div>
                            <div className="p-8 text-center space-y-3">
                                <h2 className="text-xl font-bold text-gray-900">{error}</h2>
                                <p className="text-sm text-gray-600">The link you opened is no longer available. Please contact the recruiter who shared it.</p>
                            </div>
                        </div>
                    )}
                    {!loading && !error && jo && jo.inactive && (
                        // iter130 — Professional "unavailable" notice for
                        // deactivated openings (spec-mandated copy).
                        <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden" data-testid="public-job-inactive">
                            <div className="bg-rose-700 h-3 rounded-t-xl"></div>
                            <div className="p-8 text-center space-y-4">
                                <h2 className="text-2xl font-bold text-gray-900" data-testid="public-job-inactive-title">{jo.title}</h2>
                                <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed" data-testid="public-job-inactive-message">{jo.message}</p>
                            </div>
                        </div>
                    )}
                    {!loading && !error && jo && !jo.inactive && (
                        <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden" data-testid="public-job-content">
                            <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                            <div className="p-8 space-y-5">
                                <h1 className="text-2xl font-bold text-gray-900">Our Current Openings:</h1>
                                <h2 className="text-xl font-semibold text-gray-900" data-testid="public-job-title">{jo.title}</h2>
                                {/* iter110 — Two-column details table styled per reference image:
                                    bold left labels with colons, light-gray row separators,
                                    generous vertical spacing. Empty rows omitted entirely. */}
                                {(() => {
                                    const rows = [
                                        ['Role',                jo.job_role],
                                        ['Vacancies',           jo.vacancies],
                                        ['Year of Passing Out', jo.years_of_graduation?.length ? jo.years_of_graduation.join(', ') : ''],
                                        ['Education',           jo.education?.length ? jo.education.join(', ') : ''],
                                        ['Salary',              jo.salary_range],
                                    ].filter(([, v]) => v !== null && v !== undefined && v !== '' && v !== 0);
                                    if (rows.length === 0) return null;
                                    return (
                                        <table className="w-full text-sm" data-testid="public-job-details-table">
                                            <tbody>
                                                {rows.map(([label, value]) => (
                                                    <tr key={label} className="border-b border-gray-200 last:border-b-0" data-testid={`public-job-row-${label.toLowerCase().replace(/\s+/g, '-')}`}>
                                                        <th scope="row" className="text-left font-semibold text-gray-900 py-2.5 pr-6 align-top whitespace-nowrap w-[180px]">{label}:</th>
                                                        <td className="text-gray-800 py-2.5 break-words">{value}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    );
                                })()}
                                {/* iter108 — Prefer dynamic sections; fall back to legacy fields. */}
                                {Array.isArray(jo.descriptive_sections) && jo.descriptive_sections.length > 0
                                    ? jo.descriptive_sections.map((s, i) => (
                                        (s.title || s.description) && (
                                            <div key={i} data-testid={`public-section-${i}`}>
                                                {s.title && <h3 className="font-semibold text-gray-800 mb-1">{s.title}:</h3>}
                                                {s.description && <p className="text-sm text-gray-700 whitespace-pre-line">{s.description}</p>}
                                            </div>
                                        )
                                    ))
                                    : (<>
                                        {jo.key_responsibilities && <div><h3 className="font-semibold text-gray-800 mb-1">Key Responsibilities:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.key_responsibilities}</p></div>}
                                        {jo.added_advantages && <div><h3 className="font-semibold text-gray-800 mb-1">Added Advantage:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.added_advantages}</p></div>}
                                        {jo.what_we_offer && <div><h3 className="font-semibold text-gray-800 mb-1">What We Offer:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.what_we_offer}</p></div>}
                                    </>)
                                }
                            </div>
                        </div>
                    )}
                </div>
            </div>
            <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
        </div>
    );
}
