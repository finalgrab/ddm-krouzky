#!/usr/bin/env python3
"""Monitor nových kroužků DDM Karlínské Spektrum.

Porovnává aktuální stav webu s předchozím scrapem.
Detekuje nové a odstraněné kroužky.
Generuje report pro emailovou notifikaci.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scraper import scrape_courses

DATA_DIR = Path(__file__).parent / "data"
COURSES_FILE = DATA_DIR / "courses.json"
HISTORY_FILE = DATA_DIR / "history.json"
REPORT_FILE = DATA_DIR / "new_courses_report.txt"


def format_course(c: dict) -> str:
    sched = ", ".join(
        f'{s["day"]} {s["timeFrom"]}–{s["timeTo"]}' for s in c["schedules"]
    )
    return (
        f'  {c["name"]}\n'
        f'    Věk: {c["ageFrom"]}–{c["ageTo"]} let\n'
        f'    Kdy: {sched}\n'
        f'    Kde: {c.get("locationFull", c.get("locationAbbr", ""))}\n'
        f'    Stav: {c.get("status", "")}\n'
        f'    Web: https://ddmpraha.cz/karlinske-spektrum/krouzky#id={c["id"]}'
    )


def monitor():
    DATA_DIR.mkdir(exist_ok=True)

    # Clean up previous report
    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    # Load previous state
    previous_ids = set()
    if COURSES_FILE.exists():
        prev = json.loads(COURSES_FILE.read_text(encoding="utf-8"))
        previous_ids = {c["id"] for c in prev["courses"]}

    # Scrape current state
    now = datetime.now().isoformat()
    print(f"[{now}] Scraping courses...")
    courses = scrape_courses()
    current_ids = {c["id"] for c in courses}
    print(f"Found {len(courses)} courses")

    # Detect changes
    new_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    new_courses = [c for c in courses if c["id"] in new_ids]

    # Load/update history
    history = []
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

    if new_courses:
        print(f"\n🆕 NOVÉ KROUŽKY ({len(new_courses)}):")
        for c in new_courses:
            sched = ", ".join(
                f'{s["day"]} {s["timeFrom"]}–{s["timeTo"]}' for s in c["schedules"]
            )
            print(f'  + [{c["id"]}] {c["name"]} ({c["ageFrom"]}–{c["ageTo"]} let, {sched})')

        history.append({
            "timestamp": now,
            "event": "new_courses",
            "courseIds": [c["id"] for c in new_courses],
            "courseNames": [c["name"] for c in new_courses],
        })

        # Filter by child age for the report
        children = {"Vojta (11 let)": 11, "Kryštof (10 let)": 10, "Eli (7 let)": 7}
        report_lines = [
            f"Nalezeno {len(new_courses)} nových kroužků!\n",
            f"Čas: {now}\n",
        ]

        for child_name, age in children.items():
            matching = [c for c in new_courses if c["ageFrom"] <= age <= c["ageTo"]]
            if matching:
                report_lines.append(f"\n{'='*50}")
                report_lines.append(f"Kroužky pro {child_name} ({len(matching)}):")
                report_lines.append(f"{'='*50}\n")
                for c in matching:
                    report_lines.append(format_course(c))
                    report_lines.append("")

        # Also list courses that don't match any child
        all_matching_ids = set()
        for age in children.values():
            for c in new_courses:
                if c["ageFrom"] <= age <= c["ageTo"]:
                    all_matching_ids.add(c["id"])
        unmatched = [c for c in new_courses if c["id"] not in all_matching_ids]
        if unmatched:
            report_lines.append(f"\n{'='*50}")
            report_lines.append(f"Ostatní nové kroužky (mimo věk dětí) ({len(unmatched)}):")
            report_lines.append(f"{'='*50}\n")
            for c in unmatched:
                report_lines.append(format_course(c))
                report_lines.append("")

        report = "\n".join(report_lines)
        REPORT_FILE.write_text(report, encoding="utf-8")
        print(f"\nReport uložen do {REPORT_FILE}")

    else:
        print("Žádné nové kroužky.")

    if removed_ids:
        print(f"\n❌ ODSTRANĚNÉ KROUŽKY ({len(removed_ids)}): {sorted(removed_ids)}")
        history.append({
            "timestamp": now,
            "event": "removed_courses",
            "courseIds": sorted(removed_ids),
        })

    # Save current state
    output = {
        "scrapedAt": now,
        "totalCourses": len(courses),
        "courses": courses,
    }
    COURSES_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nData uložena do {COURSES_FILE}")
    return new_courses, removed_ids


if __name__ == "__main__":
    new_courses, removed = monitor()
