import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, Upload, Trash, FolderOpen, SpinnerGap, ArrowClockwise, CheckCircle, WarningCircle, Clock, Folder } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const TYPE_LABELS = { naukri: 'Naukri Applies', pipeline: 'HR Internal Pipeline', score: 'Score Sheet' };

export default function BulkUploadModal({ type, onClose }) {
    const [pending, setPending] = useState([]);
    const [processed, setProcessed] = useState([]);
    const [failed, setFailed] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [showPending, setShowPending] = useState(true);   // expanded by default
    const [showFailed, setShowFailed] = useState(true);     // expanded by default when present
    const [showProcessed, setShowProcessed] = useState(false);
    const fileRef = useRef(null);

    const fetchStatus = useCallback(async () => {
        try {
            const res = await axios.get(`${API}/api/bulk-upload/status`, { withCredentials: true });
            const data = res.data[type] || {};
            setPending(data.pending || []);
            setProcessed(data.processed || []);
            setFailed(data.failed || []);
        } catch {}
    }, [type]);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    // ---- Live polling while a job is processing (Iter46) ----
    // Polls every 1.5s when there's a queued/processing job so the row-count
    // progress bar updates in near-real-time. Stops polling when the queue is
    // idle to save bandwidth.
    useEffect(() => {
        const hasActive = pending.some(p => p.status === 'processing' || p.status === 'queued' || p.status === 'pending');
        if (!hasActive) return;
        const id = setInterval(fetchStatus, 1500);
        return () => clearInterval(id);
    }, [pending, fetchStatus]);

    const handleUpload = async (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        // Soft size warning — Kubernetes ingress + Atlas pipeline get unhappy
        // above ~50 MB. We still attempt the upload.
        const big = Array.from(files).find(f => f.size > 50 * 1024 * 1024);
        if (big) {
            toast.warning(`${big.name} is ${(big.size / (1024 * 1024)).toFixed(1)} MB — upload may be slow or rejected by ingress`);
        }
        setUploading(true);
        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) formData.append('files', files[i]);
            await axios.post(`${API}/api/bulk-upload/${type}`, formData, {
                withCredentials: true,
                timeout: 5 * 60 * 1000,  // 5-minute timeout for large multi-file uploads
            });
            toast.success(`${files.length} file(s) added to queue`);
            fetchStatus();
        } catch (err) {
            // Surface the actual server error so debugging isn't a guessing
            // game. Falls back to status text or network message.
            const detail =
                err.response?.data?.detail ||
                err.response?.data?.message ||
                (err.response ? `${err.response.status} ${err.response.statusText || 'error'}` : null) ||
                err.message ||
                'Upload failed';
            toast.error(`Upload failed: ${detail}`);
        } finally {
            setUploading(false);
            if (fileRef.current) fileRef.current.value = '';
        }
    };

    const handleDelete = async (queueId) => {
        try {
            await axios.delete(`${API}/api/bulk-upload/${type}/${queueId}`, { withCredentials: true });
            toast.success('File removed from queue');
            fetchStatus();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to delete');
        }
    };

    const handleRefresh = () => {
        fetchStatus();
    };

    const formatSize = (bytes) => {
        if (!bytes) return '-';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const statusIcon = (status) => {
        if (status === 'completed') return <CheckCircle size={16} className="text-emerald-400" />;
        if (status === 'failed') return <WarningCircle size={16} className="text-red-400" />;
        if (status === 'processing') return <SpinnerGap size={16} className="animate-spin text-cyan-400" />;
        return <Clock size={16} className="text-zinc-500" />;
    };

    const statusBadge = (status) => {
        const display = status === 'queued' ? 'pending' : status;
        const styles = {
            pending: 'bg-zinc-800 text-zinc-400',
            processing: 'bg-cyan-900/40 text-cyan-400',
            completed: 'bg-emerald-900/40 text-emerald-400',
            failed: 'bg-red-900/40 text-red-400',
        };
        return <span className={`text-xs px-2 py-0.5 rounded ${styles[display] || styles.pending}`}>{display}</span>;
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="bulk-modal-overlay" onClick={onClose}>
            <div className="bg-zinc-900 border border-zinc-700 w-full max-w-2xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()} data-testid="bulk-modal">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
                    <h2 className="text-lg font-semibold">Bulk Upload — {TYPE_LABELS[type]}</h2>
                    <button onClick={onClose} data-testid="bulk-modal-close" className="p-1.5 hover:bg-zinc-800 transition-colors"><X size={20} /></button>
                </div>

                {/* Upload + Refresh */}
                <div className="flex items-center gap-3 px-6 py-4 border-b border-zinc-800">
                    <label className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium cursor-pointer transition-colors" data-testid="bulk-file-input-label">
                        {uploading ? <SpinnerGap size={16} className="animate-spin" /> : <Upload size={16} />}
                        Upload File(s)
                        <input ref={fileRef} type="file" multiple accept=".csv,.xlsx" onChange={handleUpload} className="hidden" data-testid="bulk-file-input" />
                    </label>
                    <button onClick={handleRefresh} data-testid="refresh-btn"
                        className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium transition-colors">
                        <ArrowClockwise size={16} /> Refresh
                    </button>
                    <span className="ml-auto text-xs text-zinc-500">Processing is automatic & sequential</span>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                    {/* Pending / Processing Files (expand/collapse) */}
                    <div>
                        <button onClick={() => setShowPending(p => !p)} data-testid="toggle-pending-btn"
                            className="flex items-center gap-2 text-sm font-medium text-zinc-400 uppercase tracking-wider hover:text-zinc-200 transition-colors w-full text-left mb-3">
                            {showPending ? <FolderOpen size={18} /> : <Folder size={18} />}
                            Pending / Processing ({pending.length})
                        </button>
                        {showPending && (pending.length === 0 ? (
                            <p className="text-sm text-zinc-600 pl-6" data-testid="no-pending">No pending files. Upload files above to start processing.</p>
                        ) : (
                            <div className="space-y-2 pl-2" data-testid="pending-list">
                                {pending.map(f => (
                                    <div key={f.id} className="flex flex-col gap-1.5 px-4 py-2.5 bg-zinc-800/50 border border-zinc-800" data-testid={`pending-file-${f.id}`}>
                                        <div className="flex items-center gap-3">
                                            {statusIcon(f.status)}
                                            <span className="text-sm truncate flex-1" title={f.name}>{f.name}</span>
                                            <span className="text-xs text-zinc-500">{formatSize(f.size)}</span>
                                            {statusBadge(f.status)}
                                            {(f.status === 'pending' || f.status === 'queued') && (
                                                <button onClick={() => handleDelete(f.id)} data-testid={`delete-${f.id}`}
                                                    className="p-1 hover:bg-zinc-700 transition-colors text-zinc-500 hover:text-red-400">
                                                    <Trash size={16} />
                                                </button>
                                            )}
                                        </div>
                                        {/* Live row-count progress (Iter46) */}
                                        {f.status === 'processing' && f.progress && f.progress.total > 0 && (
                                            <div className="pl-7" data-testid={`progress-${f.id}`}>
                                                <div className="flex items-center justify-between text-xs text-zinc-400 mb-1">
                                                    <span data-testid={`progress-count-${f.id}`}>
                                                        {f.progress.processed.toLocaleString()} / {f.progress.total.toLocaleString()} rows
                                                    </span>
                                                    <span className="text-cyan-400 font-medium">{f.progress.percent}%</span>
                                                </div>
                                                <div className="h-1.5 w-full bg-zinc-800 rounded-sm overflow-hidden">
                                                    <div
                                                        className="h-full bg-cyan-500 transition-all duration-500"
                                                        style={{ width: `${f.progress.percent}%` }}
                                                    />
                                                </div>
                                            </div>
                                        )}
                                        {f.status === 'processing' && (!f.progress || !f.progress.total) && (
                                            <div className="pl-7 text-xs text-zinc-500" data-testid={`progress-init-${f.id}`}>
                                                Starting…
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        ))}
                    </div>

                    {/* Failed Files (expand/collapse) */}
                    {failed.length > 0 && (
                        <div>
                            <button onClick={() => setShowFailed(p => !p)} data-testid="toggle-failed-btn"
                                className="flex items-center gap-2 text-sm font-medium text-red-400/80 uppercase tracking-wider hover:text-red-300 transition-colors w-full text-left mb-3">
                                {showFailed ? <FolderOpen size={18} /> : <Folder size={18} />}
                                Failed ({failed.length})
                            </button>
                            {showFailed && (
                                <div className="space-y-2 pl-2" data-testid="failed-list">
                                    {failed.map(f => (
                                        <div key={f.id} className="px-4 py-2.5 bg-red-950/20 border border-red-900/30" data-testid={`failed-file-${f.id}`}>
                                            <div className="flex items-center gap-3">
                                                <WarningCircle size={16} className="text-red-400 shrink-0" />
                                                <span className="text-sm truncate flex-1 text-red-300">{f.name}</span>
                                            </div>
                                            {f.error && <p className="text-xs text-red-400/70 mt-1 pl-7">{f.error}</p>}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Processed Files Directory */}
                    <div>
                        <button onClick={() => setShowProcessed(prev => !prev)} data-testid="toggle-processed-btn"
                            className="flex items-center gap-2 text-sm font-medium text-zinc-400 uppercase tracking-wider hover:text-zinc-200 transition-colors w-full text-left mb-3">
                            {showProcessed ? <FolderOpen size={18} /> : <Folder size={18} />}
                            processed_files ({processed.length})
                        </button>
                        {showProcessed && (
                            processed.length === 0 ? (
                                <p className="text-sm text-zinc-600 pl-6" data-testid="no-processed">No files processed yet.</p>
                            ) : (
                                <div className="space-y-1 pl-2" data-testid="processed-list">
                                    {processed.map(f => (
                                        <div key={f.id} className="flex items-center gap-3 px-4 py-2 text-sm" data-testid={`processed-file-${f.id}`}>
                                            <CheckCircle size={14} className="text-emerald-500 shrink-0" />
                                            <span className="truncate text-zinc-400" title={f.name}>{f.name}</span>
                                            <span className="text-xs text-zinc-600 ml-auto">{formatSize(f.size)}</span>
                                            {f.result && (
                                                <span className="text-xs text-zinc-500">
                                                    {f.result.inserted !== undefined ? `${f.result.inserted} ins` : ''}
                                                    {f.result.updated !== undefined ? `, ${f.result.updated} upd` : ''}
                                                </span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
