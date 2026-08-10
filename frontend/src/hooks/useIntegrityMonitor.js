import { useEffect, useRef, useCallback, useState } from 'react';

/**
 * Client-side integrity monitor for interview proctoring.
 *
 * Detects:
 *   - tab_switch   : Page visibility change or window blur
 *   - copy_paste   : Paste or right-click context menu events
 *   - silence      : Prolonged mic silence during answer windows
 *
 * Events are deduplicated via a per-kind cooldown (default 2 s).
 * The hook is inert when `active` is false.
 *
 * @param {Object}   opts
 * @param {boolean}  opts.active           - Only monitor while true (i.e. during recording)
 * @param {MediaStream|null} opts.stream   - User media stream (for silence detection)
 * @param {number|null} opts.recordingStartMs - Date.now() when recording began
 * @param {Function} opts.onEvent          - Called with { kind, at_sec, meta } on each event
 * @param {number}   [opts.cooldownMs=2000]       - Min ms between events of the same kind
 * @param {number}   [opts.silenceThresholdSec=8]  - Consecutive silence seconds before flagging
 *
 * @returns {{ events: Array }}  Accumulated events array (useful for standalone/debug display)
 */
export default function useIntegrityMonitor({
  active = false,
  stream = null,
  recordingStartMs = null,
  onEvent,
  cooldownMs = 2000,
  silenceThresholdSec = 8,
} = {}) {
  const [events, setEvents] = useState([]);
  const lastFiredRef = useRef({});       // { [kind]: timestamp }
  const silenceStartRef = useRef(null);  // ms timestamp when silence began
  const silenceFiredRef = useRef(false);  // prevent repeat silence events within one quiet stretch
  const analyserRef = useRef(null);
  const audioCtxRef = useRef(null);
  const silenceIntervalRef = useRef(null);

  // Stable reference to the current nowSec helper
  const nowSec = useCallback(() => {
    if (!recordingStartMs) return 0;
    return Math.max(0, (Date.now() - recordingStartMs) / 1000);
  }, [recordingStartMs]);

  // Fire an event, respecting per-kind cooldown
  const fire = useCallback(
    (kind, meta = {}) => {
      const now = Date.now();
      const last = lastFiredRef.current[kind] || 0;
      if (now - last < cooldownMs) return; // cooldown
      lastFiredRef.current[kind] = now;

      const evt = { kind, at_sec: parseFloat(nowSec().toFixed(2)), meta };
      setEvents((prev) => [...prev, evt]);
      if (onEvent) {
        try {
          onEvent(evt);
        } catch (_) {
          /* fire-and-forget */
        }
      }
    },
    [cooldownMs, nowSec, onEvent],
  );

  // ──────────────────────────────────────────────
  // 1. Tab switch / window blur
  // ──────────────────────────────────────────────
  useEffect(() => {
    if (!active) return;

    const onVisibility = () => {
      if (document.hidden) {
        fire('tab_switch', { trigger: 'visibilitychange' });
      }
    };
    const onBlur = () => {
      // Only fire if the page isn't already hidden (avoids double-fire
      // since visibilitychange + blur often fire together).
      if (!document.hidden) {
        fire('tab_switch', { trigger: 'window_blur' });
      }
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
    };
  }, [active, fire]);



  // ──────────────────────────────────────────────
  // 3. Silence detection (mic RMS monitoring)
  // ──────────────────────────────────────────────
  useEffect(() => {
    if (!active || !stream) return;

    // Try to get an audio track from the stream
    const audioTracks = stream.getAudioTracks();
    if (!audioTracks.length) return;

    let cancelled = false;

    const setup = () => {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        audioCtxRef.current = ctx;

        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        analyserRef.current = analyser;

        const buf = new Uint8Array(analyser.frequencyBinCount);
        const RMS_THRESHOLD = 0.015; // below this = "silence"

        silenceStartRef.current = null;
        silenceFiredRef.current = false;

        silenceIntervalRef.current = setInterval(() => {
          if (cancelled) return;
          analyser.getByteTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / buf.length);

          if (rms < RMS_THRESHOLD) {
            // Silent
            if (silenceStartRef.current === null) {
              silenceStartRef.current = Date.now();
              silenceFiredRef.current = false;
            } else if (
              !silenceFiredRef.current &&
              Date.now() - silenceStartRef.current >= silenceThresholdSec * 1000
            ) {
              fire('silence', {
                duration_sec: silenceThresholdSec,
                trigger: 'mic_rms',
              });
              silenceFiredRef.current = true;
            }
          } else {
            // Sound detected — reset
            silenceStartRef.current = null;
            silenceFiredRef.current = false;
          }
        }, 500);
      } catch (e) {
        console.warn('[IntegrityMonitor] Silence detection setup failed:', e);
      }
    };

    setup();

    return () => {
      cancelled = true;
      if (silenceIntervalRef.current) {
        clearInterval(silenceIntervalRef.current);
        silenceIntervalRef.current = null;
      }
      if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
      analyserRef.current = null;
      silenceStartRef.current = null;
      silenceFiredRef.current = false;
    };
  }, [active, stream, fire, silenceThresholdSec]);

  // ──────────────────────────────────────────────
  // 4. Real-time Face Detection via backend OpenCV
  //    Captures frames from the webcam every 2s and
  //    sends them to /detect-faces for accurate counting.
  // ──────────────────────────────────────────────
  useEffect(() => {
    if (!active || !stream) return;

    const videoTracks = stream.getVideoTracks();
    if (!videoTracks.length) return;

    let cancelled = false;

    // Create a hidden video element to read frames from
    let videoEl = document.createElement('video');
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.srcObject = stream;
    videoEl.play().catch(() => {});

    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 240;
    const ctx = canvas.getContext('2d');

    let noFaceConsecutive = 0;
    let multiFaceConsecutive = 0;

    const checkFace = async () => {
      if (cancelled || !videoEl || videoEl.readyState < 2) return;

      try {
        // Capture a frame from the webcam
        ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

        // Convert canvas to blob and send to backend
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.7));
        if (!blob || cancelled) return;

        const formData = new FormData();
        formData.append('file', blob, 'frame.jpg');

        const res = await fetch('http://localhost:8000/detect-faces', {
          method: 'POST',
          body: formData,
        });
        if (!res.ok || cancelled) return;

        const data = await res.json();
        const count = data.faces;

        // -1 means error decoding — skip
        if (count < 0) return;

        if (count === 0) {
          noFaceConsecutive++;
          multiFaceConsecutive = 0;
          // 3 consecutive checks (~6s) before flagging
          if (noFaceConsecutive >= 3) {
            fire('no_face', { trigger: 'camera_stream' });
          }
        } else if (count > 1) {
          multiFaceConsecutive++;
          noFaceConsecutive = 0;
          // 2 consecutive checks (~4s) before flagging
          if (multiFaceConsecutive >= 2) {
            fire('multi_face', { trigger: 'camera_stream', face_count: count });
          }
        } else {
          // Exactly 1 face — all good, reset counters
          noFaceConsecutive = 0;
          multiFaceConsecutive = 0;
        }
      } catch (_) {
        /* network error — skip silently */
      }
    };

    const interval = setInterval(checkFace, 2000);

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (videoEl) {
        videoEl.pause();
        videoEl.srcObject = null;
        videoEl = null;
      }
    };
  }, [active, stream, fire]);

  return { events };
}
