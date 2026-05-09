/**
 * WhatsApp Diagnostics (iter74)
 * --------------------------------------------
 * One-click probe that fires all 5 AiSensy campaigns with realistic params
 * and renders a side-by-side report (campaign / param count / HTTP /
 * AiSensy success flag / submitted_message_id / error). Use this report
 * as evidence to share with the AiSensy account holder if any campaign's
 * delivery is silently dropping at the Meta layer.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, WhatsappLogo, PaperPlaneTilt, CheckCircle, XCircle,
    Info, Copy, ClockCountdown, ShieldWarning,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function WhatsAppDiagnostics() {
    const navigate = useNavigate();
    const [running, setRunning] = useState(false);
    const [report, setReport] = useState(null);

    const runProbe = async () => {
        setRunning(true);
        setReport(null);
        try {
            const r = await axios.post(`${API}/api/bb/resend/diagnostics/whatsapp-probe`,
                {}, { withCredentials: true, timeout: 60000 });
            setReport(r.data);
            const passed = r.data?.passed || 0;
            const total = r.data?.campaigns_tested || 0;
            toast.success(`Probe complete · ${passed}/${total} campaigns submitted to AiSensy`);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Probe failed');
        } finally { setRunning(false); }
    };

    const copyReport = () => {
        if (!report) return;
        navigator.clipboard.writeText(JSON.stringify(report, null, 2));
        toast.success('Full diagnostic JSON copied to clipboard');
    };

    const copyCoworkerBrief = () => {
        if (!report) return;
        const failing = ['Schedule Detail', 'Candidate Followups1', 'Reject'];
        const ids = report.results
            .filter(r => failing.includes(r.campaign))
            .map(r => `  • ${r.campaign}: ${r.submitted_message_id || '—'}`)
            .join('\n');
        const brief = `Hi,

Our backend is successfully submitting all 5 WhatsApp campaigns to AiSensy (HTTP 200, success="true", valid submitted_message_id). However, only ShortList and OTP With Job actually deliver to the recipient's phone. These 3 are silently dropped at the Meta layer:

  • Schedule Detail
  • Candidate Followups1
  • Reject

Latest submitted_message_ids (search these in AiSensy delivery logs):
${ids}

Please check on the AiSensy dashboard for each of the 3 above:

1. Manage Campaigns / Templates → what is the Meta status? (APPROVED / PENDING / REJECTED / PAUSED / FLAGGED). Anything other than APPROVED silently drops messages.

2. Live Reports / Delivery Logs → search for the submitted_message_ids above. What is the per-message delivery state (delivered / failed / pending / dropped) and any error reason?

3. Free-tier Allowlisted Numbers → is the test phone ${report.target_phone ? '+91 ' + report.target_phone : '+91 9443109903'} on the allowlist for these 3 specific campaigns?

4. Template category → is each marked MARKETING, UTILITY, or AUTHENTICATION? MARKETING templates require an open 24-hour conversation window per recipient. The 2 working ones (ShortList, OTP With Job) are likely UTILITY/AUTHENTICATION — that's why they always go through.

5. Template variables on Meta side → does the template body actually have the same number of {{1}}…{{N}} placeholders we're sending? AiSensy accepts the call even when Meta's template definition mismatches.

Most likely fix: re-submit those 3 templates to Meta for approval as UTILITY (transactional) so they bypass the 24h window.

Thanks!`;
        navigator.clipboard.writeText(brief);
        toast.success('Coworker brief copied — paste it into a message to your AiSensy admin');
    };

    return (
        <div className="min-h-screen" data-testid="whatsapp-diagnostics-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4">
                    <div className="flex items-center gap-3 pl-12 lg:pl-0">
                        <button onClick={() => navigate('/home')} data-testid="back-btn"
                            className="p-2 rounded-lg hover:bg-[#efede5]">
                            <ArrowLeft size={18} className="text-[#1a2332]" />
                        </button>
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                            style={{ backgroundColor: '#25D36620' }}>
                            <WhatsappLogo size={22} weight="fill" color="#128C7E" />
                        </div>
                        <div>
                            <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">
                                WhatsApp Diagnostics
                            </h1>
                            <p className="text-xs text-[#6b7280] mt-0.5">
                                One-click probe across all 5 AiSensy campaigns · TEST MODE only
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {report && (
                            <>
                                <button onClick={copyCoworkerBrief} data-testid="copy-brief-btn"
                                    className="px-3 py-2 rounded-lg text-white text-sm font-semibold flex items-center gap-1.5"
                                    style={{ backgroundColor: '#1d3a8a' }}>
                                    <Copy size={14} weight="bold" /> Copy Coworker Brief
                                </button>
                                <button onClick={copyReport} data-testid="copy-report-btn"
                                    className="px-3 py-2 rounded-lg border border-[#e5e3d8] text-sm font-semibold text-[#1a2332] hover:bg-[#efede5] flex items-center gap-1.5">
                                    <Copy size={14} weight="bold" /> Copy JSON
                                </button>
                            </>
                        )}
                        <button onClick={runProbe} disabled={running} data-testid="run-probe-btn"
                            className="px-4 py-2 rounded-lg text-white text-sm font-semibold flex items-center gap-1.5 disabled:opacity-60"
                            style={{ backgroundColor: '#128C7E' }}>
                            {running ? <ClockCountdown size={14} className="animate-spin" /> : <PaperPlaneTilt size={14} weight="bold" />}
                            {running ? 'Running…' : 'Run Probe'}
                        </button>
                    </div>
                </div>
            </header>

            <main className="px-6 lg:px-10 py-8 max-w-7xl mx-auto space-y-6">
                <InfoCard />

                {report && (
                    <>
                        <Summary report={report} />
                        <div className="space-y-3">
                            {report.results.map((r, idx) => (
                                <CampaignResult key={idx} result={r} />
                            ))}
                        </div>
                        <Interpretation report={report} />
                    </>
                )}

                {!report && !running && (
                    <div className="bg-[#fffdf7] border border-dashed border-[#e5e3d8] rounded-2xl p-12 text-center">
                        <WhatsappLogo size={42} weight="duotone" className="mx-auto text-[#128C7E]" />
                        <p className="mt-4 text-sm text-[#6b7280]">
                            Click <span className="font-semibold text-[#1a2332]">Run Probe</span> to fire all 5 AiSensy campaigns
                            and capture the exact response per campaign.
                        </p>
                    </div>
                )}
            </main>
        </div>
    );
}

function InfoCard() {
    return (
        <div className="bg-blue-50 border border-blue-200 rounded-2xl p-5" data-testid="diagnostics-info-card">
            <div className="flex items-start gap-3">
                <Info size={20} weight="fill" className="text-blue-700 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-blue-900 leading-relaxed">
                    <p className="font-semibold mb-1">What this probe verifies</p>
                    <p>Fires <span className="font-mono text-xs bg-blue-100 px-1 rounded">ShortList</span>, <span className="font-mono text-xs bg-blue-100 px-1 rounded">Schedule Detail</span>, <span className="font-mono text-xs bg-blue-100 px-1 rounded">OTP With Job</span>, <span className="font-mono text-xs bg-blue-100 px-1 rounded">Candidate Followups1</span>, and <span className="font-mono text-xs bg-blue-100 px-1 rounded">Reject</span> to your test phone (<span className="font-mono">+91 9443109903</span>) and captures AiSensy's exact response per campaign.</p>
                    <p className="mt-2"><span className="font-semibold">If a campaign returns <code>success="true"</code> + <code>submitted_message_id</code> but the message doesn't reach the phone</span> → the issue is on the <span className="font-semibold">AiSensy / Meta dashboard side</span> (template approval, recipient allowlist, 24h conversation window). Share this report with your AiSensy admin to escalate.</p>
                </div>
            </div>
        </div>
    );
}

function Summary({ report }) {
    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Campaigns Tested" value={report.campaigns_tested} tone="zinc" />
            <Stat label="Passed (AiSensy 200)" value={report.passed} tone="emerald" />
            <Stat label="Failed at AiSensy" value={report.failed} tone="rose" />
            <Stat label="Target Phone" value={report.target_phone} tone="cyan" mono />
        </div>
    );
}

function Stat({ label, value, tone, mono }) {
    const TONES = {
        zinc: 'text-[#1a2332] bg-[#fffdf7] border-[#e5e3d8]',
        emerald: 'text-emerald-800 bg-emerald-50 border-emerald-200',
        rose: 'text-rose-800 bg-rose-50 border-rose-200',
        cyan: 'text-cyan-900 bg-cyan-50 border-cyan-200',
    };
    return (
        <div className={`border rounded-xl p-4 ${TONES[tone] || TONES.zinc}`}>
            <p className="text-[10px] font-semibold tracking-[0.16em] uppercase opacity-70">{label}</p>
            <p className={`mt-1 text-2xl font-bold ${mono ? 'font-mono text-base' : ''}`}>{value}</p>
        </div>
    );
}

function CampaignResult({ result }) {
    const ok = result.ok;
    return (
        <div data-testid={`probe-row-${result.campaign.replace(/\s/g, '-').toLowerCase()}`}
            className={`bg-[#fffdf7] border-2 rounded-2xl p-5 ${ok ? 'border-emerald-200' : 'border-rose-300'}`}>
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-3">
                    {ok ? <CheckCircle size={22} weight="fill" className="text-emerald-600" />
                        : <XCircle size={22} weight="fill" className="text-rose-600" />}
                    <h3 className="font-bold text-[#1a2332] text-lg font-mono">{result.campaign}</h3>
                    <span className="px-2 py-0.5 text-[11px] font-semibold rounded-md bg-[#efede5] text-[#374151]">
                        {result.param_count} param{result.param_count !== 1 ? 's' : ''}
                    </span>
                    <span className={`px-2 py-0.5 text-[11px] font-semibold rounded-md ${result.status_code === 200 ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                        HTTP {result.status_code || '—'}
                    </span>
                </div>
                {result.submitted_message_id && (
                    <code className="text-[11px] text-[#6b7280] font-mono">
                        msg_id: {result.submitted_message_id}
                    </code>
                )}
            </div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div>
                    <p className="text-[10px] font-semibold tracking-[0.14em] uppercase text-[#6b7280] mb-1">templateParams sent</p>
                    <pre className="bg-[#1a2332] text-cyan-200 p-3 rounded-lg text-[11px] overflow-x-auto whitespace-pre-wrap break-all">
{JSON.stringify(result.params, null, 2)}
                    </pre>
                </div>
                <div>
                    <p className="text-[10px] font-semibold tracking-[0.14em] uppercase text-[#6b7280] mb-1">AiSensy response body</p>
                    <pre className="bg-[#1a2332] text-emerald-200 p-3 rounded-lg text-[11px] overflow-x-auto whitespace-pre-wrap break-all">
{result.response_body || '—'}
                    </pre>
                </div>
            </div>
            {result.error_message && (
                <div className="mt-3 p-3 bg-rose-50 border border-rose-200 rounded-lg">
                    <p className="text-xs font-semibold text-rose-800">Error: <span className="font-mono">{result.error_message}</span></p>
                </div>
            )}
        </div>
    );
}

function Interpretation({ report }) {
    const allOk = report.passed === report.campaigns_tested;
    return (
        <div className={`rounded-2xl p-5 border-2 ${allOk ? 'bg-emerald-50 border-emerald-300' : 'bg-amber-50 border-amber-300'}`}>
            <div className="flex items-start gap-3">
                <ShieldWarning size={22} weight="fill" className={allOk ? 'text-emerald-700' : 'text-amber-700'} />
                <div className="text-sm leading-relaxed text-[#1a2332]">
                    {allOk ? (
                        <>
                            <p className="font-semibold mb-2">All 5 campaigns submitted successfully to AiSensy.</p>
                            <p>If any specific WhatsApp message is <span className="font-semibold">not arriving on the recipient's phone</span>, the bottleneck is at the AiSensy/Meta dashboard layer. Action items for your AiSensy admin:</p>
                            <ol className="list-decimal pl-6 mt-2 space-y-1.5">
                                <li>Open <span className="font-mono">AiSensy → Manage Campaigns</span> and confirm the template's Meta status is <span className="font-mono text-emerald-800">APPROVED</span> (not <span className="font-mono">PENDING</span>, <span className="font-mono">REJECTED</span>, <span className="font-mono">PAUSED</span>, or <span className="font-mono">FLAGGED</span>).</li>
                                <li>Search the delivery logs for the <span className="font-mono text-xs">submitted_message_id</span> values above and note the per-message delivery state (<span className="font-mono">delivered</span> / <span className="font-mono">failed</span> / <span className="font-mono">pending</span>).</li>
                                <li>Confirm the test phone <span className="font-mono">+91 {report.target_phone}</span> is on the Free-Tier "Approved Numbers" allowlist for each campaign.</li>
                                <li>Check the template category — <span className="font-mono">MARKETING</span> templates require an open 24h conversation window with the recipient; <span className="font-mono">UTILITY</span>/<span className="font-mono">AUTHENTICATION</span> templates do not.</li>
                            </ol>
                            <p className="mt-3 text-xs text-[#6b7280]">Click <span className="font-semibold">Copy JSON</span> at the top to share this full report with your AiSensy admin.</p>
                        </>
                    ) : (
                        <p className="font-semibold">Some campaigns failed at AiSensy. See the response body of each failed entry above for the exact error message.</p>
                    )}
                </div>
            </div>
        </div>
    );
}
