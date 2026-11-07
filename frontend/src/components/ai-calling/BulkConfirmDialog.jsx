import { useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';

// action: 'approve' | 'delete'
export const BulkConfirmDialog = ({ action, items, onClose, onDone }) => {
    const [consent, setConsent] = useState(false);
    const [word, setWord] = useState('');
    const [busy, setBusy] = useState(false);
    const WORD = action === 'approve' ? 'APPROVE' : 'DELETE';

    const run = async () => {
        setBusy(true);
        try {
            const ids = items.map(i => i.id);
            if (action === 'approve') {
                const r = (await aiApi.post('/test-candidates/bulk-approve', { ids, consent_confirmed: consent, confirmation: word })).data;
                toast.success(`Approved ${r.approved}. Skipped ${r.skipped.length}.`);
                r.skipped.forEach(s => toast.message(`${s.candidate_name}: ${s.reason}`));
            } else {
                const r = (await aiApi.post('/test-candidates/bulk-delete', { ids, confirmation: word })).data;
                toast.success(`Deleted ${r.deleted} test candidate(s)`);
            }
            onDone();
        } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };

    return (
        <Dialog open={!!action} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="bulk-dialog" className="bg-[#fffdf7]">
                <DialogHeader>
                    <DialogTitle>{action === 'approve' ? 'Bulk approve test recipients' : 'Delete test candidates'}</DialogTitle>
                    <DialogDescription>{items.length} selected</DialogDescription>
                </DialogHeader>
                <ul className="max-h-40 overflow-y-auto text-sm border border-[#e5e3d8] rounded-lg divide-y divide-[#efede5]" data-testid="bulk-dialog-list">
                    {items.map(i => <li key={i.id} className="px-3 py-1.5 flex justify-between"><span>{i.candidate_name}</span><span className="font-mono text-xs text-[#6b7280]">{i.phone_masked}</span></li>)}
                </ul>
                {action === 'approve' && (
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} data-testid="bulk-consent-checkbox" className="mt-1 accent-teal-700" />
                        I confirm every listed person agreed to receive AI test calls on the number shown.
                    </label>
                )}
                <label className="block text-sm">Type <b>{WORD}</b> to confirm
                    <input value={word} onChange={e => setWord(e.target.value.toUpperCase())} data-testid="bulk-confirm-input" className="mt-1 w-40 bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                </label>
                <DialogFooter>
                    <button onClick={onClose} data-testid="bulk-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                    <button onClick={run} disabled={busy || word !== WORD || (action === 'approve' && !consent)} data-testid="bulk-confirm-btn"
                        className={`px-4 py-2 rounded-lg text-white text-sm font-semibold disabled:opacity-50 ${action === 'approve' ? 'bg-teal-700' : 'bg-rose-700'}`}>Confirm</button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
