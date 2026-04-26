import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../../api';

export default function JobsList() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    apiFetch('/api/hr/jobs')
      .then((j) => active && setJobs(j))
      .catch((e) => active && setError(typeof e.detail === 'string' ? e.detail : 'Failed to load'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  if (loading) return <p className="text-slate-400">Loading jobs...</p>;
  if (error) return <p className="text-red-300">{error}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Jobs</h1>
        <Link
          to="/hr/jobs/new"
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold"
        >
          + New Job
        </Link>
      </div>

      {jobs.length === 0 ? (
        <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-10 text-center text-slate-400">
          No jobs yet.
        </div>
      ) : (
        <div className="bg-slate-800/40 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-5 py-3">Title</th>
                <th className="text-left px-5 py-3">Department</th>
                <th className="text-left px-5 py-3">Status</th>
                <th className="text-left px-5 py-3">Thresholds</th>
                <th className="text-left px-5 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {jobs.map((job) => (
                <tr key={job.id} className="hover:bg-slate-800/70">
                  <td className="px-5 py-3">
                    <Link to={`/hr/jobs/${job.id}`} className="text-indigo-300 hover:underline font-medium">
                      {job.title}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-slate-300">{job.department || '—'}</td>
                  <td className="px-5 py-3 text-slate-300">{job.status}</td>
                  <td className="px-5 py-3 text-slate-400 text-xs">
                    reject &lt; {job.auto_reject_threshold} · shortlist ≥ {job.shortlist_threshold}
                  </td>
                  <td className="px-5 py-3 text-slate-400 text-xs">
                    {new Date(job.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
