import { useState, useEffect } from 'react';
import { CaretLeft, CaretRight, CaretDoubleLeft, CaretDoubleRight } from '@phosphor-icons/react';

/**
 * Advanced pagination control with first / prev / next / last buttons,
 * page-size selector, and a manual "Go to page" input.
 *
 * Disables << + < on first page; > + >> on last page.
 *
 * Props:
 *   page         - current page (1-based)
 *   totalPages   - total number of pages (server-computed)
 *   total        - total record count (for label)
 *   pageSize     - current page size
 *   pageSizes    - allowed page sizes (default [10, 50, 100, 150, 200, 250, 300, 500])
 *   onPageChange - (newPage) => void
 *   onPageSizeChange - (newSize) => void
 */
const DEFAULT_SIZES = [10, 50, 100, 150, 200, 250, 300, 500];

export default function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  pageSizes = DEFAULT_SIZES,
  onPageChange,
  onPageSizeChange,
}) {
  const [goInput, setGoInput] = useState(String(page));

  useEffect(() => { setGoInput(String(page)); }, [page]);

  if (!total || total <= 0) return null;

  const isFirst = page <= 1;
  const isLast = page >= totalPages;

  const handleGo = () => {
    const n = parseInt(goInput, 10);
    if (Number.isFinite(n) && n >= 1 && n <= totalPages) {
      onPageChange(n);
    } else {
      setGoInput(String(page));
    }
  };

  return (
    <div className="flex items-center justify-between mt-4 flex-wrap gap-3" data-testid="pagination">
      <div className="flex items-center gap-3">
        <span className="text-sm text-zinc-500">
          Page {page} of {totalPages} ({total} records)
        </span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          data-testid="page-size-select"
          className="bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-sm"
        >
          {pageSizes.map((s) => <option key={s} value={s}>{s} / page</option>)}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <button
          disabled={isFirst}
          onClick={() => onPageChange(1)}
          data-testid="first-page-btn"
          className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="First page"
        >
          <CaretDoubleLeft size={14} />
        </button>
        <button
          disabled={isFirst}
          onClick={() => onPageChange(page - 1)}
          data-testid="prev-page-btn"
          className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Previous page"
        >
          <CaretLeft size={14} />
        </button>

        <input
          type="number"
          min={1}
          max={totalPages}
          value={goInput}
          onChange={(e) => setGoInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleGo()}
          data-testid="page-input"
          className="w-16 bg-zinc-900 border border-zinc-700 px-2 py-1.5 text-sm focus:outline-none focus:border-zinc-500 text-center"
        />
        <button
          onClick={handleGo}
          data-testid="go-page-btn"
          className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm"
        >
          Go
        </button>

        <button
          disabled={isLast}
          onClick={() => onPageChange(page + 1)}
          data-testid="next-page-btn"
          className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Next page"
        >
          <CaretRight size={14} />
        </button>
        <button
          disabled={isLast}
          onClick={() => onPageChange(totalPages)}
          data-testid="last-page-btn"
          className="px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sm disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Last page"
        >
          <CaretDoubleRight size={14} />
        </button>
      </div>
    </div>
  );
}
