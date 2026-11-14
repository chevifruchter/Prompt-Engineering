"""
הרצת פקודה בתוך sandbox של Docker (אתגר הבונוס).

הפקודות הן פקודות CMD, ולכן צריך קונטיינר של Windows:
    1. Docker Desktop -> לחיצה ימנית על האייקון -> "Switch to Windows containers..."
    2. docker pull mcr.microsoft.com/windows/nanoserver:ltsc2022
       (אפשר להחליף ל-servercore שיש בו יותר פקודות, דרך המשתנה SANDBOX_IMAGE ב-.env)

כל הרצה:
    - בקונטיינר חדש וחד-פעמי (--rm) שנמחק בסוף.
    - בלי רשת (--network none), עם הגבלת זיכרון ו-CPU.
    - עם timeout - אם הפקודה נתקעת, הקונטיינר נהרג.
    - בתוך תיקיית עבודה עם קבצי דוגמה, כדי שפקודות כמו "type notes.txt" יחזירו תוצאה אמיתית.
המחשב האמיתי לא נוגע בפקודה בשום שלב.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE = os.environ.get("SANDBOX_IMAGE", "mcr.microsoft.com/windows/nanoserver:ltsc2022")
TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT", "30"))

# קבצי דוגמה שנוצרים בתוך הקונטיינר לפני הרצת הפקודה
FIXTURES = "\r\n".join([
    r"mkdir C:\work",
    r"cd /d C:\work",
    r"mkdir downloads backup archive projects logs_old",
    r'mkdir "My Documents"',
    r"echo hello> notes.txt",
    r"echo id,name> data.csv",
    r"echo 1,test>> data.csv",
    r"echo error: disk full> log.txt",
    r"echo request timeout> app.log",
    r"echo old> old.txt",
    r"echo [main]> config.ini",
    r"echo tmp> downloads\a.tmp",
    r"echo tmp> downloads\b.tmp",
    r"echo pdf> projects\doc.pdf",
])


def to_batch(command: str) -> str:
    """
    הפקודה נכתבת לקובץ run.cmd ולא מועברת כארגומנט, כדי לא להסתבך עם מירכאות.
    בקובץ batch משתנה של לולאת for נכתב %%f במקום %f - לכן ממירים.
    """
    return re.sub(r"(?<!%)%([a-zA-Z])(?![a-zA-Z0-9_%])", r"%%\1", command)


def docker_status():
    """מחזיר (זמין?, הודעה)."""
    if not shutil.which("docker"):
        return False, "Docker לא מותקן או לא נמצא ב-PATH"
    try:
        out = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"שגיאה בבדיקת Docker: {e}"
    if out.returncode != 0:
        return False, "Docker לא רץ (הפעילי את Docker Desktop)"
    if out.stdout.strip() != "windows":
        return False, "Docker במצב Linux containers - צריך להחליף ל-Windows containers"
    return True, "Docker זמין"


def run_in_sandbox(command: str, timeout: int = TIMEOUT) -> dict:
    ok, msg = docker_status()
    if not ok:
        return {"status": "unavailable", "returncode": None, "output": msg}

    name = f"cli-sandbox-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmp:
        script = "@echo off\r\nchcp 65001 >nul\r\n" + FIXTURES + "\r\n" + to_batch(command) + "\r\n"
        (Path(tmp) / "run.cmd").write_text(script, encoding="utf-8")
        docker_cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none",
            "--memory", "512m",
            "--cpus", "1",
            "-v", f"{tmp}:C:\\input:ro",
            IMAGE,
            "cmd", "/c", "C:\\input\\run.cmd",
        ]
        try:
            proc = subprocess.run(
                docker_cmd, capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            return {"status": "timeout", "returncode": None, "output": f"הפקודה לא הסתיימה תוך {timeout} שניות"}

    output = (proc.stdout + proc.stderr).strip()
    status = "ok" if proc.returncode == 0 else "error"
    return {"status": status, "returncode": proc.returncode, "output": output[-2000:]}
