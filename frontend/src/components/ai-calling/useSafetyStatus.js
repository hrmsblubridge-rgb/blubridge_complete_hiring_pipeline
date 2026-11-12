// Shared authoritative safety-status hook.
//
// A1 reliability fixes:
//  - Keep last-known-good data on transient errors (never flip to "unavailable" because of a
//    single tab-switch race or timeout). Only mark the state unavailable after N consecutive
//    failures, so transient network blips don't block the UI.
//  - Single-flight per hook instance via an AbortController; rapid tab changes don't produce
//    duplicate concurrent requests or stale resolves.
//  - Dedupe across components: a module-level in-flight promise means multiple tabs that mount
//    the hook simultaneously (header + page) share one request, not spawn N.
//  - Clear in-flight on unmount.
//
// The backend's /safety-status is still the only trusted source. Unknown state still blocks
// calling via `callingBlocked()` — but only after we've actually confirmed we can't reach it.
import { useCallback, useEffect, useRef, useState } from 'react';
import { aiApi } from '../../pages/ai-calling/aiApi';

const POLL_MS = 15000;
const FAILURE_THRESHOLD = 2;    // mark unavailable only after this many *consecutive* failures
let inflight = null;             // module-level dedupe across simultaneous mounts

async function fetchOnce(signal) {
    if (inflight) return inflight;
    inflight = (async () => {
        try { return (await aiApi.get('/safety-status', { signal })).data; }
        finally { inflight = null; }
    })();
    return inflight;
}

export function useSafetyStatus({ pollMs = POLL_MS } = {}) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const alive = useRef(true);
    const failures = useRef(0);
    const abortRef = useRef(null);

    const load = useCallback(async () => {
        if (abortRef.current) abortRef.current.abort();
        const ctl = new AbortController(); abortRef.current = ctl;
        try {
            const r = await fetchOnce(ctl.signal);
            if (!alive.current) return;
            failures.current = 0;
            setData(r); setError(null);
        } catch (e) {
            if (!alive.current || e?.name === 'CanceledError' || e?.name === 'AbortError') return;
            failures.current += 1; setError(e);
            // Only flip to unavailable after FAILURE_THRESHOLD consecutive errors AND no prior data.
            if (failures.current >= FAILURE_THRESHOLD && !data) {
                setData({ authoritative: false, error: 'Safety status unavailable — calling blocked.' });
            }
            // If we had prior good data, keep it — the previous poll's answer is still the truth.
        } finally {
            if (alive.current) setLoading(false);
        }
    }, [data]);

    useEffect(() => {
        alive.current = true; load();
        const id = setInterval(load, pollMs);
        return () => {
            alive.current = false;
            clearInterval(id);
            if (abortRef.current) abortRef.current.abort();
        };
    }, [load, pollMs]);

    return { safety: data, error, loading, refresh: load };
}

// Pure helper so callers can't miss the authoritative guard.
export function callingBlocked(safety) {
    if (!safety || safety.authoritative === false) {
        return { blocked: true, reasons: [safety?.error || 'Safety status unavailable — calling blocked.'] };
    }
    const reasons = [];
    if (safety.emergency_stop?.active) reasons.push('Emergency Stop is ON');
    if (!safety.server?.outbound_calling_enabled) reasons.push('Server outbound calling is disabled');
    if (!safety.provider?.ready) reasons.push('Bolna provider is not verified');
    return { blocked: reasons.length > 0, reasons };
}
