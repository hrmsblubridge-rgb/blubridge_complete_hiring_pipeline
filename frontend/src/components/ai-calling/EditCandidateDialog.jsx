import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';
import { CandidateFields, EMPTY_CANDIDATE } from './CandidateFields';

export const EditCandidateDialog = ({ candidate, onClose, onDone }) => {
    const [f, setF] = useState(EMPTY_CANDIDATE);
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        if (candidate) setF({ ...EMPTY_CANDIDATE, ...candidate, phone_number: candidate.phone_e164 });
    }, [candidate]);

    const save = async () => {
        setBusy(true);
        try {
            const r = await aiApi.put(`/test-candidates/${candidate.id}`, f);
            toast.success(candidate.approved && !r.data.approved ? 'Saved. Approval was invalidated because the recipient changed.' : 'Test candidate updated');
            onDone();
        } catch (e) { toast.error(errMsg(e, 'Save failed')); } finally { setBusy(false); }
    };

    return (
        <Dialog open={!!candidate} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="edit-dialog" className="bg-[#fffdf7] max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Edit test candidate</DialogTitle>
                    <DialogDescription>{candidate?.test_candidate_id} · Changing the phone number or name revokes approval.</DialogDescription>
                </DialogHeader>
                <div className="grid sm:grid-cols-2 gap-3"><CandidateFields f={f} setF={setF} prefix="edit" /></div>
                <DialogFooter>
                    <button onClick={onClose} data-testid="edit-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                    <button onClick={save} disabled={busy} data-testid="edit-save-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Save changes</button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
