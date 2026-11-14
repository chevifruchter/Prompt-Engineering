"""
ה-agent עצמו: הוראה בשפה טבעית -> קריאה ל-LLM -> פקודת CMD.
הפרומפטים נטענים מהתיקייה prompts/ לפי גרסה (v1, v2, ...),
כך שאפשר להשוות בין איטרציות בלי לשנות קוד.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from safety import SafetyVerdict, classify

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = os.environ.get("MODEL", "gpt-4o-mini")
REFUSAL = "REM לא ניתן ליצור פקודה עבור בקשה זו"

_client = None


def get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "לא נמצא OPENAI_API_KEY. ודאי שקובץ ה-.env קיים ומכיל את המשתנה, "
                "ושהוא נמצא באותה תיקייה שממנה מריצים את הסקריפט."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def list_versions() -> list:
    versions = [p.stem for p in PROMPTS_DIR.glob("v*.md")]
    return sorted(versions, key=lambda v: int(v[1:]))


def latest_version() -> str:
    return list_versions()[-1]


def load_prompt(version: str):
    """מחזיר (system_prompt, user_template). אם אין קובץ תבנית - ההוראה נשלחת כמו שהיא."""
    system = (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8").strip()
    user_file = PROMPTS_DIR / f"{version}_user.txt"
    template = user_file.read_text(encoding="utf-8").strip() if user_file.exists() else "{request}"
    return system, template


def clean_output(raw: str) -> str:
    """
    ניקוי הפלט של המודל לפקודה אחת נקייה (רשת ביטחון בקוד).
    שימי לב: בהערכה מודדים את הפלט הגולמי (raw), כדי לראות אם הפרומפט עצמו עובד,
    ולא רק את מה שנשאר אחרי הניקוי.
    """
    text = (raw or "").strip()
    # הסרת בלוק קוד ```cmd ... ```
    fence = re.search(r"```[a-zA-Z]*\s*\n?(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return REFUSAL
    line = lines[0]
    line = re.sub(r"^(פקודה|command|cmd)\s*:\s*", "", line, flags=re.I)
    line = line.strip("`").strip()
    return line or REFUSAL


@dataclass
class AgentResult:
    request: str
    version: str
    raw: str
    command: str
    safety: SafetyVerdict


def generate(request: str, version: str = None, model: str = None) -> AgentResult:
    version = version or latest_version()
    system, template = load_prompt(version)
    completion = get_client().chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": template.replace("{request}", request)},
        ],
        temperature=0,
    )
    raw = completion.choices[0].message.content or ""
    command = clean_output(raw)
    return AgentResult(request, version, raw, command, classify(command))
