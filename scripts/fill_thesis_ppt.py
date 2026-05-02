from pathlib import Path

from pptx import Presentation


def set_title_and_subtitle(prs: Presentation) -> None:
    slide = prs.slides[0]
    slide.shapes.title.text = "Interveux: AI-Powered Mock Interview Assessment System"
    subtitle = slide.placeholders[1].text_frame
    subtitle.clear()
    subtitle.paragraphs[0].text = "Final Year Project (FYP) Thesis Presentation"
    subtitle.add_paragraph().text = "Student Name: Rameez"
    subtitle.add_paragraph().text = "Department of Information Technology"


def set_background(prs: Presentation) -> None:
    slide = prs.slides[1]
    body = slide.placeholders[1].text_frame
    body.clear()
    points = [
        "Conventional interviews are time-intensive, subjective, and inconsistent across different interviewers.",
        "Early-stage screening becomes difficult when HR teams handle many applicants with limited time.",
        "Remote hiring introduces additional challenges: low engagement, weak proctoring, and delayed feedback.",
        "Interveux addresses this gap by automating interview capture, multimodal analysis, and structured candidate scoring.",
    ]
    body.paragraphs[0].text = points[0]
    for point in points[1:]:
        body.add_paragraph().text = point


def set_significance(prs: Presentation) -> None:
    slide = prs.slides[2]
    # Slide 3 has a title and free-form content area; add textbox text if empty.
    body_shape = None
    for shape in slide.shapes:
        if shape.has_text_frame and shape != slide.shapes.title:
            body_shape = shape
            break
    if body_shape is None:
        return
    tf = body_shape.text_frame
    tf.clear()
    points = [
        "Provides standardized, data-backed screening through speech, emotion, posture, and integrity signals.",
        "Reduces manual effort using automatic shortlist/reject/review decision policies with audit logs.",
        "Improves transparency with report generation (JSON + HTML), score breakdowns, and explainable outcomes.",
        "Enables scalable digital interviews with candidate self-service flow, progress tracking, and asynchronous processing.",
    ]
    tf.paragraphs[0].text = points[0]
    for point in points[1:]:
        tf.add_paragraph().text = point


def set_objectives(prs: Presentation) -> None:
    slide = prs.slides[3]
    tf = slide.placeholders[1].text_frame
    tf.clear()
    points = [
        "Design an end-to-end platform for candidate invitation, resume upload, interview recording, and result delivery.",
        "Develop a multimodal analysis pipeline combining speech quality, facial emotion, body language, and eye contact.",
        "Compute a unified score and recommendation to support fair shortlisting decisions.",
        "Implement an HR dashboard with session lifecycle tracking, reports, and manual decision override support.",
    ]
    tf.paragraphs[0].text = points[0]
    for point in points[1:]:
        tf.add_paragraph().text = point


def set_research_questions(prs: Presentation) -> None:
    slide = prs.slides[4]
    tf = slide.placeholders[1].text_frame
    tf.clear()
    questions = [
        "How effectively can multimodal interview signals be fused into a reliable candidate assessment score?",
        "Can an automated decision engine reduce HR workload while preserving decision quality and auditability?",
        "What practical speed vs. accuracy trade-offs are required for real-time or near-real-time interview analysis?",
        "How can integrity signals (tab switch, face mismatch, no-face) improve trust in remote interview outcomes?",
    ]
    tf.paragraphs[0].text = questions[0]
    for q in questions[1:]:
        tf.add_paragraph().text = q


def set_framework(prs: Presentation) -> None:
    slide = prs.slides[5]
    tf = slide.placeholders[1].text_frame
    tf.clear()
    lines = [
        "Input Layer: Resume (PDF), Recorded Interview Video, Job Configuration.",
        "Processing Layer: Resume parsing + LLM question generation, frame/audio extraction.",
        "Analysis Layer: Whisper (speech), ViT emotion classifier, MediaPipe pose + eye contact.",
        "Scoring Layer: Feature fusion + weighted scoring + pass/fail recommendation.",
        "Decision Layer: Threshold-based auto decision (Shortlisted/Rejected/Review) with integrity-policy checks.",
        "Output Layer: HR dashboard insights, downloadable reports, candidate outcome notifications.",
    ]
    tf.paragraphs[0].text = lines[0]
    for line in lines[1:]:
        tf.add_paragraph().text = line


def set_methodology(prs: Presentation) -> None:
    slide = prs.slides[6]
    tf = slide.placeholders[1].text_frame
    tf.clear()
    steps = [
        "Research Design: Applied system-development methodology for AI-assisted recruitment.",
        "Tech Stack: FastAPI + SQLAlchemy backend, React frontend, OpenAI + Hugging Face + MediaPipe models.",
        "Pipeline: Invite candidate -> collect resume/video -> run background analysis -> generate reports.",
        "Evaluation: Validate model outputs, overall scoring behavior, decision thresholds, and usability flow.",
        "Limitations & Controls: CPU latency, model confidence variance, and fallback handling for missing signals.",
    ]
    tf.paragraphs[0].text = steps[0]
    for step in steps[1:]:
        tf.add_paragraph().text = step


def fill_presentation(template_path: Path, output_path: Path) -> None:
    prs = Presentation(str(template_path))
    if len(prs.slides) < 7:
        raise ValueError("Template must contain at least 7 slides.")

    set_title_and_subtitle(prs)
    set_background(prs)
    set_significance(prs)
    set_objectives(prs)
    set_research_questions(prs)
    set_framework(prs)
    set_methodology(prs)

    prs.save(str(output_path))


if __name__ == "__main__":
    template = Path(r"C:\Users\RAMEEZ\OneDrive\Desktop\FYP (Thesis) - Presentation Template.pptx")
    output = Path(r"C:\Users\RAMEEZ\OneDrive\Desktop\FYP (Thesis) - Presentation Template - Interveux Filled.pptx")
    fill_presentation(template, output)
    print(f"Saved: {output}")
