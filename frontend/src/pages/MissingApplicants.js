// iter82 — Missing Applicants module
// Shows candidates who either:
//   • were shortlisted but never scheduled an interview, OR
//   • scheduled an interview but never attended (otp_verified is falsy)
//
// Filters: From/To date range, Date Filter (registered|scheduled), Report Type.
// Reads from GET /api/bb/missing-applicants and exports via …/export.

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, FunnelSimple, ArrowClockwise, DownloadSimple, UserMinus } from '@phosphor-icons/react';
import { formatDateDDMMYYYY as fmtDate, formatTime12H as fmtTime } from '../utils/dateFormat';

const API = process.env.REACT_APP_BACKEND_URL;
const today = () => new Date().toISOString().slice(0, 10);

const REPORT_TYPES = [
    { value: 'all',            label: 'All' },
    { value: 'not_scheduled',  label: 'Shortlisted but interview not scheduled' },
    { value: 'not_attended',   label: 'Interview scheduled but not attended' },
];
const DATE_FILTERS = [
    { value: 'registered', label: 'Registered date' },
    { value: 'scheduled',  label: 'Scheduled date' },
];

export default function MissingApplicants() {
    const navigate = useNavigate();
    const [fromDate, setFromDate] = useState(today());
    const [toDate, setToDate] = useState(today());
    const [dateFilter, setDateFilter] = useState('registered');
    const [reportType, setReportType] = useState('all');
    const [rows, setRows] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);

    const params = useMemo(() => ({
        from_date: fromDate,
        to_date:   toDate,
        date_filter: dateFilter,
        report_type: reportType,
        page: 1, limit: 500,
    }), [fromDate, toDate, dateFilter, reportType]);

    const fetchRows = async () => {
        setLoading(true);
        try {
            const r = await axios.get(`${API}/api/bb/missing-applicants`, { withCredentials: true, params });
            setRows(r.data.data || []);
            setTotal(r.data.total || 0);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load Missing Applicants');
        } finally { setLoading(false); }
    };

    useEffect(() => { fetchRows(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const handleReset = () => {
        setFromDate(today()); setToDate(today());
        setDateFilter('registered'); setReportType('all');
        setTimeout(fetchRows, 0);
    };

    const handleExport = async (format) => {
        try {
            const r = await axios.get(`${API}/api/bb/missing-applicants/export`, {
                withCredentials: true, params: { ...params, format }, responseType: 'blob',
            });
            const blob = new Blob([r.data]);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = `Missing_Applicants_${today()}.${format}`;
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            if (e.response?.status === 404) toast.error('No data available to export');
            else toast.error('Export failed');
        }
    };

    return (
        <div className="min-h-screen" data-testid="missing-applicants-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-7xl mx-auto flex items-center gap-3 pl-12 lg:pl-0">
                    <button onClick={() => navigate('/home')} data-testid="missing-back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                        <ArrowLeft size={18} className="text-[#1a2332]" />
                    </button>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-rose-100">
                        <UserMinus size={22} weight="duotone" className="text-rose-700" />
                    </div>
                    <div>
                        <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Missing Applicants</h1>
                        <p className="text-xs text-[#6b7280] mt-0.5">Shortlisted-but-not-scheduled · Scheduled-but-not-attended</p>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                {/* Filter card */}
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div>
                            <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">From Date</label>
                            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} data-testid="missing-from-date"
                                className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        </div>
                        <div>
                            <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">To Date</label>
                            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} data-testid="missing-to-date"
                                className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        </div>
                        <div>
                            <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Date Filter</label>
                            <select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} data-testid="missing-date-filter"
                                className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm">
                                {DATE_FILTERS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Report Type</label>
                            <select value={reportType} onChange={(e) => setReportType(e.target.value)} data-testid="missing-report-type"
                                className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm">
                                {REPORT_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-3 mt-4">
                        <button onClick={fetchRows} disabled={loading} data-testid="missing-filter-btn"
                            className="px-5 py-2.5 rounded-lg bg-[#1d3a8a] hover:bg-[#162d6e] text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                            <FunnelSimple size={16} weight="bold" /> {loading ? 'Filtering…' : 'Filter'}
                        </button>
                        <button onClick={handleReset} data-testid="missing-reset-btn"
                            className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                            <ArrowClockwise size={16} /> Reset
                        </button>
                        <div className="ml-auto flex gap-2">
                            <button onClick={() => handleExport('csv')} data-testid="missing-export-csv-btn"
                                className="px-4 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                                <DownloadSimple size={16} /> CSV
                            </button>
                            <button onClick={() => handleExport('xlsx')} data-testid="missing-export-xlsx-btn"
                                className="px-4 py-2.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white font-semibold text-sm flex items-center gap-2">
                                <DownloadSimple size={16} weight="bold" /> Export XLSX
                            </button>
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden">
                    <div className="px-5 py-3 bg-[#faf9f1] border-b border-[#e5e3d8] flex items-center justify-between">
                        <div className="text-sm font-semibold text-[#1a2332]">Results <span className="text-[#9b9787] font-normal">({total})</span></div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-[#f6f4e9] text-[11px] uppercase tracking-wider text-[#6b7280]">
                                <tr>
                                    <th className="px-4 py-3 text-left">Name</th>
                                    <th className="px-4 py-3 text-left">Email</th>
                                    <th className="px-4 py-3 text-left">Phone</th>
                                    <th className="px-4 py-3 text-left">Location</th>
                                    <th className="px-4 py-3 text-left">Job Role</th>
                                    <th className="px-4 py-3 text-left">College</th>
                                    <th className="px-4 py-3 text-left">College Type</th>
                                    <th className="px-4 py-3 text-left">Degree</th>
                                    <th className="px-4 py-3 text-left">Course</th>
                                    <th className="px-4 py-3 text-left">Registered</th>
                                    <th className="px-4 py-3 text-left">Scheduled</th>
                                    <th className="px-4 py-3 text-left">Time</th>
                                    <th className="px-4 py-3 text-left">Result Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.length === 0 && !loading && (
                                    <tr><td colSpan={13} className="px-4 py-8 text-center text-[#9b9787]">No records found for the selected filters.</td></tr>
                                )}
                                {rows.map((r, i) => (
                                    <tr key={i} className="border-t border-[#ece9dc]" data-testid={`missing-row-${i}`}>
                                        <td className="px-4 py-2.5 font-medium text-[#1a2332]">{r.name || '—'}</td>
                                        <td className="px-4 py-2.5">{r.email || '—'}</td>
                                        <td className="px-4 py-2.5">{r.phone || '—'}</td>
                                        <td className="px-4 py-2.5">{r.current_location || '—'}</td>
                                        <td className="px-4 py-2.5">{r.job_role || '—'}</td>
                                        <td className="px-4 py-2.5">{r.college || '—'}</td>
                                        <td className="px-4 py-2.5">{r.college_type || '—'}</td>
                                        <td className="px-4 py-2.5">{r.degree || '—'}</td>
                                        <td className="px-4 py-2.5">{r.course || '—'}</td>
                                        <td className="px-4 py-2.5">{fmtDate((r.registered_date || '').slice(0, 10)) || '—'}</td>
                                        <td className="px-4 py-2.5">{fmtDate(r.schedule_date) || '—'}</td>
                                        <td className="px-4 py-2.5">{fmtTime(r.schedule_time) || '—'}</td>
                                        <td className="px-4 py-2.5">
                                            <span className={`inline-flex px-2 py-1 rounded text-[11px] font-semibold ${r.result_status?.startsWith('Shortlisted') ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'}`}>
                                                {r.result_status}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>
    );
}
