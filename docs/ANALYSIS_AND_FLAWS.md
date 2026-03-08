# Interveux – Project Analysis & Identified Flaws

## 1. Video analysis is slow – root causes

### 1.1 Speech (Whisper) – **critical bug + bottleneck**
- **Bug:** The code uses `whisper.pad_or_trim(audio_data)` then `whisper.decode()` once. `pad_or_trim` defaults to **30 seconds**, so only the **first 30 seconds** of the interview are transcribed. Longer videos are incorrectly analyzed.
- **Fix:** Use `model.transcribe(audio_path)` (or equivalent) to transcribe the **full** audio. This is also what makes speech the slowest step on CPU (full-length transcription).
- **Speed:** On CPU, Whisper tiny can take ~1–3× realtime (e.g. 2 min audio ≈ 2–6 min). First run is slower due to model load/download.

### 1.2 Emotion (ViT / transformers)
- **Issue:** Image-classification pipeline over many frames on **CPU** is slow (ViT is heavy).
- **Current mitigations:** `MAX_FRAMES=30`, `SUBSAMPLE_STEP=3`, batch size 16.
- **Further options:** Reduce frames/subsample via env; use GPU (CUDA/MPS) when available (code already tries).

### 1.3 Body language (MediaPipe)
- **Issue:** Per-frame `cv2.imread` + `pose.process()` in a loop; no batching.
- **Impact:** Moderate; MediaPipe is relatively fast, but I/O and Python loop add up.
- **Option:** Keep as-is or subsample more aggressively.

### 1.4 OpenAI API (diarization + tone)
- **Issue:** One blocking HTTP call after transcription adds **2–10+ seconds** latency.
- **No simple fix:** Required for quality. Could be made optional for a “fast” mode.

### 1.5 Progress UX
- **Fixed:** Progress now updates at 50 / 65 / 80 % as each of the three analysis tasks completes, so the UI no longer appears stuck at 35%.

---

## 2. Other flaws

### 2.1 Backend
- **Lazy video pipeline:** Video-related imports (e.g. `cv2`, `video_processor`) are lazy so the server can start without full deps; good. Resume/TTS still import at startup (pdfplumber, openai).
- **No timeout on analysis:** A very long or corrupt video can keep the worker busy indefinitely; consider a global timeout or max duration.
- **Temp dir cleanup:** `tempfile.mkdtemp()` is used for frames/audio; temp dir is not explicitly removed after the request (relies on OS cleanup).
- **Reports dir:** Reports are stored under `backend/reports/` with no retention or size limit; can grow unbounded.
- **In-memory progress:** `progress_store` is in-memory; restart loses state; no persistence.

### 2.2 Frontend
- **Hardcoded API URL:** `API_BASE` defaults to `http://localhost:8000`; fine for dev, needs env (e.g. `REACT_APP_API_URL`) for production.
- **No request timeout:** Fetch to `/analyze` or `/analysis-status` has no explicit timeout; slow backend can hang the UI.
- **Backend health:** Health check runs on interval; good. No retry/backoff if backend is temporarily down.

### 2.3 Security / config
- **CORS:** `allow_origins=["*"]` is acceptable for local dev; should be restricted in production.
- **API key:** `OPENAI_API_KEY` in `backend/.env`; ensure `.env` is gitignored (it is).
- **File upload:** Uploaded videos/resumes stored under `uploads/` with UUID; no scan for malicious files or size limit in code (depends on FastAPI/OS).

### 2.4 Dependencies & env
- **Python 3.14:** `requirements.txt` and `mediapipe`/torch may target newer Python; ensure compatibility with your runtime.
- **FFmpeg:** Audio extraction uses `imageio_ffmpeg` (bundled); system ffmpeg not required; good for portability.

---

## 3. Summary table

| Area            | Flaw / bottleneck                          | Severity   | Status / recommendation        |
|-----------------|--------------------------------------------|-----------|---------------------------------|
| Speech          | Only first 30 s transcribed                 | **High**  | Use full `transcribe()`; fixed  |
| Speech          | Full transcription slow on CPU             | Medium    | Use tiny; optional “fast” mode |
| Emotion         | ViT slow on CPU                            | Medium    | Env tuning; GPU if available   |
| Progress        | Stuck at 35%                               | Medium    | Fixed (50/65/80% updates)       |
| Timeout         | No max time for analysis                   | Low       | Add timeout or max duration    |
| Temp cleanup    | Temp dir not deleted                       | Low       | Optional explicit cleanup       |
| Reports         | Unbounded growth                           | Low       | Optional retention policy       |
| Frontend API URL| Hardcoded localhost                        | Low       | Use env in production           |

---

## 4. Speed vs accuracy knobs (env)

- `INTERVEUX_MAX_FRAMES` – max frames to extract (default **20**). Lower = faster, less coverage.
- `INTERVEUX_SUBSAMPLE_STEP` – use every Nth frame for emotion/body (default **4**). Higher = faster, coarser.
- Optional: `INTERVEUX_FAST_SPEECH=1` – transcribe only first 30 s (fast but incomplete; for testing only).

These are read in `video_processor.py` and emotion/body modules.

## 5. Body language “Analysis failed” fix

- **Cause:** Body analysis could throw (e.g. missing frames, `cv2.imread` None, or MediaPipe returning no landmarks), so the pipeline fell back to “Analysis failed” and posture 0.
- **Fix:** Body module now validates frames and images, handles exceptions per frame, and returns a clear fallback (e.g. “Insufficient pose data (ensure face/upper body visible)”) instead of crashing. Posture score is scaled 0–10 for the UI.
