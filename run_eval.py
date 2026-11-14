"""
הרצת כל תרחישי הבדיקה (scenarios.csv) מול גרסת פרומפט, ושמירת התוצאות.

דוגמאות:
    uv run run_eval.py --version v1
    uv run run_eval.py --all
    uv run run_eval.py --version v4 --sandbox      # כולל הרצה ב-Docker (בונוס)
    uv run run_eval.py --report                    # רק לבנות מחדש את האקסל מתוצאות קיימות

פלט (בתיקייה results/):
    iteration_v1.csv ...   - גיליון לכל איטרציה (אפשר לייבא ל-Google Sheets)
    results.xlsx           - כל האיטרציות בגיליונות נפרדים + גיליון Summary להשוואה
    failures_v1.md ...     - רשימת התרחישים שנכשלו בכל איטרציה, לניתוח
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from agent import generate, list_versions
from safety import BLOCKED, REFUSED
from evaluator import evaluate

ROOT = Path(__file__).parent
SCENARIOS = ROOT / "scenarios.csv"
RESULTS = ROOT / "results"

COLUMNS = [
    "id", "category", "input", "expected_command", "expected_safety",
    "raw_output", "command", "safety_level", "safety_reasons",
    "format_ok", "syntax_ok", "safety_ok", "correct_auto", "correct_manual",
    "sandbox_status", "sandbox_output", "score", "notes",
]
METRICS = ["format_ok", "syntax_ok", "safety_ok", "correct_auto", "score"]


def load_scenarios() -> list:
    with open(SCENARIOS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_version(version: str, use_sandbox: bool = False, sandbox_all: bool = False) -> Path:
    rows = []
    scenarios = load_scenarios()
    for i, sc in enumerate(scenarios, 1):
        print(f"[{version}] {i}/{len(scenarios)}: {sc['input'][:50]}")
        try:
            res = generate(sc["input"], version)
            raw, command, verdict = res.raw, res.command, res.safety
            level, reasons = verdict.level, " | ".join(verdict.reasons)
        except Exception as e:  # noqa: BLE001
            raw, command, level, reasons = f"ERROR: {e}", "", REFUSED, ""

        row = dict(sc)
        row.update(raw_output=raw, command=command, safety_level=level, safety_reasons=reasons)
        row.update(evaluate(sc, raw, command, level))
        row["correct_manual"] = ""

        row["sandbox_status"], row["sandbox_output"] = "", ""
        if use_sandbox and level != REFUSED and (sandbox_all or level != BLOCKED):
            from sandbox import run_in_sandbox

            sb = run_in_sandbox(command)
            row["sandbox_status"], row["sandbox_output"] = sb["status"], sb["output"]
        rows.append(row)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"iteration_{version}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    write_failures(version, rows)
    print_summary(version, rows)
    return out


def read_iteration(path: Path) -> list:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def averages(rows: list) -> dict:
    if not rows:
        return {m: 0 for m in METRICS}
    return {m: round(sum(float(r[m] or 0) for r in rows) / len(rows), 3) for m in METRICS}


def print_summary(version: str, rows: list):
    avg = averages(rows)
    print(f"\n=== {version} ===")
    for m, v in avg.items():
        print(f"  {m:13s} {v:.0%}")


def write_failures(version: str, rows: list):
    failed = [r for r in rows if float(r["score"]) < 1]
    by_cat = defaultdict(list)
    for r in failed:
        by_cat[r["category"]].append(r)
    lines = [f"# כשלים - {version}", "", f"נכשלו {len(failed)} מתוך {len(rows)} תרחישים.", ""]
    for cat, items in sorted(by_cat.items()):
        lines.append(f"## {cat} ({len(items)})")
        for r in items:
            lines += [
                f"- **#{r['id']}** {r['input']}",
                f"  - צפוי: `{r['expected_command'] or '(סירוב/חסימה)'}` ({r['expected_safety']})",
                f"  - התקבל: `{r['raw_output'].replace(chr(10), ' ⏎ ')}` -> {r['safety_level']}",
                f"  - הערות: {r['notes']}",
            ]
        lines.append("")
    (RESULTS / f"failures_{version}.md").write_text("\n".join(lines), encoding="utf-8")


def build_report():
    """בונה results.xlsx: גיליון לכל איטרציה + Summary עם מגמת השיפור."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.chart import BarChart, Reference

    files = sorted(RESULTS.glob("iteration_v*.csv"), key=lambda p: int(p.stem.split("_v")[1]))
    if not files:
        print("אין תוצאות. הריצי קודם: uv run run_eval.py --version v1")
        return

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.sheet_view.rightToLeft = True
    green = PatternFill("solid", fgColor="C6EFCE")
    red = PatternFill("solid", fgColor="FFC7CE")
    bold = Font(bold=True)

    all_data = {}
    for path in files:
        version = path.stem.replace("iteration_", "")
        rows = read_iteration(path)
        all_data[version] = rows
        ws = wb.create_sheet(version)
        ws.sheet_view.rightToLeft = True
        ws.append(COLUMNS)
        for c in ws[1]:
            c.font = bold
        for r in rows:
            ws.append([float(r[c]) if c in METRICS and r[c] != "" else r.get(c, "") for c in COLUMNS])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if COLUMNS[cell.column - 1] in METRICS[:-1]:
                    cell.fill = green if cell.value == 1 else red
        widths = {"input": 45, "raw_output": 40, "command": 35, "expected_command": 30,
                  "notes": 40, "safety_reasons": 30, "sandbox_output": 40}
        for i, col in enumerate(COLUMNS, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = widths.get(col, 13)
        ws.freeze_panes = "D2"

    # טבלת סיכום לפי איטרציה
    summary.append(["version"] + METRICS)
    for c in summary[1]:
        c.font = bold
    for version, rows in all_data.items():
        avg = averages(rows)
        summary.append([version] + [avg[m] for m in METRICS])
    n = len(all_data)
    for row in summary.iter_rows(min_row=2, max_row=n + 1, min_col=2):
        for cell in row:
            cell.number_format = "0%"

    chart = BarChart()
    chart.title = "שיפור בין איטרציות"
    chart.y_axis.scaling.max = 1
    chart.add_data(Reference(summary, min_col=2, max_col=len(METRICS) + 1, min_row=1, max_row=n + 1),
                   titles_from_data=True)
    chart.set_categories(Reference(summary, min_col=1, min_row=2, max_row=n + 1))
    chart.width, chart.height = 22, 10
    summary.add_chart(chart, f"A{n + 4}")

    # ציון לפי קטגוריה - איפה כל גרסה נשברת
    start = n + 26
    categories = sorted({r["category"] for rows in all_data.values() for r in rows})
    summary.cell(start, 1, "score לפי קטגוריה").font = bold
    summary.cell(start + 1, 1, "category").font = bold
    for j, version in enumerate(all_data, 2):
        summary.cell(start + 1, j, version).font = bold
    for i, cat in enumerate(categories, start + 2):
        summary.cell(i, 1, cat)
        for j, (version, rows) in enumerate(all_data.items(), 2):
            cat_rows = [r for r in rows if r["category"] == cat]
            cell = summary.cell(i, j, averages(cat_rows)["score"])
            cell.number_format = "0%"
    summary.column_dimensions["A"].width = 18

    out = RESULTS / "results.xlsx"
    wb.save(out)
    print(f"נשמר: {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="גרסת פרומפט, למשל v1")
    parser.add_argument("--all", action="store_true", help="להריץ את כל הגרסאות")
    parser.add_argument("--sandbox", action="store_true", help="להריץ כל פקודה ב-Docker")
    parser.add_argument("--sandbox-all", action="store_true", help="להריץ ב-Docker גם פקודות חסומות")
    parser.add_argument("--report", action="store_true", help="רק לבנות את results.xlsx")
    args = parser.parse_args()

    if not args.report:
        versions = list_versions() if args.all else [args.version or list_versions()[-1]]
        for v in versions:
            run_version(v, args.sandbox or args.sandbox_all, args.sandbox_all)
    build_report()


if __name__ == "__main__":
    main()
