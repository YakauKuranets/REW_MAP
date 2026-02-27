import React, { useEffect, useMemo, useState } from 'react';
import useMapStore from '../store/useMapStore';

const LIST_ENDPOINT = process.env.REACT_APP_PENDING_LIST_URL || '/api/pending';
const APPROVE_ENDPOINT = process.env.REACT_APP_PENDING_APPROVE_URL || '/api/pending';
const REJECT_ENDPOINT = process.env.REACT_APP_PENDING_REJECT_URL || '/api/pending';

const toNumber = (value) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const resolvePendingId = (pending) => String(pending?.id ?? pending?.pending ?? pending?.pending_id ?? '');

/**
 * @typedef {{status: string, id?: number, remaining?: number}} ModerationResponse
 */

/**
 * Moderates a pending marker with strict response validation.
 * @param {'approve'|'reject'} action
 * @param {string} markerId
 * @returns {Promise<ModerationResponse>}
 */
const moderatePending = async (action, markerId) => {
  const endpoint = action === 'approve'
    ? `${APPROVE_ENDPOINT}/${markerId}/approve`
    : `${REJECT_ENDPOINT}/${markerId}/reject`;

  const response = await fetch(endpoint, { method: 'POST' });
  if (!response.ok) throw new Error(`pending_${action}_failed`);

  const payload = await response.json();
  if (!payload || typeof payload !== 'object' || typeof payload.status !== 'string') {
    throw new Error('invalid_moderation_payload');
  }

  return payload;
};

export default function PendingRequestsPanel({ onFlyToPending }) {
  const pendingMarkers = useMapStore((s) => s.pendingMarkers);
  const setPendingMarkers = useMapStore((s) => s.setPendingMarkers);
  const removePendingMarker = useMapStore((s) => s.removePendingMarker);
  const setActivePendingMarker = useMapStore((s) => s.setActivePendingMarker);
  const activePendingMarkerId = useMapStore((s) => s.activePendingMarkerId);
  const addIncident = useMapStore((s) => s.addIncident);

  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let mounted = true;

    const loadPending = async () => {
      try {
        const response = await fetch(LIST_ENDPOINT);
        if (!response.ok) return;
        const payload = await response.json();
        if (mounted) setPendingMarkers(Array.isArray(payload) ? payload : []);
      } catch (_e) {
        // best effort only
      }
    };

    loadPending();

    return () => {
      mounted = false;
    };
  }, [setPendingMarkers]);

  const selectedPending = useMemo(() => {
    if (!activePendingMarkerId) return null;
    return pendingMarkers.find((item) => resolvePendingId(item) === String(activePendingMarkerId)) || null;
  }, [pendingMarkers, activePendingMarkerId]);

  const focusPending = (pending) => {
    const markerId = resolvePendingId(pending);
    setActivePendingMarker(markerId);
    const lon = toNumber(pending.lon ?? pending.longitude);
    const lat = toNumber(pending.lat ?? pending.latitude);
    if (lon !== null && lat !== null && onFlyToPending) {
      onFlyToPending({ lon, lat, id: markerId });
    }
  };

  const approvePending = async (pending) => {
    if (!pending || isSubmitting) return;
    const markerId = resolvePendingId(pending);

    setIsSubmitting(true);
    try {
      const payload = await moderatePending('approve', markerId);
      removePendingMarker(markerId);

      const lon = toNumber(pending.lon ?? pending.longitude);
      const lat = toNumber(pending.lat ?? pending.latitude);
      if (lon !== null && lat !== null) {
        addIncident({
          ...pending,
          id: payload.id ?? pending.address_id ?? pending.id,
          lon,
          lat,
          status: 'approved',
          source: 'pending',
        });
      }
    } catch (_e) {
      // websocket may still deliver eventual state
    } finally {
      setIsSubmitting(false);
    }
  };

  const rejectPending = async (pending) => {
    if (!pending || isSubmitting) return;
    const markerId = resolvePendingId(pending);

    setIsSubmitting(true);
    try {
      await moderatePending('reject', markerId);
      removePendingMarker(markerId);
    } catch (_e) {
      // websocket may still deliver eventual state
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    const onKeyDown = (event) => {
      if (!selectedPending || isSubmitting) return;
      if (event.key === 'Enter') {
        event.preventDefault();
        approvePending(selectedPending);
      }
      if (event.key === 'Delete') {
        event.preventDefault();
        rejectPending(selectedPending);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedPending, isSubmitting]);

  return (
    <aside className="pointer-events-auto absolute top-20 left-4 w-80 bg-black/70 backdrop-blur-md border border-yellow-500/50 rounded-xl shadow-[0_0_15px_rgba(234,179,8,0.2)] z-40 overflow-hidden">
      <div className="flex items-center gap-2 border-b border-yellow-500/30 px-3 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-yellow-300 animate-pulse shadow-[0_0_10px_rgba(250,204,21,0.9)]" />
        <h3 className="text-[11px] font-black uppercase tracking-[0.16em] text-yellow-100">ОЖИДАЮТ ПОДТВЕРЖДЕНИЯ</h3>
        <span className="ml-auto rounded border border-yellow-300/40 bg-yellow-300/10 px-1.5 py-0.5 text-[10px] font-bold text-yellow-200">
          {pendingMarkers.length}
        </span>
      </div>

      <div className="max-h-[420px] overflow-y-auto p-3 space-y-2.5">
        {pendingMarkers.map((pending) => {
          const markerId = resolvePendingId(pending);
          const isActive = markerId === String(activePendingMarkerId);
          const lon = toNumber(pending.lon ?? pending.longitude);
          const lat = toNumber(pending.lat ?? pending.latitude);

          return (
            <div
              key={markerId}
              className={`rounded-lg border p-2.5 ${isActive ? 'border-yellow-300/70 bg-yellow-300/10' : 'border-white/10 bg-black/40'}`}
            >
              <button type="button" onClick={() => focusPending(pending)} className="w-full text-left">
                <div className="text-[11px] uppercase tracking-wider text-yellow-200/90">
                  {pending.reporter || pending.user_id || pending.author || 'Agent'}
                </div>
                <div className="mt-1 text-xs text-slate-100">
                  {pending.address || pending.name || pending.title || 'Новая гео-заявка'}
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  {lat !== null && lon !== null ? `LAT ${lat.toFixed(5)} · LON ${lon.toFixed(5)}` : 'Координаты не указаны'}
                </div>
              </button>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => approvePending(pending)}
                  disabled={isSubmitting}
                  className="rounded border border-cyan-400/60 bg-cyan-500/15 px-2 py-1.5 text-[11px] font-bold text-cyan-200 transition hover:bg-cyan-500/25 disabled:opacity-50"
                >
                  ✓ Принять
                </button>
                <button
                  type="button"
                  onClick={() => rejectPending(pending)}
                  disabled={isSubmitting}
                  className="rounded border border-red-400/60 bg-red-500/15 px-2 py-1.5 text-[11px] font-bold text-red-200 transition hover:bg-red-500/25 disabled:opacity-50"
                >
                  ✗ Отклонить
                </button>
              </div>
            </div>
          );
        })}

        {pendingMarkers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-white/20 p-3 text-center text-xs text-slate-400">
            Нет входящих заявок.
          </div>
        ) : null}
      </div>
    </aside>
  );
}
