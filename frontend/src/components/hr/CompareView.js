import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiFetch } from '../../api';

const DECISION_COLORS = {
  shortlisted: 'bg-emerald-600/20 text-emerald-200 border-emerald-700',
  rejected: 'bg-red-600/20 text-red-200 border-red-700',
  review: 'bg-amber-600/20 text-amber-200 border-amber-700',
  advanced: 'bg-indigo-600/20 text-indigo-200 border-indigo-700',
};

function scoreAccent(v) {
  if (v == null) return 'text-slate-400';
  if (v >= 80) return 'text-emerald-300';
  if (v < 50) return 'text-red-300';
  return 'text-amber-300';
}

function Cell({ children, className = '' }) {
  return <td className={`px-4 py-3 align-top border-t border-slate-700 ${className}`}>{children}</td>;
}
function Head({ children, className = '' }) {
  return <th className={`px-4 py-3 text-left text-slate-400 text-xs uppercase bg-slate-900/40 ${className}`}>{children}</th>;
}

export default function CompareView() {
  const { jobId } = useParams();
  const [search] = useSearchParams();
  const idsParam = search.get('ids') || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    if (!idsParam) {
      setError('Provide 2–10 session ids in the ?ids= query parameter.');
      setLoading(false);
      return;
    }
    apiFetch(`/api/hr/compare?ids=${encodeURIComponent(idsParam)}`)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(typeof e.detail === 'string' ? e.detail : 'Failed to load'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [idsParam]);

  const subScoreKeys = useMemo(() => {
    if (!data) return [];
    const s = new Set();
    data.candidates.forEach((c) => {
      Object.entries(c.sub_scores || {}).forEach(([k, v]) => {
        if (v !== null && v !== undefined && typeof v !== 'object') s.add(k);
      });
    });
    return [...s];
  }, [data]);

  if (loading) return <p className="text-slate-400">Loading comparison...</p>;
  if (error) return <p className="text-red-300">{error}</p>;
  if (!data || !data.candidates?.length) return <p className="text-slate-400">No candidates to compare.</p>;

  const candidates = data.candidates;

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/hr/jobs/${jobId}`} className="text-sm text-indigo-400 hover:underline">&larr; Back to job</Link>
        <h1 className="text-2xl font-bold text-white mt-2">Compare candidates ({candidates.length})</h1>
        <p className="text-slate-400 text-sm">{candidates[0]?.job_title}</p>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full border border-slate-700 rounded-xl overflow-hidden text-sm">
          <thead>
            <tr>
              <Head className="sticky left-0 z-10">Field</Head>
              {candidates.map((c) => (
                <Head key={c.external_id}>
                  <Link to={`/hr/sessions/${c.external_id}`} className="text-slate-100 hover:text-indigo-300">
                    {c.candidate?.full_name || c.candidate?.email?.split('@')[0]}
                  </Link>
                  <p className="text-slate-500 text-[10px] normal-case">{c.candidate?.email}</p>
                </Head>
              ))}
            </tr>
          </thead>

          <tbody className="bg-slate-800/30">
            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 font-semibold">Overall score</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className={`font-mono font-bold text-lg ${scoreAccent(c.overall_score)}`}>
                  {c.overall_score != null ? c.overall_score.toFixed(1) : '—'}
                </Cell>
              ))}
            </tr>

            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 font-semibold">Decision</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id}>
                  {c.decision ? (
                    <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium border ${DECISION_COLORS[c.decision] || 'border-slate-600 text-slate-300'}`}>
                      {c.decision}
                    </span>
                  ) : <span className="text-slate-500">—</span>}
                </Cell>
              ))}
            </tr>

            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 font-semibold">Status</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className="text-slate-300 text-xs">{c.status}</Cell>
              ))}
            </tr>

            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 font-semibold">Integrity flags</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className="text-slate-300">
                  {(c.integrity_flags || []).length === 0 ? (
                    <span className="text-slate-500">none</span>
                  ) : (
                    <span className="text-amber-300 font-medium">{c.integrity_flags.length}</span>
                  )}
                </Cell>
              ))}
            </tr>

            {subScoreKeys.length > 0 && (
              <tr>
                <Cell colSpan={candidates.length + 1} className="sticky left-0 bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wide">
                  Sub-scores
                </Cell>
              </tr>
            )}
            {subScoreKeys.map((k) => (
              <tr key={k}>
                <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 text-xs">{k.replace(/_/g, ' ')}</Cell>
                {candidates.map((c) => {
                  const v = (c.sub_scores || {})[k];
                  if (v === undefined || v === null) {
                    return <Cell key={c.external_id} className="text-slate-500">—</Cell>;
                  }
                  if (typeof v === 'number') {
                    return <Cell key={c.external_id} className="font-mono text-slate-200">{v <= 1 ? v.toFixed(2) : v.toFixed(1)}</Cell>;
                  }
                  return <Cell key={c.external_id} className="text-slate-300">{String(v)}</Cell>;
                })}
              </tr>
            ))}

            <tr>
              <Cell colSpan={candidates.length + 1} className="sticky left-0 bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wide">
                AI hiring-manager summary
              </Cell>
            </tr>
            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 text-xs">Headline</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className="text-slate-200 text-sm italic">
                  {c.ai_summary?.headline || <span className="text-slate-500 not-italic">—</span>}
                </Cell>
              ))}
            </tr>
            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 text-xs">Strengths</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className="text-slate-200">
                  {c.ai_summary?.strengths?.length ? (
                    <ul className="list-disc list-inside text-xs space-y-1">
                      {c.ai_summary.strengths.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  ) : <span className="text-slate-500">—</span>}
                </Cell>
              ))}
            </tr>
            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 text-xs">Concerns</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id} className="text-slate-200">
                  {c.ai_summary?.concerns?.length ? (
                    <ul className="list-disc list-inside text-xs space-y-1">
                      {c.ai_summary.concerns.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  ) : <span className="text-slate-500">—</span>}
                </Cell>
              ))}
            </tr>
            <tr>
              <Cell className="sticky left-0 bg-slate-900/60 text-slate-300 text-xs">Recommendation</Cell>
              {candidates.map((c) => (
                <Cell key={c.external_id}>
                  {c.ai_summary?.recommendation ? (
                    <span className="inline-block px-2 py-0.5 rounded-md text-xs font-semibold bg-indigo-600/20 text-indigo-200 border border-indigo-700">
                      {c.ai_summary.recommendation}
                    </span>
                  ) : <span className="text-slate-500">—</span>}
                </Cell>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
