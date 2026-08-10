import json
import os
import re
import secrets
import traceback
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Resolve common env locations once.
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
_backend_env = _backend_dir / ".env"
_root_env = _project_root / ".env"


def _load_env_files():
    """
    Load env values from both project root and backend folders.
    Root first (non-destructive), then backend with override=True so backend/.env
    wins over OS environment and any discoverable .env — consistent with running the API from backend/.
    """
    load_dotenv(_root_env, override=False)
    load_dotenv(_backend_env, override=True)
    load_dotenv(override=False)


_load_env_files()

# The OpenAI Python SDK renamed the client in v1.x. We import cautiously so
# older 0.x installs still work.
try:  # pragma: no cover - defensive import
    from openai import OpenAI  # v1.x style
except Exception:  # pragma: no cover
    OpenAI = None
import openai  # keeps 0.x fallback available

# Allow overriding model via env; default to a modern lightweight model.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_client():
    """
    Create an OpenAI client compatible with both SDK 0.x and 1.x.
    Raises a clear error if no API key is present or SDK is incompatible.
    """
    # Re-load env lazily so updates to .env are picked up without stale module state.
    _load_env_files()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env or environment.")

    # Preferred path: SDK 1.x
    if OpenAI is not None:
        return OpenAI(api_key=api_key)

    # Fallback: SDK 0.x legacy usage
    openai.api_key = api_key
    return openai


def generate_questions(
    resume_text: str,
    *,
    previous_questions: Optional[list] = None,
    num_questions: int = 5,
) -> dict:
    """
    Generates interview questions based on resume text using an LLM.
    Returns a dictionary with categorized questions or an error payload.
    """
    try:
        client = _get_client()
    except Exception as e:
        # Key missing or SDK missing
        return {"error": str(e), "questions": []}

    variation_nonce = secrets.token_hex(4)
    avoid_block = ""
    if previous_questions:
        prior = [
            (q.get("question") if isinstance(q, dict) else str(q)).strip()
            for q in previous_questions
        ]
        prior = [p for p in prior if p]
        if prior:
            avoid_block = (
                "\nDo NOT repeat or closely paraphrase these previously used questions:\n"
                + "\n".join(f"- {p}" for p in prior[:15])
            )

    prompt = f"""
    You are an expert technical interviewer. I will provide you with a candidate's resume text.
    Your goal is to generate {num_questions} tailored interview questions to evaluate this candidate.
    Session variation id: {variation_nonce}.{avoid_block}
    
    Resume Content:
    {resume_text[:2000]}

    Instructions:
    - Return ONLY a JSON object.
    - Format: {{"questions": [{{"type": "Technical|Behavioral|Project", "question": "..."}}]}}
    - Use fresh angles and scenarios not covered in any prior question list above.
    """

    try:
        # SDK 1.x path
        if OpenAI is not None and isinstance(client, OpenAI):
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a technical interviewer that outputs strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.65 if previous_questions else 0.45,
                response_format={ "type": "json_object" }, # Use native JSON mode
                timeout=15, # Tighten timeout
            )
            content = response.choices[0].message.content
        else:
            # SDK 0.x fallback
            response = client.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates interview questions in JSON format."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )
            content = response["choices"][0]["message"]["content"]

        # Strip markdown code blocks if present
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        elif content.startswith("```"):
            content = content.replace("```", "")
        
        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # If model returns non-JSON, still surface the text
            return {"questions": [{"type": "General", "question": content}]}

    except Exception as e:
        # Log full traceback for debugging on the server
        traceback.print_exc()
        return {
            "error": str(e),
            "questions": [
                {"type": "Error", "question": "Could not generate questions due to an API error."}
            ],
        }


_CERT_SECTION_HEADERS = (
    "certifications & achievements",
    "certifications and achievements",
    "certifications",
    "achievements",
    "certificates",
    "credentials",
    "courses",
    "trainings",
    "professional development",
    "licenses & certifications",
)

# Known section headers that end the Certifications block.
_CERT_STOP_HEADERS = (
    "education",
    "experience",
    "professional experience",
    "work experience",
    "projects",
    "skills",
    "technical skills",
    "languages",
    "interests",
    "hobbies",
    "references",
    "publications",
    "awards",  # only stop if it's a distinct awards section
    "volunteer",
    "additional information",
)

# Bullet labels that aren't cert names themselves — the real content lives
# AFTER the dash on these lines.
_CATEGORY_LABELS = {
    "certifications",
    "certifications and achievements",
    "certifications & achievements",
    "certificates",
    "achievements",
    "competitions",
    "competition",
    "participation",
    "participations",
    "awards",
    "honors",
    "honours",
    "trainings",
    "training",
    "courses",
    "credentials",
    "licenses",
    "license",
    "certification",
}


def _split_multi_cert(content: str) -> list:
    """
    For a content string like "MongoDB & Intro to Database/SQL (Great Learning)"
    return [("MongoDB", "Great Learning"), ("Intro to Database/SQL", "Great Learning")].
    Splits by & / , / ; and pulls the parenthetical issuer if present.
    """
    # Extract trailing parenthetical issuer once.
    issuer = ""
    m = re.search(r"\(([^)]+)\)\s*$", content)
    if m:
        issuer = m.group(1).strip()
        content = content[:m.start()].strip()
    parts = [p.strip() for p in re.split(r"\s*(?:&|,|;)\s*", content) if p.strip()]
    out = []
    for p in parts:
        if len(p) >= 3:
            out.append((p, issuer))
    return out


def _extract_certifications_from_text(resume_text: str) -> list:
    """
    Regex / heuristic extractor for the "Certifications" section of a resume.
    Finds a matching section header, then walks the following lines until the
    next major section header. Each bullet / line becomes one entry.

    This is a safety net so the context never silently misses a section the
    LLM truncated or overlooked.
    """
    if not resume_text:
        return []

    lines = [ln.rstrip() for ln in resume_text.splitlines()]
    lower_lines = [ln.strip().lower() for ln in lines]

    # Find the earliest matching section header.
    start_idx = None
    for i, low in enumerate(lower_lines):
        # Match when the line is *only* (or mostly) the header text
        stripped = low.strip(" :•-–—*#")
        if stripped in _CERT_SECTION_HEADERS:
            start_idx = i + 1
            break
        # Also match when the header is embedded like "CERTIFICATIONS & ACHIEVEMENTS"
        for h in _CERT_SECTION_HEADERS:
            if stripped == h or stripped.startswith(h + " "):
                start_idx = i + 1
                break
        if start_idx is not None:
            break

    if start_idx is None:
        return []

    # Walk forward until we hit the next major section header or a blank gap.
    items: list = []
    blank_run = 0
    for i in range(start_idx, len(lines)):
        raw = lines[i].strip()
        low = lower_lines[i].strip(" :•-–—*#")

        if not raw:
            blank_run += 1
            if blank_run >= 2:
                break  # probably reached next block
            continue
        blank_run = 0

        # Stop if we hit a known "next section" header.
        if low in _CERT_STOP_HEADERS:
            break
        # Heuristic: a short ALL-CAPS line is likely a new section header.
        if raw.isupper() and 2 < len(raw) < 40 and not raw.startswith("•"):
            # but not if the line starts with a bullet dash like "• XYZ"
            if not re.match(r"^[•\-–—*]", raw):
                break

        # Strip bullet markers.
        cleaned = re.sub(r"^\s*[•\-\–\—*·]\s*", "", raw).strip()
        if not cleaned:
            continue

        # Split into "head" and "tail" around the first dash separator.
        head, tail = cleaned, ""
        m = re.split(r"\s+[—–-]\s+", cleaned, maxsplit=1)
        if len(m) == 2 and len(m[0]) >= 2 and len(m[1]) >= 2:
            head, tail = m[0].strip(), m[1].strip()

        head_key = head.lower().strip(" :")

        if head_key in _CATEGORY_LABELS and tail:
            # Line is "Category - actual content": split the tail into multiple
            # certs if joined by & / , and use the parenthetical as issuer.
            for name, issuer in _split_multi_cert(tail):
                items.append({"name": name, "issuer": issuer, "relevant": True})
        elif tail:
            # Normal "Name - Issuer" line.
            items.append({"name": head, "issuer": tail, "relevant": True})
        else:
            # Single-part line (no dash separator).
            items.append({"name": head, "issuer": "", "relevant": True})

        if len(items) >= 20:
            break

    return items


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()


def _names_overlap(a: str, b: str) -> bool:
    """True if two cert names refer to the same thing.

    We treat them as the same if one is a substring of the other (after
    normalisation) or if they share 2+ meaningful tokens. This avoids the
    LLM + regex double-counting entries like "MongoDB" vs "MongoDB & Intro
    to Database/SQL".
    """
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    stop = {"the", "and", "a", "of", "in", "for", "to", "on", "with"}
    toks_a = {t for t in na.split() if len(t) > 2 and t not in stop}
    toks_b = {t for t in nb.split() if len(t) > 2 and t not in stop}
    return len(toks_a & toks_b) >= 2


def _merge_certifications(llm_certs: list, regex_certs: list) -> list:
    """
    Merge LLM-returned and regex-extracted certification lists.

    Strategy:
      - The LLM is the authority. When it returned any certifications at all,
        use only those (with light issuer-enrichment from regex when the LLM
        didn't supply one).
      - Only when the LLM returned zero do we fall back to the regex-extracted
        list.

    This avoids double-counting entries like "MongoDB" (LLM) alongside
    "Certifications / MongoDB & Intro to Database/SQL" (regex).
    """
    cleaned_llm: list = []
    for c in (llm_certs or []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        cleaned_llm.append({
            "name": name,
            "issuer": str(c.get("issuer", "")).strip(),
            "relevant": bool(c.get("relevant", True)),
        })

    cleaned_regex: list = []
    for c in (regex_certs or []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        cleaned_regex.append({
            "name": name,
            "issuer": str(c.get("issuer", "")).strip(),
            "relevant": bool(c.get("relevant", True)),
        })

    # Also dedup within each list by overlap.
    def dedup(lst):
        out = []
        for c in lst:
            if any(_names_overlap(c["name"], e["name"]) for e in out):
                continue
            out.append(c)
        return out

    llm_uniq = dedup(cleaned_llm)
    regex_uniq = dedup(cleaned_regex)

    if llm_uniq:
        # Enrich empty issuers from regex matches where possible.
        for c in llm_uniq:
            if c["issuer"]:
                continue
            for r in regex_uniq:
                if _names_overlap(c["name"], r["name"]) and r["issuer"]:
                    c["issuer"] = r["issuer"]
                    break
        return llm_uniq

    # LLM returned nothing — use the regex result as-is.
    return regex_uniq


def extract_resume_context(
    resume_text: str,
    *,
    previous_questions: Optional[list] = None,
    num_questions: int = 5,
) -> dict:
    """
    Single LLM call that extracts interview-relevant context from a resume:
    inferred domain, certifications list, key skills, and 5 tailored questions.

    Output (DB-ready, flat keys):
        {
          "domain": "Data Analyst",
          "certifications": [
            {"name": "Google Data Analytics", "issuer": "Google", "relevant": true}
          ],
          "key_skills": ["SQL", "Python", "Power BI"],
          "questions": [{"type": "Technical"|"Behavioral"|"Project", "question": "..."}],
          "error": "..."   # only present on failure
        }
    """
    empty = {
        "domain": "General",
        "certifications": [],
        "key_skills": [],
        "questions": [],
    }

    if not resume_text or not resume_text.strip():
        return {**empty, "error": "Empty resume text."}

    try:
        client = _get_client()
    except Exception as e:
        return {**empty, "error": str(e)}

    # Give the LLM enough room to actually see the Certifications / Achievements
    # section — these often sit at the very end of the resume.
    resume_for_prompt = resume_text[:8000]
    variation_nonce = secrets.token_hex(4)
    avoid_block = ""
    if previous_questions:
        prior = [
            (q.get("question") if isinstance(q, dict) else str(q)).strip()
            for q in previous_questions
        ]
        prior = [p for p in prior if p]
        if prior:
            avoid_block = (
                "\nDo NOT repeat or closely paraphrase these previously used questions:\n"
                + "\n".join(f"- {p}" for p in prior[:15])
            )

    prompt = f"""
You are an expert technical interviewer and resume parser.

Resume Content (first {len(resume_for_prompt)} chars):
\"\"\"{resume_for_prompt}\"\"\"

Session variation id: {variation_nonce}.{avoid_block}

Perform all of the following in ONE JSON response:

1. Infer the single most likely primary job domain for this candidate
   (e.g., "Data Analyst", "Backend Engineer", "Mobile Developer",
   "Machine Learning Engineer", "DevOps Engineer"). Be specific and concise.

2. Extract every professional certification, course, online training, credential,
   OR listed achievement (e.g., coding competitions, quiz competitions, hackathons)
   the candidate lists — including any section titled "Certifications",
   "Achievements", "Courses", "Credentials", or "Certifications & Achievements".
   For each, determine whether it is RELEVANT to the inferred primary domain
   (true) or unrelated (false). Prefer the bullet text as the "name" and the
   organization / institution / issuer after the dash/em-dash as the "issuer".

3. List the top key technical/professional skills from the resume (max 12).

4. Generate exactly {num_questions} tailored interview questions to evaluate this candidate
   in the inferred domain (mix of Technical, Behavioral, and Project).
   Use new angles and scenarios not covered in any prior question list above.

Return ONLY a JSON object with this exact shape:
{{
  "domain": "string",
  "certifications": [
    {{"name": "string", "issuer": "string", "relevant": true|false}}
  ],
  "key_skills": ["string", ...],
  "questions": [
    {{"type": "Technical|Behavioral|Project", "question": "string"}}
  ]
}}
"""

    try:
        if OpenAI is not None and isinstance(client, OpenAI):
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You parse resumes and output strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.65 if previous_questions else 0.45,
                response_format={"type": "json_object"},
                timeout=25,
            )
            content = response.choices[0].message.content
        else:
            response = client.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You parse resumes and output strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.65 if previous_questions else 0.45,
            )
            content = response["choices"][0]["message"]["content"]

        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        elif content.startswith("```"):
            content = content.replace("```", "")
        content = content.strip()

        data = json.loads(content)

        # Normalize + defensive defaults
        certs_raw = data.get("certifications") or []
        llm_certifications = []
        for c in certs_raw:
            if isinstance(c, str):
                llm_certifications.append({"name": c, "issuer": "", "relevant": True})
            elif isinstance(c, dict):
                llm_certifications.append({
                    "name": str(c.get("name", "")).strip(),
                    "issuer": str(c.get("issuer", "")).strip(),
                    "relevant": bool(c.get("relevant", True)),
                })

        # Safety net: regex-extract from the raw resume text too. Used as a
        # fallback ONLY when the LLM returns nothing; otherwise the LLM output
        # is authoritative (regex may mis-split "Category - Content" lines).
        regex_certs = _extract_certifications_from_text(resume_text)
        merged = _merge_certifications(llm_certifications, regex_certs)

        if not llm_certifications and regex_certs:
            print(f"[RESUME] LLM returned 0 certifications; regex fallback recovered {len(regex_certs)}.")

        return {
            "domain": str(data.get("domain", "General")).strip() or "General",
            "certifications": [c for c in merged if c["name"]],
            "key_skills": [str(s).strip() for s in (data.get("key_skills") or []) if str(s).strip()][:12],
            "questions": data.get("questions") or [],
        }
    except Exception as e:
        traceback.print_exc()
        # Even on LLM failure, still try to return regex-extracted certs so
        # downstream scoring isn't completely blind.
        regex_certs = _extract_certifications_from_text(resume_text)
        return {**empty, "certifications": regex_certs, "error": str(e)}


def analyze_resume_communication(resume_text: str) -> dict:
    """
    Analyze resume text for communication style and return tone_analysis + improvement_tip
    (same structure as video speech analysis so the Resume Evaluator can show Confidence & Tone).
    """
    if not resume_text or not resume_text.strip():
        return {"tone_analysis": None, "improvement_tip": None, "confidence_rating": 5}

    try:
        client = _get_client()
    except Exception as e:
        print(f"[WARN] Client init failed: {e}")
        return {"tone_analysis": None, "improvement_tip": None, "confidence_rating": 5}

    prompt = f"""
    Analyze this candidate's resume text for written communication style and professionalism.

    Resume excerpt (first 2500 chars):
    "{resume_text[:2500]}"

    Evaluate:
    1. Clarity and structure of writing.
    2. Tone (formal vs informal, confidence in wording).
    3. Conciseness and impact of bullet points/summaries.

    Return ONLY a JSON object:
    {{
        "tone_analysis": "2-3 sentence summary of their written communication style",
        "improvement_tip": "One specific tip to strengthen their resume or interview communication"
    }}
    """

    try:
        if OpenAI is not None and isinstance(client, OpenAI):
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert career coach. Output strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=15,
            )
            content = response.choices[0].message.content
        else:
            response = client.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a career coach that outputs strictly JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            content = response["choices"][0]["message"]["content"]

        # Safely strip markdown code blocks if present (avoid IndexError on malformed response)
        if content.startswith("```"):
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1].replace("json", "").strip()
            else:
                content = content.strip()
        else:
            content = content.strip()
        data = json.loads(content)
        return {
            "tone_analysis": data.get("tone_analysis"),
            "improvement_tip": data.get("improvement_tip"),
            "confidence_rating": data.get("confidence_rating", 5),
        }
    except Exception as e:
        print(f"[WARN] Client init failed: {e}")
        return {"tone_analysis": None, "improvement_tip": None, "confidence_rating": 5}

