#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classroom allocation engine for MGKCT Timetable Optimization.
Two-stage heuristic:
1. Anchors teachers to consistent department/home rooms.
2. Greedily fills remaining capacity from campus-specific non-interchangeable pools.
"""

from collections import defaultdict
from typing import List, Dict, Tuple, Set, Optional
from .models import (
    RoomInfo,
    CurriculumItem,
    GroupInfo,
    ScheduledLesson,
    NUM_DAYS,
    MAX_SLOTS,
    get_required_room_type,
    get_group_campus_for_day,
    normalize_room_name,
)


def assign_physical_rooms(
    solver_values: Dict[Tuple[int, int, int], int],
    items: List[CurriculumItem],
    groups: Dict[str, GroupInfo],
    rooms: List[RoomInfo],
    pool_items: Optional[Dict[Tuple[str, str], List[CurriculumItem]]] = None,
) -> List[ScheduledLesson]:
    """Assigns specific classrooms to lessons optimized at aggregate pool level."""
    rooms_by_pool: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for r in rooms:
        norm_r = normalize_room_name(r.name)
        if norm_r not in rooms_by_pool[(r.campus, r.room_type)]:
            rooms_by_pool[(r.campus, r.room_type)].append(norm_r)

    teacher_home_room: Dict[Tuple[str, str, str], str] = {}
    for it in items:
        if it.teacher and it.home_rooms:
            c_name = groups[it.group].campus
            r_type = get_required_room_type(it.lesson_type, it.subject)
            if r_type == "спец_лаб" and (c_name, "спец_лаб") not in rooms_by_pool:
                r_type = "комп" if it.lesson_type in ("ЛР", "Пр-ка", "КП") else "лек"
            for hr in it.home_rooms:
                norm_hr = normalize_room_name(hr)
                if norm_hr in rooms_by_pool.get((c_name, r_type), []):
                    teacher_home_room[(it.teacher, c_name, r_type)] = norm_hr
                    break

    for (c_name, r_type), r_list in rooms_by_pool.items():
        t_in_pool = sorted({
            it.teacher for it in items
            if groups[it.group].campus == c_name
            and get_required_room_type(it.lesson_type, it.subject) == r_type
        })
        for idx, t_name in enumerate(t_in_pool):
            if (t_name, c_name, r_type) not in teacher_home_room and r_list:
                teacher_home_room[(t_name, c_name, r_type)] = r_list[idx % len(r_list)]

    scheduled: List[ScheduledLesson] = []

    for d in range(NUM_DAYS):
        group_last_room: Dict[str, str] = {}
        for s in range(MAX_SLOTS):
            active_by_pool: Dict[Tuple[str, str], List[CurriculumItem]] = defaultdict(list)
            for it in items:
                if solver_values.get((it.item_id, d, s), 0) == 1:
                    c_name = get_group_campus_for_day(it.group, d, groups[it.group].campus)
                    r_type = get_required_room_type(it.lesson_type, it.subject)
                    if r_type == "спец_лаб" and (c_name, "спец_лаб") not in rooms_by_pool:
                        r_type = "комп" if it.lesson_type in ("ЛР", "Пр-ка", "КП") else "лек"
                    active_by_pool[(c_name, r_type)].append(it)

            for (c_name, r_type), active_items in active_by_pool.items():
                avail_rooms = list(rooms_by_pool.get((c_name, r_type), []))
                used_rooms: Set[str] = set()
                assigned_room: Dict[int, str] = {}

                # Внешняя практика без кабинетов (class: '-') проходит вне учебных корпусов колледжа
                non_room_items = [it for it in active_items if it.lesson_type == "Пр-ка" and not it.home_rooms]
                room_needed_items = [it for it in active_items if it not in non_room_items]
                for it in non_room_items:
                    assigned_room[it.item_id] = "-"

                if r_type == "спорт":
                    for idx, it in enumerate(room_needed_items):
                        pref = None
                        if it.home_rooms:
                            for hr in it.home_rooms:
                                norm_hr = normalize_room_name(hr)
                                if norm_hr in avail_rooms:
                                    pref = norm_hr
                                    break
                        if not pref:
                            pref = avail_rooms[idx % len(avail_rooms)] if avail_rooms else "Спортзал"
                        assigned_room[it.item_id] = pref
                else:
                    candidate_pairs = []
                    for it in room_needed_items:
                        for r in avail_rooms:
                            score = 0
                            norm_hrs = [normalize_room_name(hr) for hr in (it.home_rooms or [])]
                            if r in norm_hrs:
                                score += 100
                            if r == teacher_home_room.get((it.teacher, c_name, r_type)):
                                score += 30
                            if r == group_last_room.get(it.group):
                                score += 20
                            candidate_pairs.append((score, it.item_id, r))

                    candidate_pairs.sort(key=lambda x: x[0], reverse=True)

                    for score, it_id, r in candidate_pairs:
                        if it_id not in assigned_room and r not in used_rooms:
                            assigned_room[it_id] = r
                            used_rooms.add(r)

                    free_rooms = [r for r in avail_rooms if r not in used_rooms]
                    for it in room_needed_items:
                        if it.item_id not in assigned_room:
                            assigned_room[it.item_id] = free_rooms.pop(0) if free_rooms else (
                                avail_rooms[0] if avail_rooms else "Ауд. общая"
                            )

                for it in active_items:
                    g_info = groups[it.group]
                    assigned_r = assigned_room[it.item_id]
                    if r_type != "спорт":
                        group_last_room[it.group] = assigned_r
                    scheduled.append(
                        ScheduledLesson(
                            item_id=it.item_id,
                            group=it.group,
                            campus=c_name,
                            course=g_info.course,
                            day=d,
                            slot=s,
                            subject=it.subject,
                            lesson_type=it.lesson_type,
                            teacher=it.teacher,
                            room=assigned_r,
                            subgroup=it.subgroup,
                        )
                    )

    scheduled.sort(key=lambda l: (l.campus, l.course, l.group, l.day, l.slot, l.subgroup))
    return scheduled
