import os
import tempfile
import pandas as pd
import gradio as gr

from src.llm import generate_summary_stream, generate_quiz
from src.db import (
    save_quiz_result,
    get_recent_quizzes,
    get_analytics_summary,
    test_connection,
)
from src.config import (
    GROQ_MODEL,
    has_groq,
    has_supabase,
    get_groq_api_key,
    save_groq_api_key_to_env,
    get_supabase_url,
    get_supabase_key,
    save_supabase_credentials,
)

# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------
def render_status_badge() -> str:
    """Generate markdown status pills for Groq and Supabase."""
    groq_badge = "🟢 Groq Connected" if has_groq() else "🔴 Groq Key Missing"
    sb_badge = "🟢 Supabase Connected" if has_supabase() else "🟡 Supabase in Demo Fallback Mode"
    return f"`{groq_badge}` &nbsp;|&nbsp; `{sb_badge}`"


def create_downloadable_file(topic: str, summary_text: str, quiz_data: list) -> str:
    """Create a temporary markdown file for downloading study notes and quiz."""
    clean_topic = "".join(c for c in topic if c.isalnum() or c in (" ", "_", "-")).strip() or "StudyNotes"
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"{clean_topic.replace(' ', '_')}_StudyGuide.md")

    content = f"# StudyBuddy Revision Guide: {topic}\n\n"
    content += "## 📖 Summary & Key Concepts\n\n"
    content += summary_text + "\n\n"
    content += "## 📝 Practice Quiz\n\n"

    for idx, q in enumerate(quiz_data, 1):
        content += f"### Q{idx}: {q.get('question', '')}\n"
        for opt in q.get("options", []):
            content += f"- {opt}\n"
        content += f"\n**Correct Answer:** {q.get('correct_answer', '')}\n"
        content += f"**Explanation:** {q.get('explanation', '')}\n"
        content += f"**Key Concept:** {q.get('concept', '')}\n\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def process_study_session(content: str, difficulty: str, api_key: str = ""):
    """
    Main generator:
    1. If user supplied key in UI, persists it.
    2. Streams the summary to the UI.
    3. Once streaming finishes, generates the 5-question quiz JSON.
    4. Populates the 5 Radio question components and makes them visible.
    """
    if api_key and api_key.strip():
        save_groq_api_key_to_env(api_key.strip())

    if not has_groq():
        yield (
            "⚠️ **Configuration Error**: `GROQ_API_KEY` is not set.\n\n"
            "👉 Please paste your Groq API key in the **🔑 Groq API Key Settings** box above, or save it to your `.env` file.\n\n"
            "*(You can get a free instant key at [console.groq.com/keys](https://console.groq.com/keys))*",
            gr.update(visible=False),  # quiz_group
            gr.update(visible=False),  # q1
            gr.update(visible=False),  # q2
            gr.update(visible=False),  # q3
            gr.update(visible=False),  # q4
            gr.update(visible=False),  # q5
            gr.update(visible=False),  # submit_quiz_btn
            gr.update(value="", visible=False),  # score_display
            gr.update(value="", visible=False),  # explanation_display
            [],  # quiz_state
            None,  # download_btn
        )
        return

    if not content.strip():
        yield (
            "⚠️ Please enter notes or a topic before generating.",
            gr.update(visible=False),  # quiz_group
            gr.update(visible=False),  # q1
            gr.update(visible=False),  # q2
            gr.update(visible=False),  # q3
            gr.update(visible=False),  # q4
            gr.update(visible=False),  # q5
            gr.update(visible=False),  # submit_quiz_btn
            gr.update(value="", visible=False),  # score_display
            gr.update(value="", visible=False),  # explanation_display
            [],  # quiz_state
            None,  # download_btn
        )
        return

    # Phase 1: Stream summary
    full_summary = ""
    for summary_chunk in generate_summary_stream(content, difficulty):
        full_summary = summary_chunk
        yield (
            full_summary,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            [],
            None,
        )

    # Phase 2: Generate Quiz
    try:
        quiz_data = generate_quiz(content, difficulty)
    except Exception as e:
        yield (
            full_summary + f"\n\n> ⚠️ Quiz generation failed: {str(e)}",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            [],
            None,
        )
        return

    # Phase 3: Create download file
    download_path = create_downloadable_file(
        topic=content[:50],
        summary_text=full_summary,
        quiz_data=quiz_data,
    )

    # Helper for radio components
    def radio_update(idx: int):
        if idx < len(quiz_data):
            q = quiz_data[idx]
            label = f"Q{idx + 1}: {q['question']} (Concept: {q.get('concept', 'General')})"
            return gr.update(
                label=label,
                choices=q.get("options", []),
                value=None,
                visible=True,
            )
        return gr.update(visible=False)

    yield (
        full_summary,
        gr.update(visible=True),  # quiz_group
        radio_update(0),
        radio_update(1),
        radio_update(2),
        radio_update(3),
        radio_update(4),
        gr.update(visible=True),  # submit_quiz_btn
        gr.update(value="", visible=False),
        gr.update(value="", visible=False),
        quiz_data,
        download_path,
    )


def evaluate_quiz(
    q1_ans: str,
    q2_ans: str,
    q3_ans: str,
    q4_ans: str,
    q5_ans: str,
    quiz_data: list,
    topic: str,
    difficulty: str,
):
    """Evaluate submitted quiz answers, compute score, highlight missed concepts, and persist."""
    if not quiz_data or len(quiz_data) == 0:
        return gr.update(value="⚠️ No active quiz to evaluate.", visible=True), gr.update(visible=False)

    user_answers = [q1_ans, q2_ans, q3_ans, q4_ans, q5_ans]
    score = 0
    total = len(quiz_data)
    weak_concepts = []

    explanation_md = "## 📝 Detailed Answer Explanations\n\n"

    for idx, q in enumerate(quiz_data):
        user_choice = user_answers[idx] if idx < len(user_answers) else None
        correct_choice = q.get("correct_answer", "").strip()
        concept = q.get("concept", "General Review")

        is_correct = bool(user_choice and user_choice.strip() == correct_choice)

        if is_correct:
            score += 1
            badge = "✅ **Correct**"
        else:
            badge = "❌ **Incorrect**"
            weak_concepts.append(concept)

        explanation_md += f"### Question {idx + 1}: {q.get('question')}\n"
        explanation_md += f"- Status: {badge}\n"
        explanation_md += f"- **Your Answer:** {user_choice if user_choice else '*No answer selected*'}\n"
        explanation_md += f"- **Correct Answer:** `{correct_choice}`\n"
        explanation_md += f"- **Key Concept:** *{concept}*\n"
        explanation_md += f"- **Explanation:** {q.get('explanation')}\n\n---\n\n"

    pct = round((score / total) * 100) if total > 0 else 0
    grade_emoji = "🏆" if pct >= 80 else ("💪" if pct >= 60 else "📚")
    score_md = f"""### {grade_emoji} Quiz Score: **{score} / {total}** ({pct}%)
*Difficulty: {difficulty}*
"""
    if weak_concepts:
        score_md += f"\n**🎯 Identified Focus Areas for Review:** {', '.join(set(weak_concepts))}"
    else:
        score_md += "\n🎉 **Flawless Mastery!** You aced all tested concepts on this topic."

    # Save to Supabase (or fallback)
    save_quiz_result(
        topic=topic[:80] if topic else "Untitled Study Topic",
        difficulty=difficulty,
        score=score,
        total_questions=total,
        weak_concepts=list(set(weak_concepts)),
    )

    return (
        gr.update(value=score_md, visible=True),
        gr.update(value=explanation_md, visible=True),
    )


def load_analytics_dashboard():
    """Fetch analytics and history for the Progress tab."""
    analytics = get_analytics_summary()
    history = get_recent_quizzes(limit=20)

    total_quizzes = f"{analytics['total_quizzes']} completed"
    avg_score = f"{analytics['average_percentage']}%"
    weak_str = "\n".join(f"• {c}" for c in analytics["top_weak_concepts"])

    # Prepare DataFrame
    rows = []
    for h in history:
        date_str = str(h.get("created_at", ""))[:16].replace("T", " ")
        weak_list = h.get("weak_concepts", [])
        weak_formatted = ", ".join(weak_list) if isinstance(weak_list, list) else str(weak_list)
        rows.append({
            "Date": date_str,
            "Topic": h.get("topic", "N/A"),
            "Level": h.get("difficulty", "Medium"),
            "Score": f"{h.get('score', 0)} / {h.get('total_questions', 5)}",
            "Missed Concepts": weak_formatted if weak_formatted else "None (100%)",
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Date", "Topic", "Level", "Score", "Missed Concepts"]
    )

    return total_quizzes, avg_score, weak_str, df


# ---------------------------------------------------------
# GRADIO INTERFACE LAYOUT
# ---------------------------------------------------------
custom_css = """
.study-header { text-align: center; margin-bottom: 1rem; }
.badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
.quiz-card { padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 1rem; }
"""

theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="slate")

with gr.Blocks(title="StudyBuddy AI") as demo:
    current_quiz_state = gr.State([])

    with gr.Row():
        with gr.Column(elem_classes=["study-header"]):
            gr.Markdown(
                f"""# 🎓 StudyBuddy AI
### Your High-Yield Exam Companion • Instant Summaries, Practice Quizzes & Weak-Topic Tracking
*Powered by Groq (`{GROQ_MODEL}`) & Supabase*
"""
            )
            status_badge_md = gr.Markdown(value=render_status_badge())

    # Settings Accordion for API Keys & Database
    with gr.Accordion("⚙️ Environment Settings (Groq & Supabase)", open=not (has_groq() and has_supabase())) as key_accordion:
        with gr.Row():
            api_key_input = gr.Textbox(
                label="Groq API Key (starts with gsk_...)",
                placeholder="Paste your key here (e.g. gsk_...)",
                value=get_groq_api_key(),
                type="password",
                scale=5,
            )
            save_key_btn = gr.Button("💾 Save Groq Key", variant="secondary", scale=1)
        save_status_md = gr.Markdown(
            value="💡 *Get a free Groq key at [console.groq.com/keys](https://console.groq.com/keys).*"
        )

        with gr.Row():
            sb_url_input = gr.Textbox(
                label="Supabase URL",
                placeholder="https://your-project.supabase.co",
                value=get_supabase_url(),
                scale=3,
            )
            sb_key_input = gr.Textbox(
                label="Supabase Anon Key",
                placeholder="eyJh... (public anon key)",
                value=get_supabase_key(),
                type="password",
                scale=3,
            )
            save_sb_btn = gr.Button("🔌 Connect Supabase", variant="secondary", scale=1)
        sb_status_md = gr.Markdown(
            value="💡 *Get your Project URL & Anon Key from your Supabase Dashboard: Project Settings > API.*"
        )

    with gr.Tabs():
        # TAB 1: STUDY & QUIZ
        with gr.TabItem("📖 Study & Quiz Studio"):
            with gr.Row():
                with gr.Column(scale=5):
                    notes_input = gr.Textbox(
                        label="Enter Your Notes, Textbook Excerpt, or Study Topic",
                        placeholder="Paste rough notes, slides, or enter a topic (e.g., 'Photosynthesis and the Calvin Cycle', 'Machine Learning Overfitting', 'Keynesian Economics')...",
                        lines=7,
                    )
                    with gr.Row():
                        difficulty_select = gr.Dropdown(
                            label="Target Difficulty",
                            choices=["Easy (Foundational)", "Medium (Standard Exam)", "Hard (Advanced Synthesis)"],
                            value="Medium (Standard Exam)",
                            scale=2,
                        )
                        generate_btn = gr.Button("⚡ Generate Study Guide & Quiz", variant="primary", scale=3)
                        clear_btn = gr.Button("🧹 Clear", scale=1)

                    gr.Examples(
                        examples=[
                            [
                                "Photosynthesis: Light-dependent reactions happen in thylakoid membranes, using water and sunlight to make ATP and NADPH, releasing O2. The Calvin cycle occurs in the stroma, using CO2, ATP, and NADPH to produce G3P sugar. Key enzyme is RuBisCO.",
                                "Medium (Standard Exam)",
                            ],
                            [
                                "Machine Learning Overfitting: Occurs when a model learns noise and specifics of training data rather than underlying patterns. Symptoms: high training accuracy, low validation accuracy. Solutions: L1/L2 regularization, dropout, pruning, cross-validation, and more training data.",
                                "Hard (Advanced Synthesis)",
                            ],
                            [
                                "The French Revolution (1789): Sparked by financial crisis, food shortages, and Enlightenment ideals. Estates-General convened, Third Estate formed National Assembly, Storming of the Bastille on July 14, Declaration of the Rights of Man.",
                                "Easy (Foundational)",
                            ],
                        ],
                        inputs=[notes_input, difficulty_select],
                        label="⚡ Quick Demo Examples (Click to Test)",
                    )

                with gr.Column(scale=6):
                    gr.Markdown("### 📌 High-Yield Revision Guide")
                    summary_output = gr.Markdown(value="*Your summary will stream here in real-time...*")
                    download_output = gr.File(label="📥 Download Study Guide (.md)", visible=True)

            gr.Markdown("---")

            # QUIZ SECTION
            with gr.Group(visible=False) as quiz_group:
                gr.Markdown("## 🎯 5-Question Practice Quiz")
                gr.Markdown("*Test your active recall before viewing the explanations.*")

                q1_radio = gr.Radio(choices=[], label="Q1", visible=False)
                q2_radio = gr.Radio(choices=[], label="Q2", visible=False)
                q3_radio = gr.Radio(choices=[], label="Q3", visible=False)
                q4_radio = gr.Radio(choices=[], label="Q4", visible=False)
                q5_radio = gr.Radio(choices=[], label="Q5", visible=False)

                submit_quiz_btn = gr.Button("🏁 Submit Quiz & Reveal Score", variant="primary", visible=False)

                # Post-Submission Results
                score_display = gr.Markdown(visible=False)
                explanation_display = gr.Markdown(visible=False)

        # TAB 2: PROGRESS & WEAK TOPICS
        with gr.TabItem("📊 Progress & Weak Topics"):
            with gr.Row():
                refresh_analytics_btn = gr.Button("🔄 Refresh Analytics", variant="secondary")

            with gr.Row():
                stat_total = gr.Textbox(label="Total Quizzes Taken", interactive=False)
                stat_avg = gr.Textbox(label="Average Mastery Score", interactive=False)
                stat_weak = gr.Textbox(label="Top Concepts Needing Review", lines=3, interactive=False)

            gr.Markdown("### 📜 Recent Quiz History")
            history_table = gr.Dataframe(
                headers=["Date", "Topic", "Level", "Score", "Missed Concepts"],
                datatype=["str", "str", "str", "str", "str"],
                interactive=False,
                wrap=True,
            )

    # ---------------------------------------------------------
    # EVENT CONNECTIONS
    # ---------------------------------------------------------
    def on_save_key(key: str):
        if not key.strip():
            return "⚠️ Key cannot be empty.", render_status_badge()
        save_groq_api_key_to_env(key.strip())
        return "✅ Groq API Key saved successfully to `.env`!", render_status_badge()

    save_key_btn.click(
        fn=on_save_key,
        inputs=[api_key_input],
        outputs=[save_status_md, status_badge_md],
    )

    def on_save_supabase(url: str, key: str):
        if not url.strip() or not key.strip():
            return "⚠️ Both Supabase URL and Anon Key are required.", render_status_badge()
        save_supabase_credentials(url.strip(), key.strip())
        is_ok, msg = test_connection()
        if is_ok:
            return f"✅ {msg}", render_status_badge()
        else:
            return f"⚠️ {msg}", render_status_badge()

    save_sb_btn.click(
        fn=on_save_supabase,
        inputs=[sb_url_input, sb_key_input],
        outputs=[sb_status_md, status_badge_md],
    )

    def clear_all():
        return (
            "",
            "Medium (Standard Exam)",
            "*Summary cleared. Enter a topic above to begin.*",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
            [],
            None,
        )

    clear_btn.click(
        fn=clear_all,
        inputs=[],
        outputs=[
            notes_input,
            difficulty_select,
            summary_output,
            quiz_group,
            q1_radio,
            q2_radio,
            q3_radio,
            q4_radio,
            q5_radio,
            submit_quiz_btn,
            score_display,
            explanation_display,
            current_quiz_state,
            download_output,
        ],
    )

    generate_btn.click(
        fn=process_study_session,
        inputs=[notes_input, difficulty_select, api_key_input],
        outputs=[
            summary_output,
            quiz_group,
            q1_radio,
            q2_radio,
            q3_radio,
            q4_radio,
            q5_radio,
            submit_quiz_btn,
            score_display,
            explanation_display,
            current_quiz_state,
            download_output,
        ],
    )

    submit_quiz_btn.click(
        fn=evaluate_quiz,
        inputs=[
            q1_radio,
            q2_radio,
            q3_radio,
            q4_radio,
            q5_radio,
            current_quiz_state,
            notes_input,
            difficulty_select,
        ],
        outputs=[
            score_display,
            explanation_display,
        ],
    )

    refresh_analytics_btn.click(
        fn=load_analytics_dashboard,
        inputs=[],
        outputs=[stat_total, stat_avg, stat_weak, history_table],
    )

    demo.load(
        fn=load_analytics_dashboard,
        inputs=[],
        outputs=[stat_total, stat_avg, stat_weak, history_table],
    )
