import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, Upload, Trash, FolderOpen, SpinnerGap, ArrowClockwise, CheckCircle, WarningCircle, Clock } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const TYPE_LABELS = { naukri: 'Naukri Applies', pipeline: 'HR Internal Pipeline', score: 'Score Sheet' };

export default function BulkUploadModal({ type, onClose }) {
    const [pending, setPending] = useState([]);
    const [processed, setProcessed] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [processing, setProcessing] = useState(false);
    const fileRef = useRef(null);

    const fetchStatus = useCallback(async () => {
        try {
            const res = await axios.get(`${API}/api/bulk-upload/status`, { withCredentials: true });
            const data = res.data[type] || {};
            setPending(data.pending || []);
            setProcessed(data.processed || []);
        } catch {}
    }, [type]);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 5000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    const handleUpload = async (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        setUploading(true);
        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) formData.append('files', files[i]);
            await axios.post(`${API}/api/bulk-upload/${type}`, formData, { withCredentials: true });
            toast.success(`${files.length} file(s) added to pending queue`);
            fetchStatus();
        } catch (err) {
            toast.error('Upload failed');
        } finally {
            setUploading(false);
            if (fileRef.current) fileRef.current.value = '';
        }
    };

    const handleDelete = async (filename) => {
        try {
            await axios.delete(`${API}/api/bulk-upload/${type}/${filename}`, { withCredentials: true });
            toast.success('File removed from pending');
            fetchStatus();
        } catch {
            toast.error('Failed to delete file');
        }
    };

    const handleProcessNow = async () => {
        setProcessing(true);
        try {
            const res = await axios.post(`${API}/api/bulk-upload/process-now`, {}, { withCredentials: true });
            const typeResults = res.data.results[type] || [];
            const successCount = typeResults.filter(r => r.success).length;
            toast.success(`Processed ${successCount}/${typeResults.length} file(s)`);
            fetchStatus();
        } catch {
            toast.error('Processing failed');
        } finally {
            setProcessing(false);
        }
    };

    const formatSize = (bytes) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const statusIcon = (status) => {
        if (status === 'processed') return <CheckCircle size={16} className="text-emerald-400" />;
        if (status === 'failed') return <WarningCircle size={16} className="text-red-400" />;
        if (status === 'processing') return <SpinnerGap size={16} className="animate-spin text-cyan-400" />;
        return <Clock size={16} className="text-zinc-500" />;
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="bulk-modal-overlay" onClick={onClose}>
            <div className="bg-zinc-900 border border-zinc-700 w-full max-w-2xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()} data-testid="bulk-modal">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
                    <h2 className="text-lg font-semibold">Bulk Upload — {TYPE_LABELS[type]}</h2>
                    <button onClick={onClose} data-testid="bulk-modal-close" className="p-1.5 hover:bg-zinc-800 transition-colors"><X size={20} /></button>
                </div>

                {/* Upload + Process Now */}
                <div className="flex items-center gap-3 px-6 py-4 border-b border-zinc-800">
                    <label className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium cursor-pointer transition-colors" data-testid="bulk-file-input-label">
                        {uploading ? <SpinnerGap size={16} className="animate-spin" /> : <Upload size={16} />}
                        Upload File(s)
                        <input ref={fileRef} type="file" multiple accept=".csv,.xlsx" onChange={handleUpload} className="hidden" data-testid="bulk-file-input" />
                    </label>
                    {pending.length > 0 && (
                        <button onClick={handleProcessNow} disabled={processing} data-testid="process-now-btn"
                            className="flex items-center gap-2 px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-sm font-medium transition-colors">
                            {processing ? <SpinnerGap size={16} className="animate-spin" /> : <ArrowClockwise size={16} />}
                            Process Now
                        </button>
                    )}
                    <span className="ml-auto text-xs text-zinc-500">Auto-processes every 30s</span>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                    {/* Pending Files */}
                    <div>
                        <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">Pending Files ({pending.length})</h3>
                        {pending.length === 0 ? (
                            <p className="text-sm text-zinc-600">No pending files. Upload files above.</p>
                        ) : (
                            <div className="space-y-2" data-testid="pending-list">
                                {pending.map(f => (
                                    <div key={f.name} className="flex items-center gap-3 px-4 py-2.5 bg-zinc-800/50 border border-zinc-800" data-testid={`pending-file-${f.name}`}>
                                        {statusIcon(f.status)}
                                        <span className="text-sm truncate flex-1" title={f.name}>{f.name.replace(/^\d+_/, '')}</span>
                                        <span className="text-xs text-zinc-500">{formatSize(f.size)}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded ${
                                            f.status === 'failed' ? 'bg-red-900/40 text-red-400' :
                                            f.status === 'processing' ? 'bg-cyan-900/40 text-cyan-400' :
                                            'bg-zinc-800 text-zinc-400'
                                        }`}>{f.status}</span>
                                        {f.status !== 'processing' && (
                                            <button onClick={() => handleDelete(f.name)} data-testid={`delete-${f.name}`}
                                                className="p-1 hover:bg-zinc-700 transition-colors text-zinc-500 hover:text-red-400">
                                                <Trash size={16} />
                                            </button>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Processed Files */}
                    <div>
                        <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <FolderOpen size={16} /> Processed Files ({processed.length})
                        </h3>
                        {processed.length === 0 ? (
                            <p className="text-sm text-zinc-600">No files processed yet.</p>
                        ) : (
                            <div className="space-y-1" data-testid="processed-list">
                                {processed.map(f => (
                                    <div key={f.name} className="flex items-center gap-3 px-4 py-2 text-sm" data-testid={`processed-file-${f.name}`}>
                                        <CheckCircle size={14} className="text-emerald-500 shrink-0" />
                                        <span className="truncate text-zinc-400" title={f.name}>{f.name.replace(/^\d+_/, '')}</span>
                                        <span className="text-xs text-zinc-600 ml-auto">{formatSize(f.size)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
