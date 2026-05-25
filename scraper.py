#!/usr/bin/env python3
"""Scraper kroužků DDM Karlínské Spektrum."""

import re
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LISTING_URL = "https://ddmpraha.cz/modul/aktivity/vypis.php?pobocka=1&type=krouzky"

LOCATIONS = {
    "KS": "Karlínské Spektrum",
    "SM": "Stadion mládeže",
    "SP": "Stanice přírodovědců",
    "ST": "Stanice techniků",
    "KK": "Klub Klamovka",
    "JSZ": "Jezdecké středisko Zmrzlík",
    "DDM": "DDM hl. m. Prahy",
    "SPI": "Spirála",
}

DAY_FULL = {
    "PO": "Pondělí",
    "ÚT": "Úterý",
    "ST": "Středa",
    "ČT": "Čtvrtek",
    "PÁ": "Pátek",
    "SO": "Sobota",
    "NE": "Neděle",
}

DAY_ORDER = ["PO", "ÚT", "ST", "ČT", "PÁ", "SO", "NE"]


def parse_schedule(text: str) -> list[dict]:
    """Parse schedule strings like 'PO 17:00–18:00' or 'PO–PÁ 08:00–13:00'."""
    schedules = []

    # Day range: PO–PÁ 08:00–13:00
    m = re.match(
        r"^(PO|ÚT|ST|ČT|PÁ|SO|NE)[–-](PO|ÚT|ST|ČT|PÁ|SO|NE)\s+(\d{2}:\d{2})[–-](\d{2}:\d{2})$",
        text.strip(),
    )
    if m:
        start_idx = DAY_ORDER.index(m.group(1))
        end_idx = DAY_ORDER.index(m.group(2))
        for i in range(start_idx, end_idx + 1):
            schedules.append({
                "day": DAY_ORDER[i],
                "dayFull": DAY_FULL[DAY_ORDER[i]],
                "timeFrom": m.group(3),
                "timeTo": m.group(4),
            })
        return schedules

    # Individual day-time pairs: PO 17:00–18:00 ST 16:00–17:00
    for m in re.finditer(
        r"(PO|ÚT|ST|ČT|PÁ|SO|NE)\s+(\d{2}:\d{2})[–-](\d{2}:\d{2})", text
    ):
        schedules.append({
            "day": m.group(1),
            "dayFull": DAY_FULL[m.group(1)],
            "timeFrom": m.group(2),
            "timeTo": m.group(3),
        })
    return schedules


def parse_age(text: str) -> tuple[int, int]:
    m = re.search(r"(\d+)[–-](\d+)\s*let", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 99


def scrape_courses() -> list[dict]:
    resp = requests.get(LISTING_URL, verify=False, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (DDM Krouzky Monitor)"
    })
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    courses = []
    for card in soup.select("div.col-xl-4"):
        link = card.select_one("a")
        if not link or not link.get("href"):
            continue
        id_match = re.search(r"id=(\d+)", link["href"])
        if not id_match:
            continue
        cid = int(id_match.group(1))

        name_el = card.select_one(".name")
        name = name_el.get_text(strip=True) if name_el else ""

        # Get activity div text (contains age + schedule)
        activity_div = card.select_one(".col-activity")
        if not activity_div:
            continue

        # Get text after the name div
        # Remove name element, then get remaining text
        for name_div in activity_div.select(".name"):
            name_div.decompose()
        remaining = activity_div.get_text(" ", strip=True)

        age_from, age_to = parse_age(remaining)
        schedule_text = re.sub(r"^\d+[–-]\d+\s*let\s*", "", remaining).strip()
        schedules = parse_schedule(schedule_text)

        loc_el = card.select_one(".col-activity-IK")
        loc_abbr = loc_el.get_text(strip=True) if loc_el else ""
        loc_full = LOCATIONS.get(loc_abbr, loc_abbr)

        status_el = card.select_one(".prelep")
        status = status_el.get_text(strip=True) if status_el else "VOLNÁ MÍSTA"

        courses.append({
            "id": cid,
            "name": name,
            "ageFrom": age_from,
            "ageTo": age_to,
            "schedules": schedules,
            "locationAbbr": loc_abbr,
            "locationFull": loc_full,
            "status": status,
            "url": f"https://ddmpraha.cz/karlinske-spektrum/krouzky#id={cid}",
        })

    return courses


def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    courses = scrape_courses()
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    output = {
        "scrapedAt": datetime.now().isoformat(),
        "totalCourses": len(courses),
        "courses": courses,
    }
    out_file = data_dir / "courses.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Scraped {len(courses)} courses → {out_file}")
    return courses


if __name__ == "__main__":
    main()
