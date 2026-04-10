import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, SpinnerGap, CaretLeft, CaretRight } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const SCORE_COLUMNS = ['ZA', 'C++', 'Java', 'BA', 'LA', 'Mensa Org', 'Accounts2', 'Accounts1', 'BE', 'Mensa', 'BP', 'Total Score'];

const COLUMNS = [
    { key: 'name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'phone', label: 'Phone' },
    { key: 'gender', label: 'Gender' },
    { key: 'date_of_birth', label: 'Date of Birth' },
    { key: 'date_of_application', label: 'Date of Application' },
    { key: 'status', label: 'Status' },
    ...SCORE_COLUMNS.map(c => ({ key: c, label: c })),
];

const STATUS_STYLES = {
    'Rejected': 'bg-red-900/40 text-red-400 border border-red-800/50',
    'Attended': 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50',
    'Not Attended': 'bg-orange-900/40 text-orange-400 border border-orange-800/50',
    'Shortlisted': 'bg-amber-900/40 text-amber-400 border border-amber-800/50',
    'Registered': 'bg-zinc-800/60 text-zinc-400 border border-zinc-700/50',
};

export default function RoleDrillDown() {
    const navigate = useNavigate();
    const { jobRole } = useParams();
    const decodedRole = decodeURIComponent(jobRole);
    const [data, setData] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [limit] = useState(50);
    const [loading, setLoading] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');

    const fetchData = useCallback(async (filters = {}, pg = 1) => {
        setLoading(true);
        try {
            const params = { jobRole: decodedRole, page: pg, limit };
            if (filters.startDate) params.startDate = filters.startDate;
            if (filters.endDate) params.endDate = filters.endDate;
            const res = await axios.get(`${API}/api/role`, { params, withCredentials: true });
            setData(res.data.data);
            setTotal(res.data.total);
        } catch (err) {
            toast.error('Failed to load role applicants');
        } finally {
            setLoading(false);
        }
    }, [decodedRole, limit]);

    useEffect(() => {
        fetchData({}, 1);
    }, [fetchData]);

    const handleFilter = () => {
        setPage(1);
        fetchData({ startDate, endDate }, 1);
    };

    const handleReset = () => {
        setStartDate('');
        setEndDate('');
        setPage(1);
        fetchData({}, 1);
    };

    const totalPages = Math.ceil(total / limit);
    const goToPage = (pg) => {
        setPage(pg);
        fetchData({ startDate, endDate }, pg);
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
                    <p className="text-sm text-zinc-500">Applicant details</p>
                </div>
                {!loading && (
                    <span className="ml-auto text-sm text-zinc-500" data-testid="total-count">
                        Total Applicants: {total}
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
                        No applicants found for this role.
                    </div>
                ) : (
                    <>
                        <div className="overflow-x-auto border border-zinc-800" data-testid="applicant-table">
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
                                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors" data-testid={`applicant-row-${i}`}>
                                            {COLUMNS.map(col => (
                                                <td key={col.key} className="px-4 py-3 whitespace-nowrap">
                                                    {col.key === 'status' ? (
                                                        <span className={`inline-block px-2.5 py-0.5 text-xs font-medium rounded ${STATUS_STYLES[row.status] || STATUS_STYLES['Registered']}`}
                                                            data-testid={`status-badge-${i}`}>
                                                            {row.status}
                                                        </span>
                                                    ) : SCORE_COLUMNS.includes(col.key) ? (
                                                        <span className={`tabular-nums ${row[col.key] !== '-' && row[col.key] !== undefined ? 'text-cyan-400 font-medium' : 'text-zinc-600'}`}>
                                                            {row[col.key] ?? '-'}
                                                        </span>
                                                    ) : (
                                                        <span className={col.key === 'name' ? 'font-medium' : 'text-zinc-400'}>
                                                            {row[col.key] ?? '-'}
                                                        </span>
                                                    )}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination */}
                        {totalPages > 1 && (
                            <div className="flex items-center justify-between mt-4" data-testid="pagination">
                                <span className="text-sm text-zinc-500">
                                    Page {page} of {totalPages} ({total} applicants)
                                </span>
                                <div className="flex gap-2">
                                    <button onClick={() => goToPage(page - 1)} disabled={page <= 1}
                                        data-testid="prev-page-btn"
                                        className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors">
                                        <CaretLeft size={14} /> Prev
                                    </button>
                                    <button onClick={() => goToPage(page + 1)} disabled={page >= totalPages}
                                        data-testid="next-page-btn"
                                        className="flex items-center gap-1 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors">
                                        Next <CaretRight size={14} />
                                    </button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
