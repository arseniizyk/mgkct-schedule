#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curriculum loader for MGKCT groups, rooms, and subject assignments.
Reads structured data from data/mgkct_curriculum.json with hardcoded fallback.
"""

import json
import os
from typing import List, Tuple, Optional
from .models import GroupInfo, RoomInfo, CurriculumItem, normalize_room_name


AFTERNOON_SHIFT_GROUPS = set()
OPFR_GROUPS = {"101ТП", "109ТП", "93МНЭ", "94ТП", "169ТП", "167ТП", "168МНЭ"}


def get_default_curriculum_path() -> str:
    """Finds data/mgkct_curriculum.json by walking up to project root."""
    current = os.path.dirname(os.path.abspath(__file__))
    # Check parent dirs
    for _ in range(4):
        candidate = os.path.join(current, "data", "mgkct_curriculum.json")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "mgkct_curriculum.json")


def load_curriculum_data(
    json_path: Optional[str] = None,
) -> Tuple[List[GroupInfo], List[RoomInfo], List[CurriculumItem]]:
    """Loads all 35 groups, classrooms, and curriculum items from JSON or built-in catalog."""
    path = json_path or get_default_curriculum_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        groups = [
            GroupInfo(
                name=g["name"],
                specialty_code=g.get("specialty_code", ""),
                specialty_name=g.get("specialty_name", ""),
                qualification=g.get("qualification", ""),
                course=g["course"],
                campus=g["campus"],
                max_daily_pairs=g["max_daily_pairs"],
                is_opfr=g.get("is_opfr", g["name"] in OPFR_GROUPS),
                shift=1,
            )
            for g in data["groups"]
        ]
        rooms_list = [
            RoomInfo(
                name=normalize_room_name(r["name"]),
                campus=r["campus"],
                room_type=r["room_type"],
            )
            for r in data["rooms"]
        ]
        # Ensure rooms discovered from live export are included
        existing_rooms = {(r.campus, r.name) for r in rooms_list}
        extra_rooms = [
            RoomInfo(name="Кн.1-204 маст", campus="Кнорина", room_type="маст"),
            RoomInfo(name="Кн.2-417 маст", campus="Кнорина", room_type="маст"),
            RoomInfo(name="402", campus="Казинца", room_type="лек"),
        ]
        for er in extra_rooms:
            if (er.campus, er.name) not in existing_rooms:
                rooms_list.append(er)
                existing_rooms.add((er.campus, er.name))

        items = [
            CurriculumItem(
                item_id=it["item_id"],
                group=it["group"],
                subject=it["subject"],
                lesson_type=it["lesson_type"],
                teacher=it["teacher"],
                weekly_pairs=it["weekly_pairs"],
                subgroup=0 if it["group"] in OPFR_GROUPS else it.get("subgroup", 0),
                paired_id=None if it["group"] in OPFR_GROUPS else it.get("paired_id"),
                home_rooms=[normalize_room_name(hr) for hr in it.get("home_rooms", [])],
                is_double_pair_ok=it.get(
                    "is_double_pair_ok",
                    it.get("lesson_type") in ("ЛР", "Пр-ка", "КП") or "ФЗКиЗ" in it.get("subject", "")
                ),
            )
            for it in data["curriculum_items"]
            if it.get("weekly_pairs", 0) > 0
        ]
        return groups, rooms_list, items


def load_curriculum_with_metadata(
    json_path: Optional[str] = None,
) -> Tuple[List[GroupInfo], List[RoomInfo], List[CurriculumItem], dict]:
    """Loads groups, classrooms, curriculum items, and full dataset metadata."""
    path = json_path or get_default_curriculum_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        groups, rooms, items = load_curriculum_data(json_path)
        metadata = data.get("metadata", {})
        return groups, rooms, items, metadata
    groups, rooms, items = load_curriculum_data(json_path)
    return groups, rooms, items, {}

    # Fallback minimal catalog
    groups = [
        GroupInfo("102М", "5-04-0713-10", "Мехатроника", "Техник-мехатроник", 1, "Кнорина", 4, False, 1),
        GroupInfo("104РТК", "5-04-0713-08", "Робототехника", "Техник-электроник", 1, "Казинца", 4, False, 1),
        GroupInfo("96РТК", "5-04-0713-08", "Робототехника", "Техник-электроник", 2, "Казинца", 5, False, 1),
    ]
    rooms = [
        RoomInfo("302", "Казинца", "спец_лаб"),
        RoomInfo("Кн.1-124", "Кнорина", "лек"),
    ]
    items = [
        CurriculumItem(0, "104РТК", "Химия", "Лек", "Преподаватель Химии", 2, 0, None, ["302"], False),
    ]
    return groups, rooms, items
