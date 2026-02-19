# Interveux – Models and Accuracy

Reference for every model used in the project and their reported accuracy / performance.

---

## 1. Speech-to-Text: OpenAI Whisper (`tiny`)

| Property | Value |
|----------|--------|
| **Model** | `openai-whisper` (tiny) |
| **Task** | Transcribe interview audio to text |
| **Metric** | Word Error Rate (WER) – lower is better |

**Reported accuracy (WER):**
- **LibriSpeech test-clean:** ~7% WER  
- **LibriSpeech test-other:** ~17% WER  
- **TEDLIUM:** ~8.6% WER  
- **Clean speech:** best performance  
- **Non-native accents / noisy audio:** WER can rise (e.g. ~18–46% in harder conditions)  

**Note:** Tiny is the fastest Whisper size; larger models (base, medium, large) improve WER but are slower.

---

## 2. Facial Emotion: `dima806/facial_emotions_image_detection`

| Property | Value |
|----------|--------|
| **Model** | Hugging Face – ViT-based image classifier |
| **Task** | Classify facial emotion per frame (7 classes) |
| **Overall accuracy** | **~91%** |

**Per-class precision (representative):**

| Emotion  | Precision |
|----------|-----------|
| Disgust  | 99.09%    |
| Surprise | 94.76%    |
| Happy    | 93.02%    |
| Angry    | 90.22%    |
| Fear     | 87.88%    |
| Neutral  | 87.52%    |
| Sad      | 83.94%    |

Best on Disgust; lowest on Sad. Model size ~85.8M parameters.

---

## 3. Body Language / Pose: MediaPipe Pose (BlazePose)

| Property | Value |
|----------|--------|
| **Model** | Google MediaPipe Pose (BlazePose) |
| **Task** | Detect 33 body keypoints per frame (pose estimation) |
| **Accuracy** | No single "accuracy %" – keypoint detection with **confidence scores** (0–1) per landmark |

**Details:**
- 33 keypoints (nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles, etc.).
- Designed for high-fidelity pose (e.g. fitness, yoga); good for posture and movement.
- Real-time on CPU/GPU; quality depends on visibility and occlusion.

**In this project:** Posture and movement scores are derived from these keypoints (e.g. shoulder alignment, wrist displacement), not from a separate accuracy metric.

---

## 4. Question Generation, Diarization & Tone: OpenAI GPT-4o-mini

| Property | Value |
|----------|--------|
| **Model** | OpenAI `gpt-4o-mini` (configurable via `OPENAI_MODEL`) |
| **Tasks** | Generate interview questions; diarize transcript (Interviewer vs Interviewee); rate confidence & tone |
| **Accuracy** | No single accuracy – **generative LLM**; quality is task- and prompt-dependent |

**Use in project:**
- **Questions:** Tailored to resume; evaluated by user/design, not a numeric accuracy.
- **Diarization:** Segment-level attribution; no public benchmark for this exact setup.
- **Confidence & tone:** 1–10 rating and text summary; subjective, no standard accuracy metric.

---

## 5. Text-to-Speech: OpenAI TTS-1

| Property | Value |
|----------|--------|
| **Model** | OpenAI `tts-1` |
| **Task** | Convert question text to speech (e.g. "alloy" voice) |
| **Accuracy** | N/A – **synthesis quality** (e.g. MOS, naturalness), not classification accuracy |

No single "accuracy" figure; typically evaluated by mean opinion score (MOS) or similar in research.

---

## Summary Table

| Component        | Model                          | Type        | Accuracy / metric                    |
|-----------------|---------------------------------|------------|--------------------------------------|
| Speech-to-text  | Whisper tiny                    | STT        | ~7% WER (clean); higher on hard audio |
| Emotion         | dima806/facial_emotions_...     | Classifier | ~91% overall; 84–99% per emotion     |
| Pose / body     | MediaPipe BlazePose             | Keypoints  | Confidence per keypoint; no single %  |
| Questions/tone  | GPT-4o-mini                     | LLM        | Task-dependent; no single accuracy   |
| TTS             | OpenAI TTS-1                    | Synthesis  | Quality (e.g. MOS); not accuracy %   |

Use this document when explaining how each analysis is done and what accuracy (where applicable) each model has.
