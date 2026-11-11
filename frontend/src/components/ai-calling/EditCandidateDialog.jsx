import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';
import { CandidateFields, EMPTY_CANDIDATE } from './CandidateFields';

export const EditCandidateDialog = ({ candidate, onClose, onDone }) => {
    const [f, setF] = useState(EMPTY_CANDIDATE);
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        if (candidate) setF({ ...EMPTY_CANDIDATE, ...candidate, phone_number: candidate.phone_e164, consent_for_test_call: false });
    }, [candidate]);

    const save = async () => {
        setBusy(true);
        try {
            const r = await aiApi.put(`/test-candidates/${candidate.id}`, f);
            toast.success(candidate.consent_status === 'granted' && r.data.consent_status !== 'granted' ? 'Saved. Consent was reset because the phone number changed.' : 'Test candidate updated');
            onDone();
        } catch (e) { toast.error(errMsg(e, 'Save failed')); } finally { setBusy(false); }
    };

    return (
        <Dialog open={!!candidate} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="edit-dialog" className="bg-[#fffdf7] max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Edit test candidate</DialogTitle>
                    <DialogDescription>{candidate?.test_candidate_id} · Changing the phone number needs fresh consent for the new number.</DialogDescription>
                </DialogHeader>
                <div className="grid sm:grid-cols-2 gap-3"><CandidateFields f={f} setF={setF} prefix="edit" /></div>
                {f.phone_number !== candidate?.phone_e164 && (
                    <label className="flex items-start gap-2 text-sm bg-amber-50 border border-amber-200 rounded-lg px-3 py-2" data-testid="edit-consent-row">
                        <input type="checkbox" checked={!!f.consent_for_test_call} onChange={e => setF(p => ({ ...p, consent_for_test_call: e.target.checked }))} data-testid="edit-consent-checkbox" className="mt-0.5 accent-teal-700" />
                        The colleague agreed to receive AI test calls on the NEW number.
                    </label>
                )}
                <DialogFooter>
                    <button onClick={onClose} data-testid="edit-cancel-btn" className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                    <button onClick={save} disabled={busy} data-testid="edit-save-btn" className="px-4 py-2 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">Save changes</button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
