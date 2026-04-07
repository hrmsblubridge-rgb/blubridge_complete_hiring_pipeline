import { useState, useEffect, useCallback } from 'react';
import { Layout } from '../components/Layout';
import { motion } from 'framer-motion';
import { 
    Funnel, 
    Users, 
    UserCheck, 
    UserMinus, 
    DownloadSimple,
    ArrowsClockwise,
    ChartBar,
    Table as TableIcon,
    List,
    MagnifyingGlass,
    CaretLeft,
    CaretRight,
    Trash
} from '@phosphor-icons/react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const CHART_COLORS = ['#002FA7', '#4361EE', '#374151', '#9CA3AF', '#0A0A0A', '#10B981', '#F59E0B', '#EF4444'];

export default function Dashboard() {
    const [analytics, setAnalytics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState(false);
    const [selectedRole, setSelectedRole] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');
    const [selectedRegistration, setSelectedRegistration] = useState('all');
    const [error, setError] = useState('');
    const [activeTab, setActiveTab] = useState('summary');
    
    // Data table state
    const [dataSource, setDataSource] = useState('processed');
    const [tableData, setTableData] = useState(null);
    const [tableLoading, setTableLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize] = useState(25);

    const fetchAnalytics = useCallback(async (jobRole = 'all') => {
        try {
            const params = jobRole !== 'all' ? `?job_role=${encodeURIComponent(jobRole)}` : '';
            const response = await axios.get(`${API}/api/analytics${params}`, {
                withCredentials: true
            });
            setAnalytics(response.data);
            setError('');
        } catch (err) {
            setError('Failed to load analytics');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchTableData = useCallback(async () => {
        setTableLoading(true);
        try {
            const params = new URLSearchParams({
                source: dataSource,
                page: currentPage.toString(),
                limit: pageSize.toString()
            });
            
            if (selectedRole !== 'all') params.append('job_role', selectedRole);
            if (selectedStatus !== 'all') params.append('status', selectedStatus);
            if (selectedRegistration !== 'all') params.append('registration', selectedRegistration);
            if (searchTerm) params.append('search', searchTerm);
            
            const response = await axios.get(`${API}/api/data?${params}`, {
                withCredentials: true
            });
            setTableData(response.data);
        } catch (err) {
            console.error('Failed to load table data:', err);
        } finally {
            setTableLoading(false);
        }
    }, [dataSource, currentPage, pageSize, selectedRole, selectedStatus, selectedRegistration, searchTerm]);

    useEffect(() => {
        fetchAnalytics(selectedRole);
    }, [fetchAnalytics, selectedRole]);

    useEffect(() => {
        if (activeTab === 'data') {
            fetchTableData();
        }
    }, [activeTab, fetchTableData]);

    const handleProcess = async () => {
        setProcessing(true);
        try {
            await axios.post(`${API}/api/process-data`, {}, {
                withCredentials: true
            });
            await fetchAnalytics(selectedRole);
            if (activeTab === 'data') {
                await fetchTableData();
            }
        } catch (err) {
            setError('Processing failed');
            console.error(err);
        } finally {
            setProcessing(false);
        }
    };

    const handleDownload = async (source = 'processed') => {
        try {
            const params = new URLSearchParams({ source });
            if (selectedRole !== 'all') params.append('job_role', selectedRole);
            if (selectedStatus !== 'all') params.append('status', selectedStatus);
            if (selectedRegistration !== 'all') params.append('registration', selectedRegistration);
            
            const response = await axios.get(`${API}/api/analytics/download?${params}`, {
                withCredentials: true,
                responseType: 'blob'
            });
            
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `${source}_data.csv`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError('Download failed');
            console.error(err);
        }
    };

    const handleReset = async (source = 'all') => {
        if (!window.confirm(`Are you sure you want to reset ${source} data? This cannot be undone.`)) {
            return;
        }
        try {
            await axios.delete(`${API}/api/reset-data?source=${source}`, {
                withCredentials: true
            });
            await fetchAnalytics(selectedRole);
            if (activeTab === 'data') {
                await fetchTableData();
            }
        } catch (err) {
            setError('Reset failed');
            console.error(err);
        }
    };

    const handleSearch = (e) => {
        e.preventDefault();
        setCurrentPage(1);
        fetchTableData();
    };

    if (loading) {
        return (
            <Layout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <div className="flex flex-col items-center gap-4">
                        <div className="spinner"></div>
                        <p className="label-small">Loading analytics...</p>
                    </div>
                </div>
            </Layout>
        );
    }

    const hasData = analytics && analytics.total_naukri_applies > 0;
    const statusBreakdown = analytics?.status_breakdown || {};
    const jobRoles = analytics?.job_roles || [];
    const statusValues = Object.keys(statusBreakdown);

    // Calculate funnel with dynamic status
    const getPercentage = (value, total) => {
        if (total === 0) return 0;
        return Math.round((value / total) * 100);
    };

    const funnelStages = hasData ? [
        { 
            label: 'Total Applies', 
            value: analytics.total_naukri_applies, 
            icon: Users,
            color: CHART_COLORS[0],
            width: 100
        },
        { 
            label: 'Registered', 
            value: analytics.registered, 
            icon: UserCheck,
            color: CHART_COLORS[1],
            width: getPercentage(analytics.registered, analytics.total_naukri_applies) || 85
        },
        { 
            label: 'Not Registered', 
            value: analytics.not_registered, 
            icon: UserMinus,
            color: CHART_COLORS[7],
            width: getPercentage(analytics.not_registered, analytics.total_naukri_applies) || 15,
            isSecondary: true
        },
    ] : [];

    // Get current data for table
    const currentData = tableData?.[dataSource]?.data || [];
    const currentColumns = tableData?.[dataSource]?.columns || [];
    const totalRecords = tableData?.[dataSource]?.total || 0;
    const totalPages = Math.ceil(totalRecords / pageSize);

    // Filter columns to show (exclude internal fields except important ones)
    const displayColumns = currentColumns.filter(col => 
        !col.startsWith('_') || 
        ['_registration_status', '_pipeline_status', '_normalized_email', '_normalized_phone'].includes(col)
    );

    return (
        <Layout>
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                data-testid="dashboard-content"
            >
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
                    <div>
                        <h1 className="heading-1 mb-1">Recruitment Analytics</h1>
                        <p className="text-gray-500">Dynamic schema-driven analysis</p>
                    </div>
                    
                    <div className="flex flex-wrap items-center gap-3">
                        {/* Job Role Filter */}
                        {jobRoles.length > 0 && (
                            <Select value={selectedRole} onValueChange={(v) => { setSelectedRole(v); setCurrentPage(1); }}>
                                <SelectTrigger className="w-[180px] rounded-none border-gray-200" data-testid="filter-job-role">
                                    <SelectValue placeholder="All Roles" />
                                </SelectTrigger>
                                <SelectContent className="rounded-none">
                                    <SelectItem value="all" className="rounded-none">All Roles</SelectItem>
                                    {jobRoles.map((role) => (
                                        <SelectItem key={role} value={role} className="rounded-none">{role}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}

                        {/* Process Button */}
                        <button
                            onClick={handleProcess}
                            disabled={processing}
                            className="btn-primary flex items-center gap-2"
                            data-testid="process-data-button"
                        >
                            <ArrowsClockwise size={18} weight="bold" className={processing ? 'animate-spin' : ''} />
                            {processing ? 'Processing...' : 'Process Data'}
                        </button>

                        {/* Reset Button */}
                        <button
                            onClick={() => handleReset('all')}
                            className="flex items-center gap-2 px-4 py-3 border border-red-200 text-red-600 font-bold text-sm uppercase tracking-wider hover:bg-red-50 transition-colors"
                            data-testid="reset-data-button"
                        >
                            <Trash size={18} weight="bold" />
                            Reset
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="mb-6 flex items-start gap-3 bg-red-50 border border-red-200 p-4">
                        <p className="text-red-700 text-sm">{error}</p>
                    </div>
                )}

                {/* Tabs */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className="mb-6 bg-gray-100 p-1 rounded-none">
                        <TabsTrigger 
                            value="summary" 
                            className="rounded-none data-[state=active]:bg-white data-[state=active]:shadow-none flex items-center gap-2"
                        >
                            <ChartBar size={18} weight="bold" />
                            Summary Funnel
                        </TabsTrigger>
                        <TabsTrigger 
                            value="data"
                            className="rounded-none data-[state=active]:bg-white data-[state=active]:shadow-none flex items-center gap-2"
                        >
                            <TableIcon size={18} weight="bold" />
                            Detailed Data
                        </TabsTrigger>
                    </TabsList>

                    {/* Summary Tab */}
                    <TabsContent value="summary">
                        {!hasData ? (
                            <div className="flex flex-col items-center justify-center min-h-[400px] border border-gray-200 bg-white">
                                <ChartBar size={64} weight="duotone" className="text-gray-300 mb-4" />
                                <h2 className="heading-3 mb-2">No Data Available</h2>
                                <p className="text-gray-500 text-center max-w-md mb-6">
                                    Upload your data files and click "Process Data" to generate analytics.
                                </p>
                            </div>
                        ) : (
                            <>
                                {/* Summary Stats */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                                    <div className="stat-card">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Users size={20} weight="bold" className="text-[#002FA7]" />
                                            <span className="label-small">Total Applies</span>
                                        </div>
                                        <p className="stat-value">{analytics.total_naukri_applies}</p>
                                    </div>
                                    <div className="stat-card">
                                        <div className="flex items-center gap-2 mb-2">
                                            <UserCheck size={20} weight="bold" className="text-green-600" />
                                            <span className="label-small">Registered</span>
                                        </div>
                                        <p className="stat-value text-green-600">{analytics.registered}</p>
                                    </div>
                                    <div className="stat-card">
                                        <div className="flex items-center gap-2 mb-2">
                                            <UserMinus size={20} weight="bold" className="text-red-500" />
                                            <span className="label-small">Not Registered</span>
                                        </div>
                                        <p className="stat-value text-red-500">{analytics.not_registered}</p>
                                    </div>
                                    <div className="stat-card">
                                        <div className="flex items-center gap-2 mb-2">
                                            <List size={20} weight="bold" className="text-[#002FA7]" />
                                            <span className="label-small">Statuses Found</span>
                                        </div>
                                        <p className="stat-value">{statusValues.length}</p>
                                    </div>
                                </div>

                                {/* Funnel Visualization */}
                                <div className="card mb-8" data-testid="funnel-chart">
                                    <div className="flex items-center justify-between mb-6">
                                        <div className="flex items-center gap-2">
                                            <Funnel size={24} weight="bold" className="text-[#002FA7]" />
                                            <h2 className="heading-3">Recruitment Funnel</h2>
                                        </div>
                                        <button
                                            onClick={() => handleDownload('processed')}
                                            className="flex items-center gap-2 px-4 py-2 border border-gray-200 font-bold text-xs uppercase tracking-wider hover:bg-gray-50 transition-colors"
                                            data-testid="download-csv-button"
                                        >
                                            <DownloadSimple size={16} weight="bold" />
                                            CSV
                                        </button>
                                    </div>

                                    <div className="space-y-3">
                                        {funnelStages.map((stage, index) => (
                                            <motion.div
                                                key={stage.label}
                                                initial={{ opacity: 0, x: -20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: index * 0.1 }}
                                                className="funnel-stage"
                                            >
                                                <div 
                                                    className={`flex items-center justify-between px-4 py-3 border transition-all hover:border-[#002FA7] ${stage.isSecondary ? 'border-dashed' : 'border-gray-200'}`}
                                                    style={{ 
                                                        width: `${Math.max(stage.width, 30)}%`,
                                                        marginLeft: 'auto',
                                                        marginRight: 'auto',
                                                        backgroundColor: `${stage.color}08`
                                                    }}
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <stage.icon size={18} weight="bold" style={{ color: stage.color }} />
                                                        <span className="font-semibold text-sm">{stage.label}</span>
                                                    </div>
                                                    <span className="font-bold text-lg" style={{ color: stage.color }}>
                                                        {stage.value}
                                                    </span>
                                                </div>
                                            </motion.div>
                                        ))}
                                    </div>
                                </div>

                                {/* Dynamic Status Breakdown */}
                                {statusValues.length > 0 && (
                                    <div className="card">
                                        <h3 className="heading-3 mb-4">Status Breakdown (From Registered)</h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                            {statusValues.map((status, idx) => (
                                                <div 
                                                    key={status}
                                                    className="flex items-center justify-between p-3 border border-gray-200"
                                                    style={{ backgroundColor: `${CHART_COLORS[idx % CHART_COLORS.length]}08` }}
                                                >
                                                    <span className="font-medium capitalize">{status || 'Unknown'}</span>
                                                    <span 
                                                        className="font-bold"
                                                        style={{ color: CHART_COLORS[idx % CHART_COLORS.length] }}
                                                    >
                                                        {statusBreakdown[status]}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </TabsContent>

                    {/* Data Tab */}
                    <TabsContent value="data">
                        {/* Data Source & Filters */}
                        <div className="card mb-6">
                            <div className="flex flex-col md:flex-row md:items-center gap-4">
                                {/* Data Source */}
                                <Select value={dataSource} onValueChange={(v) => { setDataSource(v); setCurrentPage(1); }}>
                                    <SelectTrigger className="w-[180px] rounded-none border-gray-200" data-testid="data-source-select">
                                        <SelectValue placeholder="Select Source" />
                                    </SelectTrigger>
                                    <SelectContent className="rounded-none">
                                        <SelectItem value="processed" className="rounded-none">Processed Data</SelectItem>
                                        <SelectItem value="naukri" className="rounded-none">Naukri Applies</SelectItem>
                                        <SelectItem value="pipeline" className="rounded-none">Pipeline Data</SelectItem>
                                    </SelectContent>
                                </Select>

                                {/* Registration Filter (for processed) */}
                                {dataSource === 'processed' && (
                                    <Select value={selectedRegistration} onValueChange={(v) => { setSelectedRegistration(v); setCurrentPage(1); }}>
                                        <SelectTrigger className="w-[180px] rounded-none border-gray-200">
                                            <SelectValue placeholder="Registration" />
                                        </SelectTrigger>
                                        <SelectContent className="rounded-none">
                                            <SelectItem value="all" className="rounded-none">All</SelectItem>
                                            <SelectItem value="registered" className="rounded-none">Registered</SelectItem>
                                            <SelectItem value="not_registered" className="rounded-none">Not Registered</SelectItem>
                                        </SelectContent>
                                    </Select>
                                )}

                                {/* Status Filter */}
                                {(dataSource === 'processed' || dataSource === 'pipeline') && statusValues.length > 0 && (
                                    <Select value={selectedStatus} onValueChange={(v) => { setSelectedStatus(v); setCurrentPage(1); }}>
                                        <SelectTrigger className="w-[180px] rounded-none border-gray-200">
                                            <SelectValue placeholder="Status" />
                                        </SelectTrigger>
                                        <SelectContent className="rounded-none">
                                            <SelectItem value="all" className="rounded-none">All Statuses</SelectItem>
                                            {statusValues.map((status) => (
                                                <SelectItem key={status} value={status} className="rounded-none capitalize">{status}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                )}

                                {/* Search */}
                                <form onSubmit={handleSearch} className="flex-1 flex gap-2">
                                    <div className="relative flex-1">
                                        <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                                        <input
                                            type="text"
                                            value={searchTerm}
                                            onChange={(e) => setSearchTerm(e.target.value)}
                                            placeholder="Search by name, email, phone..."
                                            className="input w-full pl-10"
                                            data-testid="search-input"
                                        />
                                    </div>
                                    <button type="submit" className="btn-primary">Search</button>
                                </form>

                                {/* Download */}
                                <button
                                    onClick={() => handleDownload(dataSource)}
                                    className="flex items-center gap-2 px-4 py-3 border border-gray-200 font-bold text-sm uppercase tracking-wider hover:bg-gray-50 transition-colors"
                                >
                                    <DownloadSimple size={18} weight="bold" />
                                    CSV
                                </button>
                            </div>
                        </div>

                        {/* Data Table */}
                        <div className="card overflow-hidden">
                            {tableLoading ? (
                                <div className="flex items-center justify-center py-12">
                                    <div className="spinner"></div>
                                </div>
                            ) : currentData.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-12">
                                    <TableIcon size={48} weight="duotone" className="text-gray-300 mb-4" />
                                    <p className="text-gray-500">No data available. Upload files first.</p>
                                </div>
                            ) : (
                                <>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm" data-testid="data-table">
                                            <thead>
                                                <tr className="bg-gray-50 border-b border-gray-200">
                                                    {displayColumns.slice(0, 10).map((col) => (
                                                        <th key={col} className="px-4 py-3 text-left font-bold uppercase text-xs tracking-wider text-gray-600 whitespace-nowrap">
                                                            {col.replace(/_/g, ' ').replace(/^_/, '')}
                                                        </th>
                                                    ))}
                                                    {displayColumns.length > 10 && (
                                                        <th className="px-4 py-3 text-left font-bold uppercase text-xs tracking-wider text-gray-400">
                                                            +{displayColumns.length - 10} more
                                                        </th>
                                                    )}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {currentData.map((row, idx) => (
                                                    <tr key={idx} className="border-b border-gray-100 hover:bg-gray-50">
                                                        {displayColumns.slice(0, 10).map((col) => (
                                                            <td key={col} className="px-4 py-3 whitespace-nowrap max-w-[200px] truncate">
                                                                {row[col] !== null && row[col] !== undefined ? String(row[col]) : '-'}
                                                            </td>
                                                        ))}
                                                        {displayColumns.length > 10 && (
                                                            <td className="px-4 py-3 text-gray-400">...</td>
                                                        )}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>

                                    {/* Pagination */}
                                    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
                                        <p className="text-sm text-gray-600">
                                            Showing {((currentPage - 1) * pageSize) + 1} - {Math.min(currentPage * pageSize, totalRecords)} of {totalRecords}
                                        </p>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                                disabled={currentPage === 1}
                                                className="p-2 border border-gray-200 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <CaretLeft size={18} weight="bold" />
                                            </button>
                                            <span className="px-4 py-2 border border-gray-200 bg-white font-semibold">
                                                {currentPage} / {totalPages || 1}
                                            </span>
                                            <button
                                                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                                disabled={currentPage >= totalPages}
                                                className="p-2 border border-gray-200 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <CaretRight size={18} weight="bold" />
                                            </button>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Schema Info */}
                        {tableData?.schemas && (
                            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                                {tableData.schemas.naukri && (
                                    <div className="card">
                                        <h4 className="label-small mb-3">Naukri Schema (Detected)</h4>
                                        <div className="space-y-2 text-sm">
                                            <p><span className="font-semibold">Columns:</span> {tableData.schemas.naukri.total_columns}</p>
                                            <p><span className="font-semibold">Email Column:</span> {tableData.schemas.naukri.email_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Phone Column:</span> {tableData.schemas.naukri.phone_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Name Column:</span> {tableData.schemas.naukri.name_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Job Role Column:</span> {tableData.schemas.naukri.job_role_column || 'Not detected'}</p>
                                        </div>
                                    </div>
                                )}
                                {tableData.schemas.pipeline && (
                                    <div className="card">
                                        <h4 className="label-small mb-3">Pipeline Schema (Detected)</h4>
                                        <div className="space-y-2 text-sm">
                                            <p><span className="font-semibold">Columns:</span> {tableData.schemas.pipeline.total_columns}</p>
                                            <p><span className="font-semibold">Email Column:</span> {tableData.schemas.pipeline.email_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Phone Column:</span> {tableData.schemas.pipeline.phone_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Status Column:</span> {tableData.schemas.pipeline.status_column || 'Not detected'}</p>
                                            <p><span className="font-semibold">Status Values:</span> {tableData.schemas.pipeline.status_values?.join(', ') || 'None'}</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </TabsContent>
                </Tabs>
            </motion.div>
        </Layout>
    );
}
