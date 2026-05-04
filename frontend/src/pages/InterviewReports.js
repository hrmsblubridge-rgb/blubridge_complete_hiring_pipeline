import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import dayjs from 'dayjs';
import { ArrowLeft, FunnelSimple, ArrowCounterClockwise, Export } from '@phosphor-icons/react';
import Pagination from '../components/Pagination';

const API = process.env.REACT_APP_BACKEND_URL;

export default function InterviewReports() {
    const navigate = useNavigate();
    const [data, setData] = useState([]);
    const [total, setTotal] = useState(0);
    const [summary, setSummary] = useState({});
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(100);
    const [loading, setLoading] = useState(true);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [jobRole, setJobRole] = useState('');
    const [attendance, setAttendance] = useState('');
    const [collegeType, setCollegeType] = useState('');
    const [bbRoles, setBbRoles] = useState([]);
    const [showAllRoles, setShowAllRoles] = useState(false);

    useEffect(() => {
        axios.get(`${API}/api/bb/job-roles`, { withCredentials: true }).then(r => setBbRoles(r.data.roles || [])).catch(() => {});
    }, []);

    const fetchData = useCallback(async (pg = 1, sz = 100) => {
        setLoading(true);
        try {
            const params = { page: pg, limit: sz };
            if (startDate) params.startDate = startDate;
            if (endDate) params.endDate = endDate;
            if (jobRole) params.jobRole = jobRole;
            if (attendance) params.attendance = attendance;
            if (collegeType) params.collegeType = collegeType;
            const res = await axios.get(`${API}/api/bb/interview-reports`, { params, withCredentials: true });
            setData(res.data.data || []);
            setTotal(res.data.total || 0);
            setSummary(res.data.summary || {});
        } catch { toast.error('Failed to load reports'); }
        finally { setLoading(false); }
    }, [startDate, endDate, jobRole, attendance, collegeType]);

    useEffect(() => { fetchData(1, pageSize); }, [fetchData, pageSize]);

    const applyFilters = () => { setPage(1); fetchData(1, pageSize); };
    const resetFilters = () => { setStartDate(''); setEndDate(''); setJobRole(''); setAttendance(''); setCollegeType(''); setPage(1); };
    const totalPages = Math.ceil(total / pageSize) || 1;
    const navPage = (pg) => { if (pg >= 1 && pg <= totalPages) { setPage(pg); fetchData(pg, pageSize); } };

    const handleExport = () => {
        const headers = ['NAME', 'EMAIL', 'DATE', 'TIME', 'JOB ROLE', 'COLLEGE TYPE', 'ATTENDANCE'];
        const csvRows = [headers.join(',')];
        data.forEach(r => csvRows.push([r.name, r.email, r.date, r.time, r.job_role, r.college_type, r.attendance].map(v => `"${(v || '').replace(/"/g, '""')}"`).join(',')));
        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `interview_report_${dayjs().format('YYYY-MM-DD')}.csv`; a.click();
        URL.revokeObjectURL(url);
    };

    const roleCounts = summary.role_counts || {};
    const roleEntries = Object.entries(roleCounts).sort((a, b) => b[1] - a[1]);
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
                        <select value={collegeType} onChange={e => setCollegeType(e.target.value)} data-testid="filter-college" className="block w-44 bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500">
                            <option value="">All Colleges</option><option value="Premium">Premium</option><option value="Non Premium">Non Premium</option>
                        </select>
                    </div>
                    <button onClick={applyFilters} data-testid="apply-btn" className="flex items-center gap-2 px-5 py-2 bg-cyan-700 hover:bg-cyan-600 text-sm font-medium"><FunnelSimple size={16} /> APPLY</button>
                    <button onClick={resetFilters} className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium"><ArrowCounterClockwise size={16} /> Reset</button>
                    <button onClick={handleExport} data-testid="export-btn" className="flex items-center gap-2 px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-sm font-medium"><Export size={16} /> Export</button>
                </div>
            </div>

            {/* Summaries */}
            <div className="px-8 py-4 border-b border-zinc-800">
                <div className="flex flex-wrap gap-6 items-start">
                    <div>
                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-zinc-500 uppercase tracking-wider mr-2">Roles:</span>
                            <span className="px-2 py-0.5 bg-cyan-900/40 text-cyan-400 text-xs rounded">All ({total})</span>
                            {visibleRoles.map(([r, c]) => (
                                <button key={r} onClick={() => { setJobRole(r); setPage(1); fetchData(1, pageSize); }}
                                    className={`px-2 py-0.5 text-xs rounded transition-colors ${jobRole === r ? 'bg-cyan-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}>{r} ({c})</button>
                            ))}
                            {roleEntries.length > 5 && <button onClick={() => setShowAllRoles(p => !p)} className="text-xs text-cyan-500 hover:text-cyan-400">{showAllRoles ? 'SHOW LESS' : 'SHOW ALL'}</button>}
                        </div>
                    </div>
                    <div className="flex gap-4 ml-auto text-sm">
                        <div className="text-center"><div className="text-emerald-400 text-lg font-semibold">{summary.attended || 0}</div><div className="text-zinc-500 text-xs">Attended</div></div>
                        <div className="text-center"><div className="text-orange-400 text-lg font-semibold">{summary.not_attended || 0}</div><div className="text-zinc-500 text-xs">Not Attended</div></div>
                        <div className="text-center"><div className="text-cyan-400 text-lg font-semibold">{summary.premium_colleges || 0}</div><div className="text-zinc-500 text-xs">Premium</div></div>
                        <div className="text-center"><div className="text-zinc-400 text-lg font-semibold">{summary.non_premium_colleges || 0}</div><div className="text-zinc-500 text-xs">Non Premium</div></div>
                    </div>
                </div>
            </div>

            {/* Table */}
            <div className="px-8 py-6 pb-24" data-testid="reports-section">
                {loading ? <div className="text-center py-20 text-zinc-500">Loading...</div> :
                <div className="overflow-x-auto border border-zinc-800" data-testid="reports-table">
                    <table className="w-full text-sm">
                        <thead><tr className="bg-zinc-900 border-b border-zinc-800">
                            {['NAME', 'EMAIL', 'DATE', 'TIME', 'JOB ROLE', 'COLLEGE TYPE', 'ATTENDANCE'].map(h => <th key={h} className="text-left px-4 py-3 font-medium text-zinc-400 text-xs uppercase tracking-wider whitespace-nowrap">{h}</th>)}
                        </tr></thead>
                        <tbody>
                            {data.length === 0 ? <tr><td colSpan={7} className="px-4 py-16 text-center text-zinc-500">No records found.</td></tr> :
                            data.map((r, i) => (
                                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-900/50" data-testid={`report-row-${i}`}>
                                    <td className="px-4 py-3 font-medium whitespace-nowrap">{r.name}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{r.email}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{r.date}</td>
                                    <td className="px-4 py-3 text-zinc-400 whitespace-nowrap">{r.time}</td>
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
        </div>
    );
}
