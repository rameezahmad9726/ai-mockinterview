import React, { useState } from 'react';
import { ArrowUpTrayIcon, DocumentTextIcon, ClipboardDocumentCheckIcon } from '@heroicons/react/24/outline';

function ResumeEvaluator() {
    const [file, setFile] = useState(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [questions, setQuestions] = useState(null);
    const [error, setError] = useState(null);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setError(null);
        }
    };

    const handleAnalyze = async () => {
        if (!file) return;

        setIsAnalyzing(true);
        setError(null);
        setQuestions(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('http://127.0.0.1:8000/analyze-resume', {
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
                                Analyzing...
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
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-sm animate-fade-in">
                    <h2 className="text-xl font-semibold text-white mb-6 flex items-center">
                        <ClipboardDocumentCheckIcon className="h-6 w-6 mr-2 text-green-400" />
                        Generated Interview Questions
                    </h2>

                    <div className="grid gap-6">
                        {questions.map((q, idx) => (
                            <div
                                key={idx}
                                className="bg-slate-900/50 rounded-lg p-5 border border-slate-700/50 hover:border-slate-600 transition-colors"
                            >
                                <div className="flex items-start justify-between mb-2">
                                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium border
                    ${q.type === 'Technical' ? 'bg-blue-900/30 text-blue-300 border-blue-800' :
                                            q.type === 'Behavioral' ? 'bg-purple-900/30 text-purple-300 border-purple-800' :
                                                'bg-emerald-900/30 text-emerald-300 border-emerald-800'}`}>
                                        {q.type}
                                    </span>
                                </div>
                                <p className="text-slate-200 font-medium leading-relaxed">
                                    {q.question}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default ResumeEvaluator;
