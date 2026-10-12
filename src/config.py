import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# ---------------------------------------------------------
# LLM MODEL CONFIGURATION (Single constant for quick swap)
# ---------------------------------------------------------
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def get_groq_api_key() -> str:
    """Retrieve Groq API key dynamically from env or reloaded .env file."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key and ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
        key = os.getenv("GROQ_API_KEY", "").strip()
    return key


def get_supabase_url() -> str:
    """Retrieve Supabase URL dynamically."""
    url = os.getenv("SUPABASE_URL", "").strip()
    if not url and ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
        url = os.getenv("SUPABASE_URL", "").strip()
    return url


def get_supabase_key() -> str:
    """Retrieve Supabase Anon Key dynamically."""
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not key and ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
        key = os.getenv("SUPABASE_KEY", "").strip()
    return key


def save_groq_api_key_to_env(new_key: str) -> None:
    """Save user-provided key to .env file and active environment."""
    clean_key = new_key.strip()
    os.environ["GROQ_API_KEY"] = clean_key
    
    # Read existing lines if any
    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    has_groq_line = False
    new_lines = []
    for line in lines:
        if line.startswith("GROQ_API_KEY="):
            new_lines.append(f"GROQ_API_KEY={clean_key}\n")
            has_groq_line = True
        else:
            new_lines.append(line)
            
    if not has_groq_line:
        new_lines.insert(0, f"GROQ_API_KEY={clean_key}\n")
        
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def save_supabase_credentials(url: str, key: str) -> None:
    """Save Supabase credentials to .env file and active environment."""
    clean_url = url.strip()
    clean_key = key.strip()
    if clean_url:
        os.environ["SUPABASE_URL"] = clean_url
    if clean_key:
        os.environ["SUPABASE_KEY"] = clean_key

    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated = {}
    if clean_url:
        updated["SUPABASE_URL"] = clean_url
    if clean_key:
        updated["SUPABASE_KEY"] = clean_key

    new_lines = []
    seen = set()
    for line in lines:
        matched = False
        for k, v in updated.items():
            if line.startswith(f"{k}="):
                new_lines.append(f"{k}={v}\n")
                seen.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in updated.items():
        if k not in seen:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# Backwards compatibility properties
def has_groq() -> bool:
    return bool(get_groq_api_key())


def has_supabase() -> bool:
    return bool(get_supabase_url() and get_supabase_key())
