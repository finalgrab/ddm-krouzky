#!/usr/bin/env python3
"""Monitor nových kroužků DDM Karlínské Spektrum.

Detekuje kroužky pro nový školní rok podle data zahájení (> MIN_START_DATE).
Porovnává s již známými novými kroužky a notifikuje o brand new.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from scraper import scrape_courses, fetch_start_date

# Kroužky s datem zahájení po tomto datu považujeme za nový školní rok
MIN_START_DATE = "2026-08-30"

DATA_DIR = Path(__file__).parent / "data"
COURSES_FILE = DATA_DIR / "courses.json"
HISTORY_FILE = DATA_DIR / "history.json"
REPORT_FILE = DATA_DIR / "new_courses_report.txt"
# Cache start dates so we don't re-fetch detail pages for known courses
START_DATES_CACHE_FILE = DATA_DIR / "start_dates_cache.json"


def load_known_new_ids() -> set:
    """Load IDs of courses already in courses.json (previously detected new ones)."""
    if COURSES_FILE.exists():
        data = json.loads(COURSES_FILE.read_text(encoding="utf-8"))
        return {c["id"] for c in data.get("courses", [])}
    return set()


def load_start_dates_cache() -> dict:
    """Load cached start dates {id_str: {date: 'YYYY-MM-DD', fetched: 'ISO timestamp'}}."""
    if START_DATES_CACHE_FILE.exists():
        return json.loads(START_DATES_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_start_dates_cache(cache: dict):
    START_DATES_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# Re-check old-year courses at most once per day
OLD_COURSE_CACHE_TTL_HOURS = 24


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

    known_new_ids = load_known_new_ids()
    start_dates_cache = load_start_dates_cache()

    now = datetime.now().isoformat()
    print(f"[{now}] Scraping courses...")
    print(f"  Known new: {len(known_new_ids)} previously detected new-year courses")
    print(f"  Min start date: {MIN_START_DATE}")

    scraped = scrape_courses()
    scraped_by_id = {c["id"]: c for c in scraped}
    print(f"  Scraped: {len(scraped)} courses on web")

    # For each scraped course, determine start date.
    # New-year dates are cached permanently (they won't change back).
    # Old-year dates are cached with TTL — re-checked once per day
    # in case DDM recycles the ID for the new school year.
    new_year_courses = []
    fetch_count = 0
    now_dt = datetime.fromisoformat(now)
    for c in scraped:
        cid_str = str(c["id"])
        cached = start_dates_cache.get(cid_str)
        need_fetch = True

        if cached:
            is_new_year = cached["date"] and cached["date"] > MIN_START_DATE
            if is_new_year:
                # New-year course — trust cache permanently
                need_fetch = False
            else:
                # Old-year course — re-check after TTL
                age_hours = (now_dt - datetime.fromisoformat(cached["fetched"])).total_seconds() / 3600
                if age_hours < OLD_COURSE_CACHE_TTL_HOURS:
                    need_fetch = False

        if need_fetch:
            start_date = fetch_start_date(c["id"])
            start_dates_cache[cid_str] = {"date": start_date, "fetched": now}
            fetch_count += 1
        else:
            start_date = cached["date"]

        c["startDate"] = start_date
        if start_date and start_date > MIN_START_DATE:
            new_year_courses.append(c)

    if fetch_count:
        print(f"  Fetched {fetch_count} detail pages for start dates")
    save_start_dates_cache(start_dates_cache)

    print(f"  New-year courses (start > {MIN_START_DATE}): {len(new_year_courses)}")

    # Brand new = new-year courses not yet in courses.json
    new_year_ids = {c["id"] for c in new_year_courses}
    brand_new_ids = new_year_ids - known_new_ids
    brand_new_courses = [c for c in new_year_courses if c["id"] in brand_new_ids]

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
            print(f'  + [{c["id"]}] {c["name"]} ({c["ageFrom"]}–{c["ageTo"]} let, {sched}, start: {c["startDate"]})')

        history.append({
            "timestamp": now,
            "event": "new_courses",
            "courseIds": [c["id"] for c in brand_new_courses],
            "courseNames": [c["name"] for c in brand_new_courses],
        })

        # Build email report grouped by child
        children = {"Vojta (11 let)": 11, "Kryštof (10 let)": 10, "Eli (7 let)": 7}
        report_lines = [
            f"Nalezeno {len(brand_new_courses)} nových kroužků pro školní rok 2026/27!\n",
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

    # Save all new-year courses to courses.json (for the web planner)
    output = {
        "scrapedAt": now,
        "totalCourses": len(new_year_courses),
        "courses": new_year_courses,
    }
    COURSES_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nNew-year courses: {len(new_year_courses)}")
    print(f"Data uložena do {COURSES_FILE}")
    return brand_new_courses


if __name__ == "__main__":
    brand_new = monitor()
