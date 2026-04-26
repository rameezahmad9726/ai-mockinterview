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
  const [error, setError] = useState(null);
  const [cameraOk, setCameraOk] = useState(false);
  const [micOk, setMicOk] = useState(false);
  const [level, setLevel] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setCameraOk(stream.getVideoTracks().length > 0);

        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
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
        setError(e.message || 'Could not access camera/microphone');
      }
    };

    start();

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white mb-1">System check</h2>
        <p className="text-sm text-slate-400">Make sure your camera and microphone are working before you start.</p>
      </div>

      {error ? (
        <div className="bg-red-950/60 border border-red-800 text-red-200 rounded-lg p-4 text-sm">
          Camera/mic access failed: {error}. Check your browser permissions and try again.
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
