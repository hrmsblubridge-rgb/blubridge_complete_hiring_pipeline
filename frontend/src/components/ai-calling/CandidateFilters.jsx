import { MagnifyingGlass } from '@phosphor-icons/react';
import { READINESS } from './constants';

const sel = 'bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-teal-500';

export const CandidateFilters = ({ q, setQ }) => {
    const set = (k) => (e) => setQ(p => ({ ...p, [k]: e.target.value, page: 1 }));
    return (
        <div className="flex flex-wrap gap-2 mb-3" data-testid="candidate-filters">
            <div className="relative flex-1 min-w-[200px]">
                <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9b9787]" />
                <input value={q.search} onChange={set('search')} placeholder="Search name, role, ID or phone digits" data-testid="candidate-search" className={`${sel} w-full pl-9`} />
            </div>
            <select value={q.consent} onChange={set('consent')} data-testid="filter-consent" className={sel}>
                <option value="all">All consent states</option><option value="granted">Consent recorded</option><option value="not_granted">No consent</option><option value="opted_out">Do Not Call</option>
            </select>
            <select value={q.source} onChange={set('source')} data-testid="filter-source" className={sel}>
                <option value="">All sources</option><option value="manual">Manual</option><option value="upload">Upload</option>
            </select>
            <select value={q.language} onChange={set('language')} data-testid="filter-language" className={sel}>
                <option value="">All languages</option><option>English</option><option>Tamil</option>
            </select>
            <select value={q.ready} onChange={set('ready')} data-testid="filter-readiness" className={sel}>
                <option value="">All readiness</option>
                {Object.entries(READINESS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </select>
        </div>
    );
};
