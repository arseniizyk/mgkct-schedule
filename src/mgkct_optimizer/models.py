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

BELL_SCHEDULE: Dict[str, Dict[int, str]] = {
    "Казинца": {
        0: "08:00–09:40",
        1: "09:50–11:30",
        2: "11:50–13:30",
        3: "13:40–15:20",
        4: "15:30–17:00",
    },
    "Кнорина": {
        0: "09:00–10:40",
        1: "10:50–12:40",
        2: "13:00–14:40",
        3: "14:50–16:30",
        4: "16:40–18:10",
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
