import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
const TIME_SLOTS = ['10:00 AM','10:30 AM','11:00 AM','11:30 AM','12:00 PM','12:30 PM','01:00 PM','01:30 PM','02:00 PM','02:30 PM','03:00 PM','03:30 PM','04:00 PM','04:30 PM','05:00 PM'];

function convertTo24h(t) {
    const [time, period] = t.split(' ');
    let [h, m] = time.split(':').map(Number);
    if (period === 'PM' && h !== 12) h += 12;
    if (period === 'AM' && h === 12) h = 0;
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00`;
}

function isSunday(dateStr) {
    return new Date(dateStr).getDay() === 0;
}

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

export default function InterviewSchedule() {
    const { token } = useParams();
    const [info, setInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [date, setDate] = useState('');
    const [time, setTime] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [done, setDone] = useState(false);
    const [missed, setMissed] = useState(false);

    useEffect(() => {
        axios.get(`${API}/api/pub/schedule/${token}`).then(r => {
            setInfo(r.data);
            if (r.data.reschedule_count > 0 && !r.data.schedule_date) setMissed(true);
        }).catch(() => setError('Invalid or expired link')).finally(() => setLoading(false));
    }, [token]);

    const isBlocked = (dateStr) => {
        if (!dateStr) return false;
        if (isSunday(dateStr)) return true;
        return (info?.holidays || []).includes(dateStr);
    };

    const handleSchedule = async () => {
        if (!date || !time) { alert('Please select date and time'); return; }
        if (isBlocked(date)) { alert('This date is a holiday or Sunday'); return; }
        setSubmitting(true);
        try {
            const time24 = convertTo24h(time);
            await axios.post(`${API}/api/pub/schedule/${token}`, { date, time: time24 });
            setDone(true);
        } catch (e) {
            const status = e.response?.status;
            const detail = e.response?.data?.detail || 'Failed';
            if (status === 409) {
                // OTP already verified — block reschedule with a clear message
                alert(detail);
                setError(detail);
            } else {
                alert(detail);
            }
        }
        finally { setSubmitting(false); }
    };

    if (loading) return <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center text-gray-500">Loading...</div>;
    if (error) return <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center text-red-500">{error}</div>;
    if (done) return (
        <PageShell testid="schedule-success">
            <div className="w-full max-w-md">
                <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                    <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                    <div className="p-8 text-center space-y-3">
                        <h2 className="text-xl font-bold text-gray-900">{info?.already_scheduled ? 'Interview Rescheduled!' : 'Interview Scheduled!'}</h2>
                        <p className="text-gray-600 text-sm">Your interview has been confirmed. You will receive further details via Email/WhatsApp.</p>
                    </div>
                </div>
            </div>
        </PageShell>
    );

    const today = new Date().toISOString().split('T')[0];

    return (
        <PageShell testid="schedule-page">
            <div className="w-full max-w-md">
                <div className="bg-[#fffdf7] rounded-xl shadow-sm overflow-hidden">
                    <div className="bg-[#1a2332] h-3 rounded-t-xl"></div>
                    <div className="p-8 space-y-5">
                        <h2 className="text-xl font-bold text-gray-900 text-center">
                            {info?.already_scheduled ? 'Your Interview Details' : 'Schedule Your In-Person Interview'}
                        </h2>
                        {missed && <p className="text-red-600 text-sm font-medium text-center">You have missed your interview!</p>}
                        {info?.already_scheduled && !missed && <p className="text-emerald-600 text-sm font-medium text-center">YOUR INTERVIEW IS ALREADY SCHEDULED.</p>}

                        <div className="space-y-3 text-sm">
                            <div><label className="text-xs text-gray-500 font-medium">NAME:</label><div className="mt-0.5 font-medium text-gray-900" data-testid="sched-name">{info?.name}</div></div>
                            <div><label className="text-xs text-gray-500 font-medium">EMAIL:</label><div className="mt-0.5 text-gray-700" data-testid="sched-email">{info?.email}</div></div>
                            <div><label className="text-xs text-gray-500 font-medium">PHONE:</label><div className="mt-0.5 text-gray-700" data-testid="sched-phone">{info?.phone}</div></div>
                            {info?.already_scheduled && info?.schedule_date && (
                                <><div><label className="text-xs text-gray-500 font-medium">DATE:</label><div className="mt-0.5 text-gray-700">{info.schedule_date}</div></div>
                                <div><label className="text-xs text-gray-500 font-medium">TIME:</label><div className="mt-0.5 text-gray-700">{info.schedule_time}</div></div></>
                            )}
                        </div>

                        <div className="border-t border-gray-200 pt-4 space-y-3">
                            <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Date:</label>
                                <input type="date" value={date} min={today} onChange={e => { if (!isBlocked(e.target.value)) setDate(e.target.value); else alert('Sundays and holidays are not available'); }} data-testid="sched-date"
                                    className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white" /></div>
                            <div className="space-y-1"><label className="text-xs text-gray-600 font-medium">Time:</label>
                                <select value={time} onChange={e => setTime(e.target.value)} data-testid="sched-time"
                                    className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white">
                                    <option value="">Select Time</option>
                                    {TIME_SLOTS.map(t => <option key={t}>{t}</option>)}
                                </select></div>
                        </div>

                        <button onClick={handleSchedule} disabled={submitting} data-testid="schedule-btn"
                            className="w-full py-3 bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold rounded-lg disabled:opacity-50 tracking-wide">
                            {submitting ? 'Processing...' : (info?.already_scheduled ? 'RESCHEDULE INTERVIEW' : 'SCHEDULE INTERVIEW')}
                        </button>
                    </div>
                </div>
            </div>
        </PageShell>
    );
}
