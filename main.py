"""
ממשק Gradio: הוראה בשפה טבעית -> פקודת CMD.
הפקודה לא רצה על המחשב שלך בשום מצב - רק בתוך sandbox של Docker, ורק אם ביקשת.
"""
import gradio as gr

from agent import generate, latest_version, list_versions
from safety import BLOCKED, REFUSED, RISKY
from sandbox import docker_status, run_in_sandbox

# ב-Gradio 6 השתנו כמה פרמטרים - שומרים על תאימות לשתי הגרסאות
GRADIO_6 = int(gr.__version__.split(".")[0]) >= 6
COPY = {"buttons": ["copy"]} if GRADIO_6 else {"show_copy_button": True}


def convert(message, version):
    if not message or not message.strip():
        return "", "אנא הזיני הוראה.", gr.update(visible=False, value=False), gr.update(interactive=False), ""
    try:
        res = generate(message.strip(), version)
    except Exception as e:  # noqa: BLE001
        return "", f"שגיאה בפנייה למודל: {e}", gr.update(visible=False), gr.update(interactive=False), ""

    verdict = res.safety
    info = f"**{verdict.label}**"
    if verdict.reasons:
        info += "\n\n" + "\n".join(f"- {r}" for r in verdict.reasons)

    if verdict.level == BLOCKED:
        # פקודה חסומה לא מוצגת בכלל כפקודה להרצה
        return "", info, gr.update(visible=False, value=False), gr.update(interactive=False), ""
    needs_confirm = verdict.level == RISKY
    can_run = verdict.level != REFUSED and not needs_confirm
    return (
        res.command,
        info,
        gr.update(visible=needs_confirm, value=False),
        gr.update(interactive=can_run),
        "",
    )


def on_confirm(confirmed):
    return gr.update(interactive=bool(confirmed))


def run_sandbox(command):
    if not command:
        return "אין פקודה להרצה."
    res = run_in_sandbox(command)
    title = {"ok": "✅ רצה בהצלחה", "error": "❌ החזירה שגיאה", "timeout": "⏱️ timeout",
             "unavailable": "⚠️ ה-sandbox לא זמין"}[res["status"]]
    code = f" (exit code {res['returncode']})" if res["returncode"] is not None else ""
    return f"{title}{code}\n\n{res['output']}"


with gr.Blocks(title="ממיר הוראות ל-CMD", **({} if GRADIO_6 else {"theme": "soft"})) as demo:
    gr.Markdown(
        "# ממיר הוראות בשפה טבעית לפקודת CMD\n"
        "כתבי מה את רוצה לעשות, והמערכת תחזיר פקודת CMD אחת. "
        "הפקודה **לא** מורצת על המחשב שלך - אפשר להריץ אותה רק בתוך sandbox מבודד."
    )
    with gr.Row():
        text = gr.Textbox(label="הוראה", placeholder="למשל: מה כתובת ה-IP של המחשב שלי", rtl=True, scale=4)
        version = gr.Dropdown(list_versions(), value=latest_version(), label="גרסת פרומפט", scale=1)
    convert_btn = gr.Button("המרה לפקודה", variant="primary")

    command = gr.Textbox(label="פקודת CMD", interactive=False, **COPY)
    safety_info = gr.Markdown()
    confirm = gr.Checkbox(label="הבנתי שהפקודה משנה/מוחקת קבצים, ואני מאשרת להריץ אותה ב-sandbox", visible=False)

    _, sandbox_msg = docker_status()
    run_btn = gr.Button("הרצה ב-sandbox (Docker)", interactive=False)
    gr.Markdown(f"<small>מצב ה-sandbox: {sandbox_msg}</small>")
    run_output = gr.Textbox(label="תוצאת ההרצה ב-sandbox", lines=8, interactive=False)

    gr.Examples(
        [
            "מה כתובת ה-IP של המחשב שלי",
            "אני רוצה למחוק את כל הקבצים עם סיומת .tmp בתיקייה downloads",
            "לסדר את רשימת הקבצים לפי גודל מהגדול לקטן",
            "איזה תהליכים רצים כרגע במערכת",
        ],
        inputs=text,
    )

    outputs = [command, safety_info, confirm, run_btn, run_output]
    convert_btn.click(convert, [text, version], outputs)
    text.submit(convert, [text, version], outputs)
    confirm.change(on_confirm, confirm, run_btn)
    run_btn.click(run_sandbox, command, run_output)

if __name__ == "__main__":
    demo.launch(**({"theme": "soft"} if GRADIO_6 else {}))
