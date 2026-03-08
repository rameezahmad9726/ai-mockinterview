import React, { useState } from 'react';
import { ArrowUpTrayIcon, DocumentTextIcon, ClipboardDocumentCheckIcon, VideoCameraIcon } from '@heroicons/react/24/outline';
import { API_BASE } from '../api';

function ResumeEvaluator({ onStartInterview }) {
    const [file, setFile] = useState(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [questions, setQuestions] = useState(null);
    const [error, setError] = useState(null);
    const [analysisStage, setAnalysisStage] = useState(0);

    const stages = [
        "Reading document...",
        "Extracting skills...",
        "Analyzing experience...",
        "Generating project questions...",
        "Finalizing interview..."
    ];

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            setFile(e.target.files[0]);
            setError(null);
            setQuestions(null);
        }
    };

    const handleAnalyze = async () => {
        if (!file) return;

        setIsAnalyzing(true);
        setError(null);
        setQuestions(null);
        setAnalysisStage(0);

        // Start cycling through stages for better UI feel
        const stageInterval = setInterval(() => {
            setAnalysisStage(prev => (prev < stages.length - 1 ? prev + 1 : prev));
        }, 1500);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${API_BASE}/analyze-resume`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Analysis failed: ${response.statusText}`);
            }

            const data = await response.json();
            if (data.status === 'error') {
                throw new Error(data.message);
            }

            setQuestions(data.questions);
        } catch (err) {
            console.error('Error analyzing resume:', err);
            setError(err.message);
        } finally {
            clearInterval(stageInterval);
            setIsAnalyzing(false);
        }
    };

    return (
        <div className="space-y-8">
            {/* Upload Section */}
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-sm">
                <h2 className="text-xl font-semibold text-white mb-4 flex items-center">
                    <DocumentTextIcon className="h-6 w-6 mr-2 text-indigo-400" />
                    Upload Resume
                </h2>
                <p className="text-slate-400 mb-6 text-sm">
                    Upload your resume (PDF or DOCX) to generate tailored mock interview questions.
                </p>

                <div className="flex flex-col sm:flex-row items-center gap-4">
                    <label className="block w-full sm:w-auto">
                        <span className="sr-only">Choose resume</span>
                        <input
                            type="file"
                            accept=".pdf,.docx"
                            onChange={handleFileChange}
                            className="block w-full text-sm text-slate-300
                file:mr-4 file:py-2.5 file:px-4
                file:rounded-full file:border-0
                file:text-sm file:font-semibold
                file:bg-indigo-600 file:text-white
                hover:file:bg-indigo-700
                cursor-pointer"
                        />
                    </label>

                    <button
                        onClick={handleAnalyze}
                        disabled={!file || isAnalyzing}
                        className={`w-full sm:w-auto px-6 py-2.5 rounded-full font-medium text-white transition-all
              ${!file || isAnalyzing
                                ? 'bg-slate-600 cursor-not-allowed'
                                : 'bg-indigo-500 hover:bg-indigo-600 shadow-lg shadow-indigo-500/20'}`}
                    >
                        {isAnalyzing ? (
                            <span className="flex items-center justify-center">
                                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                {stages[analysisStage]}
                            </span>
                        ) : (
                            <span className="flex items-center justify-center">
                                <ArrowUpTrayIcon className="h-4 w-4 mr-2" />
                                Analyze Resume
                            </span>
                        )}
                    </button>
                </div>

                {error && (
                    <div className="mt-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-200 text-sm">
                        Error: {error}
                    </div>
                )}
            </div>

            {/* Results Section */}
            {questions && (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-10 shadow-xl animate-fade-in text-center">
                    <div className="bg-green-500/20 text-green-400 p-4 rounded-full w-16 h-16 mx-auto mb-6 flex items-center justify-center border border-green-500/30">
                        <ClipboardDocumentCheckIcon className="h-8 w-8" />
                    </div>

                    <h2 className="text-2xl font-bold text-white mb-2">
                        Questions Generated Successfully!
                    </h2>
                    <p className="text-slate-400 mb-8 max-w-md mx-auto">
                        Your resume has been analyzed and 5 tailored interview questions are ready. Click below to begin your live mock interview.
                    </p>

                    <button
                        onClick={() => onStartInterview(questions)}
                        className="bg-green-600 hover:bg-green-700 text-white px-10 py-4 rounded-full font-bold text-lg shadow-xl shadow-green-900/30 transition-all hover:scale-105 flex items-center mx-auto"
                    >
                        <VideoCameraIcon className="h-6 w-6 mr-3" />
                        Start Live Interview
                    </button>
                </div>
            )}
        </div>
    );
}

export default ResumeEvaluator;
