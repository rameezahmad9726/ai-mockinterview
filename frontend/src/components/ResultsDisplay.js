import React from 'react';
import ScoreCard from './ScoreCard';
import EmotionChart from './EmotionChart';

const TIER_STYLE = {
  strong_hire:     { bg: 'from-emerald-700/70 to-emerald-900/70', border: 'border-emerald-400/60', icon: '🌟', text: 'text-emerald-100' },
  hire:            { bg: 'from-green-700/60 to-emerald-900/50', border: 'border-green-400/50', icon: '✅', text: 'text-green-100' },
  borderline:      { bg: 'from-amber-700/60 to-orange-900/50', border: 'border-amber-400/50', icon: '⚠️', text: 'text-amber-100' },
  not_recommended: { bg: 'from-red-800/70 to-rose-900/60', border: 'border-red-400/60', icon: '❌', text: 'text-red-100' },
};

const ISSUE_LABEL = {
  low_eye_contact: 'Low eye contact',
  poor_posture: 'Poor posture',
  low_confidence: 'Low confidence',
  excessive_movement: 'Excessive movement',
  very_still: 'Very still / stiff',
};

const ISSUE_META = {
  low_eye_contact: {
    icon: '👁',
    chip: 'bg-amber-500/20 text-amber-200 border-amber-500/40',
    advice: 'Look directly at the camera lens (not at your own face on screen). Position the window near the webcam.',
  },
  poor_posture: {
    icon: '🧍',
    chip: 'bg-orange-500/20 text-orange-200 border-orange-500/40',
    advice: 'Sit upright, keep shoulders level and square to the camera, and keep your upper body in frame.',
  },
  low_confidence: {
    icon: '😟',
    chip: 'bg-red-500/20 text-red-200 border-red-500/40',
    advice: 'Speak at a steady pace, avoid hedging words ("I think", "maybe"), and take a short breath before answering.',
  },
  excessive_movement: {
    icon: '✋',
    chip: 'bg-rose-500/20 text-rose-200 border-rose-500/40',
    advice: 'Keep hands resting until you want to emphasize a point. Avoid rocking / fidgeting.',
  },
  very_still: {
    icon: '🗿',
    chip: 'bg-sky-500/20 text-sky-200 border-sky-500/40',
    advice: 'Add natural, controlled hand gestures when explaining technical points — complete stillness can read as stiffness.',
  },
};

const THUMB_POSITION_LABELS = ['Start', 'Middle', 'End'];

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function ScoreBar({ value, max, color }) {
  const pct = Math.max(0, Math.min(1, (Number(value) || 0) / Math.max(1, max))) * 100;
  return (
    <div className="w-full h-2 bg-slate-900/60 rounded-full overflow-hidden mt-1">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function ResultsDisplay({ results }) {
  const emotion = results?.emotion_analysis || {};
  const body = results?.body_language || {};
  const speech = results?.speech_analysis || {};
  const summary = results?.final_summary || {};
  const scoring = results?.scoring || {};

  const rec = scoring.recommendation || summary?.recommendation || {};
  const tierStyle = TIER_STYLE[rec.tier] || TIER_STYLE.borderline;
  const cert = scoring.certification_score || {};
  const ans = scoring.answer_score || {};
  const beh = scoring.behavior_score || {};
  const notes = scoring.interview_notes || [];
  const intervals = scoring.lacking_intervals || [];

  return (
    <div className="space-y-6">
      {/* Scoring + recommendation */}
      {scoring.total_0_100 !== undefined && (
        <div className={`rounded-lg p-6 shadow-xl border-2 bg-gradient-to-br ${tierStyle.bg} ${tierStyle.border}`}>
          <div className="flex items-start gap-4">
            <span className="text-5xl flex-shrink-0">{tierStyle.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-3 flex-wrap">
                <h2 className={`text-2xl font-bold ${tierStyle.text}`}>{rec.label || 'Result'}</h2>
                {scoring.domain && (
                  <span className="text-xs uppercase tracking-wider text-slate-200/80 bg-slate-900/40 px-2 py-0.5 rounded-full">
                    Domain: {scoring.domain}
                  </span>
                )}
              </div>
              <div className="mt-1 text-5xl font-extrabold text-white">
                {Number(scoring.total_0_100).toFixed(1)}
                <span className="text-xl text-slate-300 font-semibold ml-1">/100</span>
              </div>
              {rec.summary && (
                <p className="text-slate-200 text-sm mt-3 leading-relaxed">{rec.summary}</p>
              )}
            </div>
          </div>

          {/* Breakdown bars with full rationales + sub-metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            {/* Candidate answers */}
            <div className="bg-slate-900/60 rounded-lg p-5 border border-slate-700 flex flex-col">
              <div className="flex justify-between items-baseline">
                <span className="text-slate-100 font-semibold text-base">Candidate Answers</span>
                <span className="text-white font-bold text-lg">{(ans.total_0_60 ?? 0).toFixed(1)}<span className="text-slate-400 text-sm">/60</span></span>
              </div>
              <ScoreBar value={ans.total_0_60} max={60} color="bg-blue-500" />
              <dl className="mt-4 text-sm text-slate-200 space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Questions evaluated</dt>
                  <dd className="text-white font-semibold">{(ans.per_question || notes || []).length}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Average relevance</dt>
                  <dd className="text-white font-semibold">{(ans.average_relevance_0_10 ?? 0).toFixed(1)}/10</dd>
                </div>
              </dl>
              {ans.rationale && (
                <p className="text-slate-300 text-sm mt-4 leading-relaxed whitespace-pre-wrap">
                  {ans.rationale}
                </p>
              )}
            </div>

            {/* Behavior & emotions */}
            <div className="bg-slate-900/60 rounded-lg p-5 border border-slate-700 flex flex-col">
              <div className="flex justify-between items-baseline">
                <span className="text-slate-100 font-semibold text-base">Behavior &amp; Emotions</span>
                <span className="text-white font-bold text-lg">{(beh.total_0_20 ?? 0).toFixed(1)}<span className="text-slate-400 text-sm">/20</span></span>
              </div>
              <ScoreBar value={beh.total_0_20} max={20} color="bg-violet-500" />
              <dl className="mt-4 text-sm text-slate-200 grid grid-cols-2 gap-x-4 gap-y-2">
                <div className="flex justify-between"><dt className="text-slate-400">Posture</dt><dd className="text-white font-semibold">{(beh.posture_points ?? 0).toFixed(1)}/6</dd></div>
                <div className="flex justify-between"><dt className="text-slate-400">Eye contact</dt><dd className="text-white font-semibold">{(beh.eye_contact_points ?? 0).toFixed(1)}/4</dd></div>
                <div className="flex justify-between"><dt className="text-slate-400">Confidence</dt><dd className="text-white font-semibold">{(beh.confidence_points ?? 0).toFixed(1)}/4</dd></div>
                <div className="flex justify-between"><dt className="text-slate-400">Movement</dt><dd className="text-white font-semibold">{(beh.movement_points ?? 0).toFixed(1)}/3</dd></div>
                <div className="flex justify-between col-span-2">
                  <dt className="text-slate-400">Filler-word penalty</dt>
                  <dd className={`font-semibold ${Number(beh.filler_penalty) < 0 ? 'text-red-300' : 'text-white'}`}>
                    {(beh.filler_penalty ?? 0).toFixed(1)}
                  </dd>
                </div>
              </dl>
              {beh.rationale && (
                <p className="text-slate-300 text-sm mt-4 leading-relaxed whitespace-pre-wrap">
                  {beh.rationale}
                </p>
              )}
            </div>

            {/* Certifications */}
            <div className="bg-slate-900/60 rounded-lg p-5 border border-slate-700 flex flex-col">
              <div className="flex justify-between items-baseline">
                <span className="text-slate-100 font-semibold text-base">Certifications</span>
                <span className="text-white font-bold text-lg">{(cert.total_0_20 ?? 0).toFixed(1)}<span className="text-slate-400 text-sm">/20</span></span>
              </div>
              <ScoreBar value={cert.total_0_20} max={20} color="bg-cyan-500" />
              <dl className="mt-4 text-sm text-slate-200 space-y-2">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Listed</dt>
                  <dd className="text-white font-semibold">{(cert.certifications || []).length}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Domain-relevant</dt>
                  <dd className="text-white font-semibold">
                    {(cert.certifications || []).filter(c => c.relevant).length}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Relevance ratio</dt>
                  <dd className="text-white font-semibold">{((cert.cert_relevance_ratio_0_1 ?? 0) * 100).toFixed(0)}%</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Answer ratio</dt>
                  <dd className="text-white font-semibold">{((cert.answer_ratio_0_1 ?? 0) * 100).toFixed(0)}%</dd>
                </div>
              </dl>
              {(cert.certifications || []).length > 0 && (
                <ul className="mt-4 space-y-1.5 text-sm">
                  {cert.certifications.map((c, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className={`mt-1.5 inline-block w-2 h-2 rounded-full flex-shrink-0 ${c.relevant ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                      <span className="text-slate-200">
                        <span className="font-medium">{c.name}</span>
                        {c.issuer && <span className="text-slate-400"> — {c.issuer}</span>}
                        {!c.relevant && <span className="ml-1 text-slate-500 italic">(not relevant)</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {cert.rationale && (
                <p className="text-slate-300 text-sm mt-4 leading-relaxed whitespace-pre-wrap">
                  {cert.rationale}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Interview notes */}
      {notes.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4">📝 Interview Notes</h3>
          <div className="space-y-4">
            {notes.map((n) => {
              const score = Number(n.answer_score_0_10) || 0;
              const pillClass = score >= 7
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : score >= 4
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-red-500/20 text-red-300 border-red-500/40';
              return (
                <div key={n.question_idx} className="bg-slate-900/40 rounded-lg p-5 border border-slate-700">
                  <div className="flex justify-between items-start gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
                        Q{n.question_idx + 1} · {n.question_type}
                      </p>
                      <p className="text-white font-semibold text-base mt-1 leading-snug">{n.question}</p>
                    </div>
                    <span className={`px-3 py-1 rounded-full border text-sm font-bold ${pillClass}`}>
                      {score.toFixed(1)}/10
                    </span>
                  </div>
                  <div className="mt-3 p-4 bg-slate-950/50 border-l-4 border-blue-500/60 rounded text-base text-slate-100 whitespace-pre-wrap leading-relaxed">
                    {n.candidate_answer}
                  </div>
                  {n.evaluation && (
                    <p className="mt-3 text-sm text-slate-300 italic leading-relaxed">{n.evaluation}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Lacking intervals */}
      {scoring.total_0_100 !== undefined && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4">⏱ Moments to Improve</h3>
          {intervals.length === 0 ? (
            <p className="text-emerald-300 text-base">No significant weak intervals detected.</p>
          ) : (
            <div className="space-y-4">
              {intervals.map((iv, i) => {
                const sevClass = iv.severity === 'severe'
                  ? 'bg-red-500 text-white'
                  : iv.severity === 'moderate'
                    ? 'bg-orange-500 text-white'
                    : 'bg-amber-500 text-slate-900';
                const sevAccent = iv.severity === 'severe'
                  ? 'border-l-red-500'
                  : iv.severity === 'moderate'
                    ? 'border-l-orange-500'
                    : 'border-l-amber-500';
                const frames = iv.frame_paths || [];
                const duration = Math.max(0, Number(iv.end_sec || 0) - Number(iv.start_sec || 0));
                const affectedFrames = Math.max(1, Number(iv.end_frame || 0) - Number(iv.start_frame || 0) + 1);
                const issues = iv.issues || [];

                return (
                  <div
                    key={i}
                    className={`bg-slate-900/40 border border-slate-700 ${sevAccent} border-l-4 rounded-lg p-5`}
                  >
                    {/* Header row: time, duration, frames, severity */}
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-slate-100 text-base font-semibold">
                          {fmtTime(iv.start_sec)} – {fmtTime(iv.end_sec)}
                        </span>
                        <span className="text-slate-400 text-sm">
                          ({duration.toFixed(1)}s)
                        </span>
                      </div>
                      <span className="text-slate-300 text-sm">
                        frames <span className="text-white font-semibold">{iv.start_frame}–{iv.end_frame}</span>
                        <span className="text-slate-400"> · {affectedFrames} affected</span>
                      </span>
                      <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${sevClass}`}>
                        {iv.severity}
                      </span>
                    </div>

                    {/* Issue chips */}
                    {issues.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-4">
                        {issues.map((iss) => {
                          const meta = ISSUE_META[iss] || { icon: '•', chip: 'bg-slate-700 text-slate-200 border-slate-600' };
                          return (
                            <span
                              key={iss}
                              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${meta.chip}`}
                            >
                              <span aria-hidden>{meta.icon}</span>
                              {ISSUE_LABEL[iss] || iss}
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {/* Thumbnails with position labels */}
                    {frames.length > 0 ? (
                      <div className="flex gap-3 flex-wrap mb-4">
                        {frames.map((url, j) => {
                          const pos = frames.length === 1
                            ? 'Representative'
                            : THUMB_POSITION_LABELS[Math.min(j, THUMB_POSITION_LABELS.length - 1)];
                          // Best-guess timestamp for this thumbnail (evenly split across the interval).
                          const rel = frames.length > 1 ? j / (frames.length - 1) : 0.5;
                          const thumbSec = Number(iv.start_sec || 0) + rel * duration;
                          return (
                            <a
                              key={j}
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                              className="block group"
                            >
                              <img
                                src={url}
                                alt={`lacking frame ${pos}`}
                                loading="lazy"
                                className="w-52 h-36 object-cover rounded-md border border-slate-700 bg-slate-800 group-hover:border-slate-400 transition"
                              />
                              <div className="mt-2 flex items-center justify-between text-sm text-slate-300">
                                <span className="uppercase tracking-wider font-semibold text-xs text-slate-400">{pos}</span>
                                <span className="font-mono">{fmtTime(thumbSec)}</span>
                              </div>
                            </a>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500 mb-4">No preview frames saved for this interval.</p>
                    )}

                    {/* Per-issue advice */}
                    {issues.length > 0 && (
                      <ul className="space-y-2 pt-4 border-t border-slate-700/60">
                        {issues.map((iss) => {
                          const meta = ISSUE_META[iss];
                          if (!meta || !meta.advice) return null;
                          return (
                            <li key={`advice-${iss}`} className="flex gap-2 text-sm text-slate-200 leading-relaxed">
                              <span className="flex-shrink-0 text-base" aria-hidden>{meta.icon}</span>
                              <span>
                                <span className="text-white font-semibold">{ISSUE_LABEL[iss]}:</span>{' '}
                                {meta.advice}
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Overall Summary */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-700 border border-slate-700 rounded-lg p-6 shadow-xl">
        <h2 className="text-2xl font-bold text-white mb-4">📊 Analysis Summary</h2>

        <div className="grid grid-cols-2 gap-4">
          <ScoreCard
            icon="😊"
            label="Dominant Emotion"
            value={summary.dominant_emotion?.toUpperCase() || 'N/A'}
            color="from-purple-600 to-pink-600"
          />
          <ScoreCard
            icon="🧍"
            label="Gesture"
            value={summary.gesture_label || 'N/A'}
            color="from-blue-600 to-cyan-600"
          />
          <ScoreCard
            icon="📈"
            label="Posture Score"
            value={`${(summary.posture_score || 0).toFixed(1)}/10`}
            color="from-green-600 to-emerald-600"
          />
          <ScoreCard
            icon="💬"
            label="Clarity Score"
            value={summary.clarity_score != null ? `${summary.clarity_score}/10` : 'N/A'}
            color="from-orange-600 to-red-600"
          />
          <ScoreCard
            icon="🛡️"
            label="Confidence"
            value={summary.confidence_score != null ? `${summary.confidence_score}/10` : 'N/A'}
            color="from-indigo-600 to-purple-600"
          />
        </div>
      </div>

      {/* Emotion Analysis */}
      {emotion.dominant_emotion && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-lg font-bold text-white mb-4">😊 Emotion Analysis</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Dominant Emotion</p>
              <p className="text-white font-bold text-lg">
                {emotion.dominant_emotion.toUpperCase()}
              </p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Frames Analyzed</p>
              <p className="text-white font-bold text-lg">{emotion.frames_analyzed}</p>
            </div>
          </div>

          {emotion.emotion_timeline && emotion.emotion_timeline.length > 0 && (
            <EmotionChart timeline={emotion.emotion_timeline} />
          )}

          {emotion.comments && emotion.comments.length > 0 && (
            <div className="mt-4 bg-slate-700 rounded p-3">
              <p className="text-slate-300 text-sm">
                💡 {emotion.comments[0]}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Speech Analysis */}
      {speech.error ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl border-l-4 border-l-red-500">
          <h3 className="text-lg font-bold text-white mb-2">🎤 Speech Analysis</h3>
          <p className="text-red-400 text-sm">⚠️ {speech.error}</p>
        </div>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-lg font-bold text-white mb-4">🎤 Speech Analysis</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Word Count</p>
              <p className="text-white font-bold text-lg">{speech.word_count || 0}</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Speaking Speed</p>
              <p className="text-white font-bold text-lg">
                {(summary.insufficient_candidate_speech || speech.insufficient_candidate_speech)
                  ? 'N/A'
                  : `${speech.speaking_speed_wpm || 0} WPM`}
              </p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Filler Words</p>
              <p className="text-white font-bold text-lg">{speech.filler_words_count ?? speech.filler_words ?? 0}</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Audio Duration</p>
              <p className="text-white font-bold text-lg">
                {speech.audio_duration_seconds ? (speech.audio_duration_seconds / 60).toFixed(1) : 0} min
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Confidence & Tone Insights (AI-Powered) */}
      {(speech.tone_analysis || speech.improvement_tip || speech.tone_analysis_skipped) && (
        <div className="bg-gradient-to-br from-indigo-900/40 to-slate-800 border border-indigo-500/30 rounded-lg p-6 shadow-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 p-2 opacity-10">
            <span className="text-6xl">🛡️</span>
          </div>
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            🛡️ Confidence & Tone Insights
            {!speech.tone_analysis_skipped && (
              <span className="text-[10px] bg-indigo-500 text-white px-2 py-0.5 rounded-full uppercase tracking-tighter">AI Analysis</span>
            )}
          </h3>

          <div className="space-y-4">
            {speech.tone_analysis_skipped && speech.tone_skip_reason && (
              <div className="bg-amber-950/40 border border-amber-500/30 rounded p-4">
                <p className="text-amber-200/90 text-xs mb-1 uppercase font-semibold">Tone analysis off</p>
                <p className="text-amber-50/95 text-sm leading-relaxed">{speech.tone_skip_reason}</p>
              </div>
            )}
            {!speech.tone_analysis_skipped && speech.tone_analysis && (
              <div className="bg-indigo-950/30 border border-indigo-500/20 rounded p-4">
                <p className="text-indigo-300 text-xs mb-1 uppercase font-semibold">Communication Style</p>
                <p className="text-white text-sm leading-relaxed">{speech.tone_analysis}</p>
              </div>
            )}

            {!speech.tone_analysis_skipped && speech.improvement_tip && (
              <div className="bg-emerald-950/30 border border-emerald-500/20 rounded p-4">
                <p className="text-emerald-300 text-xs mb-1 uppercase font-semibold">Pro Improvement Tip</p>
                <div className="flex gap-2 items-start">
                  <span className="text-emerald-400 text-lg">💡</span>
                  <p className="text-emerald-50 text-sm italic">{speech.improvement_tip}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Body Language Analysis */}
      {body.gesture_label && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-lg font-bold text-white mb-4">🧍 Body Language</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Gesture Label</p>
              <p className="text-white font-bold">{body.gesture_label}</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Posture Score</p>
              <p className="text-white font-bold text-lg">{body.posture_score || 0}/10</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Movement Score</p>
              <p className="text-white font-bold text-lg">{(body.movement_score || 0).toFixed(1)}/10</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Frames Processed</p>
              <p className="text-white font-bold text-lg">{body.frames_processed || 0}</p>
            </div>
          </div>
        </div>
      )}

      {/* Report Links (downloadable) */}
      {(results?.report_json_path || results?.report_html_path) && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-lg font-bold text-white mb-4">📄 Reports</h3>
          <div className="space-y-2">
            {results?.report_json_path && (
              <div className="flex items-center gap-3">
                <span className="text-slate-300 text-sm">✅ JSON Report</span>
                <a
                  className="text-blue-400 underline text-sm"
                  href={`http://localhost:8000/reports/${results.report_json_path.split('/').pop()}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open
                </a>
                <a
                  className="bg-slate-700 hover:bg-slate-600 text-slate-100 px-3 py-1 rounded text-sm"
                  href={`http://localhost:8000/reports/${results.report_json_path.split('/').pop()}`}
                  download
                >
                  Download JSON
                </a>
              </div>
            )}

            {results?.report_html_path && (
              <div className="flex items-center gap-3">
                <span className="text-slate-300 text-sm">✅ HTML Report</span>
                <a
                  className="text-blue-400 underline text-sm"
                  href={`http://localhost:8000/reports/${results.report_html_path.split('/').pop()}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open
                </a>
                <a
                  className="bg-slate-700 hover:bg-slate-600 text-slate-100 px-3 py-1 rounded text-sm"
                  href={`http://localhost:8000/reports/${results.report_html_path.split('/').pop()}`}
                  download
                >
                  Download HTML
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
