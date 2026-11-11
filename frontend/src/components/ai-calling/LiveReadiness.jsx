import { CheckCircle, XCircle, ShieldCheck } from '@phosphor-icons/react';
import { Card, SectionTitle } from './AICallingHeader';

const Stat = ({ label, value, testid }) => (
    <div className="bg-[#faf9f1] border border-[#e5e3d8] rounded-xl px-3 py-2"><p className="text-[11px] uppercase tracking-wider text-[#9b9787]">{label}</p><p className="text-sm font-bold text-[#1a2332]" data-testid={testid}>{value}</p></div>
);

// Read-only readiness checklist for the future Live Dispatch Authorization + monitoring counters.
export const LiveReadiness = ({ readiness, monitoring }) => (
    <Card>
        <SectionTitle icon={ShieldCheck}>Live Dispatch Authorization — readiness (cannot be activated in this phase)</SectionTitle>
        <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5 mb-4" data-testid="live-readiness-list">
            {readiness.checks.map(c => (
                <li key={c.key} className="flex items-center gap-2 text-sm" data-testid={`readiness-${c.key}`}>
                    {c.ok ? <CheckCircle size={16} weight="fill" className="text-emerald-600" /> : <XCircle size={16} weight="fill" className="text-rose-600" />}
                    <span className={c.ok ? 'text-[#1a2332]' : 'text-[#6b7280]'}>{c.label}</span>
                </li>
            ))}
        </ul>
        <p className="text-xs text-[#6b7280] mb-4" data-testid="live-authorization-state">
            Authorization: <b>{readiness.authorized ? 'ON' : 'OFF'}</b>. Activation will need a top-level admin to type “{readiness.phrase}” once every item above is green.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="live-monitoring">
            <Stat label="Daily cap (pilot)" value={`${monitoring.limits.daily_cap}/day`} testid="mon-daily-cap" />
            <Stat label="Concurrent" value={monitoring.limits.concurrent} testid="mon-concurrent" />
            <Stat label="No-answer retries" value={monitoring.limits.no_answer_retries} testid="mon-retries" />
            <Stat label="Mock used today" value={monitoring.limits.mock_used_today} testid="mon-mock-used" />
            <Stat label="Provider failures" value={monitoring.provider_failures} testid="mon-failures" />
            <Stat label="Webhook events (unmatched)" value={`${monitoring.webhook_events} (${monitoring.webhook_unmatched})`} testid="mon-webhooks" />
            <Stat label="Pending reconciliation" value={monitoring.pending_reconciliation} testid="mon-pending" />
            <Stat label="Needs review" value={monitoring.needs_review} testid="mon-review" />
        </div>
        <p className="text-[11px] text-[#9b9787] mt-2">Provider balance: {monitoring.provider_balance}</p>
    </Card>
);
