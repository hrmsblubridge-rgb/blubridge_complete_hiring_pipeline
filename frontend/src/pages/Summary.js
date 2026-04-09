import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, MagnifyingGlass, FunnelSimple, ArrowCounterClockwise, SpinnerGap } from '@phosphor-icons/react';

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

export default function Summary() {
    const navigate = useNavigate();
    const [data, setData] = useState([]);
    const [totalRegistered, setTotalRegistered] = useState(0);
    const [loading, setLoading] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [search, setSearch] = useState('');
    const [activeFilters, setActiveFilters] = useState({ startDate: '', endDate: '', search: '' });

    const fetchData = useCallback(async (filters = {}) => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (filters.startDate) params.append('startDate', filters.startDate);
            if (filters.endDate) params.append('endDate', filters.endDate);
            if (filters.search) params.append('search', filters.search);
            const res = await axios.get(`${API}/api/summary?${params}`, { withCredentials: true });
            setData(res.data.data);
            setTotalRegistered(res.data.total_registered);
        } catch (err) {
            toast.error('Failed to load summary data');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        let mounted = true;
        if (mounted) fetchData();
        return () => { mounted = false; };
    }, [fetchData]);

    const handleFilter = () => {
        const filters = { startDate, endDate, search };
        setActiveFilters(filters);
        fetchData(filters);
    };

    const handleReset = () => {
        setStartDate('');
        setEndDate('');
        setSearch('');
        setActiveFilters({ startDate: '', endDate: '', search: '' });
        fetchData({});
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="summary-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/dashboard')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="text-xl font-semibold tracking-tight">Applicants Summary Statistics</h1>
                {!loading && (
                    <span className="ml-auto text-sm text-zinc-500" data-testid="total-registered">
                        Total Registered: {totalRegistered}
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
                    <div className="space-y-1.5 flex-1 min-w-[200px]">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Search Job Role</label>
                        <div className="relative">
                            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                                placeholder="e.g. Engineer, Analyst..."
                                onKeyDown={e => e.key === 'Enter' && handleFilter()}
                                data-testid="search-input"
                                className="block w-full bg-zinc-900 border border-zinc-700 pl-9 pr-3 py-2 text-sm placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500" />
                        </div>
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
                {(activeFilters.startDate || activeFilters.endDate || activeFilters.search) && (
                    <div className="mt-3 flex gap-2 text-xs text-zinc-500">
                        <span>Active filters:</span>
                        {activeFilters.startDate && <span className="bg-zinc-800 px-2 py-0.5">From: {activeFilters.startDate}</span>}
                        {activeFilters.endDate && <span className="bg-zinc-800 px-2 py-0.5">To: {activeFilters.endDate}</span>}
                        {activeFilters.search && <span className="bg-zinc-800 px-2 py-0.5">Search: {activeFilters.search}</span>}
                    </div>
                )}
            </div>

            {/* Table */}
            <div className="px-8 py-6">
                {loading ? (
                    <div className="flex items-center justify-center py-20" data-testid="loading-spinner">
                        <SpinnerGap size={32} className="animate-spin text-zinc-500" />
                    </div>
                ) : data.length === 0 ? (
                    <div className="text-center py-20 text-zinc-500" data-testid="empty-state">
                        No data available. Upload both datasets first.
                    </div>
                ) : (
                    <div className="overflow-x-auto border border-zinc-800" data-testid="summary-table">
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
                                    <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors"
                                        data-testid={`summary-row-${i}`}>
                                        {COLUMNS.map(col => (
                                            <td key={col.key} className={`px-4 py-3 whitespace-nowrap ${col.key === 'job_role' ? 'font-medium' : 'text-zinc-400 tabular-nums'}`}>
                                                {row[col.key] ?? '-'}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                                {/* Totals row */}
                                <tr className="bg-zinc-900/70 font-medium border-t border-zinc-700" data-testid="summary-totals-row">
                                    <td className="px-4 py-3">TOTAL</td>
                                    {COLUMNS.slice(1).map(col => (
                                        <td key={col.key} className="px-4 py-3 tabular-nums">
                                            {data.reduce((sum, row) => sum + (row[col.key] || 0), 0)}
                                        </td>
                                    ))}
                                </tr>
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
