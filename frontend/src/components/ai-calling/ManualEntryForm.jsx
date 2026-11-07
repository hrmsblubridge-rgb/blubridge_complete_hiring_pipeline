import { useState } from 'react';
import { toast } from 'sonner';
import { UserPlus } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const EMPTY = { candidate_name: '', phone_number: '', job_role: '', interview_date: '', interview_time: '', language: 'English', company_name: '', office_address: '' };
const inputCls = 'w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-teal-500';

const F = ({ label, children }) => (
    <label className="block">
        <span className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</span>
        {children}
    </label>
);

export const ManualEntryForm = ({ onSaved }) => {
    const [f, setF] = useState(EMPTY);
    const [busy, setBusy] = useState(false);
    const set = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await aiApi.post('/test-candidates', f);
            toast.success('Test candidate added (not approved yet)');
            setF(EMPTY); onSaved();
        } catch (err) { toast.error(errMsg(err, 'Save failed')); }
        finally { setBusy(false); }
    };

    return (
        <Card data-testid="manual-entry-panel">
            <SectionTitle icon={UserPlus}>Add test candidate manually</SectionTitle>
            <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <F label="Candidate name *"><input className={inputCls} value={f.candidate_name} onChange={set('candidate_name')} data-testid="manual-name" required /></F>
                <F label="Phone (10-digit) *"><input className={inputCls} value={f.phone_number} onChange={set('phone_number')} inputMode="numeric" placeholder="9000000001" data-testid="manual-phone" required /></F>
                <F label="Job role *"><input className={inputCls} value={f.job_role} onChange={set('job_role')} data-testid="manual-role" required /></F>
                <F label="Language *">
                    <select className={inputCls} value={f.language} onChange={set('language')} data-testid="manual-language"><option>English</option><option>Tamil</option></select>
                </F>
                <F label="Interview date *"><input type="date" className={inputCls} value={f.interview_date} onChange={set('interview_date')} data-testid="manual-date" required /></F>
                <F label="Interview time *"><input type="time" className={inputCls} value={f.interview_time} onChange={set('interview_time')} data-testid="manual-time" required /></F>
                <F label="Company (blank = default)"><input className={inputCls} value={f.company_name} onChange={set('company_name')} data-testid="manual-company" /></F>
                <F label="Office address (blank = default)"><input className={inputCls} value={f.office_address} onChange={set('office_address')} data-testid="manual-address" /></F>
                <div className="sm:col-span-2 lg:col-span-4 flex justify-end">
                    <button type="submit" disabled={busy} data-testid="manual-submit-btn" className="px-5 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-60">{busy ? 'Saving…' : 'Add test candidate'}</button>
                </div>
            </form>
        </Card>
    );
};
