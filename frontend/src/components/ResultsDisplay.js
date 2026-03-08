import React from 'react';
import ScoreCard from './ScoreCard';
import EmotionChart from './EmotionChart';

export default function ResultsDisplay({ results }) {
  const emotion = results?.emotion_analysis || {};
  const body = results?.body_language || {};
  const speech = results?.speech_analysis || {};
  const summary = results?.final_summary || {};

  const recommendation = summary?.recommendation || {};

  return (
    <div className="space-y-6">
      {/* Recommendation Section - Detailed */}
      {recommendation.label && (
        <div className={`rounded-lg p-6 shadow-xl border-2 ${
          recommendation.recommended
            ? 'bg-gradient-to-br from-emerald-900/60 to-green-900/40 border-emerald-500/50'
            : 'bg-gradient-to-br from-amber-900/60 to-orange-900/40 border-amber-500/50'
        }`}>
          <div className="flex items-start gap-4">
            <span className="text-5xl flex-shrink-0">
              {recommendation.recommended ? '✅' : '⚠️'}
            </span>
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold text-white">
                {recommendation.recommended ? 'Recommended' : 'Not Recommended'}
              </h2>
              {recommendation.summary && (
                <p className="text-slate-200 text-sm mt-1 font-medium">
                  {recommendation.summary}
                </p>
              )}
              {recommendation.reason && (
                <p className="text-slate-300 text-sm mt-2">
                  {recommendation.reason}
                </p>
              )}

              {/* Strengths */}
              {recommendation.strengths && recommendation.strengths.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-emerald-300 text-xs font-bold uppercase tracking-wider mb-2">Strengths</h4>
                  <ul className="space-y-2">
                    {recommendation.strengths.map((s, i) => (
                      <li key={i} className="flex gap-2 text-sm">
                        <span className="text-emerald-400">✓</span>
                        <span className="text-slate-200">
                          <strong>{s.metric}</strong>
                          {s.score != null && s.metric === 'Speaking pace' && (
                            <span className="text-slate-400 ml-1">({s.score} WPM)</span>
                          )}
                          {s.score != null && s.metric === 'Filler words' && (
                            <span className="text-slate-400 ml-1">({s.score} detected)</span>
                          )}
                          {s.score != null && !['Speaking pace', 'Filler words'].includes(s.metric) && (
                            <span className="text-slate-400 ml-1">({s.score}/10)</span>
                          )}
                          : {s.feedback}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Areas to Improve */}
              {recommendation.areas_to_improve && recommendation.areas_to_improve.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-amber-300 text-xs font-bold uppercase tracking-wider mb-2">Areas to Improve</h4>
                  <ul className="space-y-3">
                    {recommendation.areas_to_improve.map((a, i) => (
                      <li key={i} className="flex gap-2 text-sm">
                        <span className="text-amber-400 flex-shrink-0">•</span>
                        <div>
                          <span className="text-slate-200">
                            <strong>{a.metric}</strong>
                            {a.score != null && a.metric === 'Speaking pace' && (
                              <span className="text-slate-400 ml-1">({a.score} WPM)</span>
                            )}
                            {a.metric === 'Filler words' && a.score != null && (
                              <span className="text-slate-400 ml-1">({a.score} detected)</span>
                            )}
                            {a.score != null && !['Speaking pace', 'Filler words'].includes(a.metric) && (
                              <span className="text-slate-400 ml-1">({a.score}/10)</span>
                            )}
                            : {a.feedback}
                          </span>
                          {a.suggestion && (
                            <p className="text-amber-100/90 text-xs mt-1 italic pl-4 border-l-2 border-amber-500/40">
                              💡 {a.suggestion}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
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
              <p className="text-white font-bold text-lg">{speech.filler_words || 0}</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Audio Duration</p>
              <p className="text-white font-bold text-lg">
                {speech.audio_duration_seconds ? (speech.audio_duration_seconds / 60).toFixed(1) : 0} min
              </p>
            </div>
          </div>
          {speech.transcript && (
            <div className="mt-4 bg-slate-700 rounded-lg p-4">
              <p className="text-slate-400 text-xs mb-3 uppercase tracking-wider font-semibold">Transcript</p>
              {speech.formatted_transcript && speech.formatted_transcript.length > 0 ? (
                <div className="space-y-4 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
                  {speech.formatted_transcript.map((segment, idx) => (
                    <div key={idx} className="flex flex-col">
                      <span className={`text-[10px] font-bold mb-1 uppercase ${segment.speaker === 'Interviewer' ? 'text-blue-400' : 'text-emerald-400'
                        }`}>
                        {segment.speaker}
                      </span>
                      <div className={`p-3 rounded-lg text-sm border ${segment.speaker === 'Interviewer'
                        ? 'bg-blue-900/20 border-blue-500/30 text-blue-100'
                        : 'bg-emerald-900/20 border-emerald-500/30 text-emerald-100'
                        }`}>
                        {segment.text}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-slate-900/50 p-3 rounded border border-slate-600">
                  <p className="text-slate-200 text-sm leading-relaxed">{speech.transcript}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Confidence & Tone Insights (AI-Powered) */}
      {(speech.tone_analysis || speech.improvement_tip) && (
        <div className="bg-gradient-to-br from-indigo-900/40 to-slate-800 border border-indigo-500/30 rounded-lg p-6 shadow-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 p-2 opacity-10">
            <span className="text-6xl">🛡️</span>
          </div>
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            🛡️ Confidence & Tone Insights
            <span className="text-[10px] bg-indigo-500 text-white px-2 py-0.5 rounded-full uppercase tracking-tighter">AI Analysis</span>
          </h3>

          <div className="space-y-4">
            {speech.tone_analysis && (
              <div className="bg-indigo-950/30 border border-indigo-500/20 rounded p-4">
                <p className="text-indigo-300 text-xs mb-1 uppercase font-semibold">Communication Style</p>
                <p className="text-white text-sm leading-relaxed">{speech.tone_analysis}</p>
              </div>
            )}

            {speech.improvement_tip && (
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
