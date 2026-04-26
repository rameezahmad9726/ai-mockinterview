import React, { useState } from 'react';
import { apiFetch } from '../../api';

export default function InviteModal({ jobId, onClose, onDone }) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const parseInvites = () => {
    const lines = text.split(/[\n,;]+/).map((l) => l.trim()).filter(Boolean);
    return lines.map((line) => {
      const m = line.match(/^\s*(.*?)\s*<\s*([^>]+)\s*>\s*$/);
      if (m) return { full_name: m[1] || undefined, email: m[2] };
      return { email: line };
    }).filter((x) => /\S+@\S+\.\S+/.test(x.email));
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    const invites = parseInvites();
    if (!invites.length) {
      setError('Add at least one valid email (one per line).');
      return;
    }
    setSubmitting(true);
    try {
      const r = await apiFetch(`/api/hr/jobs/${jobId}/invites`, {
        method: 'POST',
        body: { invites },
      });
      setResult(r);
      onDone?.(r);
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Invite failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 bg-black/60 flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <h3 className="text-white font-semibold">Invite candidates</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">×</button>
        </div>

        <form onSubmit={onSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Emails
            </label>
            <textarea
              rows={8}
              required
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
              placeholder={'alice@example.com\nBob Smith <bob@example.com>\ncarol@example.com'}
            />
            <p className="text-xs text-slate-500 mt-1">
              One per line. Optional: <code>Name &lt;email@x.com&gt;</code>.
            </p>
          </div>

          {error && (
            <div className="text-sm text-red-300 bg-red-950/50 border border-red-800 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {result && (
            <div className="text-sm text-emerald-200 bg-emerald-950/40 border border-emerald-800 rounded-lg px-3 py-2">
              {result.created} invited · {result.skipped} already invited
            </div>
          )}

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 text-white font-semibold"
            >
              {submitting ? 'Sending...' : 'Send invitations'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
