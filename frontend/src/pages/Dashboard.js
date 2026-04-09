import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Upload, ChartBar, Users, SignOut, CheckCircle, SpinnerGap } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function Dashboard() {
    const { logout } = useAuth();
    const navigate = useNavigate();
    const naukriRef = useRef(null);
    const pipelineRef = useRef(null);
    const [uploading, setUploading] = useState({ naukri: false, pipeline: false });
    const [uploadStatus, setUploadStatus] = useState({ naukri: null, pipeline: null });

    const handleUpload = async (type, file) => {
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        setUploading(prev => ({ ...prev, [type]: true }));
        setUploadStatus(prev => ({ ...prev, [type]: null }));
        try {
            const res = await axios.post(`${API}/api/upload/${type}`, formData, { withCredentials: true });
            setUploadStatus(prev => ({ ...prev, [type]: res.data }));
            toast.success(`${type === 'naukri' ? 'Naukri' : 'Pipeline'}: ${res.data.inserted} inserted, ${res.data.updated} updated`);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(prev => ({ ...prev, [type]: false }));
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
                             uploadStatus.naukri ? <CheckCircle size={22} weight="fill" className="text-emerald-500" /> :
                             <Upload size={22} className="text-zinc-500 group-hover:text-emerald-500 transition-colors" />}
                            <span className="text-base font-medium">Upload Naukri Applies Dataset</span>
                        </span>
                        {uploadStatus.naukri && (
                            <span className="text-xs text-zinc-500">{uploadStatus.naukri.inserted} new, {uploadStatus.naukri.updated} updated, {uploadStatus.naukri.mapped_columns} cols mapped</span>
                        )}
                    </button>

                    <input type="file" ref={pipelineRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('pipeline', e.target.files[0])} data-testid="pipeline-file-input" />
                    <button onClick={() => pipelineRef.current?.click()} disabled={uploading.pipeline}
                        data-testid="upload-pipeline-btn"
                        className="w-full flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-blue-600 hover:bg-zinc-900/80 transition-all group">
                        <span className="flex items-center gap-3">
                            {uploading.pipeline ? <SpinnerGap size={22} className="animate-spin text-blue-500" /> :
                             uploadStatus.pipeline ? <CheckCircle size={22} weight="fill" className="text-blue-500" /> :
                             <Upload size={22} className="text-zinc-500 group-hover:text-blue-500 transition-colors" />}
                            <span className="text-base font-medium">Upload HR Internal Pipeline Dataset</span>
                        </span>
                        {uploadStatus.pipeline && (
                            <span className="text-xs text-zinc-500">{uploadStatus.pipeline.inserted} new, {uploadStatus.pipeline.updated} updated, {uploadStatus.pipeline.mapped_columns} cols mapped</span>
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
