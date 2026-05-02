import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { API_BASE, apiFetch, getToken } from '../../api';
import InviteModal from './InviteModal';
import BulkActionBar from './BulkActionBar';

const STATUS_COLORS = {
  invited: 'bg-slate-700 text-slate-200',
  started: 'bg-blue-900/60 text-blue-200',
  submitted: 'bg-amber-900/60 text-amber-200',
  analyzing: 'bg-amber-900/60 text-amber-200',
  scored: 'bg-emerald-900/60 text-emerald-200',
  expired: 'bg-red-900/60 text-red-200',
  failed: 'bg-red-900/60 text-red-200',
};

const DECISION_COLORS = {
  shortlisted: 'bg-emerald-600/30 text-emerald-200 border-emerald-700',
  rejected: 'bg-red-600/30 text-red-200 border-red-700',
  review: 'bg-amber-600/30 text-amber-200 border-amber-700',
  advanced: 'bg-indigo-600/30 text-indigo-200 border-indigo-700',
  withdrawn: 'bg-slate-700 text-slate-200 border-slate-600',
};

function Pill({ children, className = '' }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

function ProgressCell({ status, progress, message }) {
  const show = ['submitted', 'analyzing'].includes(status);
  if (!show) return null;
  const pct = Math.max(0, Math.min(100, Number(progress || 0)));
  return (
    <div className="mt-2 w-44">
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className="h-full bg-amber-500 transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[11px] text-slate-400 mt-1 truncate">
        {message || `${pct}% complete`}
      </p>
    </div>
  );
}

export default function JobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showInvite, setShowInvite] = useState(false);
  const [selected, setSelected] = useState(new Set());

  const selectedIds = useMemo(() => [...selected], [selected]);
  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAll = (ids) => {
    setSelected((prev) => {
      if (ids.every((id) => prev.has(id))) return new Set();
      return new Set(ids);
    });
  };

  const downloadCsv = async () => {
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/hr/jobs/${jobId}/export.csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      alert('Export failed');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `job_${jobId}_candidates.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const load = useCallback(async () => {
    try {
      const [j, s] = await Promise.all([
        apiFetch(`/api/hr/jobs/${jobId}`),
        apiFetch(`/api/hr/jobs/${jobId}/sessions`),
      ]);
      setJob(j);
      setSessions(s);
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Failed to load job');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const hasInFlightAnalysis = sessions.some((s) => ['submitted', 'analyzing'].includes(s.status));
    if (!hasInFlightAnalysis) return;
    const timer = setInterval(() => load(), 3000);
    return () => clearInterval(timer);
  }, [sessions, load]);

  const onResend = async (externalId) => {
    try {
      await apiFetch(`/api/hr/sessions/${externalId}/resend-invite`, { method: 'POST' });
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Failed to resend');
    }
  };

  if (loading) return <p className="text-slate-400">Loading job...</p>;
  if (error) return <p className="text-red-300">{error}</p>;
  if (!job) return null;

  return (
    <div className="space-y-8">
      <div>
        <Link to="/hr/jobs" className="text-sm text-indigo-400 hover:underline">&larr; All jobs</Link>
        <div className="mt-2 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">{job.title}</h1>
            <p className="text-slate-400 text-sm">
              {job.department || '—'} · {job.seniority || '—'} ·{' '}
              <span className="text-slate-300">{job.status}</span>
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={downloadCsv}
              className="px-3 py-2 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 text-sm"
            >
              Export CSV
            </button>
            <button
              onClick={() => setShowInvite(true)}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold"
            >
              + Invite candidates
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-3">
          <p className="text-xs uppercase text-slate-500">Questions</p>
          <p className="text-white font-semibold">{job.num_questions}</p>
        </div>
        <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-3">
          <p className="text-xs uppercase text-slate-500">Seconds / answer</p>
          <p className="text-white font-semibold">{job.seconds_per_answer}</p>
        </div>
        <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-3">
          <p className="text-xs uppercase text-slate-500">Shortlist ≥</p>
          <p className="text-white font-semibold">{job.shortlist_threshold}</p>
        </div>
        <div className="bg-slate-800/40 border border-slate-700 rounded-lg p-3">
          <p className="text-xs uppercase text-slate-500">Auto-reject &lt;</p>
          <p className="text-white font-semibold">{job.auto_reject_threshold}</p>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Candidates ({sessions.length})</h2>
        {sessions.length === 0 ? (
          <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-10 text-center text-slate-400">
            No candidates yet.
            <div className="mt-3">
              <button
                onClick={() => setShowInvite(true)}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold"
              >
                + Invite candidates
              </button>
            </div>
          </div>
        ) : (
          <>
          <div className="bg-slate-800/40 border border-slate-700 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/60 text-slate-400 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-3 w-8">
                    <input
                      type="checkbox"
                      className="accent-indigo-500"
                      checked={sessions.length > 0 && sessions.every((s) => selected.has(s.external_id))}
                      onChange={() => toggleAll(sessions.map((s) => s.external_id))}
                    />
                  </th>
                  <th className="text-left px-5 py-3">Candidate</th>
                  <th className="text-left px-5 py-3">Status</th>
                  <th className="text-left px-5 py-3">Score</th>
                  <th className="text-left px-5 py-3">Decision</th>
                  <th className="text-left px-5 py-3">Invited</th>
                  <th className="text-left px-5 py-3">Expires</th>
                  <th className="text-right px-5 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sessions.map((s) => (
                  <tr key={s.id} className={`hover:bg-slate-800/70 ${selected.has(s.external_id) ? 'bg-slate-800/60' : ''}`}>
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        className="accent-indigo-500"
                        checked={selected.has(s.external_id)}
                        onChange={() => toggle(s.external_id)}
                      />
                    </td>
                    <td className="px-5 py-3">
                      <Link to={`/hr/sessions/${s.external_id}`} className="text-slate-100 hover:text-indigo-300">
                        {s.candidate.full_name || s.candidate.email.split('@')[0]}
                      </Link>
                      <p className="text-xs text-slate-500">{s.candidate.email}</p>
                    </td>
                    <td className="px-5 py-3">
                      <Pill className={STATUS_COLORS[s.status] || 'bg-slate-700 text-slate-200'}>{s.status}</Pill>
                      <ProgressCell
                        status={s.status}
                        progress={s.progress}
                        message={s.progress_message}
                      />
                    </td>
                    <td className="px-5 py-3 text-slate-200">{s.overall_score?.toFixed?.(1) ?? '—'}</td>
                    <td className="px-5 py-3">
                      {s.decision ? (
                        <Pill className={`border ${DECISION_COLORS[s.decision] || 'border-slate-600 text-slate-300'}`}>
                          {s.decision}
                        </Pill>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-slate-400 text-xs">
                      {new Date(s.invited_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-slate-400 text-xs">
                      {new Date(s.expires_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => onResend(s.external_id)}
                        className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-300 hover:bg-slate-800"
                      >
                        Resend
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <BulkActionBar
            jobId={jobId}
            selectedIds={selectedIds}
            onDone={() => load()}
            onClear={() => setSelected(new Set())}
            onCompare={(ids) => navigate(`/hr/jobs/${jobId}/compare?ids=${ids.join(',')}`)}
          />
          </>
        )}
      </div>

      {showInvite && (
        <InviteModal
          jobId={jobId}
          onClose={() => { setShowInvite(false); load(); }}
          onDone={() => load()}
        />
      )}
    </div>
  );
}
