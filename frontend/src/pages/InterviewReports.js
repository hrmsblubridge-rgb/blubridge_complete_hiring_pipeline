import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import dayjs from 'dayjs';
import { formatDateDDMMYYYY, formatTime12H } from '../utils/dateFormat';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, Export } from '@phosphor-icons/react';
import Pagination from '../components/Pagination';
import SortableHeader from '../components/SortableHeader';
import ExportFieldsModal from '../components/ExportFieldsModal';

const API = process.env.REACT_APP_BACKEND_URL;

const COLUMNS = [
    { key: 'name', label: 'NAME', sortable: true },
    { key: 'email', label: 'EMAIL', sortable: true },
    { key: 'date', label: 'DATE', sortable: true },
    { key: 'time', label: 'TIME', sortable: true },
    { key: 'job_role', label: 'JOB ROLE', sortable: true },
    { key: 'college_type', label: 'COLLEGE TYPE', sortable: true },
    { key: 'attendance', label: 'ATTENDANCE', sortable: true },
];

export default function InterviewReports() {
    const navigate = useNavigate();
    const [data, setData] = useState([]);
    const [total, setTotal] = useState(0);
    const [summary, setSummary] = useState({});
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(100);
    const [loading, setLoading] = useState(true);
    // iter93 — Default both date filters to today (local date) so the page
    // initially shows ONLY today's interviews. Manual changes still work.
    const _today_iso = (() => {
        const d = new Date();
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    })();
    const [startDate, setStartDate] = useState(_today_iso);
    const [endDate, setEndDate] = useState(_today_iso);
    const [jobRole, setJobRole] = useState('');
    const [attendance, setAttendance] = useState('');
    const [collegeType, setCollegeType] = useState('');
    // iter111 — Per-field Name / Email / Phone filters.
    const [nameQ, setNameQ] = useState('');
    const [emailQ, setEmailQ] = useState('');
    const [phoneQ, setPhoneQ] = useState('');
    const [bbRoles, setBbRoles] = useState([]);
    const [showAllRoles, setShowAllRoles] = useState(false);
    const [sort, setSort] = useState(null);

    useEffect(() => {
        axios.get(`${API}/api/bb/job-roles`, { withCredentials: true }).then(r => setBbRoles(r.data.roles || [])).catch(() => {});
    }, []);

    const fetchData = useCallback(async (pg = 1, sz = 100, sortState = null) => {
        setLoading(true);
        try {
            const params = { page: pg, limit: sz };
            if (startDate) params.startDate = startDate;
            if (endDate) params.endDate = endDate;
            if (jobRole) params.jobRole = jobRole;
            if (attendance) params.attendance = attendance;
            if (collegeType) params.collegeType = collegeType;
            if (nameQ) params.name = nameQ;
            if (emailQ) params.email = emailQ;
            if (phoneQ) params.phone = phoneQ;
            if (sortState?.by) { params.sort_by = sortState.by; params.sort_dir = sortState.dir; }
            const res = await axios.get(`${API}/api/bb/interview-reports`, { params, withCredentials: true });
            setData(res.data.data || []);
            setTotal(res.data.total || 0);
            setSummary(res.data.summary || {});
        } catch { toast.error('Failed to load reports'); }
        finally { setLoading(false); }
    }, [startDate, endDate, jobRole, attendance, collegeType, nameQ, emailQ, phoneQ]);

    useEffect(() => { fetchData(1, pageSize, sort); }, [fetchData, pageSize, sort]);

    const applyFilters = () => { setPage(1); fetchData(1, pageSize, sort); };
    // iter113 — Reset preserves today/today date filter; All Records drops dates entirely.
    const resetFilters = () => { setStartDate(_today_iso); setEndDate(_today_iso); setJobRole(''); setAttendance(''); setCollegeType(''); setNameQ(''); setEmailQ(''); setPhoneQ(''); setPage(1); setSort(null); };
    const handleAllRecords = () => { setStartDate(''); setEndDate(''); setPage(1); };
    const handleSortChange = (next) => { setSort(next); setPage(1); };
    const totalPages = Math.ceil(total / pageSize) || 1;
    const navPage = (pg) => { if (pg >= 1 && pg <= totalPages) { setPage(pg); fetchData(pg, pageSize, sort); } };

    const [exporting, setExporting] = useState(false);
    const [exportModalOpen, setExportModalOpen] = useState(false);

    const filterParams = useMemo(() => {
        const p = {};
        if (startDate) p.startDate = startDate;
        if (endDate) p.endDate = endDate;
        if (jobRole) p.jobRole = jobRole;
        if (attendance) p.attendance = attendance;
        if (collegeType) p.collegeType = collegeType;
        return p;
    }, [startDate, endDate, jobRole, attendance, collegeType]);

    const handleDownload = async (fieldsCsv) => {
        setExporting(true);
        try {
            const res = await axios.get(`${API}/api/bb/interview-reports/export`, {
                params: { ...filterParams, fields: fieldsCsv },
                withCredentials: true, responseType: 'blob',
            });
            const blob = new Blob([res.data], { type: res.headers['content-type'] });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Interview_Report_${dayjs().format('YYYY-MM-DD')}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success('Export downloaded');
        } catch (err) {
            if (err.response?.status === 404) {
                toast.error('No data available to export');
            } else if (err.response?.status === 400) {
                toast.error('Please select at least one field');
            } else {
                toast.error('Failed to export reports');
            }
        } finally {
            setExporting(false);
        }
    };

    const roleCounts = summary.role_counts || {};
    // iter103 — The backend's role_counts is scoped to the current filter
    // (so it collapses to just the selected role when jobRole is set). To
    // keep all chips visible, we pin the "All" view's role_counts in a ref
    // and only refresh it when no jobRole filter is active. Buttons + total
    // counts use the pinned baseline; the data table still uses the
    // filtered response.
    const baselineRoleCounts = useRef({});
    const baselineTotal = useRef(0);
    if (jobRole === '' && Object.keys(roleCounts).length) {
        baselineRoleCounts.current = roleCounts;
        baselineTotal.current = total;
    }
    const baseEntries = Object.entries(baselineRoleCounts.current).sort((a, b) => b[1] - a[1]);
    // Move the selected role to the front (after "All") so users always
    // see what they have selected at a glance.
    const roleEntries = jobRole
        ? [
              ...baseEntries.filter(([r]) => r === jobRole),
              ...baseEntries.filter(([r]) => r !== jobRole),
          ]
        : baseEntries;
    const visibleRoles = showAllRoles ? roleEntries : roleEntries.slice(0, 5);

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="interview-reports-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Interview Schedule Reports</h1>
            </header>

            {/* Filters */}
            <div className="px-8 py-5 border-b border-zinc-800">
                <div className="flex flex-wrap items-end gap-4">
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Start Date</label><input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">End Date</label><input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Job Role</label>
                        <select value={jobRole} onChange={e => setJobRole(e.target.value)} data-testid="filter-job-role" className="block w-52 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Roles</option>
                            {bbRoles.map(r => <option key={r.id} value={r.name}>{r.name}</option>)}
                        </select>
                    </div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Attendance</label>
                        <select value={attendance} onChange={e => setAttendance(e.target.value)} data-testid="filter-attendance" className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All</option><option>Attended</option><option>Not Attended</option>
                        </select>
                    </div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">College</label>
                        <select value={collegeType} onChange={e => setCollegeType(e.target.value)} data-testid="filter-college" className="block w-52 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Colleges</option>
                            <option value="NIRF">NIRF</option>
                            <option value="Non-NIRF 101-150">Non-NIRF 101-150</option>
                            <option value="Non-NIRF 151-200">Non-NIRF 151-200</option>
                            <option value="Non-NIRF 201-300">Non-NIRF 201-300</option>
                            <option value="Non-NIRF - No Rank">Non-NIRF - No Rank</option>
                        </select>
                    </div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Name</label>
                        <input type="text" list="dl-rep-names" value={nameQ} onChange={e => setNameQ(e.target.value)}
                            placeholder="Filter by name..." onKeyDown={e => e.key === 'Enter' && applyFilters()} data-testid="filter-name"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="dl-rep-names">
                            {Array.from(new Set((data || []).map(r => r.name).filter(Boolean))).slice(0, 200).map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Email</label>
                        <input type="text" list="dl-rep-emails" value={emailQ} onChange={e => setEmailQ(e.target.value)}
                            placeholder="Filter by email..." onKeyDown={e => e.key === 'Enter' && applyFilters()} data-testid="filter-email"
                            className="block w-48 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="dl-rep-emails">
                            {Array.from(new Set((data || []).map(r => r.email).filter(Boolean))).slice(0, 200).map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <div className="space-y-1"><label className="text-xs text-zinc-500 uppercase tracking-wider">Phone</label>
                        <input type="text" list="dl-rep-phones" value={phoneQ} onChange={e => setPhoneQ(e.target.value)}
                            placeholder="Filter by phone..." onKeyDown={e => e.key === 'Enter' && applyFilters()} data-testid="filter-phone"
                            className="block w-40 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" />
                        <datalist id="dl-rep-phones">
                            {Array.from(new Set((data || []).map(r => r.phone).filter(Boolean))).slice(0, 200).map(v => <option key={v} value={v} />)}
                        </datalist>
                    </div>
                    <button onClick={applyFilters} data-testid="apply-btn" className="flex items-center gap-2 px-5 py-2 bg-cyan-700 hover:bg-cyan-600 text-sm font-medium"><FunnelSimple size={16} /> APPLY</button>
                    <button onClick={resetFilters} data-testid="reset-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium"><ArrowCounterClockwise size={16} /> Reset</button>
                    <button onClick={handleAllRecords} data-testid="all-records-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm font-medium border border-zinc-700">All Records</button>
                    <button onClick={() => setExportModalOpen(true)} disabled={exporting} data-testid="export-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-60 disabled:cursor-not-allowed text-sm font-medium"><Export size={16} /> {exporting ? 'Exporting…' : 'Export'}</button>
                </div>
            </div>

            {/* Summaries */}
            <div className="px-8 py-4 border-b border-zinc-800">
                <div className="flex flex-wrap gap-6 items-start">
                    <div>
                        {/* iter102 — Filter buttons:
                              * Medium size (px-3 py-1 text-sm) for readability.
                              * Single source of truth (jobRole) drives BOTH the
                                <select> dropdown and these chip buttons — the
                                fetchData useEffect refetches automatically when
                                jobRole changes, eliminating the old
                                "click-twice" race condition.
                              * "All" chip is now clickable and resets jobRole. */}
                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-zinc-500 uppercase tracking-wider mr-2">Roles:</span>
                            <button onClick={() => { setJobRole(''); setPage(1); }}
                                data-testid="role-chip-all"
                                className={`px-3 py-1 text-sm rounded-md transition-colors ${jobRole === '' ? 'bg-cyan-700 text-white font-medium' : 'bg-cyan-900/40 text-cyan-400 hover:bg-cyan-900/60'}`}>All ({baselineTotal.current || total})</button>
                            {visibleRoles.map(([r, c]) => (
                                <button key={r} onClick={() => { setJobRole(r); setPage(1); }}
                                    data-testid={`role-chip-${r}`}
                                    className={`px-3 py-1 text-sm rounded-md transition-colors ${jobRole === r ? 'bg-cyan-700 text-white font-medium' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-white'}`}>{r} ({c})</button>
                            ))}
                            {roleEntries.length > 5 && <button onClick={() => setShowAllRoles(p => !p)} className="text-xs text-cyan-500 hover:text-cyan-400 ml-1">{showAllRoles ? 'SHOW LESS' : 'SHOW ALL'}</button>}
                        </div>
                    </div>
                    <div className="flex gap-4 ml-auto text-sm">
                        <div className="text-center"><div className="text-emerald-400 text-lg font-semibold">{summary.attended || 0}</div><div className="text-zinc-500 text-xs">Attended</div></div>
                        <div className="text-center"><div className="text-orange-400 text-lg font-semibold">{summary.not_attended || 0}</div><div className="text-zinc-500 text-xs">Not Attended</div></div>
                        <div className="text-center"><div className="text-cyan-400 text-lg font-semibold">{summary.premium_colleges || 0}</div><div className="text-zinc-500 text-xs">NIRF</div></div>
                        <div className="text-center"><div className="text-zinc-400 text-lg font-semibold">{summary.non_premium_colleges || 0}</div><div className="text-zinc-500 text-xs">Non-NIRF</div></div>
                    </div>
                </div>
            </div>

            {/* Table */}
            <div className="px-8 py-6 pb-24" data-testid="reports-section">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                <div className="overflow-x-auto border border-zinc-800" data-testid="reports-table">
                    <table className="w-full text-sm">
                        <thead><tr className="bg-zinc-900 border-b border-zinc-800">
                            {COLUMNS.map(c => (
                                <th key={c.key} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap">
                                    {c.sortable ? (
                                        <SortableHeader label={c.label} sortKey={c.key} sort={sort} onSortChange={handleSortChange} />
                                    ) : c.label}
                                </th>
                            ))}
                        </tr></thead>
                        <tbody>
                            {data.length === 0 ? <tr><td colSpan={7} className="px-4 py-16 text-center text-zinc-500">No records found.</td></tr> :
                            data.map((r, i) => (
                                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50" data-testid={`report-row-${i}`}>
                                    <td className="px-4 py-3 font-medium whitespace-nowrap">{r.name}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{r.email}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{formatDateDDMMYYYY(r.date)}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{formatTime12H(r.time)}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{r.job_role}</td>
                                    <td className="px-4 py-3 whitespace-nowrap"><span className={`px-2 py-0.5 text-xs rounded ${r.college_type?.includes('Non') ? 'bg-zinc-800 text-zinc-400' : 'bg-cyan-900/40 text-cyan-400'}`}>{r.college_type}</span></td>
                                    <td className="px-4 py-3 whitespace-nowrap"><span className={`px-2 py-0.5 text-xs rounded ${r.attendance === 'Attended' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-orange-900/40 text-orange-400'}`}>{r.attendance}</span></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>}
                {/* Pagination */}
                <Pagination
                    page={page}
                    totalPages={totalPages}
                    total={total}
                    pageSize={pageSize}
                    onPageChange={navPage}
                    onPageSizeChange={(s) => { setPageSize(s); setPage(1); }}
                />
            </div>
            <ExportFieldsModal
                open={exportModalOpen}
                onClose={() => setExportModalOpen(false)}
                filterParams={filterParams}
                onDownload={handleDownload}
            />
        </div>
    );
}
