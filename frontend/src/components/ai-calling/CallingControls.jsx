import { toast } from 'sonner';
import { PhoneOutgoing, Stop, Info } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { CALLING_DISABLED_MSG } from './constants';

export const CallingControls = ({ selectedCount }) => {
    const stop = async () => {
        try { const r = (await aiApi.post('/calls/stop')).data; toast.success(`Stopped. Cancelled ${r.cancelled_jobs} pending job(s).`); }
        catch (e) { toast.error(errMsg(e)); }
    };
    return (
        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4 space-y-3" data-testid="calling-controls">
            <div className="flex items-start gap-2 text-sm text-[#1a2332] bg-teal-50 border border-teal-200 rounded-xl px-3 py-2" data-testid="calling-disabled-message">
                <Info size={18} weight="duotone" className="text-teal-700 shrink-0 mt-0.5" /> {CALLING_DISABLED_MSG}
            </div>
            <div className="flex flex-wrap gap-2">
                <button disabled title={CALLING_DISABLED_MSG} data-testid="call-selected-btn" className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold flex items-center gap-2 opacity-40 cursor-not-allowed">
                    <PhoneOutgoing size={16} /> Call Selected ({selectedCount})
                </button>
                <button onClick={stop} data-testid="stop-calls-btn" className="px-4 py-2 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold flex items-center gap-2 hover:bg-rose-100">
                    <Stop size={16} weight="fill" /> Stop Calls
                </button>
            </div>
        </div>
    );
};
