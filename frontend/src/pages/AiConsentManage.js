import { useEffect, useState } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/ai-calling/public/consent`;
const LABEL = { granted: 'You have agreed to AI voice calls', not_given: 'You have not agreed to AI voice calls', withdrawn: 'You have withdrawn consent for AI voice calls' };
const readToken = () => { try { return sessionStorage.getItem('ai_consent_token') || ''; } catch { return ''; } };
const btn = 'w-full py-2.5 rounded-lg text-sm font-semibold disabled:opacity-40';

const ExpiredNote = () => (
    <p className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded p-2" data-testid="ai-consent-expired">
        This link has expired. It can still be used to withdraw consent or stop AI calls, but not to give consent. New links cannot be sent yet — contact the HR team if you need one.
    </p>
);

const GrantForm = ({ info, busy, onGrant }) => {
    const [agree, setAgree] = useState(false);
    return (
        <div className="space-y-3">
            <label className="flex items-start gap-2 text-xs text-gray-700">
                <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} data-testid="ai-consent-page-checkbox" className="mt-0.5" />
                <span className="whitespace-pre-line"><b className="block mb-1">{info.title}</b>{info.text}</span>
            </label>
            <button disabled={!agree || busy} onClick={onGrant} data-testid="ai-consent-grant-btn" className={`${btn} bg-[#2563eb] text-white`}>Save my agreement</button>
        </div>
    );
};

export default function AiConsentManage() {
    const [token] = useState(readToken);
    const [info, setInfo] = useState(null);
    const [err, setErr] = useState('');
    const [busy, setBusy] = useState(false);
    const cfg = { headers: { 'X-Consent-Token': token } };
    const load = () => axios.get(`${API}/manage`, cfg).then(r => setInfo(r.data))
        .catch(e => {
            if (e.response?.status === 404) { try { sessionStorage.removeItem('ai_consent_token'); } catch { /* ignore */ } }
            setErr(e.response?.status === 429 ? 'Too many attempts. Please try again later.' : 'This link is invalid or has been replaced.');
        });
    useEffect(() => { if (token) load(); else setErr('This link is invalid or has been replaced.'); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const act = async (path, body = {}) => {
        setBusy(true); setErr('');
        try { await axios.post(`${API}/manage/${path}`, body, cfg); await load(); }
        catch (e) { setErr(e.response?.data?.detail || 'Your change could not be saved. Nothing was changed.'); }
        finally { setBusy(false); }
    };

    return (
        <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center p-4" data-testid="ai-consent-page">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 max-w-md w-full p-6 space-y-4">
                <h1 className="text-xl font-bold text-[#1a2332]">AI calling preference</h1>
                {err && <p className="text-sm text-red-600" data-testid="ai-consent-error">{err}</p>}
                {info && (
                    <>
                        <p className="text-sm text-gray-700">Hi {info.first_name}. <b data-testid="ai-consent-status">{LABEL[info.consent_status] || LABEL.not_given}</b>.</p>
                        {info.do_not_call && <p className="text-xs text-gray-700" data-testid="ai-consent-dnc">AI calls to you are stopped (Do Not Call).</p>}
                        <p className="text-xs text-gray-500">Changing this never cancels or moves your interview, and does not change WhatsApp or email.</p>
                        {info.expired && <ExpiredNote />}
                        {info.can_withdraw && (
                            <button disabled={busy} onClick={() => act('withdraw')} data-testid="ai-consent-withdraw-btn" className={`${btn} bg-[#1a2332] text-white`}>Withdraw my consent</button>
                        )}
                        {info.can_grant && !info.candidate_dnc && <GrantForm info={info} busy={busy} onGrant={() => act('grant', { text_version: info.version })} />}
                        {!info.candidate_dnc && (
                            <button disabled={busy} onClick={() => act('do-not-call')} data-testid="ai-consent-dnc-btn" className={`${btn} border border-gray-300 text-gray-700`}>Never call me with AI (Do Not Call)</button>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
