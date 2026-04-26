import React, { useRef, useState } from 'react';
import { apiFetch } from '../../api';

/**
 * Uploads the candidate's resume. The backend parses it, calls the LLM, and
 * returns the tailored question list. The wizard's parent reads `questions`
 * off the returned session info to drive the Live Interview stage.
 */
export default function ResumeUpload({ token, onDone }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const info = await apiFetch(`/api/interview/${token}/resume`, {
        method: 'POST',
        body: fd,
        auth: false,
      });
      onDone?.(info);
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-white mb-1">Upload your resume</h2>
        <p className="text-sm text-slate-400">We'll tailor your interview questions to your background. PDF or DOCX, up to 10 MB.</p>
      </div>

      <div
        className="border-2 border-dashed border-slate-700 rounded-xl p-8 text-center bg-slate-900/40 cursor-pointer hover:border-indigo-500 transition-colors"
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        {file ? (
          <div>
            <p className="text-white font-medium">{file.name}</p>
            <p className="text-xs text-slate-400 mt-1">{(file.size / 1024).toFixed(0)} KB · click to choose a different file</p>
          </div>
        ) : (
          <>
            <p className="text-slate-200 font-medium">Click to choose your resume</p>
            <p className="text-xs text-slate-500 mt-1">PDF or DOCX</p>
          </>
        )}
      </div>

      {error && (
        <div className="bg-red-950/60 border border-red-800 text-red-200 rounded-lg px-3 py-2 text-sm">{error}</div>
      )}

      <button
        type="submit"
        disabled={!file || uploading}
        className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold"
      >
        {uploading ? 'Preparing your questions...' : 'Upload and continue'}
      </button>

      {uploading && (
        <p className="text-xs text-slate-500 text-center">
          We're parsing your resume and generating tailored questions. This can take ~10 seconds.
        </p>
      )}
    </form>
  );
}
