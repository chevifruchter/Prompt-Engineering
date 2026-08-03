import os
import gradio as gr
from openai import OpenAI
from dotenv import load_dotenv

# --- טעינת המפתח מתוך קובץ .env ---
# ודאי שקובץ ה-.env נמצא באותה תיקייה כמו הקובץ הזה (main.py),
# ושהוא מכיל שורה כמו:
#   OPENAI_API_KEY=sk-...

load_dotenv()  # טוען את המשתנים מתוך .env אל תוך os.environ

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError(
        "לא נמצא OPENAI_API_KEY. ודאי שקובץ ה-.env קיים ומכיל את המשתנה, "
        "ושהוא נמצא באותה תיקייה שממנה מריצים את הסקריפט."
    )

client = OpenAI(api_key=api_key)

SYSTEM_PROMPT = """
אתה מתרגם פקודות בשפה טבעית בעברית לפקודת CMD (Windows Command Prompt) יחידה שניתן להריץ ישירות.

חוקים:
1. החזר אך ורק את פקודת ה-CMD עצמה, ללא הסברים, ללא טקסט נוסף, וללא סימוני קוד (```).
2. אם הבקשה דורשת כמה שלבים, חבר אותם לשורה אחת בעזרת "&&" (או "&" אם אין תלות בהצלחת השלב הקודם).
3. אם לא ניתן להמיר את הבקשה לפקודת CMD סבירה, החזר: REM לא ניתן ליצור פקודה עבור בקשה זו
4. אל תמציא פקודות מסוכנות (כגון מחיקת דיסק שלם, פורמט, שינויי הרשאות גורפים) גם אם מתבקש - במקרה כזה החזר את שורת ה-REM מהחוק הקודם.
"""


def respond(message, history):
    """
    מקבל פקודה בעברית (message) ומחזיר פקודת CMD מקבילה.
    history מכיל את היסטוריית השיחה (לא בשימוש כרגע, אך נשלח לפונקציה ע"י Gradio).
    """
    if not message or not message.strip():
        return "אנא הזיני פקודה בעברית."

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",  # אפשר להחליף למודל אחר לפי הצורך
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0,
        )
        command = completion.choices[0].message.content.strip()
        return f"```\n{command}\n```"

    except Exception as e:
        return f"שגיאה בפנייה ל-OpenAI: {e}"


demo = gr.ChatInterface(
    fn=respond,
    title="ממיר פקודות עברית ל-CMD",
    description=(
        "כתבי פקודה בעברית (למשל: \"תציגי את רשימת הקבצים בתיקייה הנוכחית\") "
        "והבוט יחזיר פקודת CMD מתאימה. "
        "שימי לב: הבוט רק מייצר את הפקודה — הוא אינו מריץ אותה בעצמו."
    ),
    examples=[
        "תציגי את כל הקבצים בתיקייה הנוכחית כולל תיקיות מוסתרות",
        "צרי תיקייה חדשה בשם reports",
        "העתיקי את הקובץ data.csv לתיקייה backup",
    ],
    theme="soft",
)

if __name__ == "__main__":
    demo.launch()