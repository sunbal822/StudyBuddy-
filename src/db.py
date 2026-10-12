from datetime import datetime
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
from src.config import get_supabase_url, get_supabase_key

# In-memory fallback cache in case Supabase is not yet configured or temporarily offline
_MEMORY_HISTORY: List[Dict[str, Any]] = []


def get_client() -> Optional[Client]:
    """Initialize and return the Supabase client if configured."""
    url = get_supabase_url()
    key = get_supabase_key()
    if not (url and key):
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        print(f"[Supabase Warning] Failed to initialize client: {e}")
        return None


def test_connection() -> tuple[bool, str]:
    """Test connection to Supabase and verify quiz_history table readiness."""
    client = get_client()
    if not client:
        return False, "Supabase credentials not set."
    try:
        client.table("quiz_history").select("id").limit(1).execute()
        return True, "Connected! Table 'quiz_history' is verified and ready."
    except Exception as e:
        err = str(e)
        if "relation" in err or "does not exist" in err or "404" in err or "quiz_history" in err:
            return False, "Connected to Supabase, but 'quiz_history' table is missing. Run supabase_schema.sql in Supabase SQL editor!"
        return False, f"Supabase error: {err}"


def save_quiz_result(
    topic: str,
    difficulty: str,
    score: int,
    total_questions: int,
    weak_concepts: List[str],
) -> bool:
    """
    Save a completed quiz attempt to Supabase (or fallback memory store).
    Returns True if successfully stored.
    """
    record = {
        "topic": topic[:120] if topic else "General Topic",
        "difficulty": difficulty,
        "score": score,
        "total_questions": total_questions,
        "weak_concepts": weak_concepts,
        "created_at": datetime.utcnow().isoformat(),
    }

    client = get_client()
    if client:
        try:
            client.table("quiz_history").insert(record).execute()
            return True
        except Exception as e:
            print(f"[Supabase Error] Insert failed: {e}. Storing to local fallback.")

    # Fallback to in-memory store
    _MEMORY_HISTORY.insert(0, record)
    return True


def get_recent_quizzes(limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch the most recent quiz attempts."""
    client = get_client()
    if client:
        try:
            response = (
                client.table("quiz_history")
                .select("id, created_at, topic, difficulty, score, total_questions, weak_concepts")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            if response.data:
                return response.data
        except Exception as e:
            print(f"[Supabase Error] Select failed: {e}. Reading from local fallback.")

    return _MEMORY_HISTORY[:limit]


def get_analytics_summary() -> Dict[str, Any]:
    """Calculate aggregate stats for user progress and identify top weak concepts."""
    history = get_recent_quizzes(limit=50)

    if not history:
        return {
            "total_quizzes": 0,
            "average_percentage": 0,
            "top_weak_concepts": ["No quizzes completed yet!"],
        }

    total_quizzes = len(history)
    total_score = sum(item.get("score", 0) for item in history)
    total_possible = sum(item.get("total_questions", 5) for item in history)
    avg_pct = round((total_score / total_possible * 100), 1) if total_possible > 0 else 0

    # Aggregate weak concepts
    weak_concept_counts: Dict[str, int] = {}
    for item in history:
        for concept in item.get("weak_concepts", []):
            if concept and concept.strip():
                clean_concept = concept.strip()
                weak_concept_counts[clean_concept] = weak_concept_counts.get(clean_concept, 0) + 1

    sorted_concepts = sorted(weak_concept_counts.items(), key=lambda x: x[1], reverse=True)
    top_weak = [f"{concept} ({count}x missed)" for concept, count in sorted_concepts[:5]]

    if not top_weak:
        top_weak = ["None recorded! Excellent work!"]

    return {
        "total_quizzes": total_quizzes,
        "average_percentage": avg_pct,
        "top_weak_concepts": top_weak,
    }
