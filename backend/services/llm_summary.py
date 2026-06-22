"""
LLM-powered hiring-manager summary of an interview report.

Given the raw report from `video_processor.process_video` and the job context,
produces a compact JSON payload:

    {
      "strengths":   [str, ...],       # 3-5 short bullets
      "concerns":    [str, ...],       # 3-5 short bullets
      "recommendation": "SHORTLIST" | "REVIEW" | "REJECT",
      "headline": str,                  # 1-sentence human summary
      "quotes": [{"question_idx": int, "text": str}, ...],  # pulled from transcript, optional
      "score_rationale": str            # 1-2 sentences explaining the score
    }

Failures (no API key, bad response, timeout) return None — the decision engine
uses thresholds regardless, so a missing summary never blocks decisioning.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger("interveux.llm_summary")

MODEL = os.getenv("OPENAI_SUMMARY_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
TIMEOUT_S = int(os.getenv("OPENAI_SUMMARY_TIMEOUT_S", "25"))


def _safe_truncate(obj: Any, max_len: int) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str) if not isinstance(obj, str) else obj
    if len(s) <= max_len:
        return s
    return s[:max_len] + "...[truncated]"


def _get_client():
    try:
        from openai import OpenAI
    except Exception:  # pragma: no cover
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _build_prompt(report: dict, job_title: str, job_skills: list[str]) -> str:
    transcript = report.get("transcript") or report.get("speech_analysis", {}).get("transcript") or ""
    scoring = report.get("scoring") or {}
    behavior = {
        k: report.get(k)
        for k in ("confidence_score", "eye_contact_score", "trend", "feedback")
        if report.get(k) is not None
    }
    questions = report.get("questions") or []

    payload = {
        "job_title": job_title,
        "required_skills": job_skills[:20],
        "scoring_summary": {
            "total_0_100": scoring.get("total_0_100"),
            "recommendation": scoring.get("recommendation"),
            "domain": scoring.get("domain"),
        },
        "behavior": behavior,
        "questions": [
            {"idx": i, "question": (q.get("question") or q) if isinstance(q, (dict, str)) else str(q)}
            for i, q in enumerate(questions[:10])
        ],
        "transcript_excerpt": _safe_truncate(transcript, 6000),
    }
    return (
        "You are a senior hiring manager writing an internal evaluation. "
        "Review the evidence below and return STRICT JSON with keys: "
        "strengths (list[str]), concerns (list[str]), recommendation "
        "('SHORTLIST' | 'REVIEW' | 'REJECT'), headline (1 sentence), "
        "score_rationale (1-2 sentences). Be specific, cite skills or behaviors "
        "from the evidence, no fluff, no markdown.\n\n"
        f"EVIDENCE:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def generate_summary(report: dict, job_title: str, job_skills: Optional[list[str]] = None) -> Optional[dict]:
    """Return the summary dict or None if the LLM path fails."""
    if not report:
        return None
    client = _get_client()
    if client is None:
        log.info("LLM summary skipped: no client/API key")
        return None

    prompt = _build_prompt(report, job_title, job_skills or [])

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You output strictly valid JSON. No prose, no code fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            timeout=TIMEOUT_S,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
    except Exception as e:
        log.warning("LLM summary failed: %s", e)
        return None

    # Shape-check: always return the canonical keys even if model omitted some.
    def _as_list(v):
        return v if isinstance(v, list) else ([v] if v else [])

    rec = str(data.get("recommendation", "REVIEW")).upper()
    if rec not in {"SHORTLIST", "REVIEW", "REJECT"}:
        rec = "REVIEW"

    return {
        "strengths": [str(s)[:280] for s in _as_list(data.get("strengths"))][:6],
        "concerns": [str(s)[:280] for s in _as_list(data.get("concerns"))][:6],
        "recommendation": rec,
        "headline": str(data.get("headline", ""))[:500],
        "score_rationale": str(data.get("score_rationale", ""))[:500],
        "source": "llm",
    }


def build_fallback_summary(report: dict, job_title: str) -> dict:
    """Deterministic summary from scoring data when the LLM path is unavailable."""
    scoring = report.get("scoring") or {}
    total = scoring.get("total_0_100")
    rec = str(scoring.get("recommendation") or "REVIEW").upper()
    if rec not in {"SHORTLIST", "REVIEW", "REJECT"}:
        rec = "REVIEW"

    answer_block = report.get("answer_score") or scoring.get("answer_score") or {}
    per_q = answer_block.get("per_question") if isinstance(answer_block, dict) else []
    per_q = per_q or []

    strengths: list[str] = []
    concerns: list[str] = []
    for q in per_q:
        if not isinstance(q, dict):
            continue
        score = float(q.get("answer_score_0_10") or 0)
        evaluation = str(q.get("evaluation") or "").strip()
        if not evaluation:
            continue
        if score >= 7:
            strengths.append(evaluation[:280])
        elif score < 6:
            concerns.append(evaluation[:280])

    if not strengths and per_q:
        strengths.append("Candidate completed all interview questions.")
    if not concerns and total is not None and total < 60:
        concerns.append(f"Overall score ({total:.1f}/100) is below typical shortlist range.")

    headline = f"Interview summary for {job_title}."
    if total is not None:
        headline = f"Overall score {total:.1f}/100 for {job_title}."

    domain = scoring.get("domain") if isinstance(scoring.get("domain"), dict) else {}
    rationale = domain.get("rationale") or scoring.get("score_rationale")
    if not rationale and total is not None:
        rationale = f"Composite score {total:.1f}/100 from speech, behavior, and answer analysis."

    return {
        "strengths": strengths[:6],
        "concerns": concerns[:6],
        "recommendation": rec,
        "headline": headline[:500],
        "score_rationale": str(rationale or "")[:500],
        "source": "fallback",
    }


def ensure_report_summary(
    report_row: Any,
    job_title: str,
    job_skills: Optional[list[str]] = None,
    *,
    force: bool = False,
) -> dict:
    """
    Populate ``report_row.ai_summary`` via LLM, falling back to rule-based text.
    Returns the summary dict (existing or newly written).
    """
    if report_row.ai_summary and not force:
        return report_row.ai_summary

    raw = report_row.raw_report or {}
    summary = generate_summary(raw, job_title, job_skills or [])
    if not summary:
        summary = build_fallback_summary(raw, job_title)

    report_row.ai_summary = summary
    return summary
