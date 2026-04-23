"""
Interview scoring engine (100 marks total).

Breakdown:
    20  Certifications (scaled by relevance AND by answer quality).
    60  Candidate answers (domain-knowledge relevance per question).
    20  Behavior & emotions (posture, movement, eye contact, confidence, filler).

Also produces:
    - Interview notes (Q/answer/evaluation per question)
    - Lacking intervals (frame ranges where candidate under-performed)
    - Real-world recommendation tier

All returned records are DB-ready: they are plain dicts with stable, flat keys
so each can be persisted later as rows in tables like:
    interview_sessions(id, domain, total_score, tier, created_at, ...)
    score_breakdown(session_id, cert_score, answer_score, behavior_score, total)
    interview_notes(session_id, question_idx, question, answer, evaluation,
                    answer_score_0_10)
    lacking_intervals(session_id, start_sec, end_sec, start_frame, end_frame,
                      issues_json, severity)
    certifications(session_id, name, issuer, relevant, domain_match_score)
"""

from __future__ import annotations

import json
import os
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ----- Thresholds used by lacking-interval detection -----

EYE_CONTACT_LOW = float(os.environ.get("SCORING_EYE_CONTACT_LOW", "0.4"))
POSTURE_LOW_0_10 = float(os.environ.get("SCORING_POSTURE_LOW", "6.0"))
LOW_CONFIDENCE_EMOTIONS = {"nervous", "stressed", "low_confidence"}
EXCESSIVE_MOVEMENT_KEYWORD = "excessive"
VERY_STILL_KEYWORDS = ("very still", "stiff")


# ======================================================================
# Dataclasses (DB-ready records)
# ======================================================================


@dataclass
class InterviewNote:
    question_idx: int
    question: str
    question_type: str
    candidate_answer: str
    evaluation: str
    answer_score_0_10: float


@dataclass
class LackingInterval:
    start_sec: float
    end_sec: float
    start_frame: int
    end_frame: int
    issues: List[str]
    severity: str  # "minor" | "moderate" | "severe"
    # Representative frame paths captured during interval detection.
    # Populated by video_processor after it copies the frames into the
    # session's persistent uploads folder; rewritten to URLs for the UI.
    frame_paths: List[str] = field(default_factory=list)


@dataclass
class CertificationScoreDetail:
    name: str
    issuer: str
    relevant: bool
    domain_match_score: float  # 0–1


@dataclass
class AnswerScoreResult:
    total_0_60: float
    per_question: List[InterviewNote] = field(default_factory=list)
    average_relevance_0_10: float = 0.0
    rationale: str = ""


@dataclass
class CertificationScoreResult:
    total_0_20: float
    cert_relevance_ratio_0_1: float
    answer_ratio_0_1: float
    certifications: List[CertificationScoreDetail] = field(default_factory=list)
    rationale: str = ""


@dataclass
class BehaviorScoreResult:
    total_0_20: float
    posture_points: float
    movement_points: float
    eye_contact_points: float
    confidence_points: float
    filler_penalty: float
    rationale: str = ""


@dataclass
class Recommendation:
    tier: str          # "strong_hire" | "hire" | "borderline" | "not_recommended"
    label: str         # Human-facing label
    summary: str       # One-paragraph recruiter-style note
    total_score_0_100: float


@dataclass
class FinalScoring:
    total_0_100: float
    certification_score: CertificationScoreResult
    answer_score: AnswerScoreResult
    behavior_score: BehaviorScoreResult
    interview_notes: List[InterviewNote]
    lacking_intervals: List[LackingInterval]
    recommendation: Recommendation
    domain: str


# ======================================================================
# Helpers
# ======================================================================


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _questions_as_list(questions: Any) -> List[Dict[str, str]]:
    """Normalize assorted question shapes (list of str / list of dict) to list of dicts."""
    out: List[Dict[str, str]] = []
    if not questions:
        return out
    for q in questions:
        if isinstance(q, dict):
            out.append({
                "question": str(q.get("question", "")).strip(),
                "type": str(q.get("type", "General")).strip() or "General",
            })
        else:
            out.append({"question": str(q).strip(), "type": "General"})
    return [q for q in out if q["question"]]


def _transcript_candidate_text(formatted_transcript: List[Dict[str, Any]]) -> str:
    """Flatten interviewee-only text from the formatted (diarized) transcript."""
    chunks: List[str] = []
    for seg in formatted_transcript or []:
        if (seg.get("speaker") or "").lower() == "interviewee":
            text = (seg.get("text") or "").strip()
            if text and "[no audible response]" not in text.lower():
                chunks.append(text)
    return " ".join(chunks).strip()


# ======================================================================
# 1) Answers scoring (0–60) + interview notes (LLM)
# ======================================================================


def _heuristic_answer_scoring(
    questions: List[Dict[str, str]],
    formatted_transcript: List[Dict[str, Any]],
    raw_transcript: str,
) -> AnswerScoreResult:
    """Fallback when LLM is unavailable — assigns a low, word-count-driven score."""
    candidate_text = _transcript_candidate_text(formatted_transcript) or raw_transcript or ""
    words = candidate_text.split()
    total_words = len(words)
    if not questions:
        return AnswerScoreResult(total_0_60=0.0, per_question=[], average_relevance_0_10=0.0,
                                 rationale="No questions to score.")

    # Rough per-question chunking by equal word split
    per_q_words = max(1, total_words // max(1, len(questions)))
    notes: List[InterviewNote] = []
    scores: List[float] = []
    for idx, q in enumerate(questions):
        chunk = " ".join(words[idx * per_q_words:(idx + 1) * per_q_words]) or "[No audible response]"
        raw = min(10.0, (len(chunk.split()) / 30.0) * 10.0)  # ~30 words ≈ 10/10
        score = round(raw, 2)
        scores.append(score)
        notes.append(InterviewNote(
            question_idx=idx,
            question=q["question"],
            question_type=q.get("type", "General"),
            candidate_answer=chunk,
            evaluation="Heuristic fallback — LLM scoring unavailable; score reflects answer length only.",
            answer_score_0_10=score,
        ))
    avg = sum(scores) / len(scores) if scores else 0.0
    total_60 = round((avg / 10.0) * 60.0, 2)
    return AnswerScoreResult(
        total_0_60=total_60,
        per_question=notes,
        average_relevance_0_10=round(avg, 2),
        rationale="Heuristic fallback — no LLM available.",
    )


def compute_answer_scoring(
    questions: Any,
    formatted_transcript: List[Dict[str, Any]],
    raw_transcript: str,
    domain: str,
    insufficient: bool,
) -> AnswerScoreResult:
    """
    Uses the LLM to (1) map the diarized transcript back to each scheduled
    question, (2) score each answer 0–10 for relevance / depth / correctness,
    and (3) produce a short evaluation note per answer. Total is scaled to 60.
    """
    q_list = _questions_as_list(questions)
    if not q_list:
        return AnswerScoreResult(total_0_60=0.0, per_question=[], average_relevance_0_10=0.0,
                                 rationale="No questions supplied.")

    if insufficient:
        notes = [
            InterviewNote(
                question_idx=idx,
                question=q["question"],
                question_type=q.get("type", "General"),
                candidate_answer="[No audible response]",
                evaluation="Candidate did not provide an audible answer for this question.",
                answer_score_0_10=0.0,
            )
            for idx, q in enumerate(q_list)
        ]
        return AnswerScoreResult(
            total_0_60=0.0,
            per_question=notes,
            average_relevance_0_10=0.0,
            rationale="No audible candidate speech detected.",
        )

    # Fast path: if the candidate barely spoke, there's nothing worth a
    # 15–30s LLM round-trip for — use the heuristic and move on.
    candidate_word_count = len(_transcript_candidate_text(formatted_transcript).split()) \
                           if formatted_transcript else len((raw_transcript or "").split())
    if candidate_word_count < max(30, 10 * len(q_list)):
        print(f"[SCORING] Skipping answer-LLM (only {candidate_word_count} candidate words) — using heuristic.")
        return _heuristic_answer_scoring(q_list, formatted_transcript, raw_transcript)

    try:
        from modules.question_generator import _get_client, OPENAI_MODEL
        from openai import OpenAI  # type: ignore

        client = _get_client()

        # Keep the prompt compact so the LLM responds quickly. We don't need the
        # full raw transcript AND every segment — prioritise interviewee segments
        # (the ones we're actually scoring) and cap string lengths.
        interviewee_segments = []
        other_segments = []
        for s in (formatted_transcript or []):
            row = {"speaker": s.get("speaker", ""), "text": (s.get("text") or "")[:600]}
            if (row["speaker"] or "").lower() == "interviewee":
                interviewee_segments.append(row)
            else:
                other_segments.append(row)
        # Include all interviewee segments (up to 40) and only a few interviewer
        # turns for context. Raw transcript is cropped hard.
        segments = (interviewee_segments[:40]
                    + other_segments[:max(0, 20 - min(40, len(interviewee_segments)))])
        transcript_blob = {
            "raw": raw_transcript[:2500],
            "segments": segments,
        }

        prompt = f"""
You are a senior interviewer scoring a candidate for a "{domain}" role.

You will receive:
  - The ordered list of scheduled questions.
  - The diarized interview transcript (Interviewer vs Interviewee) AND the raw
    transcript as a safety fallback.

TASKS:
1. For EACH scheduled question (in order), extract the candidate's answer
   VERBATIM from the Interviewee segments. If the candidate never answered a
   given question, set answer to "[No audible response]".
2. Score each answer on relevance, correctness and depth for the "{domain}"
   role, from 0 to 10 (10 = excellent, complete, specific; 5 = partially
   relevant / shallow; 0 = off-topic or missing).
3. Write a 1-2 sentence evaluation per answer explaining what was good and
   what was missing. Do not invent skills or experience the candidate did not
   mention.
4. Add an overall `rationale` (2-3 sentences) explaining the candidate's
   domain knowledge strength across all answers.

Return ONLY JSON:
{{
  "per_question": [
    {{
      "question_idx": 0,
      "candidate_answer": "...",
      "answer_score_0_10": 0,
      "evaluation": "..."
    }}
  ],
  "rationale": "..."
}}

Scheduled questions (ordered):
{json.dumps(q_list, ensure_ascii=False)}

Transcript:
{json.dumps(transcript_blob, ensure_ascii=False)}
"""

        import time as _time
        _t0 = _time.time()
        print(f"[SCORING] Answer-scoring LLM call (prompt ~{len(prompt)} chars, {len(q_list)} questions)…")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict interview scorer. Output strictly JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=30,
        )
        print(f"[SCORING] Answer-scoring LLM completed in {_time.time() - _t0:.1f}s")
        data = json.loads(response.choices[0].message.content)

        per_q_raw = data.get("per_question") or []
        notes: List[InterviewNote] = []
        scores: List[float] = []
        # Map back by idx, preserving order of scheduled questions
        by_idx = {int(r.get("question_idx", i)): r for i, r in enumerate(per_q_raw)}
        for idx, q in enumerate(q_list):
            r = by_idx.get(idx, {})
            score = _clamp(_safe_float(r.get("answer_score_0_10"), 0.0), 0.0, 10.0)
            scores.append(score)
            notes.append(InterviewNote(
                question_idx=idx,
                question=q["question"],
                question_type=q.get("type", "General"),
                candidate_answer=str(r.get("candidate_answer", "[No audible response]")).strip()
                                 or "[No audible response]",
                evaluation=str(r.get("evaluation", "")).strip(),
                answer_score_0_10=round(score, 2),
            ))
        avg = sum(scores) / len(scores) if scores else 0.0
        total_60 = round((avg / 10.0) * 60.0, 2)
        return AnswerScoreResult(
            total_0_60=total_60,
            per_question=notes,
            average_relevance_0_10=round(avg, 2),
            rationale=str(data.get("rationale", "")).strip(),
        )
    except Exception as e:
        traceback.print_exc()
        print(f"[WARN] LLM answer scoring failed ({e}); falling back to heuristic.")
        return _heuristic_answer_scoring(q_list, formatted_transcript, raw_transcript)


# ======================================================================
# 2) Certifications scoring (0–20)
# ======================================================================


def compute_certification_scoring(
    certifications: List[Dict[str, Any]],
    domain: str,
    answers_total_0_60: float,
) -> CertificationScoreResult:
    """
    cert_score = 20 * (0.5 * cert_relevance + 0.5 * answer_ratio)

    Reasoning:
    - If certs are weak but answers are strong → still gets a solid score
      (capped around 10/20, not zero).
    - If certs are strong but answers are weak → deducted proportionally.
    - If both are strong → close to full 20.
    """
    details: List[CertificationScoreDetail] = []
    for c in certifications or []:
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        relevant = bool(c.get("relevant", True))
        details.append(CertificationScoreDetail(
            name=name,
            issuer=str(c.get("issuer", "")).strip(),
            relevant=relevant,
            domain_match_score=1.0 if relevant else 0.2,  # non-matching certs still count a little
        ))

    # Relevance ratio: (sum of per-cert domain match) / target of 3 relevant certs, capped 1.0
    if details:
        match_sum = sum(d.domain_match_score for d in details)
        cert_relevance = _clamp(match_sum / 3.0, 0.0, 1.0)
    else:
        cert_relevance = 0.0

    answer_ratio = _clamp(answers_total_0_60 / 60.0, 0.0, 1.0)
    score = 20.0 * (0.5 * cert_relevance + 0.5 * answer_ratio)
    score = round(_clamp(score, 0.0, 20.0), 2)

    if not details:
        rationale = (
            f"No certifications found on resume. Score derives entirely from answer quality "
            f"({round(answers_total_0_60,1)}/60)."
        )
    else:
        relevant_count = sum(1 for d in details if d.relevant)
        rationale = (
            f"{len(details)} certification(s) on resume, {relevant_count} relevant to {domain}. "
            f"Weighted with answer quality to avoid penalising strong domain knowledge "
            f"when certifications are thin."
        )

    return CertificationScoreResult(
        total_0_20=score,
        cert_relevance_ratio_0_1=round(cert_relevance, 3),
        answer_ratio_0_1=round(answer_ratio, 3),
        certifications=details,
        rationale=rationale,
    )


# ======================================================================
# 3) Behavior & emotions scoring (0–20)
# ======================================================================


def compute_behavior_scoring(
    emotion: Dict[str, Any],
    body: Dict[str, Any],
    speech: Dict[str, Any],
    behavior_insights: Dict[str, Any],
) -> BehaviorScoreResult:
    """
    Heuristic 0–20 behavioral score combining:
      6 pts posture (from body.posture_score 0-10)
      4 pts eye contact (from behavior_insights.eye_contact_score 0-1)
      4 pts confidence (from speech.confidence_score 1-10 / final confidence)
      3 pts movement quality (from body.gesture_label)
      3 pts emotion stability (fewer nervous/stressed frames)
    Filler-word penalty is applied on top, capped at -3 pts.
    """
    insufficient = bool(speech.get("insufficient_candidate_speech")) \
                   or speech.get("candidate_speech_detected") is False

    # Posture (0–6)
    posture_0_10 = _clamp(_safe_float(body.get("posture_score"), 0.0), 0.0, 10.0)
    posture_points = (posture_0_10 / 10.0) * 6.0

    # Eye contact (0–4)
    eye_0_1 = _clamp(_safe_float(behavior_insights.get("eye_contact_score"), 0.0), 0.0, 1.0)
    eye_contact_points = eye_0_1 * 4.0

    # Confidence (0–4) — prefer final confidence score (1-10 scale)
    conf_0_10 = _clamp(_safe_float(speech.get("confidence_score"), 5.0), 0.0, 10.0)
    confidence_points = (conf_0_10 / 10.0) * 4.0

    # Movement (0–3)
    gesture_label = (body.get("gesture_label") or "").lower()
    if "normal" in gesture_label or "controlled" in gesture_label:
        movement_points = 3.0
    elif EXCESSIVE_MOVEMENT_KEYWORD in gesture_label:
        movement_points = 1.0
    elif any(k in gesture_label for k in VERY_STILL_KEYWORDS):
        movement_points = 1.5
    else:
        movement_points = 1.5  # unknown / pose-not-detected

    # Emotion stability (0–3) — from emotion_counts distribution
    emotion_counts = emotion.get("emotion_counts") or {}
    total_frames = sum(int(v) for v in emotion_counts.values()) or 1
    nervous_frames = 0
    for k, v in emotion_counts.items():
        key = str(k).lower()
        if key in ("fear", "nervous", "angry", "sad", "stressed", "disgust", "low_confidence"):
            nervous_frames += int(v)
    nervous_ratio = nervous_frames / total_frames
    if nervous_ratio <= 0.1:
        emotion_points = 3.0
    elif nervous_ratio <= 0.3:
        emotion_points = 2.0
    elif nervous_ratio <= 0.5:
        emotion_points = 1.0
    else:
        emotion_points = 0.0

    # Filler-word penalty (max -3)
    fillers = int(_safe_float(
        speech.get("filler_words_count") if speech.get("filler_words_count") is not None
        else speech.get("filler_words"),
        0.0,
    ))
    if fillers <= 3:
        filler_penalty = 0.0
    elif fillers <= 6:
        filler_penalty = -1.0
    elif fillers <= 10:
        filler_penalty = -2.0
    else:
        filler_penalty = -3.0

    if insufficient:
        total = 0.0
        rationale = (
            "No audible candidate speech — behavior score set to 0 because body-language signals "
            "alone are not a reliable interview indicator without answers."
        )
    else:
        total = posture_points + eye_contact_points + confidence_points \
                + movement_points + emotion_points + filler_penalty
        total = round(_clamp(total, 0.0, 20.0), 2)
        rationale = (
            f"Posture {posture_points:.1f}/6, Eye {eye_contact_points:.1f}/4, "
            f"Confidence {confidence_points:.1f}/4, Movement {movement_points:.1f}/3, "
            f"Emotion {emotion_points:.1f}/3, Filler penalty {filler_penalty:.1f}."
        )

    return BehaviorScoreResult(
        total_0_20=total,
        posture_points=round(posture_points, 2),
        movement_points=round(movement_points, 2),
        eye_contact_points=round(eye_contact_points, 2),
        confidence_points=round(confidence_points, 2),
        filler_penalty=round(filler_penalty, 2),
        rationale=rationale,
    )


# ======================================================================
# 4) Lacking intervals (no LLM — pure frame scan + grouping)
# ======================================================================


def _issues_for_frame(
    mapped_emotion: str,
    posture_label: str,
    eye_contact: Optional[float],
    gesture_label_lower: str,
    is_answering: bool,
) -> List[str]:
    issues: List[str] = []
    # Only flag low eye contact while the candidate is actively answering.
    # When the TTS is playing or the candidate is reading the question on
    # screen, looking away from the webcam is expected behavior.
    if is_answering and eye_contact is not None and eye_contact < EYE_CONTACT_LOW:
        issues.append("low_eye_contact")
    if posture_label == "bad":
        issues.append("poor_posture")
    if mapped_emotion in LOW_CONFIDENCE_EMOTIONS:
        issues.append("low_confidence")
    if EXCESSIVE_MOVEMENT_KEYWORD in gesture_label_lower:
        issues.append("excessive_movement")
    elif any(k in gesture_label_lower for k in VERY_STILL_KEYWORDS):
        issues.append("very_still")
    return issues


def _time_is_in_windows(t_sec: float, windows: List[Dict[str, Any]]) -> bool:
    """Return True if ``t_sec`` falls inside any ``[start_sec, end_sec]`` window.
    When ``windows`` is empty, defaults to True (no filtering) so the pipeline
    is backward-compatible with uploads that don't ship windows (e.g. Video
    Analysis tab) — we keep the old behaviour there."""
    if not windows:
        return True
    for w in windows:
        try:
            if float(w["start_sec"]) <= t_sec <= float(w["end_sec"]):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def detect_lacking_intervals(
    frames_data: List[Dict[str, Any]],
    audio_duration_sec: float,
    gesture_label: str,
    answer_windows: Optional[List[Dict[str, Any]]] = None,
) -> List[LackingInterval]:
    """
    Group consecutive frames that share at least one issue into intervals.

    frames_data rows come from `behavior_analysis.merge_per_frame_signals` and
    include `frame`, `emotion` (mapped), `posture`, and optional `eye_contact`.

    ``answer_windows`` (optional) is a list of ``{start_sec, end_sec,
    question_idx}`` ranges from the LiveInterview frontend indicating when the
    candidate was actually answering (i.e. not listening to the TTS / reading
    the question). During non-answering periods, the eye-contact check is
    skipped — otherwise the system would unfairly flag the candidate for
    looking at the question text on screen.
    """
    if not frames_data:
        return []

    total_frames = len(frames_data)
    per_frame_sec = (float(audio_duration_sec) / total_frames) if audio_duration_sec > 0 else 1.0
    gesture_lower = (gesture_label or "").lower()
    answer_windows = answer_windows or []

    current_issues: List[str] = []
    current_start_idx: Optional[int] = None
    intervals: List[LackingInterval] = []

    def flush(end_idx: int) -> None:
        if current_start_idx is None or not current_issues:
            return
        start_sec = round(current_start_idx * per_frame_sec, 2)
        end_sec = round((end_idx + 1) * per_frame_sec, 2)
        start_frame = int(frames_data[current_start_idx].get("frame", current_start_idx + 1))
        end_frame = int(frames_data[end_idx].get("frame", end_idx + 1))
        n_issues = len(current_issues)
        duration = end_sec - start_sec
        if n_issues >= 3 or duration >= 8.0:
            severity = "severe"
        elif n_issues == 2 or duration >= 4.0:
            severity = "moderate"
        else:
            severity = "minor"

        # Pick up to 3 representative frames: start, middle, end (dedup).
        idxs = sorted({current_start_idx, (current_start_idx + end_idx) // 2, end_idx})
        frame_paths: List[str] = []
        for ix in idxs:
            if 0 <= ix < len(frames_data):
                p = frames_data[ix].get("path")
                if p and p not in frame_paths:
                    frame_paths.append(str(p))

        intervals.append(LackingInterval(
            start_sec=start_sec,
            end_sec=end_sec,
            start_frame=start_frame,
            end_frame=end_frame,
            issues=list(current_issues),
            severity=severity,
            frame_paths=frame_paths,
        ))

    for i, row in enumerate(frames_data):
        mapped_emotion = str(row.get("emotion", "calm"))
        posture_label = str(row.get("posture", "bad"))
        eye = row.get("eye_contact")
        frame_t = i * per_frame_sec
        is_answering = _time_is_in_windows(frame_t, answer_windows)
        issues = _issues_for_frame(mapped_emotion, posture_label, eye, gesture_lower, is_answering)

        if issues:
            if current_start_idx is None:
                current_start_idx = i
                current_issues = list(issues)
            else:
                # merge new issues into the same interval if any overlap or adjacency
                for iss in issues:
                    if iss not in current_issues:
                        current_issues.append(iss)
        else:
            if current_start_idx is not None:
                flush(i - 1)
                current_start_idx = None
                current_issues = []

    if current_start_idx is not None:
        flush(total_frames - 1)

    return intervals


# ======================================================================
# 5) Recommendation tier
# ======================================================================


def build_recommendation(
    total_0_100: float,
    domain: str,
    cert_score: CertificationScoreResult,
    answer_score: AnswerScoreResult,
    behavior_score: BehaviorScoreResult,
    insufficient: bool,
) -> Recommendation:
    if insufficient:
        return Recommendation(
            tier="not_recommended",
            label="Not Recommended",
            summary="No audible candidate response was captured. A hiring decision "
                    "cannot be made until the candidate re-records with a working "
                    "microphone and provides substantive answers.",
            total_score_0_100=round(total_0_100, 2),
        )

    if total_0_100 >= 90:
        tier, label = "strong_hire", "Strong Hire"
        verdict = f"Excellent fit for the {domain} role — strong domain knowledge, solid credentials, and composed delivery."
    elif total_0_100 >= 75:
        tier, label = "hire", "Hire"
        verdict = f"Good candidate for the {domain} role. Minor gaps can be addressed during onboarding."
    elif total_0_100 >= 60:
        tier, label = "borderline", "Borderline / Needs Follow-up"
        verdict = f"Partial fit for the {domain} role. Recommend a second interview focused on the weak areas below."
    else:
        tier, label = "not_recommended", "Not Recommended"
        verdict = f"Does not meet the bar for the {domain} role in this interview; domain knowledge and/or delivery need significant improvement."

    summary = (
        f"{verdict} Answers: {answer_score.total_0_60:.1f}/60 "
        f"(avg {answer_score.average_relevance_0_10:.1f}/10). "
        f"Certifications: {cert_score.total_0_20:.1f}/20. "
        f"Behavior: {behavior_score.total_0_20:.1f}/20."
    )

    return Recommendation(
        tier=tier,
        label=label,
        summary=summary,
        total_score_0_100=round(total_0_100, 2),
    )


# ======================================================================
# Orchestration
# ======================================================================


def compute_final_scoring(
    *,
    questions: Any,
    resume_context: Dict[str, Any],
    speech: Dict[str, Any],
    emotion: Dict[str, Any],
    body: Dict[str, Any],
    behavior_insights: Dict[str, Any],
    frames_data: List[Dict[str, Any]],
    answer_windows: Optional[List[Dict[str, Any]]] = None,
) -> FinalScoring:
    """
    Single entry-point. Takes all raw pipeline outputs + resume context and
    produces a DB-ready FinalScoring record.
    """
    domain = str((resume_context or {}).get("domain") or "General").strip() or "General"
    certifications = (resume_context or {}).get("certifications") or []
    insufficient = bool(speech.get("insufficient_candidate_speech")) \
                   or speech.get("candidate_speech_detected") is False

    raw_transcript = str(speech.get("transcript") or "")
    formatted_transcript = speech.get("formatted_transcript") or []

    answer_result = compute_answer_scoring(
        questions=questions,
        formatted_transcript=formatted_transcript,
        raw_transcript=raw_transcript,
        domain=domain,
        insufficient=insufficient,
    )
    cert_result = compute_certification_scoring(
        certifications=certifications,
        domain=domain,
        answers_total_0_60=answer_result.total_0_60,
    )
    behavior_result = compute_behavior_scoring(
        emotion=emotion,
        body=body,
        speech=speech,
        behavior_insights=behavior_insights,
    )

    total = round(cert_result.total_0_20 + answer_result.total_0_60 + behavior_result.total_0_20, 2)

    intervals = detect_lacking_intervals(
        frames_data=frames_data,
        audio_duration_sec=_safe_float(speech.get("audio_duration_seconds"), 0.0),
        gesture_label=str(body.get("gesture_label") or ""),
        answer_windows=answer_windows or [],
    )

    recommendation = build_recommendation(
        total_0_100=total,
        domain=domain,
        cert_score=cert_result,
        answer_score=answer_result,
        behavior_score=behavior_result,
        insufficient=insufficient,
    )

    return FinalScoring(
        total_0_100=total,
        certification_score=cert_result,
        answer_score=answer_result,
        behavior_score=behavior_result,
        interview_notes=list(answer_result.per_question),
        lacking_intervals=intervals,
        recommendation=recommendation,
        domain=domain,
    )


def final_scoring_to_dict(fs: FinalScoring) -> Dict[str, Any]:
    """Serialize FinalScoring to a plain nested dict (DB/JSON ready)."""
    return asdict(fs)
