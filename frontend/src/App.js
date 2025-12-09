import React, { useState } from 'react';
import './App.css';
import VideoUpload from './components/VideoUpload';
import ProcessingStatus from './components/ProcessingStatus';
import ResultsDisplay from './components/ResultsDisplay';
import ResumeEvaluator from './components/ResumeEvaluator';

function App() {
  const [activeTab, setActiveTab] = useState('video'); // 'video' | 'resume'
  const [currentFile, setCurrentFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const handleUpload = async (file) => {
    setCurrentFile(file);
    setIsProcessing(true);
    setError(null);
    setResults(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('http://127.0.0.1:8000/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const data = await response.json();
      // Backend returns { status, session_id, analysis }
      // where `analysis` is the object returned by process_video()
      // process_video() returns { report: { ... }, report_json_path, report_html_path }
      const analysis = data.analysis || {};
      const report = analysis.report || {};
      // Compose `results` expected by ResultsDisplay (emotion_analysis, speech_analysis, body_language, etc.)
      const resultsPayload = {
        ...(report || {}),
        report_json_path: analysis.report_json_path,
        report_html_path: analysis.report_html_path,
      };

      setResults(resultsPayload);
      setIsProcessing(false);
    } catch (err) {
      console.error('Error uploading video:', err);
      setError(err.message);
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="bg-slate-950 border-b border-slate-700 shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">
                🎥 AI Mock Interview
              </h1>
              <p className="text-slate-400 mt-1">
                Real-time video analysis & performance feedback
              </p>
            </div>
            <div className="text-right">
              <p className="text-slate-300 text-sm">
                Backend: <span className="text-green-400">●</span> Active
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Navigation Tabs */}
        <div className="flex space-x-4 mb-8 border-b border-slate-700">
          <button
            onClick={() => setActiveTab('video')}
            className={`pb-4 px-2 font-medium text-sm transition-colors relative
              ${activeTab === 'video'
                ? 'text-indigo-400 border-b-2 border-indigo-400'
                : 'text-slate-400 hover:text-slate-200'}`}
          >
            Video Analysis
          </button>
          <button
            onClick={() => setActiveTab('resume')}
            className={`pb-4 px-2 font-medium text-sm transition-colors relative
              ${activeTab === 'resume'
                ? 'text-indigo-400 border-b-2 border-indigo-400'
                : 'text-slate-400 hover:text-slate-200'}`}
          >
            Resume Evaluator
          </button>
        </div>

        {activeTab === 'video' ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left: Upload & Status */}
            <div className="lg:col-span-1 space-y-6">
              <VideoUpload onUpload={handleUpload} isProcessing={isProcessing} />

              {isProcessing && (
                <ProcessingStatus fileName={currentFile?.name} />
              )}

              {error && (
                <div className="bg-red-950 border border-red-700 rounded-lg p-4">
                  <p className="text-red-200 text-sm font-medium">❌ Error</p>
                  <p className="text-red-100 text-xs mt-1">{error}</p>
                </div>
              )}
            </div>

            {/* Right: Results */}
            <div className="lg:col-span-2">
              {results && !isProcessing ? (
                <ResultsDisplay results={results} />
              ) : !isProcessing && !error ? (
                <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 text-center">
                  <p className="text-slate-400">
                    Upload a video to see analysis results
                  </p>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          /* Resume Evaluator Tab */
          <div className="max-w-3xl mx-auto">
            <ResumeEvaluator />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-slate-950 border-t border-slate-700 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-slate-400 text-sm text-center">
            Analyze emotion, body language, and speech in real-time
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
