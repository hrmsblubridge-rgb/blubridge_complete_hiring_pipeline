// Capacity transparency panel. Shows WHY the lower cap controls throughput — never silently disables anything.
import { useEffect, useState } from 'react';
import { ChartBar, Spinner } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { toast } from 'sonner';
import { Card, SectionTitle } from './AICallingHeader';

const Row = ({ label, value, emphasize, testid }) => (
    <li className="flex justify-between text-sm py-1" data-testid={testid}>
        <span className="text-[#6b7280]">{label}</span>
        <span className={emphasize ? 'text-teal-800 font-bold' : 'text-[#1a2332] font-semibold'}>{value}</span>
    </li>
);

export const CapacitySummaryPanel = () => {
    const [d, setD] = useState(null);
    useEffect(() => { aiApi.get('/capacity-summary').then(r => setD(r.data)).catch(e => toast.error(errMsg(e))); }, []);
    if (!d) return <Card><SectionTitle icon={ChartBar}>Capacity</SectionTitle><p className="text-sm text-[#6b7280] flex items-center gap-2"><Spinner size={14} className="animate-spin" /> Loading…</p></Card>;
    return (
        <Card data-testid="capacity-summary-panel">
            <SectionTitle icon={ChartBar}>Capacity & effective throughput</SectionTitle>
            <div className="grid sm:grid-cols-2 gap-4">
                <div>
                    <p className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase mb-1">Test calling</p>
                    <ul className="divide-y divide-[#efede5]">
                        <Row label="Daily limit" value={d.test.daily_limit} testid="cap-test-daily" />
                        <Row label="Max concurrent" value={d.test.max_concurrent} testid="cap-test-concurrent" />
                    </ul>
                </div>
                <div>
                    <p className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase mb-1">Live calling</p>
                    <ul className="divide-y divide-[#efede5]">
                        <Row label="Configured daily maximum" value={d.live.configured_daily_maximum} testid="cap-live-configured" />
                        <Row label="Pilot cap" value={d.live.pilot_daily_cap} testid="cap-live-pilot" />
                        <Row label="Effective daily maximum" value={d.live.effective_daily_maximum} emphasize testid="cap-live-effective" />
                        <Row label="Max concurrent" value={d.live.max_concurrent} testid="cap-live-concurrent" />
                        <Row label="Queue capacity" value={d.live.queue_capacity} testid="cap-live-queue" />
                    </ul>
                </div>
            </div>
            <p className="text-[11px] text-[#9b9787] mt-3" data-testid="cap-explanation">{d.live.explanation}</p>
        </Card>
    );
};
