#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent validation metrics and audit engine for academic schedules.
Audits hard constraint compliance (windows, overload, cross-campus) and soft indicators.
"""

from collections import defaultdict
from typing import List, Dict, Optional, Set, Tuple
from .models import ScheduledLesson, GroupInfo


def compute_schedule_metrics(
    schedule: List[ScheduledLesson],
    groups: Dict[str, GroupInfo],
    baseline_schedule: Optional[List[ScheduledLesson]] = None,
    items: Optional[List] = None,
) -> Dict:
    """Computes comprehensive audit metrics for an academic schedule."""
    by_group_day: Dict[Tuple[str, int], Set[int]] = defaultdict(set)
    by_teacher_day: Dict[Tuple[str, int], Set[int]] = defaultdict(set)
    teacher_campuses_day: Dict[Tuple[str, int], Set[str]] = defaultdict(set)

    slot5_count = 0
    slot4_count = 0
    sat_pairs_group: Dict[str, Set[int]] = defaultdict(set)

    for les in schedule:
        by_group_day[(les.group, les.day)].add(les.slot)
        by_teacher_day[(les.teacher, les.day)].add(les.slot)
        teacher_campuses_day[(les.teacher, les.day)].add(les.campus)
        if les.slot >= 4:
            slot5_count += 1
        if les.slot == 3:
            slot4_count += 1
        if les.day == 5:
            sat_pairs_group[les.group].add(les.slot)

    student_windows = 0
    subgroup_windows = 0
    late_starts = 0
    max_daily_violations = 0
    total_group_days = 0
    first_pair_starts = 0
    shift1_group_days = 0
    shift1_first_pair_starts = 0

    group_existing_subs: Dict[str, Set[int]] = defaultdict(set)
    for les in schedule:
        if les.subgroup > 0:
            group_existing_subs[les.group].add(les.subgroup)

    by_subgroup_day: Dict[Tuple[str, int, int], Set[int]] = defaultdict(set)
    for les in schedule:
        subs = group_existing_subs.get(les.group)
        if les.subgroup == 0:
            if subs:
                for sub_k in subs:
                    by_subgroup_day[(les.group, sub_k, les.day)].add(les.slot)
            else:
                by_subgroup_day[(les.group, 0, les.day)].add(les.slot)
        else:
            by_subgroup_day[(les.group, les.subgroup, les.day)].add(les.slot)

    for (g_name, d), slots in by_group_day.items():
        if not slots:
            continue
        total_group_days += 1
        min_s, max_s = min(slots), max(slots)
        g_info = groups.get(g_name)
        shift = getattr(g_info, "shift", 1) if g_info else 1

        if shift == 1:
            shift1_group_days += 1
            if min_s == 0:
                shift1_first_pair_starts += 1

        if min_s == 0:
            first_pair_starts += 1
        else:
            late_starts += 1

        windows = (max_s - min_s + 1) - len(slots)
        student_windows += windows

        day_limit = min(g_info.max_daily_pairs, 4) if d == 5 else (g_info.max_daily_pairs if g_info else 5)
        if len(slots) > day_limit:
            max_daily_violations += 1

    for (g_name, sub_k, d), slots in by_subgroup_day.items():
        if not slots:
            continue
        min_s, max_s = min(slots), max(slots)
        w = (max_s - min_s + 1) - len(slots)
        subgroup_windows += w

    teacher_windows = 0
    cross_campus_violations = 0
    for (t_name, d), slots in by_teacher_day.items():
        if len(slots) > 1:
            teacher_windows += (max(slots) - min(slots) + 1) - len(slots)
        if len(teacher_campuses_day[(t_name, d)]) > 1:
            cross_campus_violations += 1

    teacher_max_daily_pairs = max((len(slots) for slots in by_teacher_day.values()), default=0)

    # Аудит наложений аудиторий (room_conflicts): неспортивные помещения должны быть уникальны
    room_occ: Dict[Tuple[str, str, int, int], List[ScheduledLesson]] = defaultdict(list)
    for les in schedule:
        if "спорт" not in les.room.lower():
            room_occ[(les.campus, les.room, les.day, les.slot)].append(les)
    room_conflicts = sum(len(v) - 1 for v in room_occ.values() if len(v) > 1)

    # Аудит слотов физкультуры: не более 1 слота ФЗКиЗ в день для любой группы
    pe_slots_group_day: Dict[Tuple[str, int], Set[int]] = defaultdict(set)
    for les in schedule:
        if "ФЗКиЗ" in les.subject or les.lesson_type == "ФЗКиЗ":
            pe_slots_group_day[(les.group, les.day)].add(les.slot)
    pe_daily_slot_violations = sum(1 for slots in pe_slots_group_day.values() if len(slots) > 1)

    # Аудит закрепленных кабинетов (room_home_match_pct)
    room_home_match_count = 0
    total_home_checkable = 0
    item_home_map = {it.item_id: set(it.home_rooms or []) for it in items} if items else {}
    if item_home_map:
        for les in schedule:
            hrs = item_home_map.get(les.item_id, set())
            if hrs:
                total_home_checkable += 1
                if les.room in hrs:
                    room_home_match_count += 1
    room_home_match_pct = (
        round(100.0 * room_home_match_count / max(1, total_home_checkable), 1)
        if total_home_checkable > 0 else 0.0
    )

    avg_sat_pairs = sum(len(s) for s in sat_pairs_group.values()) / max(1, len(groups))
    max_sat_slot = max((max(s) + 1 for s in sat_pairs_group.values() if s), default=0)

    shift1_start_pct = round(100.0 * shift1_first_pair_starts / max(1, shift1_group_days), 1)

    res = {
        "total_lessons": len(schedule),
        "student_windows": student_windows,
        "subgroup_windows": subgroup_windows,
        "teacher_windows": teacher_windows,
        "max_daily_violations": max_daily_violations,
        "cross_campus_violations": cross_campus_violations,
        "room_conflicts": room_conflicts,
        "pe_daily_slot_violations": pe_daily_slot_violations,
        "teacher_max_daily_pairs": teacher_max_daily_pairs,
        "room_home_match_pct": room_home_match_pct,
        "first_pair_start_pct": shift1_start_pct,
        "overall_first_pair_start_pct": round(100.0 * first_pair_starts / max(1, total_group_days), 1),
        "late_starts_days": late_starts,
        "slot5_plus_lessons": slot5_count,
        "slot4_lessons": slot4_count,
        "avg_saturday_pairs": round(avg_sat_pairs, 2),
        "max_saturday_pair_num": max_sat_slot,
    }

    if baseline_schedule is not None:
        base_set = {(l.item_id, l.day, l.slot) for l in baseline_schedule}
        new_set = {(l.item_id, l.day, l.slot) for l in schedule}
        kept = len(base_set & new_set)
        res["unchanged_lessons_count"] = kept
        res["unchanged_lessons_pct"] = round(100.0 * kept / max(1, len(schedule)), 1)

    return res
