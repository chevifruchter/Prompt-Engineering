"""
שכבת בטיחות שרצה על הפקודה *אחרי* שהמודל החזיר אותה.
לא סומכים רק על הפרומפט - גם אם המודל "השתכנע" להחזיר פקודה מסוכנת,
הקוד הזה יחסום אותה או ידרוש אישור.

שלוש רמות:
    safe     - אפשר להציג/להריץ.
    risky    - פקודה שמשנה/מוחקת דברים. דורשת אישור משתמש לפני הרצה.
    blocked  - נפסלת לחלוטין, לא מוצגת להרצה בכלל.
וגם:
    refused  - המודל עצמו סירב (החזיר REM).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SAFE = "safe"
RISKY = "risky"
BLOCKED = "blocked"
REFUSED = "refused"

# פקודות שנפסלות לחלוטין
BLOCKED_PATTERNS = [
    (r"^\s*format\b", "פרמוט כונן"),
    (r"^\s*diskpart\b", "ניהול מחיצות"),
    (r"^\s*shutdown\b", "כיבוי/אתחול המחשב"),
    (r"^\s*bcdedit\b", "שינוי הגדרות אתחול"),
    (r"^\s*cipher\b.*\s/w", "מחיקה בלתי הפיכה של מידע"),
    (r"^\s*reg\s+delete\b", "מחיקה מהרג'יסטרי"),
    (r"^\s*vssadmin\s+delete\b", "מחיקת נקודות שחזור"),
    (r"^\s*rm\s+-[a-z]*r[a-z]*f|^\s*rm\s+-[a-z]*f[a-z]*r", "rm -rf"),
    (r"^\s*(takeown|icacls)\b.*\b[a-z]:\\?(\s|$|\*)", "שינוי הרשאות על כונן שלם"),
    # מחיקה של כונן שלם / תיקיות מערכת
    (r"^\s*(del|erase|rd|rmdir)\b.*\b[a-z]:\\?(\*(\.\*)?)?(\s|\"|$)", "מחיקה של כונן שלם"),
    (r"^\s*(del|erase|rd|rmdir)\b.*\\windows\b", "מחיקת תיקיית מערכת"),
    (r"^\s*(del|erase|rd|rmdir)\b.*program files", "מחיקת תיקיית מערכת"),
    (r"^\s*(del|erase|rd|rmdir)\b.*(%systemroot%|%windir%)","מחיקת תיקיית מערכת"),
]

# פקודות שמותרות אבל משנות מצב - דורשות אישור
RISKY_PATTERNS = [
    (r"^\s*(del|erase)\b", "מחיקת קבצים"),
    (r"^\s*(rd|rmdir)\b", "מחיקת תיקייה"),
    (r"^\s*(move|ren|rename)\b", "העברה/שינוי שם"),
    (r"^\s*taskkill\b", "סגירת תהליכים"),
    (r"^\s*(sc|net)\s+(stop|delete|config|user)\b", "שינוי שירותים/משתמשים"),
    (r"^\s*reg\s+(add|import)\b", "שינוי ברג'יסטרי"),
    (r"^\s*(icacls|takeown|attrib)\b", "שינוי הרשאות/מאפיינים"),
    (r"^\s*(setx)\b", "שינוי משתני סביבה קבועים"),
    (r"^\s*(schtasks)\s+/(create|delete)", "תזמון משימות"),
    (r"^\s*(xcopy|robocopy)\b.*\s/(mir|purge)\b", "סנכרון שעלול למחוק קבצים"),
    (r">\s*[^>&|]", "דריסת תוכן קובץ"),  # הפניה > (לא >>) דורסת קובץ קיים
]


@dataclass
class SafetyVerdict:
    level: str
    reasons: list

    @property
    def label(self) -> str:
        return {
            SAFE: "✅ בטוחה",
            RISKY: "⚠️ דורשת אישור לפני הרצה",
            BLOCKED: "⛔ נחסמה",
            REFUSED: "ℹ️ המודל לא יצר פקודה",
        }[self.level]


def split_steps(command: str) -> list:
    """מפרק שרשרת פקודות (&&, ||, &, |) לשלבים בודדים, תוך התעלמות ממה שבתוך מירכאות."""
    steps, buf, in_quotes, i = [], "", False, 0
    while i < len(command):
        ch = command[i]
        if ch == '"':
            in_quotes = not in_quotes
        if not in_quotes and ch in "&|":
            if buf.strip():
                steps.append(buf.strip())
            buf = ""
            # מדלגים על && / ||
            if i + 1 < len(command) and command[i + 1] == ch:
                i += 1
        else:
            buf += ch
        i += 1
    if buf.strip():
        steps.append(buf.strip())
    return steps


def classify(command: str) -> SafetyVerdict:
    if not command or command.strip().upper().startswith("REM"):
        return SafetyVerdict(REFUSED, [])

    blocked, risky = [], []
    for step in split_steps(command):
        low = step.lower()
        for pattern, reason in BLOCKED_PATTERNS:
            if re.search(pattern, low):
                blocked.append(f"{reason}: {step}")
                break
        else:
            for pattern, reason in RISKY_PATTERNS:
                if re.search(pattern, low):
                    risky.append(f"{reason}: {step}")
                    break

    if blocked:
        return SafetyVerdict(BLOCKED, blocked)
    if risky:
        return SafetyVerdict(RISKY, risky)
    return SafetyVerdict(SAFE, [])
