import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { API_BASE, apiFetch, getToken } from '../../api';

const STATUS_COLORS = {
  invited: 'bg-slate-700 text-slate-200',
  started: 'bg-blue-900/60 text-blue-200',
  submitted: 'bg-amber-900/60 text-amber-200',
  analyzing: 'bg-amber-900/60 text-amber-200',
  scored: 'bg-emerald-900/60 text-emerald-200',
  expired: 'bg-red-900/60 text-red-200',
  failed: 'bg-red-900/60 text-red-200',
};

const DECISION_STYLES = {
  shortlisted: 'bg-emerald-600/20 text-emerald-200 border-emerald-700',
  rejected: 'bg-red-600/20 text-red-200 border-red-700',
  review: 'bg-amber-600/20 text-amber-200 border-amber-700',
  advanced: 'bg-indigo-600/20 text-indigo-200 border-indigo-700',
  withdrawn: 'bg-slate-700 text-slate-200 border-slate-600',
};

function Pill({ children, className = '' }) {
  return <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${className}`}>{children}</span>;
}

function Stat({ label, value, accent }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${accent || 'text-white'}`}>{value}</p>
    </div>
  );
}

function SubScores({ subScores }) {
  if (!subScores || Object.keys(subScores).length === 0) return null;
  const entries = Object.entries(subScores).filter(
    ([, v]) => v !== null && v !== undefined && typeof v !== 'object',
  );
  if (!entries.length) return null;
  return (
    <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">Sub-scores</h3>
      <div className="space-y-2">
        {entries.map(([k, v]) => {
          const isNumeric = typeof v === 'number';
          const pct = isNumeric ? Math.max(0, Math.min(100, v * (v <= 1 ? 100 : 1))) : null;
          return (
            <div key={k}>
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>{k.replace(/_/g, ' ')}</span>
                <span className="text-slate-200 font-mono">
                  {isNumeric ? (v <= 1 ? v.toFixed(2) : v.toFixed(1)) : String(v)}
                </span>
              </div>
              {pct !== null && (
                <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500" style={{ width: `${pct}%` }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function hasSummaryContent(summary) {
  if (!summary) return false;
  return Boolean(
    summary.headline
    || summary.score_rationale
    || summary.strengths?.length
    || summary.concerns?.length
    || summary.recommendation,
  );
}

function AiSummary({ summary, status, summaryLoading, onGenerate, generating }) {
  if (!hasSummaryContent(summary)) {
    if (status === 'scored' && summaryLoading) {
      return (
        <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5 text-sm text-slate-400">
          <p>Generating AI summary…</p>
          <p className="text-xs text-slate-500 mt-2">This usually takes a few seconds after analysis completes.</p>
        </div>
      );
    }
    return (
      <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5 text-sm text-slate-500 space-y-3">
        <p>
          No AI summary yet. It is generated automatically after analysis; if the LLM step failed a
          rule-based summary can be created instead.
        </p>
        {status === 'scored' && onGenerate && (
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating}
            className="px-3 py-1.5 text-xs rounded-md bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 text-white font-medium"
          >
            {generating ? 'Generating…' : 'Generate AI summary'}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5 space-y-4">
      {summary.source === 'fallback' && (
        <p className="text-xs text-slate-500">Rule-based summary (LLM unavailable or timed out)</p>
      )}
      {summary.headline && (
        <p className="text-slate-200 italic">&ldquo;{summary.headline}&rdquo;</p>
      )}
      {summary.strengths?.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-emerald-300 mb-2">Strengths</p>
          <ul className="list-disc list-inside space-y-1 text-sm text-slate-200">
            {summary.strengths.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {summary.concerns?.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-amber-300 mb-2">Concerns</p>
          <ul className="list-disc list-inside space-y-1 text-sm text-slate-200">
            {summary.concerns.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {summary.score_rationale && (
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Score rationale</p>
          <p className="text-sm text-slate-300">{summary.score_rationale}</p>
        </div>
      )}
      {summary.recommendation && (
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">AI recommendation</p>
          <Pill className="border border-indigo-700 bg-indigo-600/20 text-indigo-200">
            {summary.recommendation}
          </Pill>
        </div>
      )}
    </div>
  );
}

function IntegrityList({ flags }) {
  if (!flags || flags.length === 0) {
    return <p className="text-sm text-slate-500">No integrity flags recorded.</p>;
  }
  return (
    <ul className="space-y-2">
      {flags.map((f, i) => (
        <li key={i} className="text-sm text-slate-300 bg-slate-900/40 border border-slate-700 rounded px-3 py-2">
          <span className="font-medium text-amber-300">{f.kind}</span>
          <span className="text-slate-500 ml-2">at {Number(f.at_sec || 0).toFixed(1)}s</span>
          {f.meta && Object.keys(f.meta).length > 0 && (
            <pre className="text-xs text-slate-500 mt-1 font-mono">{JSON.stringify(f.meta)}</pre>
          )}
        </li>
      ))}
    </ul>
  );
}

function AnalysisProgress({ status, progress, message, error }) {
  const isProcessing = ['submitted', 'analyzing'].includes(status);
  const pct = Math.max(0, Math.min(100, Number(progress || 0)));
  const statusLabel = status === 'submitted' ? 'Queued for analysis' : 'Analyzing interview';
  const etaLabel = pct >= 95 ? 'Wrapping up...' : pct >= 70 ? 'Almost done...' : pct >= 30 ? 'Processing...' : 'Starting...';

  if (!isProcessing && status !== 'failed') return null;

  return (
    <div className={`border rounded-xl p-4 ${status === 'failed' ? 'bg-red-950/40 border-red-800' : 'bg-amber-950/30 border-amber-800/70'}`}>
      {status === 'failed' ? (
        <p className="text-sm text-red-200">
          Analysis failed{error ? `: ${error}` : '.'}
        </p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-amber-200">{statusLabel}</p>
            <p className="text-xs text-amber-300">{pct}%</p>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div className="h-full bg-amber-500 transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-amber-100/90">
            {message || etaLabel}
          </p>
        </div>
      )}
    </div>
  );
}

export default function CandidateDetail() {
  const { externalId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null); // name of button in flight
  const [sendEmailOnManual, setSendEmailOnManual] = useState(true);
  const hrToken = getToken();
  const reportFilename = data?.report_html_path ? data.report_html_path.split(/[\\/]/).pop() : null;
  const reportPublicUrl = reportFilename ? `${API_BASE}/reports/${reportFilename}` : null;
  const reportAuthenticatedUrl = useMemo(() => {
    if (!reportFilename || !hrToken) return null;
    const u = new URL(`${API_BASE}/api/hr/sessions/${externalId}/report`);
    u.searchParams.set('token', hrToken);
    return u.toString();
  }, [reportFilename, hrToken, externalId]);
  const reportIframeSrc = reportAuthenticatedUrl || reportPublicUrl;
  const reportJson = data?.report_json_path
    ? `${API_BASE}/reports/${data.report_json_path.split(/[\\/]/).pop()}`
    : null;

  const load = useCallback(async () => {
    try {
      const d = await apiFetch(`/api/hr/sessions/${externalId}`);
      setData(d);
      return d;
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Failed to load candidate');
      return null;
    } finally {
      setLoading(false);
    }
  }, [externalId]);

  useEffect(() => { load(); }, [load]);

  // Poll while the session is still being analyzed.
  useEffect(() => {
    if (!data) return;
    const still = ['submitted', 'analyzing'].includes(data.status);
    if (!still) return;
    const t = setInterval(() => load(), 3000);
    return () => clearInterval(t);
  }, [data, load]);

  // Poll while scored but the AI summary has not landed yet.
  useEffect(() => {
    if (!data || data.status !== 'scored' || hasSummaryContent(data.ai_summary)) return;
    const t = setInterval(() => load(), 3000);
    return () => clearInterval(t);
  }, [data, load]);

  const setDecision = async (status) => {
    setActing(status);
    try {
      await apiFetch(`/api/hr/sessions/${externalId}/decision`, {
        method: 'POST',
        body: { status, send_email: sendEmailOnManual },
      });
      await load();
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Failed to set decision');
    } finally {
      setActing(null);
    }
  };

  const resend = async () => {
    setActing('resend');
    try {
      await apiFetch(`/api/hr/sessions/${externalId}/resend-invite`, { method: 'POST' });
      alert('Invitation re-sent.');
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Resend failed');
    } finally {
      setActing(null);
    }
  };

  const rerunAnalysis = async () => {
    setActing('rerun-analysis');
    try {
      await apiFetch(`/api/hr/sessions/${externalId}/rerun-analysis`, { method: 'POST' });
      await load();
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Re-run failed');
    } finally {
      setActing(null);
    }
  };

  const rerunDecision = async () => {
    setActing('rerun-decision');
    try {
      const result = await apiFetch(`/api/hr/sessions/${externalId}/rerun-decision`, { method: 'POST' });
      await load();
      if (result.skipped_manual) {
        alert('Could not re-run: a manual HR decision is in place. Use the decision buttons below to change it.');
        return;
      }
      const statusLabel = result.status || 'none';
      const reason = result.reason ? `\n\n${result.reason}` : '';
      if (result.unchanged) {
        alert(`Auto-decision unchanged: ${statusLabel}.${reason}`);
      } else {
        alert(`Decision updated to ${statusLabel}.${reason}`);
      }
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Re-run failed');
    } finally {
      setActing(null);
    }
  };

  const generateSummary = async () => {
    setActing('generate-summary');
    try {
      const updated = await apiFetch(`/api/hr/sessions/${externalId}/generate-summary`, {
        method: 'POST',
        timeoutMs: 60000,
      });
      setData(updated);
    } catch (e) {
      alert(typeof e.detail === 'string' ? e.detail : 'Failed to generate AI summary');
    } finally {
      setActing(null);
    }
  };

  if (loading) return <p className="text-slate-400">Loading candidate...</p>;
  if (error) return <p className="text-red-300">{error}</p>;
  if (!data) return null;

  const candidate = data.candidate || {};
  const overall = data.overall_score;
  const decision = data.decision;
  const summaryLoading = data.status === 'scored'
    && !hasSummaryContent(data.ai_summary)
    && acting !== 'generate-summary';

  return (
    <div className="space-y-8">
      <div>
        <Link to={`/hr/jobs/${data.job_id}`} className="text-sm text-indigo-400 hover:underline">
          &larr; Back to job
        </Link>
        <div className="mt-2 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {candidate.full_name || candidate.email?.split('@')[0]}
            </h1>
            <p className="text-slate-400 text-sm">{candidate.email}</p>
            <div className="mt-2 flex items-center gap-2">
              <Pill className={STATUS_COLORS[data.status] || 'bg-slate-700 text-slate-200'}>
                {data.status}
              </Pill>
              {decision ? (
                <Pill className={`border ${DECISION_STYLES[decision] || 'border-slate-600 text-slate-300'}`}>
                  {decision}
                </Pill>
              ) : (
                <Pill className="bg-slate-800 text-slate-400 border border-slate-700">no decision</Pill>
              )}
              {data.decision_source && (
                <span className="text-xs text-slate-500">
                  ({data.decision_source === 'hr' ? 'manual' : 'auto'})
                </span>
              )}
            </div>
            {data.decision_reason && (
              <p className="mt-2 text-sm text-slate-400 max-w-xl">{data.decision_reason}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            <button
              onClick={resend}
              disabled={acting === 'resend'}
              className="px-3 py-1.5 text-xs rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800"
            >
              Resend invite
            </button>
            {data.status === 'failed' && (
              <button
                onClick={rerunAnalysis}
                disabled={acting === 'rerun-analysis'}
                className="px-3 py-1.5 text-xs rounded-md border border-amber-700 text-amber-200 hover:bg-amber-900/40"
              >
                Re-run analysis
              </button>
            )}
            {data.status === 'scored' && (
              <button
                onClick={rerunDecision}
                disabled={acting === 'rerun-decision'}
                className="px-3 py-1.5 text-xs rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                {acting === 'rerun-decision' ? 'Re-running…' : 'Re-run decision'}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Overall score" value={overall != null ? overall.toFixed(1) : '—'} accent={
          overall == null ? 'text-slate-400' :
          overall >= 80 ? 'text-emerald-300' :
          overall < 50 ? 'text-red-300' : 'text-amber-300'
        } />
        <Stat label="Invited" value={new Date(data.invited_at).toLocaleDateString()} />
        <Stat label="Submitted" value={data.submitted_at ? new Date(data.submitted_at).toLocaleDateString() : '—'} />
        <Stat label="Integrity flags" value={(data.integrity_flags || []).length} />
      </div>

      <AnalysisProgress
        status={data.status}
        progress={data.progress}
        message={data.progress_message}
        error={data.error_message}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <AiSummary
            summary={data.ai_summary}
            status={data.status}
            summaryLoading={summaryLoading}
            onGenerate={generateSummary}
            generating={acting === 'generate-summary'}
          />

          {(reportPublicUrl || reportJson) && (
            <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-4 flex flex-wrap gap-3 text-sm">
              {reportAuthenticatedUrl && (
                <a
                  href={reportAuthenticatedUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
                >
                  Open full HTML report
                </a>
              )}
              {!reportAuthenticatedUrl && reportPublicUrl && (
                <a
                  href={reportPublicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
                >
                  Open full HTML report
                </a>
              )}
              {reportJson && (
                <a
                  href={reportJson}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800"
                >
                  Download JSON
                </a>
              )}
            </div>
          )}

          {reportIframeSrc && (
            <div className="bg-slate-800/40 border border-slate-700 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">
                  Full analysis report
                </h3>
                <a
                  href={reportAuthenticatedUrl || reportPublicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-indigo-400 hover:underline shrink-0"
                >
                  Open in new tab
                </a>
              </div>
              <iframe
                title="Interview analysis report"
                src={reportIframeSrc}
                className="w-full min-h-[780px] bg-white"
              />
            </div>
          )}

          {!reportAuthenticatedUrl && reportPublicUrl && (
            <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
              Embedded via the public <span className="font-mono text-amber-200">/reports/</span> URL (no HR
              token in this browser session). Prefer the authenticated view after signing in.
            </div>
          )}

          {data.questions?.length > 0 && (
            <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">
                Questions asked
              </h3>
              <ol className="space-y-2 list-decimal list-inside text-sm text-slate-200">
                {data.questions.map((q, i) => (
                  <li key={i}>
                    <span className="text-xs text-slate-500 mr-2">{q.type || 'General'}</span>
                    {q.question || String(q)}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <div className="space-y-6">
          <SubScores subScores={data.sub_scores} />

          <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">
              Integrity flags
            </h3>
            <IntegrityList flags={data.integrity_flags} />
          </div>

          <div className="bg-slate-800/40 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">
              Decision
            </h3>
            <label className="flex items-center gap-2 text-xs text-slate-400 mb-3">
              <input
                type="checkbox"
                checked={sendEmailOnManual}
                onChange={(e) => setSendEmailOnManual(e.target.checked)}
                className="accent-indigo-500"
              />
              Email candidate on shortlist / advance / reject
            </label>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => setDecision('shortlisted')}
                disabled={!!acting}
                className="px-3 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900 text-white text-sm font-semibold"
              >
                Shortlist
              </button>
              <button
                onClick={() => setDecision('advanced')}
                disabled={!!acting}
                className="px-3 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 text-white text-sm font-semibold"
              >
                Advance to human round
              </button>
              <button
                onClick={() => setDecision('review')}
                disabled={!!acting}
                className="px-3 py-2 rounded-md bg-amber-600 hover:bg-amber-500 disabled:bg-amber-900 text-white text-sm font-semibold"
              >
                Mark for review
              </button>
              <button
                onClick={() => setDecision('rejected')}
                disabled={!!acting}
                className="px-3 py-2 rounded-md bg-red-600 hover:bg-red-500 disabled:bg-red-900 text-white text-sm font-semibold"
              >
                Reject
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-3">
              Manual decisions override auto-decisions. Review / Withdrawn never trigger candidate emails.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
