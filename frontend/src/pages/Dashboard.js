import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Upload, ChartBar, Users, SignOut, CheckCircle, SpinnerGap, FileText, UserCheck, FolderPlus } from '@phosphor-icons/react';
import BulkUploadModal from '../components/BulkUploadModal';

const API = process.env.REACT_APP_BACKEND_URL;

export default function Dashboard() {
    const { logout } = useAuth();
    const navigate = useNavigate();
    const naukriRef = useRef(null);
    const pipelineRef = useRef(null);
    const scoresheetRef = useRef(null);
    const [uploading, setUploading] = useState({ naukri: false, pipeline: false, scoresheet: false });
    const [uploadResult, setUploadResult] = useState({ naukri: null, pipeline: null, scoresheet: null });
    const [bulkType, setBulkType] = useState(null);

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
                {/* Upload Section */}
                <section className="space-y-4" data-testid="upload-section">
                    <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Upload Datasets</h2>

                    <input type="file" ref={naukriRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('naukri', e.target.files[0])} data-testid="naukri-file-input" />
                    <div className="flex items-stretch gap-2">
                        <button onClick={() => naukriRef.current?.click()} disabled={uploading.naukri}
                            data-testid="upload-naukri-btn"
                            className="flex-1 flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-emerald-600 hover:bg-zinc-900/80 transition-all group">
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
                        <button onClick={() => setBulkType('naukri')} data-testid="bulk-naukri-btn"
                            className="flex items-center gap-2 px-4 bg-zinc-900 border border-zinc-800 hover:border-emerald-600 hover:bg-zinc-900/80 transition-all text-sm text-zinc-400 hover:text-emerald-400">
                            <FolderPlus size={18} /> Bulk
                        </button>
                    </div>

                    <input type="file" ref={pipelineRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('pipeline', e.target.files[0])} data-testid="pipeline-file-input" />
                    <div className="flex items-stretch gap-2">
                        <button onClick={() => pipelineRef.current?.click()} disabled={uploading.pipeline}
                            data-testid="upload-pipeline-btn"
                            className="flex-1 flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-blue-600 hover:bg-zinc-900/80 transition-all group">
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
                        <button onClick={() => setBulkType('pipeline')} data-testid="bulk-pipeline-btn"
                            className="flex items-center gap-2 px-4 bg-zinc-900 border border-zinc-800 hover:border-blue-600 hover:bg-zinc-900/80 transition-all text-sm text-zinc-400 hover:text-blue-400">
                            <FolderPlus size={18} /> Bulk
                        </button>
                    </div>

                    <input type="file" ref={scoresheetRef} accept=".csv,.xlsx,.xls" className="hidden"
                        onChange={e => handleUpload('scoresheet', e.target.files[0])} data-testid="scoresheet-file-input" />
                    <div className="flex items-stretch gap-2">
                        <button onClick={() => scoresheetRef.current?.click()} disabled={uploading.scoresheet}
                            data-testid="upload-scoresheet-btn"
                            className="flex-1 flex items-center justify-between px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-purple-600 hover:bg-zinc-900/80 transition-all group">
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
                        <button onClick={() => setBulkType('score')} data-testid="bulk-score-btn"
                            className="flex items-center gap-2 px-4 bg-zinc-900 border border-zinc-800 hover:border-purple-600 hover:bg-zinc-900/80 transition-all text-sm text-zinc-400 hover:text-purple-400">
                            <FolderPlus size={18} /> Bulk
                        </button>
                    </div>
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
                            <div className="text-sm text-zinc-500 mt-0.5">All registered applicants with filters</div>
                        </div>
                    </button>

                    <button onClick={() => navigate('/attended-roles')} data-testid="nav-attended-btn"
                        className="w-full flex items-center gap-4 px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-emerald-600 hover:bg-zinc-900/80 transition-all group text-left">
                        <UserCheck size={28} className="text-zinc-500 group-hover:text-emerald-500 transition-colors" />
                        <div>
                            <div className="text-base font-medium">View Attended Applicants</div>
                            <div className="text-sm text-zinc-500 mt-0.5">Attended applicants with scores and filters</div>
                        </div>
                    </button>
                </section>
            </main>
            {bulkType && <BulkUploadModal type={bulkType} onClose={() => setBulkType(null)} />}
        </div>
    );
}
