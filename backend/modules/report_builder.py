import html
import json
from datetime import datetime
from pathlib import Path


def _safe_get(d, key, default=None):
    return d.get(key) if isinstance(d, dict) else default


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

    # Build detailed recommendation HTML
    recommendation_html = ""
    if recommendation.get("label"):
        rec_bg = "#dcfce7" if recommendation.get("recommended") else "#fef3c7"
        rec_border = "#22c55e" if recommendation.get("recommended") else "#f59e0b"
        recommendation_html = f'<div class="card" style="margin-bottom: 24px; padding: 20px; background: {rec_bg}; border: 2px solid {rec_border}; border-radius: 12px;">'
        recommendation_html += f'<strong style="font-size: 18px;">{"✅ Recommended" if recommendation.get("recommended") else "⚠️ Not Recommended"}</strong>'
        if recommendation.get("summary"):
            recommendation_html += f'<p style="margin-top: 8px; color: #374151; font-weight: 500;">{html.escape(recommendation.get("summary", ""))}</p>'
        if recommendation.get("reason"):
            recommendation_html += f'<p style="margin-top: 4px; color: #4b5563; font-size: 14px;">{html.escape(recommendation.get("reason", ""))}</p>'
        strengths = recommendation.get("strengths") or []
        if strengths:
            recommendation_html += '<h4 style="margin-top: 16px; font-size: 12px; color: #059669; text-transform: uppercase; letter-spacing: 0.05em;">Strengths</h4><ul style="margin: 8px 0 0 16px; padding: 0;">'
            for s in strengths:
                score_str = ""
                if s.get("score") is not None:
                    if s.get("metric") == "Speaking pace":
                        score_str = f" ({s['score']:.0f} WPM)"
                    elif s.get("metric") == "Filler words":
                        score_str = f" ({s['score']} detected)"
                    else:
                        score_str = f" ({s['score']}/10)"
                recommendation_html += f'<li style="margin-bottom: 6px; color: #374151;"><strong>{html.escape(s.get("metric", ""))}</strong>{score_str}: {html.escape(s.get("feedback", ""))}</li>'
            recommendation_html += "</ul>"
        areas = recommendation.get("areas_to_improve") or []
        if areas:
            recommendation_html += '<h4 style="margin-top: 16px; font-size: 12px; color: #d97706; text-transform: uppercase; letter-spacing: 0.05em;">Areas to Improve</h4><ul style="margin: 8px 0 0 16px; padding: 0;">'
            for a in areas:
                score_str = ""
                if a.get("score") is not None:
                    if a.get("metric") == "Speaking pace":
                        score_str = f" ({a['score']:.0f} WPM)"
                    elif a.get("metric") == "Filler words":
                        score_str = f" ({a['score']} detected)"
                    else:
                        score_str = f" ({a['score']}/10)"
                recommendation_html += f'<li style="margin-bottom: 8px; color: #374151;"><strong>{html.escape(a.get("metric", ""))}</strong>{score_str}: {html.escape(a.get("feedback", ""))}'
                if a.get("suggestion"):
                    recommendation_html += f'<p style="margin: 4px 0 0 12px; font-size: 13px; color: #6b7280; font-style: italic; border-left: 2px solid #f59e0b; padding-left: 8px;">💡 {html.escape(a.get("suggestion", ""))}</p>'
                recommendation_html += "</li>"
            recommendation_html += "</ul>"
        recommendation_html += "</div>"

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

    <!-- Recommendation -->
    {recommendation_html}

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
