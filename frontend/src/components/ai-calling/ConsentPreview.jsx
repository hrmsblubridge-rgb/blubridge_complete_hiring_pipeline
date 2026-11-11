import { useEffect, useState } from 'react';
import { Eye } from '@phosphor-icons/react';
import { aiApi } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const inputCls = 'w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm';

// Review-only mock. Nothing here is submitted or saved; the real booking form is untouched.
export const ConsentPreview = () => {
    const [p, setP] = useState(null);
    const [checked, setChecked] = useState(false);
    const [booked, setBooked] = useState(null);
    useEffect(() => { aiApi.get('/consent/preview').then(r => setP(r.data)).catch(() => {}); }, []);

    return (
        <Card data-testid="consent-preview">
            <SectionTitle icon={Eye}>Candidate consent preview (proposal, not live)</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-4">A mock of the proposed optional checkbox on the interview-booking page. Clicking here saves nothing and changes no candidate.</p>
            <div className="max-w-lg bg-white border border-[#e5e3d8] rounded-2xl p-5 space-y-3">
                <p className="text-sm font-bold text-[#1a2332]">Book your interview slot</p>
                <input disabled value="Sample Candidate" className={inputCls} readOnly />
                <div className="grid grid-cols-2 gap-2"><input disabled value="15 Jul 2026" className={inputCls} readOnly /><input disabled value="11:00 AM" className={inputCls} readOnly /></div>
                <label className="flex items-start gap-2 text-sm text-[#1a2332]">
                    <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} data-testid="consent-preview-checkbox" className="mt-1 accent-teal-700" />
                    <span className="whitespace-pre-line"><b className="block mb-1">{p?.title}</b>{p?.text || '…'}</span>
                </label>
                <button onClick={() => setBooked(checked)} data-testid="consent-preview-book-btn" className="w-full py-2.5 rounded-lg bg-teal-700 text-white text-sm font-semibold">Confirm booking</button>
                {booked !== null && (
                    <p className="text-xs bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2" data-testid="consent-preview-result">
                        Preview only — booking would succeed either way. AI call consent would be stored as <b>{booked ? 'granted' : 'not given'}</b> (version {p?.version}). Nothing was saved.
                    </p>
                )}
            </div>
            {p && <p className="text-[11px] text-[#9b9787] mt-3">Proposed storage: {p.storage.collection}, keyed by {p.storage.key}; fields: {p.storage.fields.join(', ')}.</p>}
        </Card>
    );
};
