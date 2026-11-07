import { useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';

export const ApproveDialog = ({ candidate, onClose, onDone }) => {
    const [consent, setConsent] = useState(false);
    const [last4, setLast4] = useState('');
    const [busy, setBusy] = useState(false);

    const approve = async () => {
        setBusy(true);
        try {
            await aiApi.post(`/test-candidates/${candidate.id}/approve`, { consent_confirmed: consent, phone_last4: last4 });
            toast.success('Recipient approved for test calls');
            onDone();
        } catch (e) { toast.error(errMsg(e, 'Approval failed')); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open={!!candidate} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="approve-dialog" className="bg-[#fffdf7]">
                <DialogHeader>
                    <DialogTitle>Approve test recipient</DialogTitle>
                    <DialogDescription>{candidate?.candidate_name} · {candidate?.phone_masked}</DialogDescription>
                </DialogHeader>
                <label className="flex items-start gap-2 text-sm text-[#1a2332] cursor-pointer">
                    <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} data-testid="approve-consent-checkbox" className="mt-1 accent-teal-700" />
                    I confirm this person agreed to receive AI test calls on this number.
                </label>
                <label className="block text-sm text-[#1a2332]">
                    Type the last 4 digits of the phone number to confirm
                    <input value={last4} onChange={e => setLast4(e.target.value.replace(/\D/g, '').slice(0, 4))} inputMode="numeric" data-testid="approve-last4-input"
                        className="mt-1 w-32 bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm tracking-widest focus:outline-none focus:border-teal-500" />
                </label>
                <DialogFooter>
                    <button onClick={onClose} data-testid="approve-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                    <button onClick={approve} disabled={busy || !consent || last4.length !== 4} data-testid="approve-confirm-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Approve</button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
