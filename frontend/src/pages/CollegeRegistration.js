import { useState, useEffect } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const PageShell = ({ children, testid }) => (
    <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid={testid}>
        <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
            <img src="/blubridge-logo.webp" alt="Blubridge" />
        </header>
        <div className="flex-1 flex items-start justify-center px-4 py-10">
            {children}
        </div>
        <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
    </div>
);

const formatTime = (t) => {
    if (!t) return '';
    const parts = t.split(':');
    if (parts.length < 2) return t;
    const h = parseInt(parts[0], 10);
    const m = parts[1];
    const period = h < 12 ? 'AM' : 'PM';
    const h12 = h % 12 || 12;
    return `${String(h12).padStart(2, '0')}:${m} ${period}`;
};

const formatDateDDMMYYYY = (d) => {
    if (!d) return '';
    const parts = d.split('-');
    if (parts.length !== 3) return d;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
};

export default function CollegeRegistration() {
    const [colleges, setColleges] = useState([]);
    const [scheduleInfo, setScheduleInfo] = useState(null);
    const [roleOptions, setRoleOptions] = useState([]);  // Iter56 — populated from selected schedule
    const [submitting, setSubmitting] = useState(false);
    const [done, setDone] = useState(null);
    const [f, setF] = useState({
        full_name: '', email: '', phone: '', age: '', gender: '',
        college: '', job_role: '',
        schedule_date: '', schedule_time: '',  // auto-populated read-only
        degree: '', course: '', year_of_graduation: '',
        current_location_state: '', preferred_location_city: '',
    });

    useEffect(() => {
        axios.get(`${API}/api/pub/college-form/colleges`).then(r => setColleges(r.data.colleges || [])).catch(() => {});
    }, []);

    // Iter54 Req2 + Iter56 — On COLLEGE CHANGE only: fetch schedule, populate
    // Schedule Date/Time as read-only and Job Role OPTIONS for the select dropdown.
    useEffect(() => {
        if (!f.college) {
            setScheduleInfo(null);
            setRoleOptions([]);
            setF(p => ({ ...p, job_role: '', schedule_date: '', schedule_time: '' }));
            return;
        }
        let cancelled = false;
        axios.get(`${API}/api/pub/college-form/schedule`, { params: { college: f.college } })
            .then(r => {
                if (cancelled) return;
                const s = r.data?.schedule;
                if (!s) {
                    setScheduleInfo(null);
                    setRoleOptions([]);
                    setF(p => ({ ...p, job_role: '', schedule_date: '', schedule_time: '' }));
                    return;
                }
                // Prefer structured array; fall back to splitting the legacy joined string
                const roles = Array.isArray(s.job_roles) && s.job_roles.length
                    ? s.job_roles
                    : (s.job_role ? s.job_role.split(',').map(x => x.trim()).filter(Boolean) : []);
                setScheduleInfo({ found: true });
                setRoleOptions(roles);
                setF(p => ({
                    ...p,
                    // Auto-pick when only ONE role exists; otherwise leave empty so user must select
                    job_role: roles.length === 1 ? roles[0] : '',
                    schedule_date: s.schedule_date || '',
                    schedule_time: s.schedule_time || '',
                }));
            })
            .catch(() => {
                if (cancelled) return;
                setScheduleInfo(null);
                setRoleOptions([]);
                setF(p => ({ ...p, job_role: '', schedule_date: '', schedule_time: '' }));
            });
        return () => { cancelled = true; };
    }, [f.college]);

    const handleSubmit = async () => {
        const phone = (f.phone || '').trim();
        const email = (f.email || '').trim();
        const fullName = (f.full_name || '').trim();
        const city = (f.preferred_location_city || '').trim();
        const state = (f.current_location_state || '').trim();
        if (!fullName || !email || !phone) { alert('Name, Email and Phone are required'); return; }
        if (!/^[0-9]{10}$/.test(phone)) { alert('Phone must be exactly 10 digits — no +91, no spaces, no leading 0, no extensions.'); return; }
        if (!state || !city) { alert('Current Location (State) and Preferred Location (City) are required'); return; }
        if (!f.college || !f.job_role) { alert('Please select both College and Job Role'); return; }
        setSubmitting(true);
        try {
            const payload = {
                ...f,
                age: f.age ? Number(f.age) : null,
                year_of_graduation: f.year_of_graduation ? Number(f.year_of_graduation) : null,
            };
            const r = await axios.post(`${API}/api/pub/college-form/register`, payload);
            setDone(r.data);
        } catch (e) {
            alert(e.response?.data?.detail || 'Registration failed');
        } finally {
            setSubmitting(false);
        }
    };

    if (done) {
        return (
            <PageShell testid="college-success">
                <div className="w-full max-w-lg">
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-emerald-600 h-3 rounded-t-xl"></div>
                        <div className="p-8 text-center space-y-4">
                            <h2 className="text-2xl font-bold text-emerald-700">Registration Successful!</h2>
                            <p className="text-sm text-gray-700">Your interview has been scheduled.</p>
                            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-left text-sm text-emerald-900 space-y-1">
                                <div><span className="font-semibold">College:</span> {done.college}</div>
                                <div><span className="font-semibold">Role:</span> {done.job_role}</div>
                                <div><span className="font-semibold">Date:</span> {formatDateDDMMYYYY(done.schedule_date)}</div>
                                <div><span className="font-semibold">Time:</span> {formatTime(done.schedule_time)}</div>
                            </div>
                            <p className="text-xs text-gray-500">Please arrive 15 minutes early. We'll send a reminder via email.</p>
                        </div>
                    </div>
                </div>
            </PageShell>
        );
    }

    return (
        <PageShell testid="college-registration-page">
            <div className="w-full max-w-2xl">
                <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                    <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                    <div className="p-8 space-y-5">
                        <h2 className="text-2xl font-bold text-gray-900 text-center">College Registration</h2>
                        <p className="text-sm text-center text-gray-600">Select your college and the role you're applying for. Your interview slot is set by HR.</p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Full Name *</label>
                                <input type="text" value={f.full_name} onChange={e => setF(p => ({ ...p, full_name: e.target.value }))}
                                    data-testid="reg-name" className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Email *</label>
                                <input type="email" value={f.email} onChange={e => setF(p => ({ ...p, email: e.target.value }))}
                                    data-testid="reg-email" className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Phone *</label>
                                <input
                                    type="tel"
                                    inputMode="numeric"
                                    pattern="[0-9]{10}"
                                    value={f.phone}
                                    onChange={e => setF(p => ({ ...p, phone: e.target.value.replace(/\D/g, '').slice(0, 10) }))}
                                    data-testid="reg-phone"
                                    maxLength="10"
                                    placeholder="9876543210"
                                    title="Enter only 10-digit mobile number without +91, 0, spaces or extensions."
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                <p className="text-[11px] text-gray-500 mt-1 italic">Enter only 10-digit mobile number without +91, 0, spaces or extensions.</p>
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Age</label>
                                <input type="number" value={f.age} onChange={e => setF(p => ({ ...p, age: e.target.value }))}
                                    data-testid="reg-age" className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                            </div>

                            <div>
                                <label className="text-xs text-gray-600 font-medium">College *</label>
                                <select value={f.college} onChange={e => setF(p => ({ ...p, college: e.target.value }))} data-testid="reg-college"
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white">
                                    <option value="">Select your college</option>
                                    {colleges.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                                {colleges.length === 0 && <p className="text-xs text-amber-600 mt-1">No colleges have schedules yet. Please contact HR.</p>}
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Job Role *</label>
                                <select value={f.job_role} onChange={e => setF(p => ({ ...p, job_role: e.target.value }))}
                                    disabled={!f.college || roleOptions.length === 0}
                                    data-testid="reg-role"
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white disabled:opacity-60 disabled:cursor-not-allowed">
                                    <option value="">{
                                        !f.college ? 'Select college first'
                                        : roleOptions.length === 0 ? 'No roles available for this college'
                                        : 'Select role'
                                    }</option>
                                    {roleOptions.map(r => <option key={r} value={r}>{r}</option>)}
                                </select>
                            </div>

                            {/* Iter54 Req2 — Schedule Date & Time auto-filled (read-only) on college selection */}
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Schedule Date</label>
                                <input type="text" value={f.schedule_date ? formatDateDDMMYYYY(f.schedule_date) : ''} readOnly
                                    placeholder={f.college ? 'Auto-filled from college schedule' : 'Select college first'}
                                    data-testid="reg-schedule-date"
                                    className="w-full mt-1 bg-gray-100 border border-gray-200 rounded px-3 py-2.5 text-sm text-gray-700 cursor-not-allowed" />
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Schedule Time</label>
                                <input type="text" value={f.schedule_time ? formatTime(f.schedule_time) : ''} readOnly
                                    placeholder={f.college ? 'Auto-filled from college schedule' : 'Select college first'}
                                    data-testid="reg-schedule-time"
                                    className="w-full mt-1 bg-gray-100 border border-gray-200 rounded px-3 py-2.5 text-sm text-gray-700 cursor-not-allowed" />
                            </div>

                            <div>
                                <label className="text-xs text-gray-600 font-medium">Degree</label>
                                <select value={f.degree} onChange={e => setF(p => ({ ...p, degree: e.target.value }))} data-testid="reg-degree"
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white">
                                    <option value="">Select</option>
                                    <option>B.Tech</option><option>B.E.</option><option>BCA</option><option>BSc</option>
                                    <option>M.Tech</option><option>MCA</option><option>MSc</option><option>MBA</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Course</label>
                                <input type="text" value={f.course} onChange={e => setF(p => ({ ...p, course: e.target.value }))}
                                    placeholder="e.g. Computer Science" data-testid="reg-course"
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Year of Graduation</label>
                                <select value={f.year_of_graduation} onChange={e => setF(p => ({ ...p, year_of_graduation: e.target.value }))} data-testid="reg-year"
                                    className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white">
                                    <option value="">Select</option>
                                    {[2022, 2023, 2024, 2025, 2026, 2027].map(y => <option key={y}>{y}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="text-xs text-gray-600 font-medium">Preferred City</label>
                                <input type="text" value={f.preferred_location_city} onChange={e => setF(p => ({ ...p, preferred_location_city: e.target.value }))}
                                    data-testid="reg-city" className="w-full mt-1 bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                            </div>
                        </div>

                        {f.college && !scheduleInfo?.found && (
                            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-800" data-testid="schedule-notice">
                                No active schedule found for this college yet. Please contact HR.
                            </div>
                        )}

                        <button onClick={handleSubmit} disabled={submitting} data-testid="submit-btn"
                            className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white font-bold rounded-lg tracking-wide">
                            {submitting ? 'Submitting…' : 'Submit Registration'}
                        </button>
                    </div>
                </div>
            </div>
        </PageShell>
    );
}
