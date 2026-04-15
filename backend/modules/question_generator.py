import json
import os
import traceback
from pathlib import Path
from dotenv import load_dotenv

# Resolve common env locations once.
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
_backend_env = _backend_dir / ".env"
_root_env = _project_root / ".env"


def _load_env_files():
    """
    Load env values from both project root and backend folders.
    Root first, backend second so backend/.env can override if needed.
    """
    load_dotenv(_root_env, override=False)
    load_dotenv(_backend_env, override=False)
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


def generate_questions(resume_text: str) -> dict:
    """
    Generates interview questions based on resume text using an LLM.
    Returns a dictionary with categorized questions or an error payload.
    """
    try:
        client = _get_client()
    except Exception as e:
        # Key missing or SDK missing
        return {"error": str(e), "questions": []}

    prompt = f"""
    You are an expert technical interviewer. I will provide you with a candidate's resume text.
    Your goal is to generate 5 tailored interview questions to evaluate this candidate.
    
    Resume Content:
    {resume_text[:2000]}

    Instructions:
    - Return ONLY a JSON object.
    - Format: {{"questions": [{{"type": "Technical|Behavioral|Project", "question": "..."}}]}}
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
                temperature=0.3, # Lower temperature is faster and more focused
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
        return {"tone_analysis": None, "improvement_tip": None, "confidence_rating": 5}
