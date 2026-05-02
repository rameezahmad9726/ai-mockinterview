import React, { useEffect, useRef, useState } from 'react';

/**
 * Lightweight pre-interview system check. Confirms camera + microphone
 * permissions, shows a live preview, and measures mic input level so the
 * candidate knows the system actually hears them.
 */
export default function SystemCheck({ onReady }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const audioCtxRef = useRef(null);
  const [error, setError] = useState(null);
  const [cameraOk, setCameraOk] = useState(false);
  const [micOk, setMicOk] = useState(false);
  const [level, setLevel] = useState(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const cleanup = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
        audioCtxRef.current.close();
        audioCtxRef.current = null;
      }
      if (videoRef.current) videoRef.current.srcObject = null;
    };

    const formatError = (e) => {
      if (!e) return 'Could not access camera/microphone';
      if (e.name === 'NotReadableError') {
        return 'Device is currently in use by another app/tab. Close Zoom/Meet/Teams/other tabs and retry';
      }
      if (e.name === 'NotAllowedError') {
        return 'Permission blocked. Please allow camera and microphone in browser site settings';
      }
      if (e.name === 'NotFoundError') {
        return 'No camera/microphone detected on this device';
      }
      return e.message || 'Could not access camera/microphone';
    };

    const tryGetUserMedia = async () => {
      const attempts = [
        { video: true, audio: true },
        {
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 24, max: 30 } },
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        },
        { video: { facingMode: 'user' }, audio: true }
      ];

      let lastError = null;
      for (const constraints of attempts) {
        try {
          return await navigator.mediaDevices.getUserMedia(constraints);
        } catch (err) {
          lastError = err;
        }
      }
      throw lastError || new Error('Could not access camera/microphone');
    };

    const start = async () => {
      try {
        cleanup();
        setError(null);
        setCameraOk(false);
        setMicOk(false);
        setLevel(0);

        const stream = await tryGetUserMedia();
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setCameraOk(stream.getVideoTracks().length > 0);

        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        audioCtxRef.current = ctx;
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);
        const buf = new Uint8Array(analyser.frequencyBinCount);

        const loop = () => {
          analyser.getByteTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / buf.length);
          const pct = Math.min(100, Math.round(rms * 400));
          setLevel(pct);
          if (pct > 5) setMicOk(true);
          rafRef.current = requestAnimationFrame(loop);
        };
        loop();
      } catch (e) {
        setError(formatError(e));
      }
    };

    start();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [attempt]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white mb-1">System check</h2>
        <p className="text-sm text-slate-400">Make sure your camera and microphone are working before you start.</p>
      </div>

      {error ? (
        <div className="bg-red-950/60 border border-red-800 text-red-200 rounded-lg p-4 text-sm space-y-3">
          <p>Camera/mic access failed: {error}.</p>
          <button
            onClick={() => setAttempt((n) => n + 1)}
            className="inline-flex items-center rounded-md bg-red-800 hover:bg-red-700 px-3 py-1.5 text-xs font-semibold text-red-100"
          >
            Retry system check
          </button>
        </div>
      ) : (
        <>
          <div className="aspect-video bg-slate-900 border border-slate-700 rounded-xl overflow-hidden">
            <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
              <p className="text-xs uppercase text-slate-500">Camera</p>
              <p className={`font-semibold ${cameraOk ? 'text-emerald-300' : 'text-slate-300'}`}>
                {cameraOk ? 'Detected' : 'Waiting...'}
              </p>
            </div>
            <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
              <p className="text-xs uppercase text-slate-500">Microphone</p>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden mt-2">
                <div className={`h-full transition-all ${micOk ? 'bg-emerald-500' : 'bg-amber-500'}`} style={{ width: `${level}%` }} />
              </div>
              <p className={`text-xs mt-1 ${micOk ? 'text-emerald-300' : 'text-slate-400'}`}>
                {micOk ? 'Mic OK — try saying "hello"' : 'Speak to test your mic'}
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
              onReady?.();
            }}
            disabled={!cameraOk || !micOk}
            className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold"
          >
            {cameraOk && micOk ? 'Continue' : 'Waiting for camera + mic...'}
          </button>
        </>
      )}
    </div>
  );
}
