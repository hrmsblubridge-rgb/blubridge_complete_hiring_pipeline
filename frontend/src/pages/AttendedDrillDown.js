import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, SpinnerGap, CaretLeft, CaretRight, CaretDoubleLeft, CaretDoubleRight, MagnifyingGlass } from '@phosphor-icons/react';
import { formatDateDDMMYYYY } from '../utils/dateFormat';
import SortableHeader from '../components/SortableHeader';

const API = process.env.REACT_APP_BACKEND_URL;
const PAGE_SIZE = 100;

// iter70 — Round columns supplied dynamically by backend (`/api/attended`).
const BASE_COLS = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'email', label: 'Email', sortable: true },
    { key: 'phone', label: 'Phone', sortable: true },
    { key: 'age', label: 'Age' },
    { key: 'gender', label: 'Gender' },
    { key: 'college', label: 'College', sortable: true },
    { key: 'degree', label: 'Degree', sortable: true },
    { key: 'course', label: 'Course', sortable: true },
    { key: 'year_of_graduation', label: 'Year of Graduation', sortable: true },
    { key: 'job_role', label: 'Job Role', sortable: true },
    { key: 'schedule_date', label: 'Schedule Date', sortable: true },
    { key: 'result_status', label: 'Result Status', sortable: true },
];

export default function AttendedDrillDown() {
    const navigate = useNavigate();
    const { jobRole } = useParams();
    const decodedRole = decodeURIComponent(jobRole);
    const [data, setData] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [search, setSearch] = useState('');
    const [round, setRound] = useState('');
    const [goToPage, setGoToPage] = useState('');
    const [sort, setSort] = useState(null);
    // iter70 — Round columns from backend (bb_rounds, alphabetical, AFTER Result Status).
    const [roundCols, setRoundCols] = useState([]);
    const ALL_COLS = [
        ...BASE_COLS,
        ...roundCols.map(c => ({ key: c, label: c })),
    ];
    const SCORE_COLS = roundCols;

    const fetchData = useCallback(async (filters = {}, pg = 1, sortState = null) => {
        setLoading(true);
        try {
            const params = { jobRole: decodedRole, page: pg, limit: PAGE_SIZE };
            if (filters.startDate) params.startDate = filters.startDate;
            if (filters.endDate) params.endDate = filters.endDate;
            if (filters.search) params.search = filters.search;
            if (filters.round) params.round = filters.round;
            if (sortState?.by) { params.sort_by = sortState.by; params.sort_dir = sortState.dir; }
            const res = await axios.get(`${API}/api/attended`, { params, withCredentials: true });
            setData(res.data.data);
            setTotal(res.data.total);
            if (Array.isArray(res.data.round_columns)) setRoundCols(res.data.round_columns);
        } catch (err) {
            toast.error('Failed to load attended applicants');
        } finally {
            setLoading(false);
        }
    }, [decodedRole]);

    useEffect(() => { fetchData({}, 1, null); }, [fetchData]);

    const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

    const applyFilters = (pg = 1) => {
        setPage(pg);
        fetchData({ startDate, endDate, search, round }, pg, sort);
    };

    const handleReset = () => {
        setStartDate(''); setEndDate(''); setSearch(''); setRound(''); setPage(1); setSort(null);
        fetchData({}, 1, null);
    };

    const handleSortChange = (next) => {
        setSort(next);
        setPage(1);
        fetchData({ startDate, endDate, search, round }, 1, next);
    };

    const navigatePage = (pg) => {
        if (pg < 1 || pg > totalPages) return;
        setPage(pg);
        fetchData({ startDate, endDate, search, round }, pg, sort);
    };

    const handleGoToPage = () => {
        const pg = parseInt(goToPage);
        if (pg >= 1 && pg <= totalPages) { navigatePage(pg); setGoToPage(''); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="attended-drilldown-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/attended-roles')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <div>
                    <h1 className="text-xl font-semibold tracking-tight" data-testid="role-title">{decodedRole}</h1>
                    <p className="text-sm text-zinc-500">Attended applicants with scores</p>
                </div>
                {!loading && <span className="ml-auto text-sm text-zinc-500" data-testid="total-count">Total: {total}</span>}
            </header>

            {/* Filters */}
            <div className="px-8 py-5 border-b border-zinc-800" data-testid="filters-section">
                <div className="flex flex-wrap items-end gap-4">
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Search</label>
                        <div className="relative">
                            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                                placeholder="Name, email, phone..."
                                onKeyDown={e => e.key === 'Enter' && applyFilters(1)}
                                data-testid="search-input"
                                className="block w-52 bg-zinc-900 border border-zinc-700 pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Start Date</label>
                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                            data-testid="start-date-input"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">End Date</label>
                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                            data-testid="end-date-input"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Round Filter</label>
                        <select value={round} onChange={e => setRound(e.target.value)}
                            data-testid="round-filter"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Rounds</option>
                            {SCORE_COLS.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                    </div>
                    <button onClick={() => applyFilters(1)} data-testid="filter-btn"
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
                    <div className="flex justify-center py-20"><SpinnerGap size={32} className="animate-spin text-zinc-500" /></div>
                ) : data.length === 0 ? (
                    <div className="text-center py-20 text-zinc-500" data-testid="empty-state">No attended applicants found.</div>
                ) : (
                    <>
                        <div className="overflow-x-auto border border-zinc-800" data-testid="attended-table">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-zinc-900 border-b border-zinc-800">
                                        {ALL_COLS.map(col => (
                                            <th key={col.key} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap">
                                                {col.sortable ? (
                                                    <SortableHeader label={col.label} sortKey={col.key} sort={sort} onSortChange={handleSortChange} />
                                                ) : col.label}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.map((row, i) => (
                                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors" data-testid={`attended-row-${i}`}>
                                            {ALL_COLS.map(col => (
                                                <td key={col.key} className="px-4 py-3 whitespace-nowrap">
                                                    {SCORE_COLS.includes(col.key) ? (
                                                        <span className={`tabular-nums ${row[col.key] !== '-' && row[col.key] !== undefined ? 'text-cyan-400 font-medium' : 'text-zinc-600'}`}>{row[col.key] ?? '-'}</span>
                                                    ) : col.key === 'result_status' ? (
                                                        <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
                                                            String(row[col.key]).toLowerCase().includes('reject') ? 'bg-red-900/40 text-red-400 border border-red-800/50' :
                                                            String(row[col.key]).toLowerCase().includes('select') ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' :
                                                            'text-zinc-400'
                                                        }`}>{row[col.key] ?? '-'}</span>
                                                    ) : (
                                                        <span className={col.key === 'name' ? 'font-medium' : 'text-zinc-400'}>{col.key === 'schedule_date' ? formatDateDDMMYYYY(row[col.key]) : (row[col.key] ?? '-')}</span>
                                                    )}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination */}
                        <div className="flex items-center justify-between mt-4" data-testid="pagination">
                            <span className="text-sm text-zinc-500">Page {page} of {totalPages} ({total} records)</span>
                            <div className="flex items-center gap-2">
                                <button onClick={() => navigatePage(1)} disabled={page <= 1} data-testid="first-page-btn"
                                    className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm"><CaretDoubleLeft size={14} /></button>
                                <button onClick={() => navigatePage(page - 1)} disabled={page <= 1} data-testid="prev-page-btn"
                                    className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm"><CaretLeft size={14} /></button>
                                <input type="number" value={goToPage} onChange={e => setGoToPage(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && handleGoToPage()}
                                    placeholder={page} data-testid="page-input"
                                    className="w-16 bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-sm text-center focus:outline-none focus:border-zinc-500" />
                                <button onClick={handleGoToPage} data-testid="go-btn"
                                    className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm">Go</button>
                                <button onClick={() => navigatePage(page + 1)} disabled={page >= totalPages} data-testid="next-page-btn"
                                    className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm"><CaretRight size={14} /></button>
                                <button onClick={() => navigatePage(totalPages)} disabled={page >= totalPages} data-testid="last-page-btn"
                                    className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm"><CaretDoubleRight size={14} /></button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
