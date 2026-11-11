import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/ai-calling/public/consent`;
const LABEL = { granted: 'You have agreed to AI voice calls', not_given: 'You have not agreed to AI voice calls', withdrawn: 'You have withdrawn consent for AI voice calls' };

export default function AiConsentManage() {
    const { token } = useParams();
    const [info, setInfo] = useState(null);
    const [err, setErr] = useState('');
    const [agree, setAgree] = useState(false);
    const [busy, setBusy] = useState(false);
    const load = () => axios.get(`${API}/${token}`).then(r => setInfo(r.data)).catch(e => setErr(e.response?.status === 404 ? 'This link is invalid or has expired.' : 'Could not load your preference.'));
    useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

    const act = async (fn) => {
        setBusy(true); setErr('');
        try { await fn(); await load(); setAgree(false); } catch (e) { setErr(e.response?.data?.detail || 'Your change could not be saved. Nothing was changed.'); } finally { setBusy(false); }
    };

    return (
        <div className="min-h-screen bg-[#f3f1e9] flex items-center justify-center p-4" data-testid="ai-consent-page">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 max-w-md w-full p-6 space-y-4">
                <h1 className="text-xl font-bold text-[#1a2332]">AI calling preference</h1>
                {err && <p className="text-sm text-red-600" data-testid="ai-consent-error">{err}</p>}
                {info && (
                    <>
                        <p className="text-sm text-gray-700">Hi {info.first_name}. <b data-testid="ai-consent-status">{LABEL[info.consent_status] || LABEL.not_given}</b>.</p>
                        <p className="text-xs text-gray-500">Changing this never cancels or moves your interview.</p>
                        {info.consent_status === 'granted' ? (
                            <button disabled={busy} onClick={() => act(() => axios.post(`${API}/${token}/withdraw`))} data-testid="ai-consent-withdraw-btn"
                                className="w-full py-2.5 rounded-lg bg-[#1a2332] text-white text-sm font-semibold disabled:opacity-50">Withdraw my consent</button>
                        ) : info.has_booking && (
                            <div className="space-y-3">
                                <label className="flex items-start gap-2 text-xs text-gray-700">
                                    <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} data-testid="ai-consent-page-checkbox" className="mt-0.5" />
                                    <span>{info.text}</span>
                                </label>
                                <button disabled={!agree || busy} onClick={() => act(() => axios.post(`${API}/${token}`, { granted: true, text_version: info.version, source: 'consent_page' }))}
                                    data-testid="ai-consent-grant-btn" className="w-full py-2.5 rounded-lg bg-[#2563eb] text-white text-sm font-semibold disabled:opacity-40">Save my agreement</button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
