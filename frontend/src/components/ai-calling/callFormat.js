const STATE_CLS = {
    Pending: 'bg-amber-100 text-amber-800', 'In Progress': 'bg-sky-100 text-sky-800', Completed: 'bg-emerald-100 text-emerald-800',
    Failed: 'bg-rose-100 text-rose-700', 'Needs Review': 'bg-orange-100 text-orange-800', Reviewed: 'bg-zinc-200 text-zinc-700',
};

export const StateBadge = ({ s }) => (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold whitespace-nowrap ${STATE_CLS[s] || 'bg-zinc-100 text-zinc-700'}`} data-testid="call-state-badge">{s}</span>
);

export const yesNo = (v) => (v === true ? 'Yes' : v === false ? 'No' : 'UNKNOWN');

export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : null);
