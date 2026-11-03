#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data structures, types, and grid constants for MGKCT Timetable Optimization Engine.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
NUM_DAYS = 6
MAX_SLOTS = 5  # Slots 0..4 (1st..5th academic pairs; resolves Pigeonhole bottleneck)

CAMPUSES = ["Казинца", "Кнорина"]
ROOM_TYPES = ["лек", "комп", "маст", "спец_лаб", "спорт"]


def normalize_room_name(name: str) -> str:
    """Normalizes classroom identifiers, removing misleading suffixes and unifying whitespace/prefixes."""
    if not name or name == "-":
        return "-"
    s = name.strip()
    for tag in ["(к)", "(лаб)", " (к)", " (лаб)"]:
        s = s.replace(tag, "")
    s = s.strip()
    if s.startswith("Кн ") or s.startswith("Кн  "):
        s = "Кн." + s[3:].strip()
    return " ".join(s.split())


def get_group_campus_for_day(group_name: str, day: int, base_campus: str = "") -> str:
    """
    Returns the physical campus of a group for a specific day (0=Mon..5=Sat).
    Enforces agreed whitelist of hybrid groups:
    - 107ТЭ: Казинца on Wed (2) and Fri (4); Кнорина on Mon, Tue, Thu, Sat.
    - 108ТЭ: Казинца on Tue (1) and Thu (3); Кнорина on Mon, Wed, Fri, Sat.
    - All other groups strictly remain at their base campus.
    """
    if group_name == "107ТЭ":
        return "Казинца" if day in (2, 4) else "Кнорина"
    if group_name == "108ТЭ":
        return "Казинца" if day in (1, 3) else "Кнорина"
    return base_campus or "Казинца"

BELL_SCHEDULE: Dict[str, Dict[int, str]] = {
    "Казинца": {
        0: "09:00–10:40",
        1: "10:50–12:40",
        2: "13:00–14:40",
        3: "14:50–16:30",
        4: "16:40–18:20",
        5: "18:30–20:10",
    },
    "Кнорина": {
        0: "09:00–10:40",
        1: "10:50–12:40",
        2: "13:00–14:40",
        3: "14:50–16:30",
        4: "16:40–18:20",
        5: "18:30–20:10",
    },
}


@dataclass
class GroupInfo:
    name: str
    specialty_code: str
    specialty_name: str
    qualification: str
    course: int           # 1, 2, 3, 4
    campus: str           # "Казинца" or "Кнорина"
    max_daily_pairs: int  # 4 for course 1, 5 for courses 2-4
    is_opfr: bool = False
    shift: int = 1        # 1 = morning shift, 2 = afternoon shift


@dataclass
class RoomInfo:
    name: str
    campus: str           # "Казинца" or "Кнорина"
    room_type: str        # "лек", "комп", "маст", "спец_лаб", "спорт"


@dataclass
class CurriculumItem:
    item_id: int
    group: str
    subject: str
    lesson_type: str      # "Лек", "ЛР", "ФЗКиЗ", "Пр-ка", "КП"
    teacher: str
    weekly_pairs: int
    subgroup: int = 0     # 0 = entire group, 1 = subgroup 1, 2 = subgroup 2
    paired_id: Optional[str] = None  # ID for synchronized split subgroups
    home_rooms: Optional[List[str]] = None
    is_double_pair_ok: bool = False  # True for ЛР, Пр-ка, КП, ФЗКиЗ


@dataclass
class ScheduledLesson:
    item_id: int
    group: str
    campus: str
    course: int
    day: int              # 0..5 (Mon..Sat)
    slot: int             # 0..4 (Pair 1..5)
    subject: str
    lesson_type: str
    teacher: str
    room: str
    subgroup: int = 0


def get_required_room_type(lesson_type: str, subject: str = "") -> str:
    """Maps lesson type and subject to physical classroom pool."""
    if lesson_type == "ФЗКиЗ" or subject == "ФЗКиЗ" or "ФЗКиЗ" in subject:
        return "спорт"
    s_low = subject.lower()
    if "маст" in s_low or "слесмех" in s_low or "элект практ" in s_low or "оснавт в мехатр" in s_low:
        return "маст"
    if any(kw in s_low for kw in (
        "нтин", "функц. микроэл", "цифр и микр тех", "пром электр",
        "тех и обо вэипх", "тоэ", "матвед", "химия"
    )):
        return "спец_лаб"
    if lesson_type in ("ЛР", "Пр-ка", "КП"):
        return "комп"
    return "лек"
