import React, { useRef } from 'react';

export default function VideoUpload({ onUpload, isProcessing }) {
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.currentTarget.classList.add('border-blue-500', 'bg-slate-700');
  };

  const handleDragLeave = (e) => {
    e.currentTarget.classList.remove('border-blue-500', 'bg-slate-700');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('border-blue-500', 'bg-slate-700');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      onUpload(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files.length > 0) {
      onUpload(e.target.files[0]);
    }
  };

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 shadow-xl">
      <h2 className="text-xl font-bold text-white mb-4">📤 Upload Video</h2>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className="border-2 border-dashed border-slate-600 rounded-lg p-8 text-center cursor-pointer transition-all hover:border-blue-500 hover:bg-slate-700/50"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          onChange={handleFileSelect}
          disabled={isProcessing}
          className="hidden"
        />

        <div onClick={() => fileInputRef.current?.click()}>
          <p className="text-4xl mb-3">🎬</p>
          <p className="text-white font-medium mb-1">
            {isProcessing ? 'Processing...' : 'Drag video here or click to upload'}
          </p>
          <p className="text-slate-400 text-sm">
            Supports MP4, WebM, and other video formats
          </p>
        </div>
      </div>

      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={isProcessing}
        className="w-full mt-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium py-2 px-4 rounded-lg transition-colors"
      >
        {isProcessing ? '⏳ Processing...' : '📁 Select File'}
      </button>
    </div>
  );
}
