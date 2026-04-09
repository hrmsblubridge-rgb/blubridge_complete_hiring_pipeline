import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, SpinnerGap } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const COLUMNS = [
    { key: 'job_role', label: 'Job Role' },
    { key: 'total_applicants', label: 'Total Applicants' },
    { key: 'shortlisted', label: 'Total Shortlisted' },
    { key: 'rejected', label: 'Total Rejected' },
    { key: 'scheduled', label: 'Total Interview Scheduled' },
    { key: 'not_scheduled', label: 'Total Interview Not Scheduled' },
    { key: 'attended', label: 'Total Attended' },
    { key: 'not_attended', label: 'Total Not Attended' },
];

export default function RoleDrillDown() {
    const navigate = useNavigate();
    const { jobRole } = useParams();
    const decodedRole = decodeURIComponent(jobRole);
    const [data, setData] = useState([]);
    const [totalRegistered, setTotalRegistered] = useState(0);
    const [loading, setLoading] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');

    const fetchData = useCallback(async (filters = {}) => {
        setLoading(true);
        try {
            const params = { jobRole: decodedRole };
            if (filters.startDate) params.startDate = filters.startDate;
            if (filters.endDate) params.endDate = filters.endDate;
            const res = await axios.get(`${API}/api/role`, { params, withCredentials: true });
            setData(res.data.data);
            setTotalRegistered(res.data.total_registered);
        } catch (err) {
            toast.error('Failed to load role analytics');
        } finally {
            setLoading(false);
        }
    }, [decodedRole]);

    useEffect(() => {
        let mounted = true;
        if (mounted) fetchData();
        return () => { mounted = false; };
    }, [fetchData]);

    const handleFilter = () => fetchData({ startDate, endDate });

    const handleReset = () => {
        setStartDate('');
        setEndDate('');
        fetchData({});
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="role-drilldown-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/roles')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <div>
                    <h1 className="text-xl font-semibold tracking-tight" data-testid="role-title">{decodedRole}</h1>
                    <p className="text-sm text-zinc-500">Role-specific analytics</p>
                </div>
                {!loading && (
                    <span className="ml-auto text-sm text-zinc-500" data-testid="total-registered">
                        Registered: {totalRegistered}
                    </span>
                )}
            </header>

            {/* Filters */}
            <div className="px-8 py-5 border-b border-zinc-800" data-testid="filters-section">
                <div className="flex flex-wrap items-end gap-4">
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Start Date</label>
                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                            data-testid="start-date-input"
                            className="block w-44 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">End Date</label>
                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                            data-testid="end-date-input"
                            className="block w-44 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <button onClick={handleFilter} data-testid="filter-btn"
                        className="flex items-center gap-2 px-5 py-2 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium transition-colors">
                        <FunnelSimple size={16} /> Filter
                    </button>
                    <button onClick={handleReset} data-testid="reset-btn"
                        className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium transition-colors">
                        <ArrowCounterClockwise size={16} /> Reset
                    </button>
                </div>
            </div>

            {/* Table */}
            <div className="px-8 py-6">
                {loading ? (
                    <div className="flex items-center justify-center py-20" data-testid="loading-spinner">
                        <SpinnerGap size={32} className="animate-spin text-zinc-500" />
                    </div>
                ) : data.length === 0 ? (
                    <div className="text-center py-20 text-zinc-500" data-testid="empty-state">
                        No data available for this role.
                    </div>
                ) : (
                    <div className="overflow-x-auto border border-zinc-800" data-testid="role-table">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-zinc-900 border-b border-zinc-800">
                                    {COLUMNS.map(col => (
                                        <th key={col.key} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap">
                                            {col.label}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((row, i) => (
                                    <tr key={i} className="border-b border-zinc-800/50" data-testid={`role-row-${i}`}>
                                        {COLUMNS.map(col => (
                                            <td key={col.key} className={`px-4 py-3 whitespace-nowrap ${col.key === 'job_role' ? 'font-medium' : 'text-zinc-400 tabular-nums'}`}>
                                                {row[col.key] ?? '-'}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
