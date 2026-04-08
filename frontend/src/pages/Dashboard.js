import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    ChartBar, 
    SignOut, 
    Upload, 
    Users, 
    UserCheck, 
    UserMinus,
    CheckCircle,
    XCircle,
    Calendar,
    CalendarX,
    ClockClockwise,
    CaretRight,
    CaretDown,
    X,
    CaretLeft,
    CloudArrowUp,
    FileXls,
    Warning
} from '@phosphor-icons/react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

// Data Table Modal Component
function DataTableModal({ isOpen, onClose, title, endpoint, columns }) {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [limit] = useState(50);

    const fetchData = useCallback(async () => {
        if (!isOpen) return;
        setLoading(true);
        try {
            const response = await axios.get(`${API}/api/data/${endpoint}?page=${page}&limit=${limit}`, {
                withCredentials: true
            });
            setData(response.data.data || []);
            setTotal(response.data.total || 0);
        } catch (error) {
            console.error('Failed to fetch data:', error);
        } finally {
            setLoading(false);
        }
    }, [isOpen, endpoint, page, limit]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const totalPages = Math.ceil(total / limit);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-white w-full max-w-6xl max-h-[85vh] flex flex-col border border-gray-200"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
                    <div>
                        <h2 className="heading-3">{title}</h2>
                        <p className="text-sm text-gray-500">{total} records found</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-gray-200 transition-colors"
                        data-testid="close-modal-btn"
                    >
                        <X size={24} weight="bold" />
                    </button>
                </div>

                {/* Table with scroll */}
                <div className="flex-1 overflow-auto">
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <div className="spinner"></div>
                        </div>
                    ) : data.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                            <Users size={48} weight="duotone" className="text-gray-300 mb-4" />
                            <p>No data available</p>
                        </div>
                    ) : (
                        <table className="w-full text-sm min-w-max">
                            <thead className="sticky top-0 bg-gray-100 border-b border-gray-200">
                                <tr>
                                    {columns.map((col) => (
                                        <th key={col} className="px-4 py-3 text-left font-bold uppercase text-xs tracking-wider text-gray-600 whitespace-nowrap">
                                            {col.replace(/_/g, ' ')}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((row, idx) => (
                                    <tr key={idx} className="border-b border-gray-100 hover:bg-gray-50">
                                        {columns.map((col) => (
                                            <td key={col} className="px-4 py-3 whitespace-nowrap">
                                                {row[col] !== null && row[col] !== undefined ? String(row[col]) : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* Pagination */}
                <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50">
                    <p className="text-sm text-gray-600">
                        Showing {((page - 1) * limit) + 1} - {Math.min(page * limit, total)} of {total}
                    </p>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            className="p-2 border border-gray-200 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <CaretLeft size={18} weight="bold" />
                        </button>
                        <span className="px-4 py-2 border border-gray-200 bg-white font-semibold">
                            {page} / {totalPages || 1}
                        </span>
                        <button
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                            className="p-2 border border-gray-200 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <CaretRight size={18} weight="bold" />
                        </button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

// Upload Modal Component
function UploadModal({ isOpen, onClose, onUploadComplete }) {
    const [naukriFile, setNaukriFile] = useState(null);
    const [pipelineFile, setPipelineFile] = useState(null);
    const [naukriUploading, setNaukriUploading] = useState(false);
    const [pipelineUploading, setPipelineUploading] = useState(false);
    const [naukriResult, setNaukriResult] = useState(null);
    const [pipelineResult, setPipelineResult] = useState(null);
    const [error, setError] = useState('');

    const handleNaukriUpload = async () => {
        if (!naukriFile) return;
        setNaukriUploading(true);
        setError('');
        
        const formData = new FormData();
        formData.append('file', naukriFile);

        try {
            const response = await axios.post(`${API}/api/upload/naukri`, formData, {
                withCredentials: true,
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setNaukriResult(response.data);
            setNaukriFile(null);
            onUploadComplete();
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed');
        } finally {
            setNaukriUploading(false);
        }
    };

    const handlePipelineUpload = async () => {
        if (!pipelineFile) return;
        setPipelineUploading(true);
        setError('');
        
        const formData = new FormData();
        formData.append('file', pipelineFile);

        try {
            const response = await axios.post(`${API}/api/upload/pipeline`, formData, {
                withCredentials: true,
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setPipelineResult(response.data);
            setPipelineFile(null);
            onUploadComplete();
        } catch (err) {
            setError(err.response?.data?.detail || 'Upload failed');
        } finally {
            setPipelineUploading(false);
        }
    };

    const handleClose = () => {
        setNaukriFile(null);
        setPipelineFile(null);
        setNaukriResult(null);
        setPipelineResult(null);
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-white w-full max-w-2xl border border-gray-200"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
                    <h2 className="heading-3">Upload Datasets</h2>
                    <button onClick={handleClose} className="p-2 hover:bg-gray-200 transition-colors" data-testid="close-upload-modal-btn">
                        <X size={24} weight="bold" />
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    {error && (
                        <div className="flex items-start gap-3 bg-red-50 border border-red-200 p-4">
                            <Warning size={20} weight="fill" className="text-red-500 flex-shrink-0 mt-0.5" />
                            <p className="text-red-700 text-sm">{error}</p>
                        </div>
                    )}

                    {/* Section 1: Naukri Upload */}
                    <div className="border border-gray-200 p-4">
                        <h3 className="font-bold mb-3 flex items-center gap-2">
                            <CloudArrowUp size={20} weight="bold" className="text-[#002FA7]" />
                            Section 1: Naukri Applies Data
                        </h3>
                        
                        {naukriResult ? (
                            <div className="bg-green-50 border border-green-200 p-4">
                                <div className="flex items-center gap-2 mb-2">
                                    <CheckCircle size={20} weight="fill" className="text-green-600" />
                                    <p className="font-semibold text-green-800">{naukriResult.message}</p>
                                </div>
                                <p className="text-sm text-green-700">Inserted: {naukriResult.inserted}, Updated: {naukriResult.updated}</p>
                            </div>
                        ) : (
                            <>
                                <div 
                                    className="upload-zone cursor-pointer min-h-[120px]"
                                    onClick={() => document.getElementById('naukri-file').click()}
                                    data-testid="naukri-upload-zone"
                                >
                                    <input
                                        id="naukri-file"
                                        type="file"
                                        accept=".csv,.xlsx"
                                        onChange={(e) => setNaukriFile(e.target.files[0])}
                                        className="hidden"
                                    />
                                    {naukriFile ? (
                                        <div className="flex items-center gap-3">
                                            <FileXls size={32} weight="duotone" className="text-[#002FA7]" />
                                            <div>
                                                <p className="font-semibold">{naukriFile.name}</p>
                                                <p className="text-sm text-gray-500">{(naukriFile.size / 1024).toFixed(1)} KB</p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="text-center">
                                            <CloudArrowUp size={32} className="text-gray-400 mx-auto mb-2" />
                                            <p className="text-sm text-gray-500">Click to upload Naukri file (CSV/XLSX)</p>
                                        </div>
                                    )}
                                </div>
                                {naukriFile && (
                                    <button
                                        onClick={handleNaukriUpload}
                                        disabled={naukriUploading}
                                        className="btn-primary w-full mt-3 flex items-center justify-center gap-2"
                                    >
                                        {naukriUploading ? (
                                            <>
                                                <div className="spinner w-4 h-4 border-white border-t-transparent"></div>
                                                Uploading...
                                            </>
                                        ) : (
                                            'Upload Naukri Data'
                                        )}
                                    </button>
                                )}
                            </>
                        )}
                    </div>

                    {/* Section 2: Pipeline Upload */}
                    <div className="border border-gray-200 p-4">
                        <h3 className="font-bold mb-3 flex items-center gap-2">
                            <CloudArrowUp size={20} weight="bold" className="text-[#002FA7]" />
                            Section 2: HR Internal Pipeline Data
                        </h3>
                        
                        {pipelineResult ? (
                            <div className="bg-green-50 border border-green-200 p-4">
                                <div className="flex items-center gap-2 mb-2">
                                    <CheckCircle size={20} weight="fill" className="text-green-600" />
                                    <p className="font-semibold text-green-800">{pipelineResult.message}</p>
                                </div>
                                <p className="text-sm text-green-700">Inserted: {pipelineResult.inserted}, Updated: {pipelineResult.updated}</p>
                            </div>
                        ) : (
                            <>
                                <div 
                                    className="upload-zone cursor-pointer min-h-[120px]"
                                    onClick={() => document.getElementById('pipeline-file').click()}
                                    data-testid="pipeline-upload-zone"
                                >
                                    <input
                                        id="pipeline-file"
                                        type="file"
                                        accept=".csv,.xlsx"
                                        onChange={(e) => setPipelineFile(e.target.files[0])}
                                        className="hidden"
                                    />
                                    {pipelineFile ? (
                                        <div className="flex items-center gap-3">
                                            <FileXls size={32} weight="duotone" className="text-[#002FA7]" />
                                            <div>
                                                <p className="font-semibold">{pipelineFile.name}</p>
                                                <p className="text-sm text-gray-500">{(pipelineFile.size / 1024).toFixed(1)} KB</p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="text-center">
                                            <CloudArrowUp size={32} className="text-gray-400 mx-auto mb-2" />
                                            <p className="text-sm text-gray-500">Click to upload Pipeline file (CSV/XLSX)</p>
                                        </div>
                                    )}
                                </div>
                                {pipelineFile && (
                                    <button
                                        onClick={handlePipelineUpload}
                                        disabled={pipelineUploading}
                                        className="btn-primary w-full mt-3 flex items-center justify-center gap-2"
                                    >
                                        {pipelineUploading ? (
                                            <>
                                                <div className="spinner w-4 h-4 border-white border-t-transparent"></div>
                                                Uploading...
                                            </>
                                        ) : (
                                            'Upload Pipeline Data'
                                        )}
                                    </button>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

// Hierarchical Panel Component
function HierarchyPanel({ 
    icon: Icon, 
    title, 
    count, 
    color, 
    onClick, 
    onExpand, 
    isExpanded, 
    children, 
    level = 0,
    testId 
}) {
    const hasChildren = children && children.length > 0;
    const paddingLeft = level * 24;

    return (
        <div>
            <div 
                className="flex items-center border border-gray-200 bg-white hover:border-[#002FA7] transition-all cursor-pointer"
                style={{ marginLeft: paddingLeft }}
            >
                {hasChildren && (
                    <button 
                        onClick={(e) => { e.stopPropagation(); onExpand(); }}
                        className="px-3 py-4 border-r border-gray-200 hover:bg-gray-50"
                    >
                        {isExpanded ? <CaretDown size={18} weight="bold" /> : <CaretRight size={18} weight="bold" />}
                    </button>
                )}
                <div 
                    className="flex-1 flex items-center justify-between px-4 py-4"
                    onClick={onClick}
                    data-testid={testId}
                >
                    <div className="flex items-center gap-3">
                        <Icon size={24} weight="bold" style={{ color }} />
                        <span className="font-semibold">{title}</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold" style={{ color }}>{count}</span>
                        <CaretRight size={18} className="text-gray-400" />
                    </div>
                </div>
            </div>
            
            <AnimatePresence>
                {isExpanded && hasChildren && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="space-y-2 mt-2"
                    >
                        {children}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export default function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    
    const [counts, setCounts] = useState(null);
    const [loading, setLoading] = useState(true);
    const [uploadModalOpen, setUploadModalOpen] = useState(false);
    const [tableModal, setTableModal] = useState({ open: false, title: '', endpoint: '', columns: [] });
    
    // Expansion states
    const [registeredExpanded, setRegisteredExpanded] = useState(false);
    const [shortlistedExpanded, setShortlistedExpanded] = useState(false);
    const [scheduledExpanded, setScheduledExpanded] = useState(false);

    const fetchCounts = useCallback(async () => {
        try {
            const response = await axios.get(`${API}/api/dashboard-counts`, {
                withCredentials: true
            });
            setCounts(response.data);
        } catch (error) {
            console.error('Failed to fetch counts:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchCounts();
    }, [fetchCounts]);

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const openTableModal = (title, endpoint, columns) => {
        setTableModal({ open: true, title, endpoint, columns });
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#F9FAFB]">
                <div className="flex flex-col items-center gap-4">
                    <div className="spinner"></div>
                    <p className="label-small">Loading dashboard...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#F9FAFB]">
            {/* Header */}
            <header className="bg-white border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 bg-[#002FA7] flex items-center justify-center">
                                <ChartBar size={20} weight="bold" className="text-white" />
                            </div>
                            <span className="font-bold text-lg tracking-tight">RECRUIT<span className="text-[#002FA7]">IQ</span></span>
                        </div>

                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setUploadModalOpen(true)}
                                className="btn-primary flex items-center gap-2"
                                data-testid="upload-datasets-btn"
                            >
                                <Upload size={18} weight="bold" />
                                Upload Datasets
                            </button>
                            <span className="text-sm text-gray-600">Welcome, {user}</span>
                            <button
                                onClick={handleLogout}
                                className="flex items-center gap-2 text-sm text-gray-600 hover:text-[#E63946] transition-colors"
                                data-testid="logout-btn"
                            >
                                <SignOut size={18} weight="bold" />
                                Logout
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    <h1 className="heading-1 mb-2">Analytics Dashboard</h1>
                    <p className="text-gray-500 mb-8">Click panels to view detailed data. Expand to drill down.</p>

                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                        <div className="stat-card">
                            <div className="flex items-center gap-2 mb-2">
                                <Users size={20} weight="bold" className="text-[#002FA7]" />
                                <span className="label-small">Total Applies</span>
                            </div>
                            <p className="stat-value">{counts?.total_applies || 0}</p>
                        </div>
                        <div className="stat-card">
                            <div className="flex items-center gap-2 mb-2">
                                <UserCheck size={20} weight="bold" className="text-green-600" />
                                <span className="label-small">Registered</span>
                            </div>
                            <p className="stat-value text-green-600">{counts?.registered || 0}</p>
                        </div>
                        <div className="stat-card">
                            <div className="flex items-center gap-2 mb-2">
                                <UserMinus size={20} weight="bold" className="text-red-500" />
                                <span className="label-small">Unregistered</span>
                            </div>
                            <p className="stat-value text-red-500">{counts?.unregistered || 0}</p>
                        </div>
                    </div>

                    {/* Hierarchical Panels */}
                    <div className="space-y-3">
                        {/* Unregistered Panel */}
                        <HierarchyPanel
                            icon={UserMinus}
                            title="Unregistered Applicants"
                            count={counts?.unregistered || 0}
                            color="#EF4444"
                            onClick={() => openTableModal(
                                'Unregistered Applicants',
                                'unregistered',
                                ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth']
                            )}
                            testId="panel-unregistered"
                        />

                        {/* Registered Panel */}
                        <HierarchyPanel
                            icon={UserCheck}
                            title="Registered Applicants"
                            count={counts?.registered || 0}
                            color="#10B981"
                            onClick={() => openTableModal(
                                'Registered Applicants',
                                'registered',
                                ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth']
                            )}
                            onExpand={() => setRegisteredExpanded(!registeredExpanded)}
                            isExpanded={registeredExpanded}
                            testId="panel-registered"
                        >
                            {/* Shortlisted */}
                            <HierarchyPanel
                                icon={CheckCircle}
                                title="Shortlisted Applicants"
                                count={counts?.shortlisted || 0}
                                color="#3B82F6"
                                level={1}
                                onClick={() => openTableModal(
                                    'Shortlisted Applicants',
                                    'shortlisted',
                                    ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'location', 'email_type']
                                )}
                                onExpand={() => setShortlistedExpanded(!shortlistedExpanded)}
                                isExpanded={shortlistedExpanded}
                                testId="panel-shortlisted"
                            >
                                {/* Scheduled */}
                                <HierarchyPanel
                                    icon={Calendar}
                                    title="Interview Scheduled"
                                    count={counts?.scheduled || 0}
                                    color="#8B5CF6"
                                    level={2}
                                    onClick={() => openTableModal(
                                        'Interview Scheduled',
                                        'scheduled',
                                        ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'schedule_date', 'schedule_time', 'reschedule_count']
                                    )}
                                    onExpand={() => setScheduledExpanded(!scheduledExpanded)}
                                    isExpanded={scheduledExpanded}
                                    testId="panel-scheduled"
                                >
                                    {/* Attended */}
                                    <HierarchyPanel
                                        icon={CheckCircle}
                                        title="Attended"
                                        count={counts?.attended || 0}
                                        color="#059669"
                                        level={3}
                                        onClick={() => openTableModal(
                                            'Attended Applicants',
                                            'attended',
                                            ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth', 'schedule_date', 'schedule_time', 'reschedule_count', 'otp_verified', 'result_mail', 'result_update', 'result_status']
                                        )}
                                        testId="panel-attended"
                                    />
                                    {/* Not Attended */}
                                    <HierarchyPanel
                                        icon={ClockClockwise}
                                        title="Not Attended"
                                        count={counts?.not_attended || 0}
                                        color="#F59E0B"
                                        level={3}
                                        onClick={() => openTableModal(
                                            'Not Attended Applicants',
                                            'not-attended',
                                            ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth', 'schedule_date', 'schedule_time', 'reschedule_count', 'otp_verified', 'otp_expired']
                                        )}
                                        testId="panel-not-attended"
                                    />
                                </HierarchyPanel>

                                {/* Not Scheduled */}
                                <HierarchyPanel
                                    icon={CalendarX}
                                    title="Interview Not Scheduled"
                                    count={counts?.not_scheduled || 0}
                                    color="#6B7280"
                                    level={2}
                                    onClick={() => openTableModal(
                                        'Interview Not Scheduled',
                                        'not-scheduled',
                                        ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth', 'location', 'loca_change', 'attend_inperson', 'email_type', 'confirm_box']
                                    )}
                                    testId="panel-not-scheduled"
                                />
                            </HierarchyPanel>

                            {/* Rejected */}
                            <HierarchyPanel
                                icon={XCircle}
                                title="Rejected Applicants"
                                count={counts?.rejected || 0}
                                color="#DC2626"
                                level={1}
                                onClick={() => openTableModal(
                                    'Rejected Applicants',
                                    'rejected',
                                    ['name', 'email', 'phone', 'job_title', 'date_of_application', 'gender', 'date_of_birth', 'location', 'loca_change', 'attend_inperson', 'email_type', 'confirm_box']
                                )}
                                testId="panel-rejected"
                            />
                        </HierarchyPanel>
                    </div>
                </motion.div>
            </main>

            {/* Upload Modal */}
            <AnimatePresence>
                {uploadModalOpen && (
                    <UploadModal
                        isOpen={uploadModalOpen}
                        onClose={() => setUploadModalOpen(false)}
                        onUploadComplete={fetchCounts}
                    />
                )}
            </AnimatePresence>

            {/* Data Table Modal */}
            <AnimatePresence>
                {tableModal.open && (
                    <DataTableModal
                        isOpen={tableModal.open}
                        onClose={() => setTableModal({ open: false, title: '', endpoint: '', columns: [] })}
                        title={tableModal.title}
                        endpoint={tableModal.endpoint}
                        columns={tableModal.columns}
                    />
                )}
            </AnimatePresence>
        </div>
    );
}
