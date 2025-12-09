import React, { useEffect, useState, useMemo } from 'react';

export default function ProcessingStatus({ fileName }) {
  const [stage, setStage] = useState(0);

  const stages = useMemo(
    () => [
      { emoji: '📸', label: 'Extracting frames...', duration: 3000 },
      { emoji: '🎵', label: 'Extracting audio...', duration: 2000 },
      { emoji: '🎤', label: 'Analyzing speech...', duration: 4000 },
      { emoji: '😃', label: 'Analyzing emotions...', duration: 4000 },
      { emoji: '🧍', label: 'Analyzing body language...', duration: 3000 },
      { emoji: '📄', label: 'Generating report...', duration: 2000 },
    ],
    []
  );

  useEffect(() => {
    if (stage < stages.length) {
      const timer = setTimeout(() => {
        setStage(stage + 1);
      }, stages[stage].duration);
      return () => clearTimeout(timer);
    }
  }, [stage, stages]);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
      <h2 className="text-xl font-bold text-white mb-4">⚙️ Processing</h2>

      <p className="text-slate-300 text-sm mb-6 truncate">
        File: <span className="text-blue-400">{fileName}</span>
      </p>

      <div className="space-y-3">
        {stages.map((s, idx) => (
          <div key={idx} className="flex items-center">
            <div
              className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-lg transition-all ${idx < stage
                ? 'bg-green-600 text-white'
                : idx === stage
                  ? 'bg-blue-600 text-white animate-pulse'
                  : 'bg-slate-700 text-slate-400'
                }`}
            >
              {idx < stage ? '✓' : s.emoji}
            </div>
            <p
              className={`ml-3 font-medium ${idx < stage
                ? 'text-green-400'
                : idx === stage
                  ? 'text-blue-400'
                  : 'text-slate-400'
                }`}
            >
              {s.label}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-6 bg-slate-700 rounded-full h-2 overflow-hidden">
        <div
          className="bg-gradient-to-r from-blue-500 to-cyan-500 h-full transition-all duration-500"
          style={{ width: `${Math.min(100, ((stage + 1) / stages.length) * 100)}%` }}
        />
      </div>

      <p className="text-slate-400 text-xs mt-3 text-center">
        {Math.min(100, Math.round(((stage + 1) / stages.length) * 100))}% Complete
      </p>
    </div >
  );
}
