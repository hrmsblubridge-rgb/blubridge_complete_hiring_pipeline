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
                    {!loading && !error && jo && (
                        <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden" data-testid="public-job-content">
                            <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                            <div className="p-8 space-y-5">
                                <h1 className="text-2xl font-bold text-gray-900">Our Current Openings:</h1>
                                <h2 className="text-xl font-semibold text-gray-900" data-testid="public-job-title">{jo.title}</h2>
                                <div className="grid grid-cols-2 gap-3 text-sm">
                                    {jo.job_role && <div><span className="font-medium text-gray-600">Role:</span> <span className="text-gray-900">{jo.job_role}</span></div>}
                                    {jo.vacancies && <div><span className="font-medium text-gray-600">Vacancies:</span> <span className="text-gray-900">{jo.vacancies}</span></div>}
                                    {jo.years_of_graduation?.length > 0 && <div><span className="font-medium text-gray-600">Year of Passing Out:</span> <span className="text-gray-900">{jo.years_of_graduation.join(', ')}</span></div>}
                                    {jo.education?.length > 0 && <div className="col-span-2"><span className="font-medium text-gray-600">Education:</span> <span className="text-gray-900">{jo.education.join(', ')}</span></div>}
                                    {jo.salary_range && <div><span className="font-medium text-gray-600">Salary:</span> <span className="text-gray-900">{jo.salary_range}</span></div>}
                                </div>
                                {jo.key_responsibilities && <div><h3 className="font-semibold text-gray-800 mb-1">Key Responsibilities:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.key_responsibilities}</p></div>}
                                {jo.added_advantages && <div><h3 className="font-semibold text-gray-800 mb-1">Added Advantage:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.added_advantages}</p></div>}
                                {jo.what_we_offer && <div><h3 className="font-semibold text-gray-800 mb-1">What We Offer:</h3><p className="text-sm text-gray-700 whitespace-pre-line">{jo.what_we_offer}</p></div>}
                            </div>
                        </div>
                    )}
                </div>
            </div>
            <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
        </div>
    );
}
