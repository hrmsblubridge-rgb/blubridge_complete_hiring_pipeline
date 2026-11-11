import { useState } from 'react';

// Confirmation dialog for marking / removing AI Calling Do Not Call. The reason is stored in the audit log.
export const DncDialog = ({ action, onCancel, onConfirm, busy }) => {
    const [reason, setReason] = useState('');
    const removing = action === 'remove';
    return (
        <div className="fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-4" data-testid="dnc-dialog">
            <div className="bg-zinc-900 border border-zinc-700 max-w-sm w-full p-5 space-y-3">
                <p className="text-sm font-semibold text-white">{removing ? 'Remove admin Do Not Call?' : 'Mark AI Calling Do Not Call?'}</p>
                <p className="text-xs text-zinc-400">
                    {removing
                        ? 'Only the admin-imposed restriction is removed. Candidate requests and withdrawn or missing consent still block every AI call. No call is placed.'
                        : 'All future AI calls to this candidate are blocked at once and pending AI call jobs are cancelled. The interview, WhatsApp and email are not changed.'}
                </p>
                <textarea value={reason} onChange={e => setReason(e.target.value)} maxLength={300} rows={2} data-testid="dnc-reason-input"
                    placeholder={removing ? 'Reason (required)' : 'Reason (optional)'}
                    className="w-full bg-zinc-950 border border-zinc-700 text-sm text-white p-2 focus:outline-none focus:border-cyan-600" />
                <div className="flex justify-end gap-2">
                    <button onClick={onCancel} data-testid="dnc-cancel-btn" className="text-xs px-3 py-1.5 text-zinc-400 hover:text-white">Cancel</button>
                    <button disabled={busy || (removing && !reason.trim())} onClick={() => onConfirm(reason)} data-testid="dnc-confirm-btn"
                        className={`text-xs px-3 py-1.5 border disabled:opacity-40 ${removing ? 'border-emerald-800 text-emerald-400 bg-emerald-900/30' : 'border-red-800 text-red-400 bg-red-900/30'}`}>
                        {busy ? 'Saving…' : removing ? 'Remove Do Not Call' : 'Mark Do Not Call'}
                    </button>
                </div>
            </div>
        </div>
    );
};
