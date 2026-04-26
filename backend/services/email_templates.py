"""
Plain-text + HTML email templates rendered with simple {placeholder} merging.

Keeping this dependency-free for now (no Jinja) so emails work on a fresh venv.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RenderedEmail:
    subject: str
    text: str
    html: str


def _render(template: str, **ctx: str) -> str:
    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


_INVITE_SUBJECT = "Interview invitation: {{job_title}} at {{company}}"

_INVITE_TEXT = """Hi {{candidate_name}},

{{company}} has invited you to complete a short video interview for the {{job_title}} role.

Start here (link expires {{expires_at}}):
{{interview_url}}

What to expect:
 - {{num_questions}} questions, ~{{seconds_per_answer}} seconds per answer.
 - Camera + microphone access required.
 - Your responses are analyzed automatically; you'll hear back from our team within a few days.

If the link doesn't work, paste it into your browser. Questions? Reply to this email.

-- The {{company}} Hiring Team
"""

_INVITE_HTML = """\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#1e293b; max-width:560px; margin:0 auto; padding:24px;">
  <h2 style="color:#4f46e5; margin-top:0;">Interview invitation</h2>
  <p>Hi {{candidate_name}},</p>
  <p><strong>{{company}}</strong> has invited you to complete a short video interview for the
  <strong>{{job_title}}</strong> role.</p>
  <p style="text-align:center; margin:28px 0;">
    <a href="{{interview_url}}" style="background:#4f46e5; color:#fff; padding:12px 22px; border-radius:8px; text-decoration:none; font-weight:600;">
      Start interview
    </a>
  </p>
  <p style="color:#475569; font-size:14px;">
    This link expires <strong>{{expires_at}}</strong>.<br>
    {{num_questions}} questions &middot; ~{{seconds_per_answer}} seconds per answer &middot; camera &amp; mic required.
  </p>
  <p style="color:#64748b; font-size:12px; margin-top:32px;">
    If the button doesn't work, paste this URL into your browser:<br>
    <span style="word-break:break-all;">{{interview_url}}</span>
  </p>
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:24px 0;">
  <p style="color:#94a3b8; font-size:12px;">-- The {{company}} Hiring Team</p>
</body>
</html>
"""


def render_invite(
    *,
    candidate_name: str,
    company: str,
    job_title: str,
    interview_url: str,
    expires_at: str,
    num_questions: int,
    seconds_per_answer: int,
) -> RenderedEmail:
    ctx = {
        "candidate_name": candidate_name or "there",
        "company": company,
        "job_title": job_title,
        "interview_url": interview_url,
        "expires_at": expires_at,
        "num_questions": str(num_questions),
        "seconds_per_answer": str(seconds_per_answer),
    }
    return RenderedEmail(
        subject=_render(_INVITE_SUBJECT, **ctx),
        text=_render(_INVITE_TEXT, **ctx),
        html=_render(_INVITE_HTML, **ctx),
    )


# ---------- Shortlist (positive outcome) ----------

_SHORTLIST_SUBJECT = "Next steps — {{job_title}} at {{company}}"

_SHORTLIST_TEXT = """Hi {{candidate_name}},

Thanks for completing your interview for the {{job_title}} role at {{company}}.
We were impressed with your responses and would like to move forward.

{{next_step_text}}

Looking forward to speaking with you soon.

-- The {{company}} Hiring Team
"""

_SHORTLIST_HTML = """\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#1e293b; max-width:560px; margin:0 auto; padding:24px;">
  <h2 style="color:#059669; margin-top:0;">Good news!</h2>
  <p>Hi {{candidate_name}},</p>
  <p>Thanks for completing your interview for the <strong>{{job_title}}</strong> role at
  <strong>{{company}}</strong>. We were impressed with your responses and would like to move forward.</p>
  {{next_step_html}}
  <p>Looking forward to speaking with you soon.</p>
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:24px 0;">
  <p style="color:#94a3b8; font-size:12px;">-- The {{company}} Hiring Team</p>
</body>
</html>
"""


def render_shortlist(
    *,
    candidate_name: str,
    company: str,
    job_title: str,
    calendly_url: Optional[str] = None,
) -> RenderedEmail:
    if calendly_url:
        next_text = f"Please pick a time that works for you: {calendly_url}"
        next_html = (
            f'<p style="text-align:center; margin:28px 0;">'
            f'<a href="{calendly_url}" style="background:#059669; color:#fff; padding:12px 22px; '
            f'border-radius:8px; text-decoration:none; font-weight:600;">Book your next interview</a>'
            f'</p>'
        )
    else:
        next_text = "Our hiring team will reach out shortly with next steps."
        next_html = f'<p>{next_text}</p>'

    ctx = {
        "candidate_name": candidate_name or "there",
        "company": company,
        "job_title": job_title,
        "next_step_text": next_text,
        "next_step_html": next_html,
    }
    return RenderedEmail(
        subject=_render(_SHORTLIST_SUBJECT, **ctx),
        text=_render(_SHORTLIST_TEXT, **ctx),
        html=_render(_SHORTLIST_HTML, **ctx),
    )


# ---------- Rejection (kind, non-specific) ----------

_REJECT_SUBJECT = "Update on your application — {{job_title}}"

_REJECT_TEXT = """Hi {{candidate_name}},

Thank you for taking the time to interview for the {{job_title}} role at {{company}}.
After careful review, we've decided to move forward with other candidates whose
experience more closely matches what we're looking for right now.

This was a competitive process and we genuinely appreciate your effort. We'll
keep your details on file and encourage you to apply again in the future.

Best of luck with your search.

-- The {{company}} Hiring Team
"""

_REJECT_HTML = """\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#1e293b; max-width:560px; margin:0 auto; padding:24px;">
  <h2 style="color:#475569; margin-top:0;">Update on your application</h2>
  <p>Hi {{candidate_name}},</p>
  <p>Thank you for taking the time to interview for the <strong>{{job_title}}</strong> role at
  <strong>{{company}}</strong>. After careful review, we've decided to move forward with
  other candidates whose experience more closely matches what we're looking for right now.</p>
  <p>This was a competitive process and we genuinely appreciate your effort. We'll keep
  your details on file and encourage you to apply again in the future.</p>
  <p>Best of luck with your search.</p>
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:24px 0;">
  <p style="color:#94a3b8; font-size:12px;">-- The {{company}} Hiring Team</p>
</body>
</html>
"""


def render_reject(
    *,
    candidate_name: str,
    company: str,
    job_title: str,
) -> RenderedEmail:
    ctx = {
        "candidate_name": candidate_name or "there",
        "company": company,
        "job_title": job_title,
    }
    return RenderedEmail(
        subject=_render(_REJECT_SUBJECT, **ctx),
        text=_render(_REJECT_TEXT, **ctx),
        html=_render(_REJECT_HTML, **ctx),
    )


# ---------- Reminder (before link expires) ----------

_REMINDER_SUBJECT = "Reminder: complete your {{job_title}} interview (expires {{expires_at}})"

_REMINDER_TEXT = """Hi {{candidate_name}},

A quick reminder that your interview link for the {{job_title}} role at {{company}}
expires on {{expires_at}}. It only takes a few minutes to complete.

Start here:
{{interview_url}}

-- The {{company}} Hiring Team
"""

_REMINDER_HTML = """\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#1e293b; max-width:560px; margin:0 auto; padding:24px;">
  <h2 style="color:#b45309; margin-top:0;">Your interview link is about to expire</h2>
  <p>Hi {{candidate_name}},</p>
  <p>A quick reminder that your interview link for the <strong>{{job_title}}</strong> role at
  <strong>{{company}}</strong> expires on <strong>{{expires_at}}</strong>.</p>
  <p style="text-align:center; margin:28px 0;">
    <a href="{{interview_url}}" style="background:#b45309; color:#fff; padding:12px 22px; border-radius:8px; text-decoration:none; font-weight:600;">
      Complete your interview
    </a>
  </p>
  <p style="color:#64748b; font-size:12px;">
    If the button doesn't work, paste this URL into your browser:<br>
    <span style="word-break:break-all;">{{interview_url}}</span>
  </p>
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:24px 0;">
  <p style="color:#94a3b8; font-size:12px;">-- The {{company}} Hiring Team</p>
</body>
</html>
"""


def render_reminder(
    *,
    candidate_name: str,
    company: str,
    job_title: str,
    interview_url: str,
    expires_at: str,
) -> RenderedEmail:
    ctx = {
        "candidate_name": candidate_name or "there",
        "company": company,
        "job_title": job_title,
        "interview_url": interview_url,
        "expires_at": expires_at,
    }
    return RenderedEmail(
        subject=_render(_REMINDER_SUBJECT, **ctx),
        text=_render(_REMINDER_TEXT, **ctx),
        html=_render(_REMINDER_HTML, **ctx),
    )


# ---------- HR daily digest ----------

_DIGEST_SUBJECT = "Interveux daily digest: {{new_shortlists}} shortlists, {{new_reviews}} need review"

_DIGEST_TEXT = """Hello,

Here is your hiring pipeline activity from the last 24 hours.

Shortlisted: {{new_shortlists}}
Need review: {{new_reviews}}
Rejected:    {{new_rejects}}
Submitted:   {{new_submits}}

{{digest_body_text}}

Open the HR dashboard: {{dashboard_url}}

-- Interveux
"""

_DIGEST_HTML = """\
<!doctype html>
<html>
<body style="font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#1e293b; max-width:640px; margin:0 auto; padding:24px;">
  <h2 style="color:#4f46e5; margin-top:0;">Daily digest</h2>
  <p>Here is your hiring pipeline activity from the last 24 hours.</p>
  <table style="width:100%; border-collapse:collapse; margin:16px 0;">
    <tr>
      <td style="padding:8px; border:1px solid #e2e8f0;"><strong>Shortlisted</strong></td>
      <td style="padding:8px; border:1px solid #e2e8f0; text-align:right;">{{new_shortlists}}</td>
      <td style="padding:8px; border:1px solid #e2e8f0;"><strong>Need review</strong></td>
      <td style="padding:8px; border:1px solid #e2e8f0; text-align:right;">{{new_reviews}}</td>
    </tr>
    <tr>
      <td style="padding:8px; border:1px solid #e2e8f0;"><strong>Rejected</strong></td>
      <td style="padding:8px; border:1px solid #e2e8f0; text-align:right;">{{new_rejects}}</td>
      <td style="padding:8px; border:1px solid #e2e8f0;"><strong>Submitted</strong></td>
      <td style="padding:8px; border:1px solid #e2e8f0; text-align:right;">{{new_submits}}</td>
    </tr>
  </table>
  {{digest_body_html}}
  <p style="text-align:center; margin:28px 0;">
    <a href="{{dashboard_url}}" style="background:#4f46e5; color:#fff; padding:10px 20px; border-radius:8px; text-decoration:none; font-weight:600;">
      Open HR dashboard
    </a>
  </p>
  <hr style="border:none; border-top:1px solid #e2e8f0; margin:24px 0;">
  <p style="color:#94a3b8; font-size:12px;">-- Interveux</p>
</body>
</html>
"""


def render_digest(
    *,
    new_shortlists: int,
    new_reviews: int,
    new_rejects: int,
    new_submits: int,
    digest_body_text: str,
    digest_body_html: str,
    dashboard_url: str,
) -> RenderedEmail:
    ctx = {
        "new_shortlists": str(new_shortlists),
        "new_reviews": str(new_reviews),
        "new_rejects": str(new_rejects),
        "new_submits": str(new_submits),
        "digest_body_text": digest_body_text,
        "digest_body_html": digest_body_html,
        "dashboard_url": dashboard_url,
    }
    return RenderedEmail(
        subject=_render(_DIGEST_SUBJECT, **ctx),
        text=_render(_DIGEST_TEXT, **ctx),
        html=_render(_DIGEST_HTML, **ctx),
    )
