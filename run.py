import sys
from pathlib import Path

# Ensure project root is in Python path for clean module imports
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ui import demo, theme, custom_css

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 StudyBuddy AI is launching locally...")
    print("👉 Open your browser at: http://localhost:7860")
    print("=" * 60)
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=theme,
        css=custom_css,
    )
