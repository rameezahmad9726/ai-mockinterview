import html
import json
from datetime import datetime
from pathlib import Path


def _safe_get(d, key, default=None):
    return d.get(key) if isinstance(d, dict) else default


_TIER_STYLE = {
    "strong_hire":     {"bg": "#dcfce7", "border": "#16a34a", "emoji": "🌟", "text": "#065f46"},
    "hire":            {"bg": "#ecfdf5", "border": "#22c55e", "emoji": "✅", "text": "#065f46"},
    "borderline":      {"bg": "#fef3c7", "border": "#f59e0b", "emoji": "⚠️", "text": "#92400e"},
    "not_recommended": {"bg": "#fee2e2", "border": "#ef4444", "emoji": "❌", "text": "#991b1b"},
}


def _issue_label(issue: str) -> str:
    return {
        "low_eye_contact": "low eye contact",
        "poor_posture": "poor posture",
        "low_confidence": "low confidence",
        "excessive_movement": "excessive movement",
        "very_still": "very still / stiff",
    }.get(issue, issue.replace("_", " "))


def _fmt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m:02d}:{s:02d}"


def _build_scoring_html(scoring: dict, recommendation: dict) -> str:
    if not scoring:
        return ""
    total = scoring.get("total_0_100")
    rec = scoring.get("recommendation") or recommendation or {}
    tier = rec.get("tier") or "borderline"
    style = _TIER_STYLE.get(tier, _TIER_STYLE["borderline"])

    cert = scoring.get("certification_score") or {}
    ans = scoring.get("answer_score") or {}
    beh = scoring.get("behavior_score") or {}
    domain = scoring.get("domain") or "General"

    def bar(value, max_value, color):
        pct = 0 if not max_value else max(0.0, min(1.0, float(value) / float(max_value))) * 100.0
        return (
            f'<div style="background:#e5e7eb;border-radius:999px;height:10px;overflow:hidden;margin-top:4px;">'
            f'<div style="width:{pct:.1f}%;height:100%;background:{color};"></div></div>'
        )

    header = (
        f'<div class="card" style="padding:22px;background:{style["bg"]};border:2px solid {style["border"]};'
        f'border-radius:14px;margin-bottom:24px;">'
        f'<div style="display:flex;align-items:flex-start;gap:14px;">'
        f'<div style="font-size:36px;line-height:1;">{style["emoji"]}</div>'
        f'<div style="flex:1;">'
        f'<div style="font-size:22px;font-weight:700;color:{style["text"]};">'
        f'{html.escape(rec.get("label", "Result"))}'
        f' &nbsp;<span style="font-size:14px;font-weight:500;color:#374151;">'
        f'Domain: {html.escape(str(domain))}</span></div>'
        f'<div style="font-size:40px;font-weight:800;color:{style["text"]};margin-top:4px;">'
        f'{total if total is not None else "—"}<span style="font-size:18px;color:#6b7280;">/100</span></div>'
        f'<p style="margin-top:6px;color:#374151;font-size:14px;line-height:1.5;">'
        f'{html.escape(rec.get("summary", ""))}</p>'
        f'</div></div>'
    )

    def row(title, value, max_v, color, rationale):
        return (
            f'<div style="padding:12px 14px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<strong style="color:#111827;font-size:14px;">{title}</strong>'
            f'<span style="font-weight:700;color:#111827;">{value:.1f}/{max_v}</span></div>'
            f'{bar(value, max_v, color)}'
            f'<p style="margin:6px 0 0 0;color:#6b7280;font-size:12px;line-height:1.5;">'
            f'{html.escape(rationale or "")}</p>'
            f'</div>'
        )

    rows = (
        row("Candidate Answers (Domain Knowledge)",
            ans.get("total_0_60", 0.0), 60, "#2563eb", ans.get("rationale", ""))
        + row("Behavior & Emotions",
              beh.get("total_0_20", 0.0), 20, "#8b5cf6", beh.get("rationale", ""))
        + row("Certifications",
              cert.get("total_0_20", 0.0), 20, "#0ea5e9", cert.get("rationale", ""))
    )

    breakdown = (
        f'<div style="display:grid;gap:10px;margin-top:14px;">{rows}</div>'
        f'</div>'  # closes header card
    )
    return header + breakdown


def _build_interview_notes_html(notes: list) -> str:
    if not notes:
        return ""
    items = []
    for n in notes:
        score = n.get("answer_score_0_10", 0.0)
        bg = "#ecfdf5" if score >= 7 else "#fef3c7" if score >= 4 else "#fee2e2"
        qtype = n.get("question_type", "General")
        items.append(
            f'<div style="padding:14px 16px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div><span style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;color:#6b7280;">'
            f'Q{n.get("question_idx", 0) + 1} · {html.escape(str(qtype))}</span>'
            f'<div style="font-weight:600;color:#111827;margin-top:2px;">{html.escape(n.get("question", ""))}</div></div>'
            f'<span style="background:{bg};padding:4px 10px;border-radius:999px;font-weight:700;color:#111827;">'
            f'{score:.1f}/10</span></div>'
            f'<div style="margin-top:10px;padding:10px 12px;background:#f9fafb;border-left:3px solid #60a5fa;'
            f'border-radius:6px;color:#1f2937;font-size:13px;white-space:pre-wrap;">'
            f'{html.escape(n.get("candidate_answer", ""))}</div>'
            f'<p style="margin:8px 0 0 0;color:#6b7280;font-size:12px;line-height:1.5;"><em>'
            f'{html.escape(n.get("evaluation", ""))}</em></p>'
            f'</div>'
        )
    return (
        '<h2>Interview Notes</h2>'
        '<p class="subtitle">Candidate answer per scheduled question with evaluation.</p>'
        + "".join(items)
    )


def _build_lacking_intervals_html(intervals: list) -> str:
    if not intervals:
        return (
            '<h2>Moments to Improve</h2>'
            '<p class="subtitle" style="color:#059669;">No significant weak intervals detected during the recording.</p>'
        )
    sev_color = {"minor": "#f59e0b", "moderate": "#ea580c", "severe": "#dc2626"}
    rows = []
    for iv in intervals:
        color = sev_color.get(iv.get("severity", "minor"), "#f59e0b")
        issues = ", ".join(_issue_label(i) for i in (iv.get("issues") or []))
        frame_urls = iv.get("frame_paths") or []
        thumbs_html = ""
        if frame_urls:
            thumb_imgs = "".join(
                f'<img src="{html.escape(url)}" alt="lacking frame" '
                f'style="width:110px;height:82px;object-fit:cover;border-radius:6px;'
                f'border:1px solid #e5e7eb;background:#f3f4f6;" loading="lazy" />'
                for url in frame_urls
            )
            thumbs_html = (
                f'<div style="display:flex;gap:6px;flex-wrap:wrap;">{thumb_imgs}</div>'
            )
        else:
            thumbs_html = '<span style="color:#9ca3af;font-size:12px;">—</span>'

        rows.append(
            f'<tr>'
            f'<td>{_fmt_time(iv.get("start_sec", 0))} – {_fmt_time(iv.get("end_sec", 0))}</td>'
            f'<td>{iv.get("start_frame", 0)} – {iv.get("end_frame", 0)}</td>'
            f'<td>{html.escape(issues)}</td>'
            f'<td>{thumbs_html}</td>'
            f'<td><span style="background:{color};color:#fff;padding:2px 10px;border-radius:999px;'
            f'font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">{html.escape(iv.get("severity","minor"))}</span></td>'
            f'</tr>'
        )
    return (
        '<h2>Moments to Improve</h2>'
        '<p class="subtitle">Timestamps / frame ranges where the candidate showed weak signals.</p>'
        '<div class="table-wrapper"><table>'
        '<thead><tr><th>Time</th><th>Frames</th><th>Issues</th><th>Preview</th><th>Severity</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></div>'
    )


def _build_transcript_html(speech):
    """Build HTML for transcript with speaker separation if available."""
    formatted_transcript = _safe_get(speech, "formatted_transcript", [])
    
    if formatted_transcript and isinstance(formatted_transcript, list):
        # Build speaker-separated transcript
        transcript_html = '<div style="background: #f9fafb; padding: 16px; border-radius: 8px; max-height: 500px; overflow-y: auto;">'
        
        for segment in formatted_transcript:
            speaker = segment.get("speaker", "Unknown")
            text = html.escape(segment.get("text", ""))
            
            # Different styling for interviewer vs interviewee
            if speaker == "Interviewer":
                bg_color = "#dbeafe"
                text_color = "#1e40af"
                label_color = "#1e3a8a"
            else:
                bg_color = "#dcfce7"
                text_color = "#166534"
                label_color = "#14532d"
            
            transcript_html += f'''
                <div style="margin-bottom: 12px;">
                    <div style="font-weight: 600; font-size: 12px; color: {label_color}; margin-bottom: 4px;">
                        {speaker}
                    </div>
                    <div style="background: {bg_color}; color: {text_color}; padding: 10px 14px; border-radius: 8px; font-size: 14px; line-height: 1.6;">
                        {text}
                    </div>
                </div>
            '''
        
        transcript_html += '</div>'
        return transcript_html
    else:
        # Fallback to plain transcript
        transcript = _safe_get(speech, "transcript", "")
        transcript_escaped = html.escape(transcript) if transcript else "[No transcript]"
        return f'<pre>{transcript_escaped}</pre>'


def build_html_report(report: dict) -> str:
    """
    Take the full analysis report (same structure as video_processor output)
    and return an HTML string.
    """

    emotion = _safe_get(report, "emotion_analysis", {})
    body = _safe_get(report, "body_language", {})
    speech = _safe_get(report, "speech_analysis", {})
    summary = _safe_get(report, "final_summary", {})

    dominant_emotion = _safe_get(summary, "dominant_emotion", "N/A")
    gesture_label = _safe_get(summary, "gesture_label", "N/A")
    posture_score = _safe_get(summary, "posture_score", "N/A")
    movement_score = _safe_get(summary, "movement_score", "N/A")
    # When insufficient candidate speech, these can be None - show N/A
    _sw = summary.get("speaking_speed_wpm")
    speaking_speed = "N/A" if _sw is None else _sw
    _cs = summary.get("clarity_score")
    clarity_score = "N/A" if _cs is None else _cs
    _cf = summary.get("confidence_score")
    confidence_score = "N/A" if _cf is None else _cf
    recommendation = _safe_get(summary, "recommendation", {})
    scoring = _safe_get(report, "scoring", {}) or {}

    frames_analyzed = _safe_get(emotion, "frames_analyzed", 0)
    emotion_counts = _safe_get(emotion, "emotion_counts", {})

    audio_duration = _safe_get(speech, "audio_duration_seconds", "N/A")
    word_count = _safe_get(speech, "word_count", "N/A")
    transcript = _safe_get(speech, "transcript", "")

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Simple emotion counts table rows
    emotion_rows = ""
    for emo, count in emotion_counts.items():
        emotion_rows += f"""
            <tr>
                <td>{html.escape(str(emo))}</td>
                <td>{count}</td>
            </tr>
        """

    # Escape transcript for HTML
    transcript_html = html.escape(transcript) if transcript else "[No transcript]"

    # Pretty JSON block (optional, for debugging)
    pretty_json = html.escape(json.dumps(report, indent=2, ensure_ascii=False))

    # ------- New scoring-based recommendation + breakdown -------
    recommendation_html = _build_scoring_html(scoring, recommendation)
    notes_html = _build_interview_notes_html(scoring.get("interview_notes") or [])
    lacking_html = _build_lacking_intervals_html(scoring.get("lacking_intervals") or [])

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Interview Analysis Report</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f5f5f7;
            margin: 0;
            padding: 0;
            color: #111827;
        }}
        .container {{
            max-width: 960px;
            margin: 32px auto;
            padding: 24px 28px 32px;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 18px 40px rgba(15,23,42,0.08);
        }}
        h1 {{
            font-size: 28px;
            margin-bottom: 4px;
        }}
        h2 {{
            font-size: 20px;
            margin-top: 28px;
            margin-bottom: 10px;
        }}
        h3 {{
            font-size: 16px;
            margin-top: 18px;
            margin-bottom: 6px;
        }}
        .subtitle {{
            color: #6b7280;
            font-size: 14px;
            margin-bottom: 20px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            background: #eef2ff;
            color: #3730a3;
            font-weight: 500;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-top: 10px;
        }}
        .card {{
            border-radius: 12px;
            padding: 14px 16px;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
        }}
        .card strong {{
            display: block;
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 3px;
        }}
        .card span {{
            font-size: 15px;
            font-weight: 600;
        }}
        .table-wrapper {{
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #e5e7eb;
            background: #f9fafb;
            margin-top: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            padding: 8px 10px;
            text-align: left;
        }}
        th {{
            background: #111827;
            color: #f9fafb;
            font-weight: 500;
        }}
        tr:nth-child(even) td {{
            background: #f3f4f6;
        }}
        .pill {{
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            background: #ecfdf3;
            color: #166534;
            font-weight: 500;
        }}
        .pill.neutral {{
            background: #eff6ff;
            color: #1d4ed8;
        }}
        .pill.warning {{
            background: #fffbeb;
            color: #92400e;
        }}
        .pill.danger {{
            background: #fef2f2;
            color: #b91c1c;
        }}
        details {{
            margin-top: 8px;
        }}
        summary {{
            cursor: pointer;
            font-size: 14px;
            color: #2563eb;
        }}
        pre {{
            font-size: 13px;
            background: #0b1120;
            color: #e5e7eb;
            padding: 12px 14px;
            border-radius: 8px;
            overflow-x: auto;
        }}
        .footer {{
            margin-top: 26px;
            font-size: 12px;
            color: #9ca3af;
            text-align: right;
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>Interview Analysis Report</h1>
    <div class="subtitle">
        Generated on <strong>{created_at}</strong>
    </div>

    <!-- Recommendation + scoring breakdown -->
    {recommendation_html}

    <!-- Interview notes (Q/A/evaluation per question) -->
    {notes_html}

    <!-- Moments to improve (lacking frame intervals) -->
    {lacking_html}

    <!-- Overview -->
    <h2>Overview</h2>
    <div class="grid">
        <div class="card">
            <strong>Dominant Emotion</strong>
            <span>{html.escape(str(dominant_emotion))}</span>
        </div>
        <div class="card">
            <strong>Body Language</strong>
            <span>{html.escape(str(gesture_label))}</span>
        </div>
        <div class="card">
            <strong>Posture Score</strong>
            <span>{round(posture_score, 3) if isinstance(posture_score, (int, float)) else posture_score}</span>
        </div>
        <div class="card">
            <strong>Movement Score</strong>
            <span>{round(movement_score, 3) if isinstance(movement_score, (int, float)) else movement_score}</span>
        </div>
        <div class="card">
            <strong>Speaking Speed</strong>
            <span>{speaking_speed if speaking_speed == "N/A" else f"{speaking_speed} WPM"}</span>
        </div>
        <div class="card">
            <strong>Clarity / Confidence</strong>
            <span>{clarity_score} / {confidence_score}</span>
        </div>
    </div>

    <!-- Emotion Analysis -->
    <h2>Emotion Analysis</h2>
    <div class="grid">
        <div class="card">
            <strong>Frames Analyzed</strong>
            <span>{frames_analyzed}</span>
        </div>
        <div class="card">
            <strong>Dominant Emotion</strong>
            <span class="pill neutral">{html.escape(str(dominant_emotion))}</span>
        </div>
    </div>

    <h3>Emotion Distribution</h3>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>Emotion</th>
                    <th>Count</th>
                </tr>
            </thead>
            <tbody>
                {emotion_rows or "<tr><td colspan='2'>No emotion data available.</td></tr>"}
            </tbody>
        </table>
    </div>

    <!-- Body Language -->
    <h2>Body Language</h2>
    <div class="grid">
        <div class="card">
            <strong>Overall Gesture</strong>
            <span>{html.escape(str(gesture_label))}</span>
        </div>
        <div class="card">
            <strong>Posture Score</strong>
            <span>{round(posture_score, 3) if isinstance(posture_score, (int, float)) else posture_score}</span>
        </div>
        <div class="card">
            <strong>Movement Score</strong>
            <span>{round(movement_score, 3) if isinstance(movement_score, (int, float)) else movement_score}</span>
        </div>
        <div class="card">
            <strong>Total Frames (pose)</strong>
            <span>{_safe_get(body, "total_frames", "N/A")}</span>
        </div>
    </div>

    <!-- Speech Analysis -->
    <h2>Speech Analysis</h2>
    <div class="grid">
        <div class="card">
            <strong>Audio Duration</strong>
            <span>{round(audio_duration, 2) if isinstance(audio_duration, (int, float)) else audio_duration} sec</span>
        </div>
        <div class="card">
            <strong>Word Count</strong>
            <span>{word_count}</span>
        </div>
        <div class="card">
            <strong>Speaking Speed</strong>
            <span>{speaking_speed if speaking_speed == "N/A" else f"{speaking_speed} WPM"}</span>
        </div>
        <div class="card">
            <strong>Filler Words</strong>
            <span>{_safe_get(speech, "filler_words_count", 0)}</span>
        </div>
    </div>

    <h3>Transcript</h3>
    <details open>
        <summary>Show / hide transcript</summary>
        {_build_transcript_html(speech)}
    </details>

    <!-- Raw JSON (optional for debugging) -->
    <h2>Raw JSON (Debug)</h2>
    <details>
        <summary>Show raw JSON report</summary>
        <pre>{pretty_json}</pre>
    </details>

    <div class="footer">
        Generated by AI Mock Interview Analyzer
    </div>
</div>
</body>
</html>
"""
    return html_doc


def save_html_report(report: dict, output_path: Path) -> Path:
    """
    Build HTML and save to the given path.
    Returns the Path object.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_doc = build_html_report(report)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path
