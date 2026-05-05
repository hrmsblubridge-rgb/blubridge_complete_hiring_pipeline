import { CaretUp, CaretDown, CaretUpDown } from '@phosphor-icons/react';

/**
 * SortableHeader — column header that cycles asc → desc → none on click.
 *
 * Usage:
 *   <SortableHeader label="Name" sortKey="name" sort={sort} onSortChange={setSort} />
 *
 * `sort` shape:  { by: 'name', dir: 'asc' | 'desc' }  or  null/undefined when inactive.
 * `onSortChange(next)` receives the new sort or `null` when cycling off.
 */
export default function SortableHeader({ label, sortKey, sort, onSortChange, className = '' }) {
    const active = sort?.by === sortKey;
    const dir = active ? sort?.dir : null;

    const handleClick = () => {
        if (!active) {
            onSortChange({ by: sortKey, dir: 'asc' });
        } else if (dir === 'asc') {
            onSortChange({ by: sortKey, dir: 'desc' });
        } else {
            onSortChange(null);
        }
    };

    return (
        <button
            type="button"
            onClick={handleClick}
            data-testid={`sort-${sortKey}`}
            className={`inline-flex items-center gap-1 select-none cursor-pointer hover:text-cyan-400 transition-colors ${active ? 'text-cyan-400' : ''} ${className}`}
        >
            <span>{label}</span>
            {!active && <CaretUpDown size={12} weight="bold" className="opacity-40" />}
            {active && dir === 'asc' && <CaretUp size={12} weight="bold" />}
            {active && dir === 'desc' && <CaretDown size={12} weight="bold" />}
        </button>
    );
}
