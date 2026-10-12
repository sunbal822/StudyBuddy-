import sys
from pathlib import Path
from fastapi import FastAPI
import gradio as gr

# Ensure root directory is in sys.path for module resolution in Vercel Serverless
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ui import demo

app = FastAPI(
    title="StudyBuddy AI",
    description="AI-powered study assistant generating summaries, quizzes, and tracking weak concepts.",
    version="1.0.0",
)

@app.get("/api/health")
def health_check():
    """Health check endpoint to verify serverless container readiness."""
    return {"status": "healthy", "service": "StudyBuddy AI", "version": "1.0.0"}

# Mount Gradio Blocks application at the root route
app = gr.mount_gradio_app(app, demo, path="/")
