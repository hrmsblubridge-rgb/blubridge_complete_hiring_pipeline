import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const STATES = ["Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","New Delhi","Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Jammu And Kashmir","Karnataka","Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura","Uttar Pradesh","Uttarakhand","West Bengal"];
const UG_DEGREES = ["BBA","BSc","BA","BBM","B.E","B.Tech","BMC","BJ / BJMC","Other"];
const PG_DEGREES = ["MBA","MSc","MA","M.E","M.Tech","MMC","MJ / MJMC","Other"];
const GRAD_YEARS = ["2020","2021","2022","2023","2024","2025","2026","2027"];

export default function PublicRegistration() {
    const { formId } = useParams();
    const [form, setForm] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [step, setStep] = useState('jd');
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState(null);
    const [f, setF] = useState({ full_name:'', email:'', phone:'', age:'', current_location_state:'', preferred_location_city:'', year_of_graduation:'', degree:'', course:'', college:'', location_change:null, attend_in_person:null });

    useEffect(() => {
        axios.get(`${API}/api/pub/form/${formId}`).then(r => {
            setForm(r.data);
            setStep(r.data.job_description_attached && r.data.job_opening ? 'jd' : 'form');
        }).catch(() => setError('Form not found')).finally(() => setLoading(false));
    }, [formId]);

    const showLocationQuestions = () => {
        if (!form?.conditions?.locations?.length) return false;
        const city = f.preferred_location_city.trim().toLowerCase();
        return city && !form.conditions.locations.map(l => l.toLowerCase()).includes(city);
    };

    const handleSubmit = async () => {
        if (!f.full_name.trim() || !f.email.trim() || !f.phone.trim()) { alert('Full Name, Email, and Phone are required'); return; }
        setSubmitting(true);
        try {
            const payload = { form_id: formId, ...f, age: f.age ? Number(f.age) : null, year_of_graduation: f.year_of_graduation ? Number(f.year_of_graduation) : null };
            const r = await axios.post(`${API}/api/pub/register`, payload);
            setResult(r.data);
            if (form?.job_role?.toLowerCase().includes('ai') && form?.job_role?.toLowerCase().includes('ml')) {
                setStep('aiml');
            } else {
                setStep('success');
            }
        } catch (e) { alert(e.response?.data?.detail || 'Registration failed'); }
        finally { setSubmitting(false); }
    };

    if (loading) return <div className="min-h-screen bg-[#f0ebe3] flex items-center justify-center text-gray-500">Loading...</div>;
    if (error) return <div className="min-h-screen bg-[#f0ebe3] flex items-center justify-center text-red-500">{error}</div>;

    // Job Description Page
    if (step === 'jd' && form?.job_opening) {
        const jo = form.job_opening;
        return (
            <div className="min-h-screen bg-[#f0ebe3]" data-testid="jd-page">
                <header className="bg-[#f0ebe3] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.png" alt="Blubridge" className="h-10" />
                </header>
                <div className="max-w-2xl mx-auto px-6 py-10">
                    <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="p-8 space-y-5">
                            <h1 className="text-2xl font-bold text-gray-900">Our Current Openings:</h1>
                            <h2 className="text-xl font-semibold text-gray-900">{jo.title}</h2>
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
                            <button onClick={() => setStep('form')} data-testid="apply-now-btn"
                                className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg text-center mt-4">Apply Now</button>
                        </div>
                    </div>
                </div>
                <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
            </div>
        );
    }

    // AI & ML Info Page (Joining Our Deep Learning Research Team)
    if (step === 'aiml') {
        return (
            <div className="min-h-screen bg-[#f0ebe3]" data-testid="aiml-page">
                <header className="bg-[#f0ebe3] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.png" alt="Blubridge" className="h-10" />
                </header>
                <div className="max-w-2xl mx-auto px-6 py-10">
                    <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="p-8 space-y-4">
                            <h2 className="text-xl font-bold text-gray-900">Joining Our Deep Learning Research Team</h2>
                            <h3 className="font-semibold text-gray-800">What You Need to Know?</h3>
                            <div className="text-sm text-gray-700 space-y-2">
                                <p><b>a) Are we a startup?</b> No. We are a Deep Learning Research Organization, not a startup.</p>
                                <p><b>b) Who is funding us?</b> We are entirely self-funded.</p>
                                <p><b>c) Am I eligible to apply?</b> Ask yourself: Do I truly understand the depth of Deep Learning research?</p>
                                <p><b>d) Where do I begin?</b> Begin by appearing for the initial interview rounds.</p>
                                <p><b>e) How is the pay?</b> We offer competitive compensation.</p>
                                <p><b>f) Why is this opportunity unique?</b> We offer a rare research environment focused solely on foundation model development.</p>
                                <p><b>g) Who should not apply?</b> Those looking for a routine 9-to-5 job. Anyone who struggled with 12th-grade mathematics.</p>
                            </div>
                            <div className="bg-[#eef4ff] border border-[#c8deff] rounded-lg p-4 mt-4">
                                <label className="flex items-start gap-2 cursor-pointer">
                                    <input type="checkbox" className="mt-1 accent-blue-600 w-4 h-4" />
                                    <span className="text-sm text-gray-700">I have read and understood the information above, and I am willing to join Blubridge's Deep Learning Research Unit under these expectations.</span>
                                </label>
                            </div>
                            <button onClick={() => setStep('success')} data-testid="aiml-apply-btn"
                                className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg mt-4">APPLY</button>
                        </div>
                    </div>
                </div>
                <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
            </div>
        );
    }

    // Success Page
    if (step === 'success') {
        return (
            <div className="min-h-screen bg-[#f0ebe3] flex flex-col" data-testid="success-page">
                <header className="bg-[#f0ebe3] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.png" alt="Blubridge" className="h-10" />
                </header>
                <div className="flex-1 flex items-center justify-center px-6">
                    <div className="max-w-lg w-full">
                        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                            <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                            <div className="p-8 text-center space-y-4">
                                <h2 className="text-xl font-bold text-gray-900">Submission Successful!</h2>
                                <p className="text-gray-600 text-sm">Thank you for completing your registration form. We appreciate your interest in joining Blubridge Technologies.</p>
                                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-left text-sm text-gray-700">
                                    <p className="font-semibold mb-1">Next Steps:</p>
                                    <p>Our team will review your responses, and you will receive an update on your application via Email / WhatsApp within 24 hours.</p>
                                </div>
                                {result?.schedule_token && (
                                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-left text-sm text-emerald-800">
                                        <p className="font-semibold mb-1">You are shortlisted!</p>
                                        <a href={`/schedule-interview/${result.schedule_token}`} className="text-blue-600 underline">Schedule your interview</a>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
                <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
            </div>
        );
    }

    // Main Registration Form — exact clone of blubridge.ai reference
    return (
        <div className="min-h-screen bg-[#f0ebe3] flex flex-col" data-testid="registration-form-page">
            <header className="bg-[#f0ebe3] border-b border-gray-300 py-4 px-6 flex justify-center">
                <img src="/blubridge-logo.png" alt="Blubridge" className="h-10" />
            </header>

            <div className="flex-1 flex items-start justify-center px-4 py-10">
                <div className="w-full max-w-[640px]">
                    <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="px-8 py-8">
                            <h2 className="text-2xl font-bold text-gray-900 text-center mb-8" style={{fontFamily:'serif'}}>Registration Form</h2>

                            {/* Full Name + Email */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 mb-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Full Name:</label>
                                    <input type="text" value={f.full_name} onChange={e => setF(p => ({...p, full_name:e.target.value}))} data-testid="reg-name" required
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Email Address:</label>
                                    <input type="email" value={f.email} onChange={e => setF(p => ({...p, email:e.target.value}))} data-testid="reg-email" required
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                </div>
                            </div>

                            {/* Phone + Age */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 mb-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Phone Number:</label>
                                    <input type="text" value={f.phone} onChange={e => setF(p => ({...p, phone:e.target.value}))} data-testid="reg-phone" required maxLength="10"
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                    <p className="text-xs text-gray-500 mt-1 italic">Note: Active WhatsApp number (Required)</p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Age:</label>
                                    <input type="number" value={f.age} onChange={e => setF(p => ({...p, age:e.target.value}))} data-testid="reg-age" required min="18" max="80"
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                </div>
                            </div>

                            {/* State + City */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 mb-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Current Location (State):</label>
                                    <select value={f.current_location_state} onChange={e => setF(p => ({...p, current_location_state:e.target.value}))} data-testid="reg-state" required
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white appearance-none">
                                        <option value="">Select State</option>
                                        {STATES.map(s => <option key={s}>{s}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Preferred Location (City)<span className="text-red-500">*</span>:</label>
                                    <input type="text" value={f.preferred_location_city} onChange={e => setF(p => ({...p, preferred_location_city:e.target.value}))} data-testid="reg-city" required
                                        placeholder="Start typing city name..."
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white placeholder:text-gray-400" />
                                </div>
                            </div>

                            {/* Conditional: Location change + Attend in person */}
                            {showLocationQuestions() && (
                                <div className="mb-5 space-y-4 bg-[#fafafa] border border-gray-200 rounded-lg p-5" data-testid="location-questions">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">Are you willing to relocate to Chennai for a full-time, on-site role? <span className="text-red-500">*</span></label>
                                        <div className="flex gap-6">{['Yes','No'].map(v => <label key={v} className="flex items-center gap-2 text-sm cursor-pointer"><input type="radio" name="loca_change" checked={f.location_change===v} onChange={() => setF(p => ({...p, location_change:v}))} className="accent-blue-600 w-4 h-4" />{v}</label>)}</div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">Can you attend an in-person interview at our Chennai office? <span className="text-red-500">*</span></label>
                                        <div className="flex gap-6">{['Yes','No'].map(v => <label key={v} className="flex items-center gap-2 text-sm cursor-pointer"><input type="radio" name="attend_inperson" checked={f.attend_in_person===v} onChange={() => setF(p => ({...p, attend_in_person:v}))} className="accent-blue-600 w-4 h-4" />{v}</label>)}</div>
                                    </div>
                                </div>
                            )}

                            {/* Year of Graduation + College */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 mb-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Year of Graduation:</label>
                                    <select value={f.year_of_graduation} onChange={e => setF(p => ({...p, year_of_graduation:e.target.value}))} data-testid="reg-year" required
                                        className="w-full bg-white border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 appearance-none">
                                        <option value="">Select</option>
                                        {GRAD_YEARS.map(y => <option key={y}>{y}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">College:</label>
                                    <input type="text" value={f.college} onChange={e => setF(p => ({...p, college:e.target.value}))} data-testid="reg-college" required
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                </div>
                            </div>

                            {/* Degree + Course */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5 mb-5">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Degree:</label>
                                    <select value={f.degree} onChange={e => setF(p => ({...p, degree:e.target.value}))} data-testid="reg-degree" required
                                        className="w-full bg-white border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 appearance-none">
                                        <option value="">Select a degree</option>
                                        <optgroup label="UG">{UG_DEGREES.map(d => <option key={d} value={d}>{d}</option>)}</optgroup>
                                        <optgroup label="PG">{PG_DEGREES.map(d => <option key={d} value={d}>{d}</option>)}</optgroup>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Course:</label>
                                    <select value={f.course} onChange={e => setF(p => ({...p, course:e.target.value}))} data-testid="reg-course" required
                                        className="w-full bg-white border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 appearance-none">
                                        <option value="">Select a course</option>
                                    </select>
                                </div>
                            </div>

                            {/* Declaration */}
                            <div className="mt-6 mb-6">
                                <label className="flex items-start gap-3 cursor-pointer">
                                    <input type="checkbox" className="mt-0.5 accent-blue-600 w-4 h-4" required />
                                    <span className="text-sm text-gray-700">I hereby confirm that all the information provided above is accurate to the best of my knowledge.</span>
                                </label>
                            </div>

                            {/* Submit */}
                            <div className="flex justify-center">
                                <button onClick={handleSubmit} disabled={submitting} data-testid="proceed-btn"
                                    className="px-14 py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg disabled:opacity-50 tracking-wide text-base">
                                    {submitting ? 'Processing...' : 'Proceed'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
        </div>
    );
}
