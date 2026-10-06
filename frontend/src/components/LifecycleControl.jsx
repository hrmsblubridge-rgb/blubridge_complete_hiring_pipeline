import { useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Square, X } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * iter130 — Activate / Deactivate lifecycle control. Reused on
 * ManageJobRoles, JobOpenings, and HiringForms list pages. Shows:
 *   • a pulsing green/red status dot
 *   • a square activate/deactivate icon button
 *   • a modal with the current status, cascade-preview counts (when
 *     applicable), and the action button (red Deactivate / green
 *     Activate).
 *
 * Props
 * ─────
 *   entity       'job-roles' | 'job-openings' | 'hiring-forms'
 *   id           backend id used in `/api/bb/{entity}/{id}/{action}`
 *   name         display name (shown inside the confirmation modal)
 *   status       'active' | 'inactive' (controlled by parent list)
 *   onChanged    () => void   parent refresh callback
 *   testIdPrefix optional override for data-testid attributes
 */
export default function LifecycleControl({ entity, id, name, status, onChanged, testIdPrefix }) {
    const [open, setOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [preview, setPreview] = useState(null);
    const [errorMsg, setErrorMsg] = useState('');

    const isActive = (status || 'active') === 'active';
    const tid = testIdPrefix || `lifecycle-${entity}-${id}`;

    const fetchPreview = useCallback(async () => {
        // Only roles & openings cascade; forms are standalone.
        if (entity === 'hiring-forms' || !isActive) { setPreview(null); return; }
        try {
            const res = await axios.get(
                `${API}/api/bb/${entity}/${id}/cascade-preview`,
                { withCredentials: true },
            );
            setPreview(res.data);
        } catch { setPreview(null); }
    }, [entity, id, isActive]);

    const handleOpen = async () => {
        setOpen(true);
        setPreview(null);
        setErrorMsg('');
        await fetchPreview();
    };

    const handleAction = async () => {
        setSubmitting(true);
        setErrorMsg('');
        const action = isActive ? 'deactivate' : 'activate';
        try {
            const res = await axios.post(
                `${API}/api/bb/${entity}/${id}/${action}`,
                {},
                { withCredentials: true },
            );
            const c = res?.data?.cascade;
            if (action === 'deactivate' && c && (c.openings_affected || c.forms_affected)) {
                toast.success(
                    `Deactivated. Also deactivated ${c.openings_affected || 0} opening(s) and ${c.forms_affected || 0} form(s).`,
                );
            } else {
                toast.success(action === 'activate' ? 'Activated' : 'Deactivated');
            }
            setOpen(false);
            onChanged && onChanged();
        } catch (err) {
            // iter131 — Dependency-block popups: when the backend returns
            // 409, the detail message is the spec-mandated copy
            // ("Cannot activate. The associated Job Role is currently
            // inactive. Please activate the Job Role first." etc.). Show
            // it inline INSIDE the modal so the user sees the exact
            // reason without losing context.
            const status = err.response?.status;
            const detail = err.response?.data?.detail || 'Failed';
            if (status === 409) {
                setErrorMsg(detail);
            } else {
                toast.error(detail);
            }
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <>
            {/* Square activate/deactivate trigger. Color reflects current state.
                The aria-label communicates the next action a click would perform. */}
            <button
                onClick={handleOpen}
                data-testid={`${tid}-btn`}
                title={isActive ? 'Deactivate' : 'Activate'}
                aria-label={isActive ? 'Deactivate' : 'Activate'}
                className={`p-2 transition-colors ${isActive
                    ? 'text-emerald-400 hover:bg-emerald-900/30'
                    : 'text-red-400 hover:bg-red-900/30'}`}
            >
                <Square size={16} weight="fill" />
            </button>

            {open && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                     data-testid={`${tid}-modal`}>
                    <div className="bg-zinc-900 border border-zinc-700 w-full max-w-md mx-4 p-6 space-y-5">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-white">
                                {isActive ? 'Deactivate' : 'Activate'}{' '}
                                {entity === 'job-roles' ? 'Job Role'
                                    : entity === 'job-openings' ? 'Job Opening'
                                    : 'Hiring Form'}
                            </h2>
                            <button onClick={() => setOpen(false)}
                                    className="p-1 text-zinc-500 hover:text-white"
                                    data-testid={`${tid}-close-btn`}>
                                <X size={20} />
                            </button>
                        </div>

                        {name && (
                            <div className="text-sm text-zinc-300">
                                <span className="text-zinc-500 mr-2">Name:</span>{name}
                            </div>
                        )}

                        <div className="text-sm">
                            <span className="text-zinc-500 mr-2">Current Status:</span>
                            <span className={isActive ? 'text-emerald-400' : 'text-red-400'}
                                  data-testid={`${tid}-status-label`}>
                                {isActive ? 'Active' : 'Inactive'}
                            </span>
                        </div>

                        {/* Cascade warning — only shown when about to deactivate
                            a role/opening AND there are downstream actives. */}
                        {isActive && preview && (preview.openings || preview.forms) ? (
                            <div className="bg-amber-950/40 border border-amber-800/60 px-3 py-2 text-amber-300 text-sm"
                                 data-testid={`${tid}-cascade-warning`}>
                                ⚠ This will also deactivate{' '}
                                {entity === 'job-roles' && (
                                    <><strong>{preview.openings || 0}</strong> job opening(s) and </>
                                )}
                                <strong>{preview.forms || 0}</strong> hiring form(s).
                                Reactivating will NOT auto-restore them.
                            </div>
                        ) : null}

                        {/* iter131 — Dependency-block popup (inline). Surfaces
                            the spec-mandated "Cannot activate. The associated
                            Job Role / Job Opening is currently inactive." copy
                            from the 409 backend response. */}
                        {errorMsg && (
                            <div className="bg-red-950/40 border border-red-800/70 px-3 py-2 text-red-300 text-sm"
                                 data-testid={`${tid}-dependency-error`}>
                                {errorMsg}
                            </div>
                        )}

                        <div className="flex justify-end gap-3">
                            <button onClick={() => setOpen(false)}
                                    className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm text-white"
                                    data-testid={`${tid}-cancel-btn`}>
                                Cancel
                            </button>
                            <button
                                onClick={handleAction}
                                disabled={submitting}
                                data-testid={`${tid}-confirm-btn`}
                                className={`px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${isActive
                                    ? 'bg-red-700 hover:bg-red-600'
                                    : 'bg-emerald-700 hover:bg-emerald-600'}`}
                            >
                                {submitting ? '…' : (isActive ? 'Deactivate' : 'Activate')}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

/**
 * Pulsing green/red status dot for the top-left of an entity card/row.
 * Pure presentational — no API calls, no modal.
 */
export function StatusDot({ status, testId }) {
    const isActive = (status || 'active') === 'active';
    const color = isActive ? 'bg-emerald-500' : 'bg-red-500';
    return (
        <span
            data-testid={testId || `status-dot-${isActive ? 'active' : 'inactive'}`}
            title={isActive ? 'Active' : 'Inactive'}
            className={`inline-block w-2 h-2 rounded-full ${color} animate-pulse shadow-[0_0_6px_currentColor]`}
            style={{ color: isActive ? '#10b981' : '#ef4444' }}
        />
    );
}
