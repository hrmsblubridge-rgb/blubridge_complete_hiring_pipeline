import { inputCls } from './constants';

export const EMPTY_CANDIDATE = { candidate_name: '', phone_number: '', job_role: '', interview_date: '', interview_time: '', language: 'English', company_name: '', office_address: '' };

const F = ({ label, children }) => (
    <label className="block">
        <span className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</span>
        {children}
    </label>
);

export const CandidateFields = ({ f, setF, prefix }) => {
    const set = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));
    const t = (k) => `${prefix}-${k}`;
    return (
        <>
            <F label="Candidate name *"><input className={inputCls} value={f.candidate_name} onChange={set('candidate_name')} data-testid={t('name')} required /></F>
            <F label="Indian mobile number *"><input className={inputCls} value={f.phone_number} onChange={set('phone_number')} placeholder="+919000000001" inputMode="tel" data-testid={t('phone')} required /></F>
            <F label="Job role *"><input className={inputCls} value={f.job_role} onChange={set('job_role')} data-testid={t('role')} required /></F>
            <F label="Preferred language *">
                <select className={inputCls} value={f.language} onChange={set('language')} data-testid={t('language')}><option>English</option><option>Tamil</option></select>
            </F>
            <F label="Interview date *"><input type="date" className={inputCls} value={f.interview_date} onChange={set('interview_date')} data-testid={t('date')} required /></F>
            <F label="Interview time (IST) *"><input type="time" className={inputCls} value={f.interview_time} onChange={set('interview_time')} data-testid={t('time')} required /></F>
            <F label="Company name *"><input className={inputCls} value={f.company_name} onChange={set('company_name')} data-testid={t('company')} required /></F>
            <F label="Chennai office address *"><input className={inputCls} value={f.office_address} onChange={set('office_address')} data-testid={t('address')} required /></F>
        </>
    );
};
