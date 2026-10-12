import json
from typing import Generator, List, Dict, Any
from groq import Groq, RateLimitError, APIConnectionError, APIStatusError
from src.config import GROQ_MODEL, get_groq_api_key

STUDY_SUMMARY_SYSTEM_PROMPT = """You are StudyBuddy, an elite academic coach and subject-matter tutor.
Your mission is to turn user notes or topics into high-yield, crystal-clear exam revision summaries.
Structure your output cleanly in Markdown:
1. 🎯 **Executive Summary** (2-3 concise sentences distilling the big picture)
2. 🔑 **Core Concepts & Definitions** (bullet points with bold terms and crisp explanations)
3. 💡 **Memory Hooks & Real-World Analogies** (vivid mental models that make ideas stick)
4. ⚠️ **Common Exam Pitfalls & Traps** (frequent student mistakes and how to avoid them)

Tone: Encouraging, rigorous, concise, and structured for active recall.
"""

QUIZ_GENERATOR_SYSTEM_PROMPT = """You are an expert exam question designer.
Generate exactly 5 high-quality multiple-choice questions (MCQs) based on the provided material.
You MUST output valid, parseable JSON only, matching this exact schema:
{
  "questions": [
    {
      "id": 1,
      "question": "Question text here?",
      "options": [
        "A) Option 1",
        "B) Option 2",
        "C) Option 3",
        "D) Option 4"
      ],
      "correct_answer": "A) Option 1",
      "explanation": "Clear explanation of why this is correct and why other options are wrong.",
      "concept": "Specific concept tested (e.g., Photosynthesis Phase 1)"
    }
  ]
}
Ensure exactly 4 options per question starting with A), B), C), D).
Ensure correct_answer exactly matches one of the 4 strings in options.
Output pure JSON with no markdown backticks or commentary.
"""


def get_client(custom_key: str = "") -> Groq:
    """Initialize and return the Groq SDK client."""
    key = custom_key.strip() if custom_key else get_groq_api_key()
    if not key:
        raise ValueError(
            "GROQ_API_KEY is not set. Please add GROQ_API_KEY to your .env file or enter your key in the settings panel."
        )
    return Groq(api_key=key)


def generate_summary_stream(content: str, difficulty: str = "Medium") -> Generator[str, None, None]:
    """
    Stream a structured study summary for the given notes or topic.
    Yields chunks of text in real-time for responsive UI rendering.
    """
    if not content.strip():
        yield "⚠️ Please enter some notes or a topic first."
        return

    try:
        client = get_client()
        user_message = (
            f"Target Exam Difficulty Level: {difficulty}\n\n"
            f"Study Material / Topic to summarize:\n{content.strip()}"
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": STUDY_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            max_tokens=1500,
            stream=True,
        )

        full_text = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            full_text += delta
            yield full_text

    except ValueError as e:
        yield f"⚠️ Configuration Error: {str(e)}"
    except RateLimitError:
        yield "⚠️ Groq Rate Limit reached! Please wait 10 seconds and try again."
    except APIConnectionError:
        yield "⚠️ Network Error: Unable to reach Groq API. Please verify your internet connection."
    except APIStatusError as e:
        yield f"⚠️ Groq API Error ({e.status_code}): {e.message}"
    except Exception as e:
        yield f"⚠️ An unexpected error occurred: {str(e)}"


def generate_quiz(content: str, difficulty: str = "Medium") -> List[Dict[str, Any]]:
    """
    Generate a 5-question multiple choice quiz formatted as structured JSON.
    Returns a list of question dictionaries.
    """
    if not content.strip():
        raise ValueError("Cannot generate a quiz from empty content.")

    client = get_client()
    user_message = (
        f"Difficulty: {difficulty}\n"
        f"Generate 5 distinct multiple-choice questions to test deep understanding of the following content:\n\n"
        f"{content.strip()}"
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": QUIZ_GENERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=2200,
            response_format={"type": "json_object"},
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)

        # Handle variations like {"questions": [...]} or direct list
        questions = data.get("questions", data) if isinstance(data, dict) else data

        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("Quiz response did not contain a valid list of questions.")

        # Standardize question schema
        normalized_questions = []
        for idx, q in enumerate(questions[:5], start=1):
            normalized_questions.append({
                "id": idx,
                "question": q.get("question", f"Question {idx}"),
                "options": q.get("options", []),
                "correct_answer": q.get("correct_answer", ""),
                "explanation": q.get("explanation", "No explanation provided."),
                "concept": q.get("concept", "General Review"),
            })

        return normalized_questions

    except RateLimitError:
        raise RuntimeError("Groq Rate Limit exceeded. Please wait a moment before trying again.")
    except APIConnectionError:
        raise RuntimeError("Network connection to Groq API failed.")
    except json.JSONDecodeError:
        raise RuntimeError("Failed to parse quiz response into valid JSON from LLM.")
    except Exception as e:
        raise RuntimeError(f"Quiz generation error: {str(e)}")
