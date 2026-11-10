import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Warning, PhoneOutgoing } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { inputCls } from './constants';

const newKey = () => (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}-key`);

const Row = ({ k, v, testid }) => (
    <div className="flex justify-between gap-4 text-sm py-1 border-b border-[#efede5] last:border-0">
        <span className="text-[#6b7280]">{k}</span><span className="font-semibold text-[#1a2332] text-right" data-testid={testid}>{v || '—'}</span>
    </div>
);

export const CallNowDialog = ({ candidate, onClose, onDone }) => {
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const key = useMemo(() => (candidate ? newKey() : ''), [candidate]);
    const match = !!candidate && name.trim() === candidate.candidate_name.trim();

    const submit = async () => {
        if (!match || busy) return;
        setBusy(true);
        try {
            const r = (await aiApi.post(`/test-candidates/${candidate.id}/call-now`, { idempotency_key: key, confirm_name: name.trim() })).data;
            if (r.duplicate) toast.info('This call was already sent — no second call placed.');
            else if (r.state === 'accepted') toast.success('Bolna accepted the call. Follow it in Call History.');
            else if (r.state === 'rejected') toast.error(`Bolna rejected the call: ${r.error}`);
            else toast.warning('Bolna response unclear — calling is locked while we check the status automatically.');
            onDone(r);
        } catch (e) { toast.error(errMsg(e, 'Call not placed')); setBusy(false); }
    };

    return (
        <Dialog open={!!candidate} onOpenChange={(o) => !o && !busy && onClose()}>
            <DialogContent data-testid="call-now-dialog" className="bg-[#fffdf7] max-w-lg">
                <DialogHeader>
                    <DialogTitle>Place one real test call</DialogTitle>
                    <DialogDescription>Only this recipient will be called, once. No automatic redial.</DialogDescription>
                </DialogHeader>
                {candidate && (
                    <div className="space-y-4">
                        <div className="flex gap-2 text-sm text-rose-800 bg-rose-50 border border-rose-200 rounded-xl px-3 py-2" data-testid="call-now-warning">
                            <Warning size={18} weight="fill" className="shrink-0 mt-0.5" />
                            This places a real, chargeable phone call through Bolna AI to the number below.
                        </div>
                        <div className="bg-white border border-[#e5e3d8] rounded-xl px-3 py-2">
                            <Row k="Candidate" v={candidate.candidate_name} testid="call-now-name" />
                            <Row k="Mobile" v={candidate.phone_masked} testid="call-now-phone" />
                            <Row k="Job role" v={candidate.job_role} />
                            <Row k="Interview (IST)" v={`${candidate.interview_date} ${candidate.interview_time}`} />
                            <Row k="Language" v={candidate.language} />
                            <Row k="Company" v={candidate.company_name} />
                        </div>
                        <label className="block text-xs text-[#6b7280]">Type <b className="text-[#1a2332]">{candidate.candidate_name}</b> to authorise this call
                            <input value={name} onChange={e => setName(e.target.value)} className={`${inputCls} mt-1`} data-testid="call-now-confirm-input" autoComplete="off" />
                        </label>
                        <div className="flex justify-end gap-2">
                            <button onClick={onClose} disabled={busy} data-testid="call-now-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                            <button onClick={submit} disabled={!match || busy} data-testid="call-now-confirm-btn"
                                className="px-4 py-2 rounded-lg bg-rose-700 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-rose-800">
                                <PhoneOutgoing size={16} /> {busy ? 'Calling…' : 'Call now'}
                            </button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
};
