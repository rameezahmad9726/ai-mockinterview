import React from 'react';

export default function ScoreCard({ icon, label, value, color }) {
  return (
    <div className={`bg-gradient-to-br ${color} rounded-lg p-4 text-white shadow-lg`}>
      <p className="text-2xl mb-2">{icon}</p>
      <p className="text-slate-200 text-xs mb-1">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}
