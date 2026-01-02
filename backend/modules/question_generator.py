import json
import os
import traceback
from dotenv import load_dotenv

# The OpenAI Python SDK renamed the client in v1.x. We import cautiously so
# older 0.x installs still work.
try:  # pragma: no cover - defensive import
    from openai import OpenAI  # v1.x style
except Exception:  # pragma: no cover
    OpenAI = None
import openai  # keeps 0.x fallback available

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Allow overriding model via env; default to a modern lightweight model.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _get_client():
    """
    Create an OpenAI client compatible with both SDK 0.x and 1.x.
    Raises a clear error if no API key is present or SDK is incompatible.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env or environment.")

    # Preferred path: SDK 1.x
    if OpenAI is not None:
        return OpenAI(api_key=OPENAI_API_KEY)

    # Fallback: SDK 0.x legacy usage
    openai.api_key = OPENAI_API_KEY
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
