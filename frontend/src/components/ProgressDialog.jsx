import { SpinnerGap, CheckCircle, WarningCircle, X } from '@phosphor-icons/react';

/**
 * ProgressDialog — iter155
 * ------------------------------------------------------------
 * A single reusable "waiting for a long operation" modal for
 * uploads, imports and exports.  Mirrors the UX pattern already
 * present in `BulkUploadModal` (spinner + progress bar + label)
 * so the entire application looks consistent.
 *
 * States:
 *   - open + no `variant`     → indeterminate spinner + message
 *   - variant="success"       → green tick + message + auto-close on backdrop click
 *   - variant="error"         → red icon + error text + explicit close
 *
 * Progress bar renders only when a numeric `percent` is passed.
 *
 * The component itself is *presentational* — the parent owns the
 * `open` state, the `title`, the `message`, and (optionally) the
 * `percent` (0–100).  There is no lifecycle, no timers, no
 * animation state — that's intentional; we don't want a shared
 * component to invent side-effects on top of whatever the caller
 * is doing.
 */
export default function ProgressDialog({
    open,
    title = 'Working…',
    message = 'Please wait while the operation completes.',
    percent,               // 0..100 (optional; renders bar if provided)
    variant = 'busy',      // 'busy' | 'success' | 'error'
    onClose,               // shown only when variant !== 'busy'
    testId = 'progress-dialog',
}) {
    if (!open) return null;

    const isBusy = variant === 'busy';
    const isSuccess = variant === 'success';
    const isError = variant === 'error';

    return (
        <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 backdrop-blur-sm"
            data-testid={`${testId}-overlay`}
            // Backdrop is intentionally NOT click-through while busy — the
            // user should not be able to dismiss a running upload/export
            // by accident. Success/error variants close on backdrop click.
            onClick={isBusy ? undefined : onClose}
        >
            <div
                className="bg-zinc-900 border border-zinc-700 w-full max-w-sm mx-4 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
                data-testid={testId}
            >
                <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-zinc-800">
                    <div className="flex items-center gap-2.5">
                        {isBusy && <SpinnerGap size={18} className="animate-spin text-cyan-400" />}
                        {isSuccess && <CheckCircle size={18} className="text-emerald-400" />}
                        {isError && <WarningCircle size={18} className="text-red-400" />}
                        <h3 className="text-sm font-semibold text-white" data-testid={`${testId}-title`}>{title}</h3>
                    </div>
                    {!isBusy && onClose && (
                        <button
                            onClick={onClose}
                            className="p-1 text-zinc-500 hover:text-white"
                            aria-label="Close"
                            data-testid={`${testId}-close`}
                        >
                            <X size={16} />
                        </button>
                    )}
                </div>
                <div className="px-5 py-4 space-y-3">
                    <p className="text-sm text-zinc-300" data-testid={`${testId}-message`}>{message}</p>
                    {typeof percent === 'number' && (
                        <div>
                            <div className="flex items-center justify-between text-xs text-zinc-400 mb-1">
                                <span>Progress</span>
                                <span className="text-cyan-400 font-medium" data-testid={`${testId}-percent`}>
                                    {Math.max(0, Math.min(100, Math.round(percent)))}%
                                </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-800 rounded-sm overflow-hidden">
                                <div
                                    className="h-full bg-cyan-500 transition-all duration-300"
                                    style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
                                />
                            </div>
                        </div>
                    )}
                    {/* Indeterminate track — shown when busy without a numeric percent. */}
                    {isBusy && typeof percent !== 'number' && (
                        <div className="h-1.5 w-full bg-zinc-800 rounded-sm overflow-hidden" data-testid={`${testId}-indeterminate`}>
                            <div className="h-full w-1/3 bg-cyan-500/70 animate-pulse" />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
