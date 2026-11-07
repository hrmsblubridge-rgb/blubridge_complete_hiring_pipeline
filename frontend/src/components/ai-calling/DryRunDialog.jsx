import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle, XCircle, Info } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';

export const DryRunDialog = ({ candidate, onClose }) => {
    const [r, setR] = useState(null);
    useEffect(() => {
        if (!candidate) return;
        setR(null);
        aiApi.post(`/test-candidates/${candidate.id}/dry-run`).then(x => setR(x.data)).catch(e => { toast.error(errMsg(e, 'Dry run failed')); onClose(); });
    }, [candidate, onClose]);

    return (
        <Dialog open={!!candidate} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="dry-run-dialog" className="bg-[#fffdf7] max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Dry run — call request preview</DialogTitle>
                    <DialogDescription>{candidate?.candidate_name} · nothing is sent to Bolna</DialogDescription>
                </DialogHeader>
                {!r ? <p className="text-sm text-[#9b9787]">Preparing…</p> : (
                    <div className="space-y-3">
                        <ul className="space-y-1" data-testid="dry-run-checks">
                            {r.checks.map(c => (
                                <li key={c.key} className="flex items-center gap-2 text-xs">
                                    {c.ok ? <CheckCircle size={14} weight="fill" className="text-emerald-600" /> : c.informational ? <Info size={14} weight="fill" className="text-amber-600" /> : <XCircle size={14} weight="fill" className="text-rose-500" />}
                                    {c.label}{c.informational && !c.ok ? ' (blocks real dispatch)' : ''}
                                </li>
                            ))}
                        </ul>
                        {r.prepared ? (
                            <pre className="text-[11px] bg-[#1a2332] text-emerald-100 rounded-xl p-3 overflow-x-auto" data-testid="dry-run-request">{`${r.method} ${r.url}\n${JSON.stringify({ headers: r.headers, body: r.body }, null, 2)}`}</pre>
                        ) : <p className="text-sm text-rose-700" data-testid="dry-run-blocked">Request not prepared — resolve the failed checks above.</p>}
                        <p className="text-xs text-[#6b7280]">would_send: <b>{String(r.would_send)}</b></p>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
};
