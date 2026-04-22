import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const STATES = ["Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Delhi","Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka","Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura","Uttar Pradesh","Uttarakhand","West Bengal"];
const DEGREES = ["B.Tech","B.E","B.Sc","BCA","M.Tech","M.E","M.Sc","MCA","MBA","Ph.D","Other"];

export default function PublicRegistration() {
    const { formId } = useParams();
    const [form, setForm] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [step, setStep] = useState('jd'); // 'jd' | 'form' | 'aiml' | 'success'
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
            setStep('success');
        } catch (e) { alert(e.response?.data?.detail || 'Registration failed'); }
        finally { setSubmitting(false); }
    };

    if (loading) return <div className="min-h-screen bg-white flex items-center justify-center text-gray-500">Loading...</div>;
    if (error) return <div className="min-h-screen bg-white flex items-center justify-center text-red-500">{error}</div>;

    // Job Description Page
    if (step === 'jd' && form?.job_opening) {
        const jo = form.job_opening;
        return (
            <div className="min-h-screen bg-gray-50" data-testid="jd-page">
                <div className="max-w-2xl mx-auto px-6 py-10">
                    <h1 className="text-2xl font-bold text-gray-900 mb-6">Our Current Openings:</h1>
                    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
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
                    </div>
                    <button onClick={() => setStep('form')} data-testid="apply-now-btn"
                        className="mt-6 w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg text-center">Apply Now</button>
                </div>
            </div>
        );
    }

    // AI & ML Info Page
    if (step === 'aiml') {
        return (
            <div className="min-h-screen bg-gray-50" data-testid="aiml-page">
                <div className="max-w-2xl mx-auto px-6 py-10">
                    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
                        <h2 className="text-xl font-bold text-gray-900">Joining Our Deep Learning Research Team</h2>
                        <h3 className="font-semibold text-gray-800">What You Need to Know?</h3>
                        <div className="text-sm text-gray-700 space-y-2">
                            <p><b>a) Are we a startup?</b> No. We are a Deep Learning Research Organization, not a startup.</p>
                            <p><b>b) Who is funding us?</b> We are entirely self-funded.</p>
                            <p><b>c) Am I eligible to apply?</b> Ask yourself: Do I truly understand the depth of Deep Learning research? Am I ready to work with first principles of Machine Learning, not frameworks alone?</p>
                            <p><b>d) Where do I begin?</b> Begin by appearing for the initial interview rounds. If selected, you'll be invited to a second stage where a strong grasp of Mathematics for Machine Learning is essential.</p>
                            <p><b>e) How is the pay?</b> We offer competitive compensation. You'll be working on Deep Learning from first principles — how many organizations offer that?</p>
                            <p><b>f) Why is this opportunity unique?</b> We offer a rare research environment focused solely on foundation model development.</p>
                            <p><b>g) Who should not apply?</b> Those looking for a routine 9-to-5 job. Anyone who struggled with 12th-grade mathematics.</p>
                        </div>
                        <label className="flex items-start gap-2 mt-4">
                            <input type="checkbox" id="aiml-confirm" className="mt-1 accent-blue-600" />
                            <span className="text-sm text-gray-700">I have read and understood the information above, and I am willing to join Blubridge's Deep Learning Research Unit under these expectations.</span>
                        </label>
                    </div>
                    <button onClick={() => setStep('success')} data-testid="aiml-apply-btn"
                        className="mt-6 w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg">APPLY</button>
                </div>
            </div>
        );
    }

    // Success Page
    if (step === 'success') {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center" data-testid="success-page">
                <div className="max-w-lg mx-auto px-6 py-16 text-center">
                    <div className="bg-white border border-gray-200 rounded-lg p-8 space-y-4">
                        <div className="text-4xl mb-2">BLUBRIDGE</div>
                        <h2 className="text-xl font-bold text-gray-900">Submission Successful!</h2>
                        <p className="text-gray-600">Thank you for completing your registration form. We appreciate your interest in joining Blubridge Technologies.</p>
                        <div className="bg-gray-50 border border-gray-200 rounded p-4 text-left text-sm text-gray-700">
                            <p className="font-semibold mb-1">Next Steps:</p>
                            <p>Our team will review your responses, and you will receive an update on your application via Email / WhatsApp within 24 hours.</p>
                        </div>
                        {result?.schedule_token && (
                            <div className="bg-emerald-50 border border-emerald-200 rounded p-4 text-left text-sm text-emerald-800">
                                <p className="font-semibold mb-1">You are shortlisted!</p>
                                <a href={`/schedule-interview/${result.schedule_token}`} className="text-blue-600 underline">Schedule your interview</a>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    // Registration Form
    return (
        <div className="min-h-screen bg-gray-50" data-testid="registration-form-page">
            <div className="max-w-xl mx-auto px-6 py-10">
                <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-5">
                    <h2 className="text-xl font-bold text-gray-900 text-center">Registration Form</h2>
                    {form?.job_role && <p className="text-sm text-gray-500 text-center">Role: {form.job_role}</p>}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Full Name: *</label><input type="text" value={f.full_name} onChange={e => setF(p => ({...p, full_name:e.target.value}))} data-testid="reg-name" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Email Address: *</label><input type="email" value={f.email} onChange={e => setF(p => ({...p, email:e.target.value}))} data-testid="reg-email" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Phone Number: *</label><input type="text" value={f.phone} onChange={e => setF(p => ({...p, phone:e.target.value}))} data-testid="reg-phone" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /><p className="text-xs text-gray-400">Note: Active WhatsApp number (Required)</p></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Age:</label><input type="number" value={f.age} onChange={e => setF(p => ({...p, age:e.target.value}))} data-testid="reg-age" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Current Location (State):</label>
                            <select value={f.current_location_state} onChange={e => setF(p => ({...p, current_location_state:e.target.value}))} data-testid="reg-state" className="w-full border border-gray-300 rounded px-3 py-2 text-sm"><option value="">Select State</option>{STATES.map(s => <option key={s}>{s}</option>)}</select></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Preferred Location (City) *:</label><input type="text" value={f.preferred_location_city} onChange={e => setF(p => ({...p, preferred_location_city:e.target.value}))} data-testid="reg-city" placeholder="Start typing city name..." className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Year of Graduation:</label><input type="number" value={f.year_of_graduation} onChange={e => setF(p => ({...p, year_of_graduation:e.target.value}))} data-testid="reg-year" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Degree:</label>
                            <select value={f.degree} onChange={e => setF(p => ({...p, degree:e.target.value}))} data-testid="reg-degree" className="w-full border border-gray-300 rounded px-3 py-2 text-sm"><option value="">Select a degree</option>{DEGREES.map(d => <option key={d}>{d}</option>)}</select></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Course:</label><input type="text" value={f.course} onChange={e => setF(p => ({...p, course:e.target.value}))} data-testid="reg-course" placeholder="Select a course" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                        <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">College:</label><input type="text" value={f.college} onChange={e => setF(p => ({...p, college:e.target.value}))} data-testid="reg-college" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" /></div>
                    </div>
                    {showLocationQuestions() && (
                        <div className="border-t border-gray-200 pt-4 space-y-3" data-testid="location-questions">
                            <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Are you willing to relocate? *</label>
                                <div className="flex gap-4">{['Yes','No'].map(v => <label key={v} className="flex items-center gap-1.5 text-sm"><input type="radio" name="location_change" checked={f.location_change===v} onChange={() => setF(p => ({...p, location_change:v}))} className="accent-blue-600" />{v}</label>)}</div></div>
                            <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Can you attend an in-person interview? *</label>
                                <div className="flex gap-4">{['Yes','No'].map(v => <label key={v} className="flex items-center gap-1.5 text-sm"><input type="radio" name="attend_in_person" checked={f.attend_in_person===v} onChange={() => setF(p => ({...p, attend_in_person:v}))} className="accent-blue-600" />{v}</label>)}</div></div>
                        </div>
                    )}
                    <label className="flex items-start gap-2"><input type="checkbox" className="mt-1 accent-blue-600" /><span className="text-xs text-gray-600">I hereby confirm that all the information provided above is accurate to the best of my knowledge.</span></label>
                    <button onClick={() => { if (form?.job_role?.toLowerCase().includes('ai') && form?.job_role?.toLowerCase().includes('ml')) { handleSubmit().then(() => setStep('aiml')); } else { handleSubmit(); } }} disabled={submitting} data-testid="proceed-btn"
                        className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg disabled:opacity-50">{submitting ? 'Processing...' : 'PROCEED'}</button>
                </div>
            </div>
        </div>
    );
}
