import React from 'react';

export default function EmotionChart({ timeline }) {
  if (!timeline || timeline.length === 0) return null;

  // Get unique emotions and their counts
  const emotionCounts = timeline.reduce((acc, item) => {
    acc[item.emotion] = (acc[item.emotion] || 0) + 1;
    return acc;
  }, {});

  const maxCount = Math.max(...Object.values(emotionCounts));

  return (
    <div className="mt-4">
      <p className="text-slate-400 text-xs mb-3">Emotion Distribution</p>
      <div className="space-y-2">
        {Object.entries(emotionCounts).map(([emotion, count]) => (
          <div key={emotion} className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-300 w-20">{emotion}</span>
            <div className="flex-1 bg-slate-700 rounded-full h-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-blue-500 to-cyan-500 h-full transition-all"
                style={{ width: `${(count / maxCount) * 100}%` }}
              />
            </div>
            <span className="text-xs text-slate-400 w-8 text-right">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
