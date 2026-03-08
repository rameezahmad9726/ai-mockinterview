import React, { useState, useEffect } from 'react';
import './App.css';
import VideoUpload from './components/VideoUpload';
import ProcessingStatus from './components/ProcessingStatus';
import ResultsDisplay from './components/ResultsDisplay';
import ResumeEvaluator from './components/ResumeEvaluator';
import LiveInterview from './components/LiveInterview';
import { API_BASE } from './api';

function App() {
  const [activeTab, setActiveTab] = useState('video'); // 'video' | 'resume' | 'live'
  const [currentFile, setCurrentFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [interviewQuestions, setInterviewQuestions] = useState([]);
  const [sessionId, setSessionId] = useState(`session_${Date.now()}`);
  const [backendReachable, setBackendReachable] = useState(null); // null = checking, true/false = result

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(API_BASE);
        if (!cancelled) setBackendReachable(res.ok);
      } catch {
        if (!cancelled) setBackendReachable(false);
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const handleStartInterview = (questions) => {
    setInterviewQuestions(questions);
    setSessionId(`session_${Date.now()}`);
    setActiveTab('live');
  };

  const pollAnalysisStatus = async (sid) => {
    try {
      const response = await fetch(`${API_BASE}/analysis-status/${sid}`);
      const data = await response.json();

      if (data.status === "error") {
        setError(data.message);
        setIsProcessing(false);
        return;
      }

      if (data.progress === 100 && data.result) {
        const report = data.result.report || {};
        setResults({
          ...(report || {}),
          report_json_path: data.result.report_json_path,
          report_html_path: data.result.report_html_path,
        });
        setIsProcessing(false);
      } else {
        // Continue polling
        setTimeout(() => pollAnalysisStatus(sid), 2000);
      }
    } catch (err) {
      console.error('Polling error:', err);
      setTimeout(() => pollAnalysisStatus(sid), 5000);
    }
  };

  const handleUpload = async (file) => {
    setCurrentFile(file);
    setIsProcessing(true);
    setError(null);
    setResults(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const data = await response.json();
      if (data.status === "started") {
        pollAnalysisStatus(data.session_id);
      } else {
        throw new Error("Failed to start analysis");
      }
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
                🎥 Interveux
              </h1>
              <p className="text-slate-400 mt-1">
                Real-time video analysis & performance feedback
              </p>
            </div>
            <div className="text-right">
              <p className="text-slate-300 text-sm">
                Backend:{' '}
                {backendReachable === null ? (
                  <span className="text-slate-500">● Checking...</span>
                ) : backendReachable ? (
                  <span className="text-green-400">● Active</span>
                ) : (
                  <span className="text-amber-400" title="Start the backend: cd backend; python main.py">● Unreachable</span>
                )}
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
          <button
            onClick={() => setActiveTab('live')}
            disabled={interviewQuestions.length === 0}
            className={`pb-4 px-2 font-medium text-sm transition-colors relative
              ${activeTab === 'live'
                ? 'text-indigo-400 border-b-2 border-indigo-400'
                : (interviewQuestions.length === 0 ? 'text-slate-600 cursor-not-allowed' : 'text-slate-400 hover:text-slate-200')}`}
          >
            Live Interview
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
        ) : activeTab === 'resume' ? (
          /* Resume Evaluator Tab */
          <div className="max-w-3xl mx-auto">
            {backendReachable === false && (
              <div className="mb-6 p-4 bg-amber-900/30 border border-amber-700 rounded-lg text-amber-200 text-sm">
                Backend is not reachable. Start it with: <code className="bg-slate-800 px-2 py-1 rounded">cd backend; python main.py</code> (from project root in PowerShell)
              </div>
            )}
            <ResumeEvaluator onStartInterview={handleStartInterview} />
          </div>
        ) : (
          /* Live Interview Tab */
          <LiveInterview questions={interviewQuestions} sessionId={sessionId} />
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
