import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../../api';

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-3xl font-bold text-white mt-1">{value}</p>
      {sub ? <p className="text-xs text-slate-500 mt-1">{sub}</p> : null}
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [s, j] = await Promise.all([
          apiFetch('/api/hr/dashboard/summary'),
          apiFetch('/api/hr/jobs'),
        ]);
        if (!active) return;
        setSummary(s);
        setJobs(j);
      } catch (e) {
        if (!active) return;
        setError(typeof e.detail === 'string' ? e.detail : 'Failed to load dashboard');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  if (loading) return <p className="text-slate-400">Loading dashboard...</p>;
  if (error) return <p className="text-red-300">{error}</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <Link
          to="/hr/jobs/new"
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold"
        >
          + New Job
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          label="Jobs"
          value={summary.jobs.total}
          sub={`${summary.jobs.open} open`}
        />
        <StatCard
          label="Sessions"
          value={summary.sessions.total}
          sub={`${summary.sessions.submitted} submitted`}
        />
        <StatCard label="Shortlisted" value={summary.decisions.shortlisted} />
        <StatCard label="Rejected" value={summary.decisions.rejected} />
      </div>

      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Recent jobs</h2>
        {jobs.length === 0 ? (
          <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-8 text-center text-slate-400">
            No jobs yet. <Link className="text-indigo-400 hover:underline" to="/hr/jobs/new">Create your first job</Link>.
          </div>
        ) : (
          <div className="bg-slate-800/40 border border-slate-700 rounded-xl divide-y divide-slate-700">
            {jobs.map((job) => (
              <Link
                key={job.id}
                to={`/hr/jobs/${job.id}`}
                className="flex items-center justify-between px-5 py-3 hover:bg-slate-800/60 transition-colors"
              >
                <div>
                  <p className="text-white font-medium">{job.title}</p>
                  <p className="text-xs text-slate-400">
                    {job.department || '—'} · {job.seniority || '—'} · {job.status}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">
                    shortlist ≥ {job.shortlist_threshold} · reject &lt; {job.auto_reject_threshold}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
