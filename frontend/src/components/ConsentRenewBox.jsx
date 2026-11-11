import { useState } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/ai-calling/public/consent/renew/booking`;

// Booking link + last 4 digits of the registered mobile → a NEW private consent link. Changes no consent, sends nothing.
export const ConsentRenewBox = ({ token }) => {
    const [open, setOpen] = useState(false);
    const [digits, setDigits] = useState('');
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState('');
    const [link, setLink] = useState('');
    const submit = async () => {
        setBusy(true); setErr('');
        try { setLink((await axios.post(API, { schedule_token: token, phone_last4: digits })).data.manage_token); }
        catch (e) { setErr(e.response?.data?.detail || 'We could not verify these details. Please check and try again.'); }
        finally { setBusy(false); }
    };
    if (!open) {
        return <button type="button" onClick={() => setOpen(true)} data-testid="ai-consent-renew-open" className="text-xs text-[#2563eb] underline">Need a new AI calling consent link?</button>;
    }
    return (
        <div className="text-xs text-gray-700 bg-[#f8fafc] border border-gray-200 rounded p-3 space-y-2" data-testid="ai-consent-renew-box">
            {link ? (
                <p data-testid="ai-consent-renew-success">
                    Your new private link (valid 30 days, older links stop working):{' '}
                    <a href={`/ai-consent#t=${link}`} target="_blank" rel="noreferrer noopener" className="text-[#2563eb] underline" data-testid="ai-consent-renew-link">Manage AI calling consent</a>
                </p>
            ) : (
                <>
                    <p>Enter the last 4 digits of the mobile number you registered with. Nothing about your interview or your AI call preference changes.</p>
                    <div className="flex gap-2">
                        <input value={digits} onChange={e => setDigits(e.target.value.replace(/\D/g, '').slice(0, 4))} inputMode="numeric" maxLength={4}
                            placeholder="1234" data-testid="ai-consent-renew-digits" className="w-24 border border-gray-300 rounded px-2 py-1.5 text-sm tracking-widest" />
                        <button type="button" disabled={digits.length !== 4 || busy} onClick={submit} data-testid="ai-consent-renew-submit"
                            className="px-3 py-1.5 rounded bg-[#1a2332] text-white font-semibold disabled:opacity-40">{busy ? 'Checking…' : 'Get my link'}</button>
                    </div>
                    {err && <p className="text-red-600" data-testid="ai-consent-renew-error">{err}</p>}
                </>
            )}
        </div>
    );
};
