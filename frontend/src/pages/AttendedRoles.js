import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import dayjs from 'dayjs';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, SpinnerGap, CaretLeft, CaretRight, CaretDoubleLeft, CaretDoubleRight, MagnifyingGlass, Eye } from '@phosphor-icons/react';
import SortableHeader from '../components/SortableHeader';
import CandidateJourneyModal from '../components/CandidateJourneyModal';

const API = process.env.REACT_APP_BACKEND_URL;
const PAGE_SIZES = [10, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500];

// iter70 — Round columns are now built DYNAMICALLY from the backend response
// (`/api/attended` returns `round_columns` from `bb_rounds`, sorted alphabetically).
// The base columns are static and always rendered before round columns.
const BASE_COLS = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'email', label: 'Email', sortable: true },
    { key: 'phone', label: 'Phone', sortable: true },
    { key: 'college_status', label: 'College Status', sortable: true },
    { key: 'college', label: 'College', sortable: true },
    { key: 'degree', label: 'Degree', sortable: true },
    { key: 'course', label: 'Course', sortable: true },
    { key: 'year_of_graduation', label: 'Year of Graduation', sortable: true },
    { key: 'job_role', label: 'Job Role', sortable: true },
    { key: 'schedule_date', label: 'Scheduled Date', sortable: true },
    { key: 'result_status', label: 'Result Status', sortable: true },
];

const DATE_COLS = ['schedule_date'];
const COLLEGE_STATUS_OPTIONS = ['All', 'NIRF', 'Non NIRF'];

function fmtDate(val) {
    if (!val || val === '-') return '-';
    const d = dayjs(val);
    return d.isValid() ? d.format('DD-MM-YYYY') : val;
}

export default function AttendedApplicants() {
    const navigate = useNavigate();
    const [data, setData] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(100);
    const [loading, setLoading] = useState(true);
    const [jobRoles, setJobRoles] = useState([]);
    const [jobRole, setJobRole] = useState('');
    const [round, setRound] = useState('');
    // iter108 — Default current day filter so Attended Applicants loads
    // only today's records on initial mount. Reset reverts to "all history".
    const _today = new Date().toISOString().slice(0, 10);
    const [startDate, setStartDate] = useState(_today);
    const [endDate, setEndDate] = useState(_today);
    const [search, setSearch] = useState('');
    const [collegeStatus, setCollegeStatus] = useState('');
    const [goToPage, setGoToPage] = useState('');
    const [sort, setSort] = useState(null);
    const [journeyCandidate, setJourneyCandidate] = useState(null);  // Iter52
    // iter70 — Round columns supplied by backend (dynamic, from bb_rounds).
    const [roundCols, setRoundCols] = useState([]);

    const ALL_COLS = [
        ...BASE_COLS,
        ...roundCols.map(c => ({ key: c, label: c })),
    ];
    const SCORE_COLS = roundCols;

    useEffect(() => {
        (async () => {
            try {
                const res = await axios.get(`${API}/api/job-roles`, { withCredentials: true });
                setJobRoles(res.data.job_roles || []);
            } catch {}
        })();
    }, []);

    const fetchData = useCallback(async (filters = {}, pg = 1, size = 100, sortState = null) => {
        setLoading(true);
        try {
            const params = { page: pg, limit: size };
            if (filters.jobRole) params.jobRole = filters.jobRole;
            if (filters.startDate) params.startDate = filters.startDate;
            if (filters.endDate) params.endDate = filters.endDate;
            if (filters.search) params.search = filters.search;
            if (filters.round) params.round = filters.round;
            if (filters.collegeStatus) params.collegeStatus = filters.collegeStatus;
            if (sortState?.by) { params.sort_by = sortState.by; params.sort_dir = sortState.dir; }
            const res = await axios.get(`${API}/api/attended`, { params, withCredentials: true });
            setData(res.data.data);
            setTotal(res.data.total);
            // iter70 — adopt dynamic round columns from backend
            if (Array.isArray(res.data.round_columns)) {
                setRoundCols(res.data.round_columns);
            }
        } catch {
            toast.error('Failed to load attended applicants');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // iter108 — Initial fetch uses default today/today filter.
        fetchData({ startDate: _today, endDate: _today }, 1, 100, null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fetchData]);

    const totalPages = Math.ceil(total / pageSize) || 1;

    const applyFilters = (pg = 1) => {
        setPage(pg);
        fetchData({ jobRole, startDate, endDate, search, round, collegeStatus }, pg, pageSize, sort);
    };

    const handleReset = () => {
        setJobRole(''); setRound(''); setStartDate(''); setEndDate(''); setSearch(''); setCollegeStatus(''); setPage(1); setPageSize(100); setSort(null);
        fetchData({}, 1, 100, null);
    };

    const handleSortChange = (next) => {
        setSort(next);
        setPage(1);
        fetchData({ jobRole, startDate, endDate, search, round, collegeStatus }, 1, pageSize, next);
    };

    const navigatePage = (pg) => {
        if (pg < 1 || pg > totalPages) return;
        setPage(pg);
        fetchData({ jobRole, startDate, endDate, search, round, collegeStatus }, pg, pageSize, sort);
    };

    const handlePageSizeChange = (newSize) => {
        setPageSize(newSize);
        setPage(1);
        fetchData({ jobRole, startDate, endDate, search, round, collegeStatus }, 1, newSize, sort);
    };

    const handleGoToPage = () => {
        const pg = parseInt(goToPage);
        if (pg >= 1 && pg <= totalPages) { navigatePage(pg); setGoToPage(''); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="attended-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="text-xl font-semibold tracking-tight">View Attended Applicants</h1>
                {!loading && <span className="ml-auto text-sm text-zinc-500" data-testid="total-count">Total: {total}</span>}
            </header>

            {/* Filters */}
            <div className="px-8 py-5 border-b border-zinc-800" data-testid="filters-section">
                <div className="flex flex-wrap items-end gap-4">
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role</label>
                        <select value={jobRole} onChange={e => setJobRole(e.target.value)} data-testid="job-role-filter"
                            className="block w-52 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Jobs</option>
                            {jobRoles.map(r => <option key={r.job_role} value={r.job_role}>{r.job_role}</option>)}
                        </select>
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Round Filter</label>
                        <select value={round} onChange={e => setRound(e.target.value)} data-testid="round-filter"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Rounds</option>
                            {SCORE_COLS.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Start Date</label>
                        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} data-testid="start-date-input"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">End Date</label>
                        <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} data-testid="end-date-input"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">Search</label>
                        <div className="relative">
                            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                                placeholder="Name, email, phone, role..."
                                onKeyDown={e => e.key === 'Enter' && applyFilters(1)} data-testid="search-input"
                                className="block w-52 bg-zinc-900 border border-zinc-700 pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <label className="text-xs text-zinc-500 uppercase tracking-wider">College Status</label>
                        <select value={collegeStatus} onChange={e => setCollegeStatus(e.target.value)} data-testid="college-status-filter"
                            className="block w-48 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            {COLLEGE_STATUS_OPTIONS.map(o => <option key={o} value={o === 'All' ? '' : o}>{o}</option>)}
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
                ) : (
                    <>
                        <div className="overflow-x-auto border border-zinc-800" data-testid="attended-table">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-zinc-900 border-b border-zinc-800">
                                        <th className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap w-16">Action</th>
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
                                    {data.length === 0 ? (
                                        <tr data-testid="empty-state-row">
                                            <td colSpan={ALL_COLS.length + 1} className="px-4 py-16 text-center text-zinc-500">No records found.</td>
                                        </tr>
                                    ) : data.map((row, i) => (
                                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors" data-testid={`attended-row-${i}`}>
                                            <td className="px-4 py-3 whitespace-nowrap">
                                                {/* Iter52 — A–Z row action: opens the full candidate journey modal */}
                                                <button
                                                    onClick={() => setJourneyCandidate({ email: row.email, phone: row.phone })}
                                                    data-testid={`journey-btn-${i}`}
                                                    title="View Candidate Journey"
                                                    className="p-1.5 text-zinc-500 hover:text-cyan-400 hover:bg-zinc-800"
                                                >
                                                    <Eye size={16} />
                                                </button>
                                            </td>
                                            {ALL_COLS.map(col => (
                                                <td key={col.key} className="px-4 py-3 whitespace-nowrap">
                                                    {SCORE_COLS.includes(col.key) ? (
                                                        <span className={`tabular-nums ${row[col.key] !== '-' && row[col.key] !== undefined ? 'text-cyan-400 font-medium' : 'text-zinc-600'}`}>{row[col.key] ?? '-'}</span>
                                                    ) : col.key === 'college_status' ? (
                                                        <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
                                                            row[col.key] === 'NIRF' ? 'bg-cyan-900/40 text-cyan-400 border border-cyan-800/50' :
                                                            'bg-zinc-800/60 text-zinc-400 border border-zinc-700/50'
                                                        }`}>{row[col.key]}</span>
                                                    ) : col.key === 'result_status' ? (
                                                        <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
                                                            String(row[col.key]).toLowerCase().includes('reject') ? 'bg-red-900/40 text-red-400 border border-red-800/50' :
                                                            String(row[col.key]).toLowerCase().includes('select') ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50' :
                                                            'text-zinc-400'
                                                        }`}>{row[col.key] ?? '-'}</span>
                                                    ) : (
                                                        <span className={col.key === 'name' ? 'font-medium' : 'text-zinc-400'}>
                                                            {DATE_COLS.includes(col.key) ? fmtDate(row[col.key]) : (row[col.key] ?? '-')}
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
                        {data.length > 0 && (
                        <div className="flex items-center justify-between mt-4" data-testid="pagination">
                            <div className="flex items-center gap-3">
                                <span className="text-sm text-zinc-500">Page {page} of {totalPages} ({total} records)</span>
                                <select value={pageSize} onChange={e => handlePageSizeChange(Number(e.target.value))} data-testid="page-size-select"
                                    className="bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-sm focus:outline-none focus:border-zinc-500">
                                    {PAGE_SIZES.map(s => <option key={s} value={s}>{s} / page</option>)}
                                </select>
                            </div>
                            <div className="flex items-center gap-2">
                                {page > 1 && <>
                                    <button onClick={() => navigatePage(1)} data-testid="first-page-btn"
                                        className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"><CaretDoubleLeft size={14} /></button>
                                    <button onClick={() => navigatePage(page - 1)} data-testid="prev-page-btn"
                                        className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"><CaretLeft size={14} /></button>
                                </>}
                                <input type="number" value={goToPage} onChange={e => setGoToPage(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && handleGoToPage()}
                                    placeholder={page} data-testid="page-input"
                                    className="w-16 bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-sm text-center focus:outline-none focus:border-zinc-500" />
                                <button onClick={handleGoToPage} data-testid="go-btn"
                                    className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm">Go</button>
                                {page < totalPages && <>
                                    <button onClick={() => navigatePage(page + 1)} data-testid="next-page-btn"
                                        className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"><CaretRight size={14} /></button>
                                    <button onClick={() => navigatePage(totalPages)} data-testid="last-page-btn"
                                        className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"><CaretDoubleRight size={14} /></button>
                                </>}
                            </div>
                        </div>
                        )}
                    </>
                )}
            </div>
            {/* Iter52 — Candidate Journey modal */}
            {journeyCandidate && (
                <CandidateJourneyModal candidate={journeyCandidate} onClose={() => setJourneyCandidate(null)} />
            )}
        </div>
    );
}
