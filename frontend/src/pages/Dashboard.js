import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Upload, ChartBar, Users, SignOut, CheckCircle, SpinnerGap, Database, FileText } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function Dashboard() {
    const { logout } = useAuth();
    const navigate = useNavigate();
    const naukriRef = useRef(null);
    const pipelineRef = useRef(null);
    const scoresheetRef = useRef(null);
    const [uploading, setUploading] = useState({ naukri: false, pipeline: false, scoresheet: false });
    const [uploadResult, setUploadResult] = useState({ naukri: null, pipeline: null, scoresheet: null });
    const [status, setStatus] = useState(null);

    const fetchStatus = async () => {
        try {
            const res = await axios.get(`${API}/api/status`, { withCredentials: true });
            setStatus(res.data);
        } catch {}
    };

    useEffect(() => {
        let mounted = true;
        if (mounted) fetchStatus();
        return () => { mounted = false; };
    }, []);

    const handleUpload = async (type, file) => {
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        setUploading(prev => ({ ...prev, [type]: true }));
        setUploadResult(prev => ({ ...prev, [type]: null }));
        try {
            const endpoint = type === 'scoresheet' ? 'upload/scoresheet' : `upload/${type}`;
            const res = await axios.post(`${API}/api/${endpoint}`, formData, { withCredentials: true });
            setUploadResult(prev => ({ ...prev, [type]: res.data }));
            const label = type === 'naukri' ? 'Naukri' : type === 'pipeline' ? 'Pipeline' : 'Score Sheet';
            toast.success(`${label}: ${res.data.inserted} inserted${res.data.updated !== undefined ? `, ${res.data.updated} updated` : ''}`);
            fetchStatus();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(prev => ({ ...prev, [type]: false }));
            if (naukriRef.current) naukriRef.current.value = '';
            if (pipelineRef.current) pipelineRef.current.value = '';
            if (scoresheetRef.current) scoresheetRef.current.value = '';
        }
    };

    const handleLogout = async () => {
        try {
            await axios.post(`${API}/api/logout`, {}, { withCredentials: true });
        } catch {}
        logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="dashboard-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center justify-between">
                <h1 className="text-xl font-semibold tracking-tight">Recruitment Analytics</h1>
                <button onClick={handleLogout} data-testid="logout-btn"
                    className="flex items-center gap-2 text-sm text-zinc-400 hover:text-white transition-colors">
                    <SignOut size={18} /> Logout
                </button>
            </header>

            <main className="max-w-3xl mx-auto px-6 py-12 space-y-8">
                {/* DB Status */}
                {status && (
                    <section className="flex items-center gap-6 px-5 py-3 bg-zinc-900/50 border border-zinc-800 text-sm" data-testid="db-status">
                        <Database size={18} className="text-zinc-500 shrink-0" />
                        <span className="text-zinc-400">
                            Naukri: <span className="text-white font-medium" data-testid="naukri-count">{status.naukri_count}</span>
                        </span>
                        <span className="text-zinc-400">
                            Pipeline: <span className="text-white font-medium" data-testid="pipeline-count">{status.pipeline_count}</span>
                        </span>
                        <span className="text-zinc-400">
                            Registered: <span className="text-white font-medium" data-testid="registered-count">{status.registered_count}</span>
                        </span>
                        <span className="text-zinc-400">
                            Score Sheets: <span className="text-white font-medium" data-testid="scoresheet-count">{status.score_sheet_count || 0}</span>
                        </span>
                    </section>
                )}

                {/* Upload Section */}
                <section className="space-y-4" data-testid="upload-section">
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Upload Datasets</h2>

                    <input type="file" ref={naukriRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('naukri', e.target.files[0])} data-testid="naukri-file-input" />
                    <button onClick={() => naukriRef.current?.click()} disabled={uploading.naukri}
                        data-testid="upload-naukri-btn"
                        className="w-full flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-emerald-600 hover:bg-zinc-900/80 transition-all group">
                        <span className="flex items-center gap-3">
                            {uploading.naukri ? <SpinnerGap size={22} className="animate-spin text-emerald-500" /> :
                             uploadResult.naukri ? <CheckCircle size={22} weight="fill" className="text-emerald-500" /> :
                             <Upload size={22} className="text-zinc-500 group-hover:text-emerald-500 transition-colors" />}
                            <span className="text-base font-medium">Upload Naukri Applies Dataset</span>
                        </span>
                        {uploadResult.naukri && (
                            <span className="text-xs text-zinc-500">{uploadResult.naukri.inserted} new, {uploadResult.naukri.updated} updated</span>
                        )}
                    </button>

                    <input type="file" ref={pipelineRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('pipeline', e.target.files[0])} data-testid="pipeline-file-input" />
                    <button onClick={() => pipelineRef.current?.click()} disabled={uploading.pipeline}
                        data-testid="upload-pipeline-btn"
                        className="w-full flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-blue-600 hover:bg-zinc-900/80 transition-all group">
                        <span className="flex items-center gap-3">
                            {uploading.pipeline ? <SpinnerGap size={22} className="animate-spin text-blue-500" /> :
                             uploadResult.pipeline ? <CheckCircle size={22} weight="fill" className="text-blue-500" /> :
                             <Upload size={22} className="text-zinc-500 group-hover:text-blue-500 transition-colors" />}
                            <span className="text-base font-medium">Upload HR Internal Pipeline Dataset</span>
                        </span>
                        {uploadResult.pipeline && (
                            <span className="text-xs text-zinc-500">{uploadResult.pipeline.inserted} new, {uploadResult.pipeline.updated} updated</span>
                        )}
                    </button>

                    <input type="file" ref={scoresheetRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('scoresheet', e.target.files[0])} data-testid="scoresheet-file-input" />
                    <button onClick={() => scoresheetRef.current?.click()} disabled={uploading.scoresheet}
                        data-testid="upload-scoresheet-btn"
                        className="w-full flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-purple-600 hover:bg-zinc-900/80 transition-all group">
                        <span className="flex items-center gap-3">
                            {uploading.scoresheet ? <SpinnerGap size={22} className="animate-spin text-purple-500" /> :
                             uploadResult.scoresheet ? <CheckCircle size={22} weight="fill" className="text-purple-500" /> :
                             <FileText size={22} className="text-zinc-500 group-hover:text-purple-500 transition-colors" />}
                            <span className="text-base font-medium">Upload Score Sheet</span>
                        </span>
                        {uploadResult.scoresheet && (
                            <span className="text-xs text-zinc-500">{uploadResult.scoresheet.inserted} scores imported</span>
                        )}
                    </button>
                </section>

                {/* Navigation Panels */}
                <section className="space-y-4 pt-4" data-testid="nav-section">
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Analytics</h2>

                    <button onClick={() => navigate('/summary')} data-testid="nav-summary-btn"
                        className="w-full flex items-center gap-4 px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-amber-600 hover:bg-zinc-900/80 transition-all group text-left">
                        <ChartBar size={28} className="text-zinc-500 group-hover:text-amber-500 transition-colors" />
                        <div>
                            <div className="text-base font-medium">View Applicants Summary Statistics</div>
                            <div className="text-sm text-zinc-500 mt-0.5">Role-wise funnel breakdown with filters</div>
                        </div>
                    </button>

                    <button onClick={() => navigate('/roles')} data-testid="nav-roles-btn"
                        className="w-full flex items-center gap-4 px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-violet-600 hover:bg-zinc-900/80 transition-all group text-left">
                        <Users size={28} className="text-zinc-500 group-hover:text-violet-500 transition-colors" />
                        <div>
                            <div className="text-base font-medium">View Applicants</div>
                            <div className="text-sm text-zinc-500 mt-0.5">Browse applicants by job role</div>
                        </div>
                    </button>
                </section>
            </main>
        </div>
    );
}
