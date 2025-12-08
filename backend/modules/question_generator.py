import os
import openai
import json
from dotenv import load_dotenv

load_dotenv()

# Configure OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

def generate_questions(resume_text: str) -> dict:
    """
    Generates interview questions based on resume text using an LLM.
    Returns a dictionary with categorized questions.
    """
    if not OPENAI_API_KEY:
        return {
            "error": "OpenAI API key not found. Please set OPENAI_API_KEY in .env file.",
            "questions": []
        }

    prompt = f"""
    You are an expert technical interviewer. I will provide you with a candidate's resume text.
    Your goal is to generate 5-7 tailored interview questions to evaluate this candidate.

    Resume Content:
    {resume_text[:3000]}  # Truncate to avoid token limits if necessary

    Instructions:
    1. Analyze the candidate's skills, experience, and projects.
    2. Generate a mix of:
       - Technical Questions (based on specific tools/languages mentioned)
       - Behavioral Questions (based on experiences/roles)
       - Project-based Questions (asking for details on specific projects)
    3. Return the output strictly as a JSON object with this structure:
    {{
      "questions": [
        {{ "type": "Technical", "question": "..." }},
        {{ "type": "Behavioral", "question": "..." }},
        {{ "type": "Project", "question": "..." }}
      ]
    }}
    """

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates interview questions in JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        content = response.choices[0].message.content
        # validation to ensure we got valid JSON
        try:
            data = json.loads(content)
            return data
        except json.JSONDecodeError:
            # Fallback if raw text is returned, attempt to wrap it
            return {"questions": [{"type": "General", "question": content}]}

    except Exception as e:
        print(f"Error generating questions: {e}")
        return {
            "error": str(e),
            "questions": [
                {"type": "Error", "question": "Could not generate questions due to an API error."}
            ]
        }
