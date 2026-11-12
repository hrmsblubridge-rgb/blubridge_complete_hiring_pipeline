// Shared authoritative safety-status hook.
//
// Reliability fixes (iter: no-abort-race):
//  - Shared in-flight promise across hook instances (header + page) so a second mount reuses
//    one request instead of spawning N.
//  - No per-call AbortController. The old design let one hook instance abort the shared
//    in-flight promise on cleanup / strict-mode double-invoke, rejecting it for every other
//    caller with AbortError. Two such rejections (FAILURE_THRESHOLD) flipped the UI to
//    "Safety status unavailable — calling blocked." even while the backend was healthy.
//  - `alive` ref prevents state updates after unmount — safer than tearing down the request.
//  - Only flip to "unavailable" after N consecutive real failures AND we never had good data.
//  - Last-known-good data is kept on transient errors.
//
// The backend's /safety-status is still the only trusted source.
import { useCallback, useEffect, useRef, useState } from 'react';
import { aiApi } from '../../pages/ai-calling/aiApi';

const POLL_MS = 15000;
const FAILURE_THRESHOLD = 2;    // mark unavailable only after this many *consecutive* failures
let inflight = null;             // module-level dedupe across simultaneous mounts

async function fetchOnce() {
    if (inflight) return inflight;
    inflight = (async () => {
        try { return (await aiApi.get('/safety-status')).data; }
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
    const dataRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const r = await fetchOnce();
            if (!alive.current) return;
            failures.current = 0;
            dataRef.current = r;
            setData(r); setError(null);
        } catch (e) {
            if (!alive.current) return;
            if (e?.name === 'CanceledError' || e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') return;
            failures.current += 1; setError(e);
            // Only flip to unavailable after FAILURE_THRESHOLD consecutive errors AND no prior data.
            if (failures.current >= FAILURE_THRESHOLD && !dataRef.current) {
                setData({ authoritative: false, error: 'Safety status unavailable — calling blocked.' });
            }
            // If we had prior good data, keep it — the previous poll's answer is still the truth.
        } finally {
            if (alive.current) setLoading(false);
        }
    }, []);

    useEffect(() => {
        alive.current = true;
        load();
        const id = setInterval(load, pollMs);
        return () => {
            alive.current = false;
            clearInterval(id);
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
