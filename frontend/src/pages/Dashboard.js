import { useState, useEffect, useCallback } from 'react';
import { Layout } from '../components/Layout';
import { motion } from 'framer-motion';
import { 
    Funnel, 
    Users, 
    UserCheck, 
    UserMinus, 
    ListChecks, 
    XCircle as XCircleIcon,
    Calendar,
    CalendarX,
    CheckCircle,
    Clock,
    DownloadSimple,
    ArrowsClockwise,
    ChartBar
} from '@phosphor-icons/react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const CHART_COLORS = ['#002FA7', '#4361EE', '#374151', '#9CA3AF', '#0A0A0A'];

export default function Dashboard() {
    const [analytics, setAnalytics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState(false);
    const [selectedRole, setSelectedRole] = useState('all');
    const [error, setError] = useState('');

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

    useEffect(() => {
        fetchAnalytics(selectedRole);
    }, [fetchAnalytics, selectedRole]);

    const handleProcess = async () => {
        setProcessing(true);
        try {
            await axios.post(`${API}/api/process`, {}, {
                withCredentials: true
            });
            await fetchAnalytics(selectedRole);
        } catch (err) {
            setError('Processing failed');
            console.error(err);
        } finally {
            setProcessing(false);
        }
    };

    const handleDownload = async () => {
        try {
            const params = selectedRole !== 'all' ? `?job_role=${encodeURIComponent(selectedRole)}` : '';
            const response = await axios.get(`${API}/api/analytics/download${params}`, {
                withCredentials: true,
                responseType: 'blob'
            });
            
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', 'analytics_report.csv');
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError('Download failed');
            console.error(err);
        }
    };

    const handleRoleChange = (value) => {
        setSelectedRole(value);
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

    // Calculate funnel percentages
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
            label: 'Shortlisted', 
            value: analytics.shortlisted, 
            icon: ListChecks,
            color: CHART_COLORS[2],
            width: getPercentage(analytics.shortlisted, analytics.registered) || 60
        },
        { 
            label: 'Scheduled', 
            value: analytics.scheduled, 
            icon: Calendar,
            color: CHART_COLORS[3],
            width: getPercentage(analytics.scheduled, analytics.shortlisted) || 40
        },
        { 
            label: 'Attended', 
            value: analytics.attended, 
            icon: CheckCircle,
            color: CHART_COLORS[4],
            width: getPercentage(analytics.attended, analytics.scheduled) || 25
        },
    ] : [];

    return (
        <Layout>
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                data-testid="dashboard-content"
            >
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
                    <div>
                        <h1 className="heading-1 mb-1">Recruitment Funnel</h1>
                        <p className="text-gray-500">Analyze your candidate pipeline</p>
                    </div>
                    
                    <div className="flex flex-wrap items-center gap-3">
                        {/* Job Role Filter */}
                        <Select value={selectedRole} onValueChange={handleRoleChange}>
                            <SelectTrigger 
                                className="w-[180px] rounded-none border-gray-200" 
                                data-testid="filter-job-role"
                            >
                                <SelectValue placeholder="All Roles" />
                            </SelectTrigger>
                            <SelectContent className="rounded-none">
                                <SelectItem value="all" className="rounded-none">All Roles</SelectItem>
                                {analytics?.job_roles?.map((role) => (
                                    <SelectItem key={role} value={role} className="rounded-none">
                                        {role}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {/* Process Button */}
                        <button
                            onClick={handleProcess}
                            disabled={processing}
                            className="btn-primary flex items-center gap-2"
                            data-testid="process-data-button"
                        >
                            <ArrowsClockwise 
                                size={18} 
                                weight="bold" 
                                className={processing ? 'animate-spin' : ''}
                            />
                            {processing ? 'Processing...' : 'Process Data'}
                        </button>

                        {/* Download Button */}
                        {hasData && (
                            <button
                                onClick={handleDownload}
                                className="flex items-center gap-2 px-4 py-3 border border-gray-200 font-bold text-sm uppercase tracking-wider hover:bg-gray-50 transition-colors"
                                data-testid="download-csv-button"
                            >
                                <DownloadSimple size={18} weight="bold" />
                                CSV
                            </button>
                        )}
                    </div>
                </div>

                {error && (
                    <div className="mb-6 flex items-start gap-3 bg-red-50 border border-red-200 p-4">
                        <XCircleIcon size={20} weight="fill" className="text-red-500 flex-shrink-0 mt-0.5" />
                        <p className="text-red-700 text-sm">{error}</p>
                    </div>
                )}

                {!hasData ? (
                    /* Empty State */
                    <div className="flex flex-col items-center justify-center min-h-[400px] border border-gray-200 bg-white">
                        <ChartBar size={64} weight="duotone" className="text-gray-300 mb-4" />
                        <h2 className="heading-3 mb-2">No Data Available</h2>
                        <p className="text-gray-500 text-center max-w-md mb-6">
                            Upload your Naukri Applies and Pipeline Data, then click "Process Data" to generate analytics.
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
                                    <CheckCircle size={20} weight="bold" className="text-[#002FA7]" />
                                    <span className="label-small">Attended</span>
                                </div>
                                <p className="stat-value">{analytics.attended}</p>
                            </div>
                        </div>

                        {/* Funnel Visualization */}
                        <div className="card mb-8" data-testid="funnel-chart">
                            <div className="flex items-center gap-2 mb-6">
                                <Funnel size={24} weight="bold" className="text-[#002FA7]" />
                                <h2 className="heading-3">Recruitment Funnel</h2>
                            </div>

                            <div className="space-y-4">
                                {funnelStages.map((stage, index) => (
                                    <motion.div
                                        key={stage.label}
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: index * 0.1 }}
                                        className="funnel-stage"
                                    >
                                        <div 
                                            className="flex items-center justify-between px-4 py-4 border border-gray-200 transition-all hover:border-[#002FA7]"
                                            style={{ 
                                                width: `${Math.max(stage.width, 30)}%`,
                                                marginLeft: 'auto',
                                                marginRight: 'auto',
                                                backgroundColor: `${stage.color}08`
                                            }}
                                        >
                                            <div className="flex items-center gap-3">
                                                <stage.icon size={20} weight="bold" style={{ color: stage.color }} />
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

                        {/* Detailed Stats */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Shortlisting Status */}
                            <div className="card">
                                <h3 className="heading-3 mb-4">Shortlisting Status</h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200">
                                        <div className="flex items-center gap-2">
                                            <ListChecks size={18} weight="bold" className="text-green-600" />
                                            <span className="font-medium">Shortlisted</span>
                                        </div>
                                        <span className="font-bold text-green-600">{analytics.shortlisted}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-red-50 border border-red-200">
                                        <div className="flex items-center gap-2">
                                            <XCircleIcon size={18} weight="bold" className="text-red-500" />
                                            <span className="font-medium">Rejected</span>
                                        </div>
                                        <span className="font-bold text-red-500">{analytics.rejected}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Scheduling Status */}
                            <div className="card">
                                <h3 className="heading-3 mb-4">Scheduling Status</h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between p-3 bg-blue-50 border border-blue-200">
                                        <div className="flex items-center gap-2">
                                            <Calendar size={18} weight="bold" className="text-blue-600" />
                                            <span className="font-medium">Scheduled</span>
                                        </div>
                                        <span className="font-bold text-blue-600">{analytics.scheduled}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200">
                                        <div className="flex items-center gap-2">
                                            <CalendarX size={18} weight="bold" className="text-gray-600" />
                                            <span className="font-medium">Not Scheduled</span>
                                        </div>
                                        <span className="font-bold text-gray-600">{analytics.not_scheduled}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Attendance Status */}
                            <div className="card md:col-span-2">
                                <h3 className="heading-3 mb-4">Attendance Status</h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200">
                                        <div className="flex items-center gap-2">
                                            <CheckCircle size={18} weight="bold" className="text-green-600" />
                                            <span className="font-medium">Attended</span>
                                        </div>
                                        <span className="font-bold text-green-600">{analytics.attended}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-orange-50 border border-orange-200">
                                        <div className="flex items-center gap-2">
                                            <Clock size={18} weight="bold" className="text-orange-600" />
                                            <span className="font-medium">Not Attended</span>
                                        </div>
                                        <span className="font-bold text-orange-600">{analytics.not_attended}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </>
                )}
            </motion.div>
        </Layout>
    );
}
