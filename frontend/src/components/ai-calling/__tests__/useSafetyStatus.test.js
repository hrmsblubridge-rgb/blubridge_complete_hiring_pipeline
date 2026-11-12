/**
 * Regression tests for useSafetyStatus — the hook that drove the "Safety
 * status unavailable — calling blocked." preview-env bug.
 *
 * What the old bug was
 * --------------------
 * The previous implementation had a module-level dedupe promise bound to the
 * first caller's AbortController. When the header and a page mounted the hook
 * simultaneously, both awaited the SAME promise. Any time one hook instance
 * called `load()` again, it aborted its own controller — rejecting the shared
 * promise for every other caller with AbortError. Two such rejections tripped
 * FAILURE_THRESHOLD and flipped the UI to "unavailable" even while
 * /safety-status was returning 200.
 *
 * These tests exercise:
 *  1. Deduplication: concurrent callers share one in-flight request.
 *  2. Polling + recovery: after a transient failure the next good response
 *     clears the failure counter and keeps the UI authoritative.
 *  3. Rapid navigation: a second mount that unmounts before the first response
 *     arrives MUST NOT abort the shared request for other live mounts.
 *  4. callingBlocked() pure helper — authoritative=false must block, and
 *     emergency_stop/server/provider gates must each independently block.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useSafetyStatus, callingBlocked } from '../useSafetyStatus';

// Mock the axios instance the hook uses.
jest.mock('../../../pages/ai-calling/aiApi', () => ({
    aiApi: { get: jest.fn() },
}));
const { aiApi } = require('../../../pages/ai-calling/aiApi');

const GOOD = {
    authoritative: true,
    emergency_stop: { active: true },
    switches: { ai_test_enabled: true, ai_live_enabled: false },
    server: { outbound_calling_enabled: false },
    provider: { ready: true },
};

beforeEach(() => jest.clearAllMocks());

test('callingBlocked() blocks when authoritative=false', () => {
    const r = callingBlocked({ authoritative: false, error: 'X' });
    expect(r.blocked).toBe(true);
    expect(r.reasons[0]).toMatch(/unavailable|X/);
});

test('callingBlocked() blocks when emergency_stop active, server disabled, or provider not ready', () => {
    expect(callingBlocked({ authoritative: true, emergency_stop: { active: true }, server: { outbound_calling_enabled: true }, provider: { ready: true } }).blocked).toBe(true);
    expect(callingBlocked({ authoritative: true, emergency_stop: { active: false }, server: { outbound_calling_enabled: false }, provider: { ready: true } }).blocked).toBe(true);
    expect(callingBlocked({ authoritative: true, emergency_stop: { active: false }, server: { outbound_calling_enabled: true }, provider: { ready: false } }).blocked).toBe(true);
    expect(callingBlocked({ authoritative: true, emergency_stop: { active: false }, server: { outbound_calling_enabled: true }, provider: { ready: true } }).blocked).toBe(false);
});

test('two concurrent hook mounts share one in-flight request (dedupe)', async () => {
    aiApi.get.mockResolvedValue({ data: GOOD });
    const a = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    const b = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    await waitFor(() => expect(a.result.current.safety).toEqual(GOOD));
    await waitFor(() => expect(b.result.current.safety).toEqual(GOOD));
    // Dedupe means one network call for the two simultaneous mounts.
    expect(aiApi.get).toHaveBeenCalledTimes(1);
    a.unmount(); b.unmount();
});

test('a transient failure DOES NOT flip UI to unavailable if good data had landed before', async () => {
    aiApi.get.mockResolvedValueOnce({ data: GOOD });
    const h = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    await waitFor(() => expect(h.result.current.safety).toEqual(GOOD));

    aiApi.get.mockRejectedValueOnce(new Error('transient'));
    await act(async () => { await h.result.current.refresh(); });

    // Last-known-good preserved; banner not shown.
    expect(h.result.current.safety).toEqual(GOOD);
    expect(h.result.current.safety.authoritative).toBe(true);
    h.unmount();
});

test('N consecutive failures with no prior data flip authoritative=false', async () => {
    aiApi.get.mockRejectedValue(new Error('boom'));
    const h = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    // First poll + explicit refreshes -> cross FAILURE_THRESHOLD.
    await waitFor(() => expect(aiApi.get).toHaveBeenCalled());
    await act(async () => { await h.result.current.refresh(); });
    await act(async () => { await h.result.current.refresh(); });
    await waitFor(() => expect(h.result.current.safety?.authoritative).toBe(false));
    expect(callingBlocked(h.result.current.safety).blocked).toBe(true);
    h.unmount();
});

test('rapid unmount of one of two concurrent mounts does NOT break the other', async () => {
    // Simulates the real bug: header mounts (A), page mounts (B), then page
    // unmounts/re-mounts quickly (tab switch). Old hook aborted the shared
    // in-flight here and A received AbortError. Fix: no per-call aborts.
    let resolve;
    aiApi.get.mockImplementation(() => new Promise(r => { resolve = r; }));
    const a = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    const b = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    // Unmount B before response arrives.
    b.unmount();
    // Now land the response.
    resolve({ data: GOOD });
    await waitFor(() => expect(a.result.current.safety).toEqual(GOOD));
    a.unmount();
});

test('successful refresh clears a previous failure (recovery)', async () => {
    aiApi.get.mockRejectedValueOnce(new Error('boom'));
    const h = renderHook(() => useSafetyStatus({ pollMs: 100000 }));
    await waitFor(() => expect(aiApi.get).toHaveBeenCalled());
    aiApi.get.mockResolvedValueOnce({ data: GOOD });
    await act(async () => { await h.result.current.refresh(); });
    await waitFor(() => expect(h.result.current.safety).toEqual(GOOD));
    expect(h.result.current.safety.authoritative).toBe(true);
    h.unmount();
});
