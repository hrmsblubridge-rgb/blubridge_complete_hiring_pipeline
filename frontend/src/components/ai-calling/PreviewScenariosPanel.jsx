// Synthetic Preview & Diagnostics. Shows both calling purposes side-by-side.
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Eye } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

const Table = ({ rows, testid }) => (
    <div className="overflow-x-auto" data-testid={testid}>
        <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-[#9b9787]">
                <tr>{['Scenario', 'Due', 'OTP', 'Eligibility', 'Block reason', 'Retry', 'Outcome'].map(h => <th key={h} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody>
                {rows.map((r, i) => (
                    <tr key={i} className="border-t border-[#efede5]" data-testid={`${testid}-row-${i}`}>
                        <td className="px-2 py-1.5 font-semibold">{r.scenario}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap">{r.due_time_ist}</td>
                        <td className="px-2 py-1.5">{r.otp_interpretation || '—'}</td>
                        <td className="px-2 py-1.5"><span className={r.eligibility === 'ELIGIBLE' ? 'text-emerald-700 font-semibold' : r.eligibility === 'BLOCKED' ? 'text-rose-700 font-semibold' : 'text-amber-700 font-semibold'}>{r.eligibility}</span></td>
                        <td className="px-2 py-1.5 text-[#6b7280]">{r.blocking_reason || '—'}</td>
                        <td className="px-2 py-1.5 text-[#6b7280]">{r.retry_timeline}</td>
                        <td className="px-2 py-1.5">{r.simulated_outcome}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

export const PreviewScenariosPanel = () => {
    const [d, setD] = useState(null);
    useEffect(() => { aiApi.get('/preview/scenarios').then(r => setD(r.data)).catch(e => toast.error(errMsg(e))); }, []);
    if (!d) return null;
    return (
        <Card data-testid="preview-scenarios-panel">
            <SectionTitle icon={Eye}>Synthetic Preview & Diagnostics — both purposes</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-3">Synthetic bookings only. No real candidate data is read; no Bolna outbound request is made.</p>
            <div className="space-y-5">
                <div>
                    <p className="text-[11px] font-semibold tracking-wider text-teal-800 uppercase mb-1">Pre-Interview Confirmation</p>
                    <Table rows={d.interview_confirmation} testid="preview-confirm-table" />
                </div>
                <div>
                    <p className="text-[11px] font-semibold tracking-wider text-rose-800 uppercase mb-1">Missed-Interview Follow-up (OTP-based)</p>
                    <Table rows={d.missed_interview_followup} testid="preview-missed-table" />
                </div>
            </div>
        </Card>
    );
};
