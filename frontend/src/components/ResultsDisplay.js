import React from 'react';
import ScoreCard from './ScoreCard';
import EmotionChart from './EmotionChart';

export default function ResultsDisplay({ results }) {
  const emotion = results?.emotion_analysis || {};
  const body = results?.body_language || {};
  const speech = results?.speech_analysis || {};
  const summary = results?.final_summary || {};

  return (
    <div className="space-y-6">
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
            value={`${summary.clarity_score || 0}/10`}
            color="from-orange-600 to-red-600"
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
      {!speech.error && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
          <h3 className="text-lg font-bold text-white mb-4">🎤 Speech Analysis</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Word Count</p>
              <p className="text-white font-bold text-lg">{speech.word_count || 0}</p>
            </div>
            <div className="bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs">Speaking Speed</p>
              <p className="text-white font-bold text-lg">{speech.speaking_speed_wpm || 0} WPM</p>
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
            <div className="mt-4 bg-slate-700 rounded p-3">
              <p className="text-slate-400 text-xs mb-2">Transcript</p>
              <p className="text-slate-200 text-sm">{speech.transcript}</p>
            </div>
          )}
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
                  href={`http://127.0.0.1:8000/reports/${results.report_json_path.split('/').pop()}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open
                </a>
                <a
                  className="bg-slate-700 hover:bg-slate-600 text-slate-100 px-3 py-1 rounded text-sm"
                  href={`http://127.0.0.1:8000/reports/${results.report_json_path.split('/').pop()}`}
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
                  href={`http://127.0.0.1:8000/reports/${results.report_html_path.split('/').pop()}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open
                </a>
                <a
                  className="bg-slate-700 hover:bg-slate-600 text-slate-100 px-3 py-1 rounded text-sm"
                  href={`http://127.0.0.1:8000/reports/${results.report_html_path.split('/').pop()}`}
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
