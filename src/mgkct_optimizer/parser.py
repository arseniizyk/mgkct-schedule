#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live web scraper and parser for MGKCT weekly academic timetables.
Extracts real group schedules, real teacher assignments, subjects, subgroups,
classrooms, and bell-grid volumes directly from mgkct.minskedu.gov.by.
Detects Belarusian public holidays for the academic week.
"""

import datetime
import json
import os
import re
import ssl
import sys
import urllib.request
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .holidays import get_week_holidays, parse_date
from .loader import (
    AFTERNOON_SHIFT_GROUPS,
    OPFR_GROUPS,
    get_default_curriculum_path,
    load_curriculum_data,
)
from .models import CurriculumItem, GroupInfo, RoomInfo, get_required_room_type

STUDENTS_TIMETABLE_URL = "https://mgkct.minskedu.gov.by/personnel/for-students/weekly-timetable"
TEACHERS_TIMETABLE_URL = "https://mgkct.minskedu.gov.by/personnel/for-teachers/weekly-timetable"

CODE_TO_FULL_GROUP = {
    "100": "100МНЭ",
    "101": "101ТП",
    "102": "102М",
    "103": "103М",
    "104": "104РТК",
    "105": "105ТП",
    "106": "106МНЭ",
    "107": "107ТЭ",
    "108": "108ТЭ",
    "109": "109ТП",
    "167": "167ТП",
    "168": "168МНЭ",
    "169": "169ТП",
    "79": "79ТЭ",
    "80": "80РТК",
    "81": "81ТП",
    "82": "82ТП",
    "83": "83МНЭ",
    "84": "84МНЭ",
    "85": "85М",
    "86": "86РТК",
    "87": "87ТП",
    "88": "88ТП",
    "89": "89ТП",
    "90": "90МНЭ",
    "91": "91МНЭ",
    "92": "92МНЭ",
    "93": "93МНЭ",
    "94": "94ТП",
    "95": "95М",
    "96": "96РТК",
    "97": "97РТК",
    "98": "98ТП",
    "99": "99ТП",
    "9": "9СР",
}

ROOM_ALIAS_MAP = {
    "Кн 1-109(к)": "Кн.1-109 (к)",
    "Кн.1-109(к)": "Кн.1-109 (к)",
    "Кн.1-224(к)": "Кн.1-224 (к)",
    "3-205(к)": "3-205 (к)",
    "3-208(к)": "3-208 (к)",
    "3-212(к)": "3-212 (к)",
    "3-103(лаб)": "3-103 (лаб)",
    "3-103 к": "3-103 (лаб)",
    "501(к)": "501 (к)",
    "503(к)": "503 (к)",
    "504(к)": "504 (к)",
}


def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetches text content from URL with browser-like user agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return response.read().decode("utf-8")


def parse_date_range(html: str) -> Tuple[str, str]:
    """Extracts start date and end date of schedule week from H3."""
    m = re.search(r"<h3>(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})</h3>", html)
    if m:
        start_raw, end_raw = m.groups()
        start_iso = datetime.datetime.strptime(start_raw, "%d.%m.%Y").strftime("%Y-%m-%d")
        end_iso = datetime.datetime.strptime(end_raw, "%d.%m.%Y").strftime("%Y-%m-%d")
        return start_iso, end_iso
    return "2026-11-02", "2026-11-08"


def clean_html_lines(html_text: str) -> List[str]:
    """Splits cell by <br> tags and strips HTML tags and non-breaking spaces."""
    lines = [
        re.sub(r"<[^>]+>", "", l).strip()
        for l in re.split(r"<br\s*/?>", html_text)
        if l.strip() and l.strip() != "&nbsp;"
    ]
    return lines


def parse_slot_cell(
    s_lines: List[str], r_lines: List[str]
) -> List[Tuple[int, str, str, str, str]]:
    """
    Parses subject cell lines and room cell lines into list of lessons:
    [(subgroup, subject, lesson_type, teacher, room)]
    """
    sub_chunks: List[Tuple[Optional[int], List[str]]] = []
    current_sub = None
    current_chunk: List[str] = []

    for line in s_lines:
        m = re.match(r"^([123])\.(.*)", line)
        if m:
            if current_chunk:
                sub_chunks.append((current_sub, current_chunk))
            current_sub = int(m.group(1))
            rem = m.group(2).strip()
            current_chunk = [rem] if rem else []
        else:
            current_chunk.append(line)
    if current_chunk:
        sub_chunks.append((current_sub, current_chunk))

    if not sub_chunks:
        return []

    items = []
    if sub_chunks[0][0] is None:
        # Undivided lesson
        chunk = sub_chunks[0][1]
        subj = chunk[0] if len(chunk) > 0 else ""
        ltype = ""
        teacher = ""
        if len(chunk) > 1:
            tm = re.match(r"^\((.*?)\)$", chunk[1])
            if tm:
                ltype = tm.group(1)
                teacher = chunk[2] if len(chunk) > 2 else ""
            else:
                teacher = chunk[1]
        room = r_lines[0] if r_lines else ""
        items.append((0, subj, ltype, teacher, room))
    else:
        # Lessons for subgroups
        for idx, (sub_k, chunk) in enumerate(sub_chunks):
            subj = chunk[0] if len(chunk) > 0 else ""
            ltype = ""
            teacher = ""
            if len(chunk) > 1:
                tm = re.match(r"^\((.*?)\)$", chunk[1])
                if tm:
                    ltype = tm.group(1)
                    teacher = chunk[2] if len(chunk) > 2 else ""
                else:
                    teacher = chunk[1]
            room = r_lines[idx] if idx < len(r_lines) else (r_lines[0] if r_lines else "")
            items.append((sub_k or 0, subj, ltype, teacher, room))

    return items


def normalize_room_name(name: str) -> str:
    """Standardizes room spelling and aliases."""
    r = name.strip()
    return ROOM_ALIAS_MAP.get(r, r)


def parse_schedule_html(
    html: str,
    base_groups: Optional[List[GroupInfo]] = None,
    base_rooms: Optional[List[RoomInfo]] = None,
) -> Dict[str, Any]:
    """
    Parses MGKCT schedule HTML into structured curriculum data dict.
    Preserves group metadata, extracts real teachers, subjects, and rooms,
    and detects Belarus holidays.
    """
    start_date_iso, end_date_iso = parse_date_range(html)
    holidays_dict = get_week_holidays(start_date_iso)

    # Catalogs from base loader
    if not base_groups or not base_rooms:
        base_groups, base_rooms, _ = load_curriculum_data()

    group_map = {g.name: g for g in base_groups}
    room_map = {(r.campus, r.name): r for r in base_rooms}
    all_rooms_set = {r.name for r in base_rooms}

    tables = re.findall(r"<h2>Группа - (.*?)</h2>.*?<table.*?>(.*?)</table>", html, re.DOTALL)

    # Aggregators
    group_item_counts: Dict[str, Dict[Tuple[str, str, str, int], int]] = defaultdict(
        lambda: defaultdict(int)
    )
    group_item_rooms: Dict[str, Dict[Tuple[str, str, str, int], Set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    group_subgroup_sync: Dict[str, Set[Tuple[int, ...]]] = defaultdict(set)
    active_teachers_set: Set[str] = set()

    for g_raw, tbl in tables:
        g_code = g_raw.replace("*", "").strip()
        g_name = CODE_TO_FULL_GROUP.get(g_code, g_code)
        is_opfr = g_name in OPFR_GROUPS

        rows = re.findall(r"<tr>(.*?)</tr>", tbl, re.DOTALL)
        for r_idx, r in enumerate(rows[2:]):
            cells = re.findall(r"<td.*?>(.*?)</td>", r, re.DOTALL)
            if len(cells) < 12:
                continue

            for d in range(6):
                s_raw = cells[d * 2].strip()
                r_raw = cells[d * 2 + 1].strip()
                if not s_raw or s_raw == "&nbsp;":
                    continue

                s_lines = clean_html_lines(s_raw)
                r_lines = clean_html_lines(r_raw)
                parsed_lessons = parse_slot_cell(s_lines, r_lines)

                if is_opfr:
                    # OPFR groups never split
                    parsed_lessons = [
                        (0, subj, ltype, teacher, room)
                        for (_, subj, ltype, teacher, room) in parsed_lessons
                    ]

                for sub_k, subj, ltype, teacher, room in parsed_lessons:
                    room_norm = normalize_room_name(room)
                    key = (subj, ltype, teacher, sub_k)
                    group_item_counts[g_name][key] += 1
                    if room_norm and room_norm != "-":
                        group_item_rooms[g_name][key].add(room_norm)
                        all_rooms_set.add(room_norm)
                    if teacher:
                        active_teachers_set.add(teacher)

                if len(parsed_lessons) >= 2 and not is_opfr:
                    subs_tuple = tuple(sorted(p[0] for p in parsed_lessons if p[0] > 0))
                    if len(subs_tuple) >= 2:
                        group_subgroup_sync[g_name].add(subs_tuple)

    # Build curriculum items
    curriculum_items_list = []
    item_id_counter = 0

    for g_name, items_dict in group_item_counts.items():
        is_opfr = g_name in OPFR_GROUPS

        # Map to find paired items
        pe_sub_items = []
        for (subj, ltype, teacher, sub_k), count in items_dict.items():
            if ("ФЗКиЗ" in subj or ltype == "ФЗКиЗ") and sub_k > 0:
                pe_sub_items.append((subj, ltype, teacher, sub_k, count))

        pe_paired_id = f"{g_name}_ФЗКиЗ_subgroups" if len(pe_sub_items) >= 2 else None

        for (subj, ltype, teacher, sub_k), count in items_dict.items():
            home_rooms = sorted(group_item_rooms[g_name].get((subj, ltype, teacher, sub_k), []))
            is_double = (
                ltype in ("ЛР", "Пр-ка", "КП")
                or "ФЗКиЗ" in subj
                or "практ" in subj.lower()
            )

            paired_id = None
            if not is_opfr and sub_k > 0:
                if ("ФЗКиЗ" in subj or ltype == "ФЗКиЗ") and pe_paired_id:
                    paired_id = pe_paired_id
                else:
                    # Check if other subgroups take this subject
                    other_subs = [
                        sk
                        for (s, lt, t, sk) in items_dict.keys()
                        if s == subj and sk != sub_k and sk > 0
                    ]
                    if other_subs:
                        paired_id = f"{g_name}_{subj}_subgroups"

            curriculum_items_list.append({
                "item_id": item_id_counter,
                "group": g_name,
                "subject": subj,
                "lesson_type": ltype or "Лек",
                "teacher": teacher or "Преподаватель",
                "weekly_pairs": count,
                "subgroup": 0 if is_opfr else sub_k,
                "paired_id": paired_id,
                "home_rooms": home_rooms,
                "is_double_pair_ok": is_double,
            })
            item_id_counter += 1

    # Prepare groups list
    groups_data = []
    for g_name, g_obj in group_map.items():
        groups_data.append({
            "name": g_obj.name,
            "code_on_site": next((k for k, v in CODE_TO_FULL_GROUP.items() if v == g_obj.name), g_obj.name),
            "campus": g_obj.campus,
            "course": g_obj.course,
            "specialty_code": g_obj.specialty_code,
            "specialty_name": g_obj.specialty_name,
            "qualification": g_obj.qualification,
            "max_daily_pairs": g_obj.max_daily_pairs,
            "is_opfr": g_obj.is_opfr,
            "shift": g_obj.shift,
        })

    # Prepare rooms list
    rooms_data = [
        {"name": r.name, "campus": r.campus, "room_type": r.room_type}
        for r in base_rooms
    ]

    result = {
        "metadata": {
            "college": "УО «Минский государственный колледж цифровых технологий» (МГКЦТ)",
            "source_students": STUDENTS_TIMETABLE_URL,
            "source_teachers": TEACHERS_TIMETABLE_URL,
            "extracted_at": datetime.datetime.now().strftime("%Y-%m-%d"),
            "week_start_date": start_date_iso,
            "week_end_date": end_date_iso,
            "belarus_holidays": {str(k): v for k, v in holidays_dict.items()},
            "total_groups": len(groups_data),
            "total_curriculum_items": len(curriculum_items_list),
            "total_rooms": len(rooms_data),
            "active_teachers": len(active_teachers_set),
        },
        "groups": groups_data,
        "rooms": rooms_data,
        "curriculum_items": curriculum_items_list,
    }
    return result


def scrape_and_update_curriculum(
    output_path: Optional[str] = None,
    url: str = STUDENTS_TIMETABLE_URL,
) -> str:
    """Scrapes live website and updates curriculum JSON file."""
    path = output_path or get_default_curriculum_path()
    print(f"Fetching live schedule from {url}...")
    html = fetch_url(url)
    print(f"Parsing curriculum data from HTML ({len(html)} bytes)...")
    data = parse_schedule_html(html)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    meta = data["metadata"]
    print("=" * 60)
    print("MGKCT REAL CURRICULUM SCRAPING COMPLETE")
    print(f"  Target: {path}")
    print(f"  Week: {meta.get('week_start_date')} to {meta.get('week_end_date')}")
    print(f"  Belarus Holidays: {meta.get('belarus_holidays')}")
    print(f"  Groups: {meta.get('total_groups')}")
    print(f"  Curriculum Items: {meta.get('total_curriculum_items')}")
    print(f"  Active Teachers: {meta.get('active_teachers')}")
    print("=" * 60)
    return path


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    scrape_and_update_curriculum(target)


if __name__ == "__main__":
    main()
