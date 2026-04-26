import React, { useState } from 'react';
import { apiFetch } from '../../api';

/**
 * Floating action bar shown when one or more candidates are selected on the
 * job detail page. Supports explicit-selection bulk decisions (via session_ids)
 * and rule-based shortcuts ("advance top N", "reject below score").
 */
export default function BulkActionBar({ jobId, selectedIds, onDone, onClear, onCompare }) {
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(null); // 'top' | 'below' | null
  const [topN, setTopN] = useState(5);
  const [belowScore, setBelowScore] = useState(50);
  const [sendEmail, setSendEmail] = useState(true);

  const apply = async (payload) => {
    setBusy(true);
    try {
      const r = await apiFetch(`/api/hr/jobs/${jobId}/bulk-decision`, {
        method: 'POST',
        body: payload,
      });
      onDone?.(r);
      onClear?.();
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Bulk action failed');
    } finally {
      setBusy(false);
      setMenuOpen(null);
    }
  };

  const applySelected = (status) => {
    if (!selectedIds.length) return;
    apply({
      status,
      session_ids: selectedIds,
      reason: `Bulk ${status} (manual selection of ${selectedIds.length})`,
      send_email: sendEmail,
    });
  };

  const applyTopN = () => apply({
    status: 'shortlisted',
    rule: 'top_n',
    top_n: topN,
    reason: `Auto-shortlist top ${topN}`,
    send_email: sendEmail,
  });

  const applyBelowScore = () => apply({
    status: 'rejected',
    rule: 'below_score',
    score: belowScore,
    reason: `Auto-reject below ${belowScore}`,
    send_email: sendEmail,
  });

  return (
    <div className="sticky bottom-4 z-10 mx-auto max-w-3xl bg-slate-900/95 backdrop-blur border border-slate-700 shadow-2xl rounded-xl p-4 flex flex-wrap items-center gap-3">
      <span className="text-sm text-slate-200 font-semibold">
        {selectedIds.length > 0 ? `${selectedIds.length} selected` : 'No selection'}
      </span>

      <label className="flex items-center gap-1.5 text-xs text-slate-400 ml-auto">
        <input
          type="checkbox"
          checked={sendEmail}
          onChange={(e) => setSendEmail(e.target.checked)}
          className="accent-indigo-500"
        />
        Email candidates
      </label>

      <div className="flex flex-wrap items-center gap-2">
        <button
          disabled={busy || !selectedIds.length}
          onClick={() => applySelected('shortlisted')}
          className="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900 text-white text-xs font-semibold"
        >
          Shortlist
        </button>
        <button
          disabled={busy || !selectedIds.length}
          onClick={() => applySelected('rejected')}
          className="px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-500 disabled:bg-red-900 text-white text-xs font-semibold"
        >
          Reject
        </button>
        <button
          disabled={busy || !selectedIds.length}
          onClick={() => applySelected('review')}
          className="px-3 py-1.5 rounded-md bg-amber-600 hover:bg-amber-500 disabled:bg-amber-900 text-white text-xs font-semibold"
        >
          Review
        </button>

        <div className="w-px h-6 bg-slate-700 mx-1" />

        <button
          disabled={busy || selectedIds.length < 2}
          onClick={() => onCompare?.(selectedIds)}
          className="px-3 py-1.5 rounded-md border border-indigo-700 text-indigo-200 hover:bg-indigo-900/40 text-xs font-semibold disabled:opacity-40"
          title={selectedIds.length < 2 ? 'Select 2+ candidates to compare' : ''}
        >
          Compare ({selectedIds.length})
        </button>

        <div className="relative">
          <button
            disabled={busy}
            onClick={() => setMenuOpen(menuOpen === 'top' ? null : 'top')}
            className="px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 text-xs font-semibold"
          >
            Advance top N ▾
          </button>
          {menuOpen === 'top' && (
            <div className="absolute bottom-full right-0 mb-2 bg-slate-900 border border-slate-700 rounded-lg p-3 min-w-[220px] space-y-2 shadow-xl">
              <label className="block text-xs text-slate-400">N</label>
              <input
                type="number"
                min={1}
                max={100}
                value={topN}
                onChange={(e) => setTopN(parseInt(e.target.value || 0, 10))}
                className="w-full px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-100 text-sm"
              />
              <button
                onClick={applyTopN}
                disabled={busy || topN <= 0}
                className="w-full px-2 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
              >
                Shortlist top {topN}
              </button>
            </div>
          )}
        </div>

        <div className="relative">
          <button
            disabled={busy}
            onClick={() => setMenuOpen(menuOpen === 'below' ? null : 'below')}
            className="px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 text-xs font-semibold"
          >
            Reject below X ▾
          </button>
          {menuOpen === 'below' && (
            <div className="absolute bottom-full right-0 mb-2 bg-slate-900 border border-slate-700 rounded-lg p-3 min-w-[220px] space-y-2 shadow-xl">
              <label className="block text-xs text-slate-400">Score threshold</label>
              <input
                type="number"
                min={0}
                max={100}
                value={belowScore}
                onChange={(e) => setBelowScore(parseFloat(e.target.value || 0))}
                className="w-full px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-100 text-sm"
              />
              <button
                onClick={applyBelowScore}
                disabled={busy}
                className="w-full px-2 py-1.5 rounded-md bg-red-600 hover:bg-red-500 text-white text-xs font-semibold"
              >
                Reject below {belowScore}
              </button>
            </div>
          )}
        </div>

        {selectedIds.length > 0 && (
          <button
            onClick={onClear}
            className="px-2 py-1 text-xs text-slate-400 hover:text-white"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
