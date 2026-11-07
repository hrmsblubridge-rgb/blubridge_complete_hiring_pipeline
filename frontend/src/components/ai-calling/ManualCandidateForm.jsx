import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { UserPlus } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { CandidateFields, EMPTY_CANDIDATE } from './CandidateFields';

export const ManualCandidateForm = ({ settings, onSaved }) => {
    const defaults = { ...EMPTY_CANDIDATE, company_name: settings?.default_company_name || '', office_address: settings?.default_office_address || '' };
    const [f, setF] = useState(defaults);
    const [busy, setBusy] = useState(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { setF(p => ({ ...p, company_name: p.company_name || defaults.company_name, office_address: p.office_address || defaults.office_address })); }, [settings]);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = await aiApi.post('/test-candidates', f);
            toast.success(`Added ${r.data.candidate_name} (${r.data.phone_masked}). Approval still required.`);
            setF(defaults); onSaved();
        } catch (err) { toast.error(errMsg(err, 'Save failed')); }
        finally { setBusy(false); }
    };

    return (
        <Card data-testid="manual-entry-panel">
            <SectionTitle icon={UserPlus}>Add test candidate manually</SectionTitle>
            <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <CandidateFields f={f} setF={setF} prefix="manual" />
                <div className="sm:col-span-2 lg:col-span-4 flex justify-end">
                    <button type="submit" disabled={busy} data-testid="manual-submit-btn" className="px-5 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-60">{busy ? 'Saving…' : 'Add test candidate'}</button>
                </div>
            </form>
        </Card>
    );
};
