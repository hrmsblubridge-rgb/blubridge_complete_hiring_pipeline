// Shared authoritative safety-status hook. Every AI Calling tab reads from this one source so the
// screens cannot disagree about Emergency Stop / server-flag / provider readiness state.
//
// The backend's /safety-status is the only trusted source. If it fails, `authoritative === false`
// and the UI MUST treat every calling action as blocked (never guess OFF).
import { useCallback, useEffect, useRef, useState } from 'react';
import { aiApi } from '../../pages/ai-calling/aiApi';

const POLL_MS = 15000;

export function useSafetyStatus({ pollMs = POLL_MS } = {}) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const alive = useRef(true);

    const load = useCallback(async () => {
        try {
            const r = await aiApi.get('/safety-status');
            if (!alive.current) return;
            setData(r.data); setError(null);
        } catch (e) {
            if (!alive.current) return;
            setError(e); setData((d) => d || { authoritative: false, error: 'Safety status unavailable — calling blocked.' });
        } finally {
            if (alive.current) setLoading(false);
        }
    }, []);

    useEffect(() => {
        alive.current = true; load();
        const id = setInterval(load, pollMs);
        return () => { alive.current = false; clearInterval(id); };
    }, [load, pollMs]);

    return { safety: data, error, loading, refresh: load };
}

// Pure helper so callers (and tests) can't miss the authoritative guard.
export function callingBlocked(safety) {
    if (!safety || safety.authoritative === false) return { blocked: true, reasons: [safety?.error || 'Safety status unavailable — calling blocked.'] };
    const reasons = [];
    if (safety.emergency_stop?.active) reasons.push('Emergency Stop is ON');
    if (!safety.server?.outbound_calling_enabled) reasons.push('Server outbound calling is disabled');
    if (!safety.provider?.ready) reasons.push('Bolna provider is not verified');
    return { blocked: reasons.length > 0, reasons };
}
