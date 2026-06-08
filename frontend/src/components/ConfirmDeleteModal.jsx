import { Warning, X } from '@phosphor-icons/react';

/**
 * ConfirmDeleteModal — single polished confirmation dialog used across the
 * app for any destructive action (delete round, job role, job opening,
 * hiring form, team round, etc.).
 *
 * Props:
 *   open:        boolean — whether the modal is visible
 *   title:       headline (e.g. "Delete Job Role?")
 *   description: explanatory body — keep it concrete (mention the entity
 *                being deleted and what cascades).
 *   itemLabel:   the name/title of the item — rendered in bold so the
 *                user sees exactly what they're about to delete.
 *   onConfirm:   called when the user clicks Delete
 *   onClose:     called when the user clicks Cancel / the X / the backdrop
 *   testId:      data-testid prefix (default "confirm-delete")
 *   confirmLabel:default "Delete"
 *
 * iter146 — destructive actions now ALWAYS go through this modal instead
 * of `window.confirm()` (which is ugly + not testable) or instant delete
 * (which has caused accidental data loss).
 */
export default function ConfirmDeleteModal({
    open, title = 'Delete?', description,
    itemLabel, onConfirm, onClose,
    testId = 'confirm-delete',
    confirmLabel = 'Delete',
}) {
    if (!open) return null;
    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            data-testid={`${testId}-modal`}
            onClick={onClose}
        >
            <div
                className="bg-zinc-900 border border-red-900/40 w-full max-w-md mx-4 flex flex-col max-h-[90vh] min-h-0 shadow-2xl"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-5 pb-4 shrink-0 border-b border-zinc-800">
                    <div className="flex items-center gap-2.5">
                        <Warning size={20} weight="fill" className="text-red-400" />
                        <h2 className="text-base font-semibold text-white">{title}</h2>
                    </div>
                    <button onClick={onClose} className="text-zinc-500 hover:text-white shrink-0" aria-label="Close">
                        <X size={18} />
                    </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-2.5 text-sm text-zinc-300">
                    {itemLabel && (
                        <p>
                            You're about to delete{' '}
                            <span className="text-white font-medium">{itemLabel}</span>.
                        </p>
                    )}
                    {description && <p className="text-zinc-400">{description}</p>}
                    <p className="text-red-400 text-xs">This action cannot be undone.</p>
                </div>

                <div className="flex justify-end gap-2 p-5 pt-3 shrink-0 border-t border-zinc-800 bg-zinc-900">
                    <button
                        onClick={onClose}
                        data-testid={`${testId}-cancel`}
                        className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-sm"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        data-testid={`${testId}-confirm`}
                        className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-medium"
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
