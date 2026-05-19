import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { normalizePhone, maskPhoneInput, PHONE_HELPER_TEXT, PHONE_ERROR_TEXT } from '../utils/phone';

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
        // eslint-disable-next-line no-console
        console.log('[PublicRegistration] fetching form', { API, formId });
        axios.get(`${API}/api/pub/form/${formId}`).then(r => {
            // eslint-disable-next-line no-console
            console.log('[PublicRegistration] form loaded', r.data);
            setForm(r.data);
            setStep(r.data.job_description_attached && r.data.job_opening ? 'jd' : 'form');
        }).catch((err) => {
            // eslint-disable-next-line no-console
            console.error('[PublicRegistration] fetch failed', err);
            setError('Form not found');
        }).finally(() => setLoading(false));
    }, [formId]);

    const showLocationQuestions = () => {
        if (!form?.conditions?.locations?.length) return false;
        const city = f.preferred_location_city.trim().toLowerCase();
        return city && !form.conditions.locations.map(l => l.toLowerCase()).includes(city);
    };

    const [phoneTouched, setPhoneTouched] = useState(false);
    const phoneNorm = normalizePhone(f.phone);

    const handleSubmit = async () => {
        const email = (f.email || '').trim();
        const fullName = (f.full_name || '').trim();
        const city = (f.preferred_location_city || '').trim();
        const state = (f.current_location_state || '').trim();
        if (!fullName || !email || !f.phone) { alert('Full Name, Email, and Phone are required'); return; }
        if (!phoneNorm.ok) { alert(phoneNorm.error); return; }
        // Replace raw input with normalized 10-digit form so backend sees the canonical value.
        setF(p => ({ ...p, phone: phoneNorm.value }));
        if (!state || !city) { alert('Current Location (State) and Preferred Location (City) are required'); return; }
        setSubmitting(true);
        try {
            const payload = { form_id: formId, ...f, age: f.age ? Number(f.age) : null, year_of_graduation: f.year_of_graduation ? Number(f.year_of_graduation) : null };
            const r = await axios.post(`${API}/api/pub/register`, payload);
            setResult(r.data);
            // For AI/ML role we still show the "What You Need to Know" interstitial,
            // then the result page. For all other forms go straight to result.
            const isShortlisted = r.data?.status === 'SHORTLISTED' || r.data?.is_shortlisted;
            const isAimlRole = form?.job_role?.toLowerCase().includes('ai') && form?.job_role?.toLowerCase().includes('ml');
            // Both the custom instructions page AND the AI/ML interstitial are now
            // gated by the same `show_instruction_page` admin toggle. When set to No,
            // neither interstitial appears — registrants go straight to result.
            if (form?.show_instruction_page) {
                if ((form.instruction_content || '').trim()) {
                    setStep('instructions');
                } else if (isShortlisted && isAimlRole) {
                    setStep('aiml');
                } else {
                    setStep('result');
                }
            } else {
                setStep('result');
            }
        } catch (e) {
            // Friendly handling for the 4-month re-registration block (409)
            const status = e.response?.status;
            const detail = e.response?.data?.detail || 'Registration failed';
            if (status === 409) {
                setResult({ status: 'BLOCKED', is_shortlisted: false, message: detail, reason: 'ALREADY_ATTENDED' });
                setStep('result');
            } else {
                alert(detail);
            }
        }
        finally { setSubmitting(false); }
    };

    if (loading) return <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center text-gray-500">Loading...</div>;
    if (error) return <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center text-red-500">{error}</div>;

    // Job Description Page
    if (step === 'jd' && form?.job_opening) {
        const jo = form.job_opening;
        return (
            <div className="min-h-screen bg-[#f3f1e9]" data-testid="jd-page">
                <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
                </header>
                <div className="max-w-2xl mx-auto px-6 py-10">
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="p-8 space-y-5">
                            <h1 className="text-2xl font-bold text-gray-900">Our Current Openings:</h1>
                            <h2 className="text-xl font-semibold text-gray-900">{jo.title}</h2>
                            {/* iter110 — Two-column details table styled per reference image. */}
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
                                    <table className="w-full text-sm" data-testid="jd-details-table">
                                        <tbody>
                                            {rows.map(([label, value]) => (
                                                <tr key={label} className="border-b border-gray-200 last:border-b-0" data-testid={`jd-row-${label.toLowerCase().replace(/\s+/g, '-')}`}>
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
                                        <div key={i} data-testid={`jd-section-${i}`}>
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
                            <button onClick={() => setStep('form')} data-testid="apply-now-btn"
                                className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg text-center mt-4">Apply Now</button>
                        </div>
                    </div>
                </div>
                <footer className="py-4 text-center text-sm text-gray-500">Copyright 2026 &copy; <b>Blubridge.com</b></footer>
            </div>
        );
    }

    // Custom Instruction Page (admin-controlled per form)
    if (step === 'instructions') {
        const isShortlisted = result?.status === 'SHORTLISTED' || result?.is_shortlisted;
        const goNext = () => {
            if (isShortlisted && form?.job_role?.toLowerCase().includes('ai') && form?.job_role?.toLowerCase().includes('ml')) {
                setStep('aiml');
            } else {
                setStep('result');
            }
        };
        return (
            <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid="instruction-page">
                <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
                </header>
                <div className="flex-1 max-w-3xl w-full mx-auto px-6 py-10">
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm p-8 md:p-12 text-[#1a1a1a]">
                        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-6" data-testid="instruction-page-title">Important Instructions</h1>
                        <div
                            className="prose prose-sm md:prose-base max-w-none text-gray-800"
                            data-testid="instruction-page-content"
                            dangerouslySetInnerHTML={{ __html: form?.instruction_content || '' }}
                        />
                        <div className="mt-10 flex justify-end">
                            <button
                                onClick={goNext}
                                data-testid="instruction-page-continue-btn"
                                className="px-6 py-3 bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium rounded transition-colors"
                            >
                                Continue
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // AI & ML Info Page (Joining Our Deep Learning Research Team)
    if (step === 'aiml') {
        return (
            <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid="aiml-page">
                <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
                </header>
                <div className="flex-1 max-w-4xl w-full mx-auto px-6 py-10">
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm p-10 md:p-14 text-[#1a1a1a]">
                        {/* Title */}
                        <h2 className="text-2xl font-bold text-center underline underline-offset-4 decoration-2">Joining Our Deep Learning Research Team</h2>
                        <h3 className="text-xl font-bold text-center mt-2 mb-10">What You Need to Know ?</h3>

                        {/* a) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">a) Are we a startup?</h4>
                            <p className="text-sm leading-relaxed text-gray-800"><b>No.</b> We are a <b>Deep Learning Research Organization</b>, not a startup.</p>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* b) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">b) Who is funding us?</h4>
                            <p className="text-sm leading-relaxed text-gray-800">We are entirely <b>self-funded.</b></p>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* c) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">c) Am I eligible to apply?</h4>
                            <p className="text-sm text-gray-800">Ask yourself the following:</p>
                            <ul className="list-disc pl-6 space-y-1.5 text-sm text-gray-800 leading-relaxed marker:text-gray-700">
                                <li>Do I truly understand the <b>depth of Deep Learning research?</b></li>
                                <li>Am I aware this is a pragmatic, mathematics-driven science, not just a language task?</li>
                                <li>Am I ready to work with first principles of Machine Learning, not frameworks alone?</li>
                            </ul>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* d) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">d) Where do I begin? What should I study for the interview?</h4>
                            <ul className="list-disc pl-6 space-y-1.5 text-sm text-gray-800 leading-relaxed marker:text-gray-700">
                                <li>Begin by appearing for the <b>initial interview rounds.</b></li>
                                <li>If selected, you'll be invited to a <b>second stage</b> where a strong grasp of Mathematics for Machine Learning is essential.</li>
                                <li>You'll get <b>up to a month</b> to prepare. Final selection is based on a <b>Maths for Deep Learning</b> test.</li>
                            </ul>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* e) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">e) How is the pay?</h4>
                            <p className="text-sm text-gray-800">We offer competitive compensation, but ask you to consider:</p>
                            <ul className="list-disc pl-6 space-y-1.5 text-sm text-gray-800 leading-relaxed marker:text-gray-700">
                                <li>You'll be working on Deep Learning from first principles — how many organizations offer that?</li>
                                <li>We are among the very few in India genuinely building a foundation model, not just hyping it.</li>
                                <li>Building from "first principles" is not the same as starting "from scratch."</li>
                                <li>If you were to study this in a university:
                                    <ul className="pl-5 mt-1.5 space-y-1.5 list-none">
                                        <li className="flex gap-2"><span className="text-gray-600">▸</span><span>You'd likely go abroad (e.g., the US)</span></li>
                                        <li className="flex gap-2"><span className="text-gray-600">▸</span><span>Pay for a Master's degree</span></li>
                                        <li className="flex gap-2"><span className="text-gray-600">▸</span><span>Learn theory without real-world application</span></li>
                                    </ul>
                                </li>
                            </ul>
                            <p className="text-sm text-gray-800 leading-relaxed pt-2">
                                <span className="text-yellow-500 mr-1">💡</span>
                                <b>If compensation is your main driver,</b> you will find better-paying jobs. We are seeking <b>like-minded individuals</b> who value the mission over money.
                            </p>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* f) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">f) Why is this opportunity unique?</h4>
                            <ul className="list-disc pl-6 space-y-1.5 text-sm text-gray-800 leading-relaxed marker:text-gray-700">
                                <li>We offer a <b>rare research environment</b> focused solely on foundation model development.</li>
                                <li>We're assembling a team of <b>passionate, like-minded individuals</b></li>
                                <li>Whether you're a research scholar or a self-taught enthusiast — if you have the fire to understand and build <b>Large Language Models</b>, you're welcome to apply.</li>
                            </ul>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* g) */}
                        <div className="space-y-2">
                            <h4 className="text-base font-bold">g) Who should not apply?</h4>
                            <ul className="list-disc pl-6 space-y-1.5 text-sm text-gray-800 leading-relaxed marker:text-gray-700">
                                <li>Those looking for a <b>routine 9-to-5 job</b></li>
                                <li>Anyone who <b>struggled with 12th-grade mathematics</b></li>
                            </ul>
                        </div>
                        <hr className="my-7 border-gray-200" />

                        {/* Confirmation */}
                        <label className="flex items-start gap-3 cursor-pointer pl-2">
                            <input type="checkbox" data-testid="aiml-accept-checkbox"
                                checked={f.aiml_accepted || false}
                                onChange={(e) => setF(p => ({ ...p, aiml_accepted: e.target.checked }))}
                                className="mt-1 w-4 h-4 shrink-0 accent-blue-600" />
                            <span className="text-sm text-gray-800 leading-relaxed">I have read and understood the information above, and I am willing to join Blubridge's Deep Learning Research Unit under these expectations.</span>
                        </label>

                        {/* APPLY button */}
                        <div className="flex justify-center mt-8">
                            <button onClick={() => f.aiml_accepted && setStep('result')}
                                disabled={!f.aiml_accepted}
                                data-testid="aiml-apply-btn"
                                className={`px-16 py-3 text-sm font-bold tracking-wider text-white rounded-lg transition-colors ${f.aiml_accepted ? 'bg-[#1E4FFF] hover:bg-[#1840d6]' : 'bg-[#bfd5ff] cursor-not-allowed'}`}>
                                APPLY
                            </button>
                        </div>
                    </div>
                </div>
                <footer className="bg-[#1f1f1f] text-gray-300 py-5 px-6 mt-10">
                    <div className="max-w-4xl mx-auto text-sm">
                        Copyright 2026 &copy; <b className="text-white">Blubridge.com</b>
                    </div>
                </footer>
            </div>
        );
    }

    // Result Page — dynamic shortlisted / rejected UI
    if (step === 'result' || step === 'success') {
        const isShortlisted = result?.status === 'SHORTLISTED' || result?.is_shortlisted;
        const reason = result?.reason || '';
        const message = result?.message || '';
        const showSchedule = result?.showSchedule || (isShortlisted && result?.schedule_token);
        // Prefer backend-supplied absolute scheduleLink (uses FRONTEND_URL); fall back to relative.
        const scheduleHref = result?.scheduleLink || (result?.schedule_token ? `/schedule-interview/${result.schedule_token}` : '#');
        // Mark schedule_initiated BEFORE navigating so the 5-min delayed
        // Schedule Link worker doesn't also email/whatsapp the candidate.
        const handleScheduleClick = (e) => {
            const tok = result?.schedule_token;
            if (tok) {
                // Fire-and-forget; navigation continues regardless
                axios.post(`${API}/api/pub/schedule-click/${tok}`).catch(() => {});
            }
        };

        return (
            <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid={isShortlisted ? 'result-shortlisted' : `result-rejected-${(reason || 'general').toLowerCase()}`}>
                <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                    <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
                </header>
                <div className="flex-1 flex items-center justify-center px-6 py-10">
                    <div className="max-w-lg w-full">
                        <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                            <div className={`h-3 rounded-t-xl ${isShortlisted ? 'bg-emerald-600' : 'bg-[#1a2332]'}`}></div>
                            <div className="p-8 text-center space-y-5">
                                {isShortlisted ? (
                                    <>
                                        <h2 className="text-2xl font-bold text-emerald-700" data-testid="result-title">You are shortlisted!</h2>
                                        <p className="text-sm text-gray-700">Congratulations on clearing the initial screening.</p>
                                        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-left text-sm text-emerald-900">
                                            <p>{message}</p>
                                        </div>
                                        {showSchedule && (
                                            <a href={scheduleHref} onClick={handleScheduleClick} data-testid="schedule-cta-btn"
                                                className="inline-block w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg text-center">
                                                Schedule Interview
                                            </a>
                                        )}
                                    </>
                                ) : (
                                    <>
                                        <h2 className="text-xl font-bold text-gray-900" data-testid="result-title">Thank you for applying</h2>
                                        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-left text-sm text-gray-700" data-testid="result-message">
                                            <p>{message}</p>
                                        </div>
                                        <p className="text-xs text-gray-500">A confirmation has been sent to your email and WhatsApp.</p>
                                    </>
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
        <div className="min-h-screen bg-[#f3f1e9] flex flex-col" data-testid="registration-form-page">
            <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex justify-center">
                <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
            </header>

            <div className="flex-1 flex items-start justify-center px-4 py-10">
                <div className="w-full max-w-[640px]">
                    <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                        <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                        <div className="px-8 py-8">
                            <h2 className="text-2xl font-bold text-gray-900 text-center mb-8">Registration Form</h2>

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
                                    <input
                                        type="tel"
                                        inputMode="tel"
                                        value={f.phone}
                                        onChange={e => setF(p => ({...p, phone: maskPhoneInput(e.target.value)}))}
                                        onBlur={() => {
                                            setPhoneTouched(true);
                                            // iter95 — Visually replace the field with the 10-digit
                                            // canonical form on blur so the user sees exactly what
                                            // will be stored. Silent: no toast, only the helper text.
                                            const n = normalizePhone(f.phone);
                                            if (n.ok && n.value !== f.phone) setF(p => ({...p, phone: n.value}));
                                        }}
                                        data-testid="reg-phone"
                                        required
                                        maxLength="13"
                                        title={PHONE_HELPER_TEXT}
                                        placeholder="9876543210 or +919876543210"
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
                                    {phoneTouched && f.phone && !phoneNorm.ok ? (
                                        <p className="text-xs text-red-600 mt-1" data-testid="reg-phone-error">{PHONE_ERROR_TEXT}</p>
                                    ) : (
                                        <p className="text-xs text-gray-500 mt-1 italic">{PHONE_HELPER_TEXT}</p>
                                    )}
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
                                    <input type="text" value={f.course} onChange={e => setF(p => ({...p, course:e.target.value}))} data-testid="reg-course" required
                                        placeholder="e.g. Computer Science, Mechanical, MBA Finance"
                                        className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-4 py-3 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" />
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
