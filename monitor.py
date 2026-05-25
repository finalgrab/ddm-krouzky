#!/usr/bin/env python3
"""Monitor nových kroužků DDM Karlínské Spektrum.

Porovnává aktuální stav webu s baseline (staré kroužky) + již známými novými.
Do courses.json zapisuje JEN nové kroužky (ne staré z minulého roku).
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
BASELINE_FILE = DATA_DIR / "baseline_ids.json"
COURSES_FILE = DATA_DIR / "courses.json"
HISTORY_FILE = DATA_DIR / "history.json"
REPORT_FILE = DATA_DIR / "new_courses_report.txt"


def load_baseline_ids() -> set:
    """Load IDs of old courses (current school year) that should be ignored."""
    if BASELINE_FILE.exists():
        return set(json.loads(BASELINE_FILE.read_text(encoding="utf-8")))
    return set()


def load_known_new_ids() -> set:
    """Load IDs of courses already in courses.json (previously detected new ones)."""
    if COURSES_FILE.exists():
        data = json.loads(COURSES_FILE.read_text(encoding="utf-8"))
        return {c["id"] for c in data.get("courses", [])}
    return set()


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

    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    baseline_ids = load_baseline_ids()
    known_new_ids = load_known_new_ids()
    # All IDs we already know about (baseline + previously detected new)
    all_known_ids = baseline_ids | known_new_ids

    now = datetime.now().isoformat()
    print(f"[{now}] Scraping courses...")
    print(f"  Baseline: {len(baseline_ids)} old course IDs")
    print(f"  Known new: {len(known_new_ids)} previously detected new courses")

    scraped = scrape_courses()
    scraped_ids = {c["id"] for c in scraped}
    print(f"  Scraped: {len(scraped)} courses on web")

    # Newly appeared = on web but not in any known set
    brand_new_ids = scraped_ids - all_known_ids
    brand_new_courses = [c for c in scraped if c["id"] in brand_new_ids]

    # Courses to show on web = everything that's NOT in baseline
    web_courses = [c for c in scraped if c["id"] not in baseline_ids]

    # Load history
    history = []
    if HISTORY_FILE.exists():
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

    if brand_new_courses:
        print(f"\n🆕 NOVÉ KROUŽKY ({len(brand_new_courses)}):")
        for c in brand_new_courses:
            sched = ", ".join(
                f'{s["day"]} {s["timeFrom"]}–{s["timeTo"]}' for s in c["schedules"]
            )
            print(f'  + [{c["id"]}] {c["name"]} ({c["ageFrom"]}–{c["ageTo"]} let, {sched})')

        history.append({
            "timestamp": now,
            "event": "new_courses",
            "courseIds": [c["id"] for c in brand_new_courses],
            "courseNames": [c["name"] for c in brand_new_courses],
        })

        # Build email report grouped by child
        children = {"Vojta (11 let)": 11, "Kryštof (10 let)": 10, "Eli (7 let)": 7}
        report_lines = [
            f"Nalezeno {len(brand_new_courses)} nových kroužků!\n",
            f"Čas: {now}\n",
        ]

        for child_name, age in children.items():
            matching = [c for c in brand_new_courses if c["ageFrom"] <= age <= c["ageTo"]]
            if matching:
                report_lines.append(f"\n{'='*50}")
                report_lines.append(f"Kroužky pro {child_name} ({len(matching)}):")
                report_lines.append(f"{'='*50}\n")
                for c in matching:
                    report_lines.append(format_course(c))
                    report_lines.append("")

        all_matching_ids = set()
        for age in children.values():
            for c in brand_new_courses:
                if c["ageFrom"] <= age <= c["ageTo"]:
                    all_matching_ids.add(c["id"])
        unmatched = [c for c in brand_new_courses if c["id"] not in all_matching_ids]
        if unmatched:
            report_lines.append(f"\n{'='*50}")
            report_lines.append(f"Ostatní nové kroužky ({len(unmatched)}):")
            report_lines.append(f"{'='*50}\n")
            for c in unmatched:
                report_lines.append(format_course(c))
                report_lines.append("")

        report = "\n".join(report_lines)
        REPORT_FILE.write_text(report, encoding="utf-8")
        print(f"\nReport uložen do {REPORT_FILE}")
    else:
        print("\nŽádné nové kroužky.")

    # Save web-visible courses (only non-baseline)
    output = {
        "scrapedAt": now,
        "totalCourses": len(web_courses),
        "courses": web_courses,
    }
    COURSES_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nWeb courses: {len(web_courses)} (excluding {len(baseline_ids)} baseline)")
    print(f"Data uložena do {COURSES_FILE}")
    return brand_new_courses


if __name__ == "__main__":
    brand_new = monitor()
