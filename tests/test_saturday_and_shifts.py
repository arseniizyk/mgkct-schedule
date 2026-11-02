#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Empirical test suite for Saturday Grid & Slot 3 and Shift 2 Afternoon Start.
Audits baseline and disruption schedules against AGENTS.md specifications.
"""

import os
import sys
import json
from collections import defaultdict, Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from mgkct_optimizer.loader import load_curriculum_data, get_default_curriculum_path
from mgkct_optimizer.models import ScheduledLesson


def load_data():
    curriculum_path = get_default_curriculum_path()
    groups, rooms, items = load_curriculum_data(curriculum_path)
    solved_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mgkct_solved_schedule.json")
    with open(solved_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    baseline = []
    for l in data["schedule"]:
        baseline.append(ScheduledLesson(
            item_id=l["item_id"],
            group=l["group"],
            campus=l["campus"],
            course=l["course"],
            day=l["day"],
            slot=l["slot"],
            subject=l["subject"],
            lesson_type=l["lesson_type"],
            teacher=l["teacher"],
            room=l["room"],
            subgroup=l.get("subgroup", 0),
        ))
    return groups, rooms, items, baseline


def audit_saturday_grid(schedule, schedule_name="Baseline"):
    print(f"\n=======================================================")
    print(f"AUDIT TARGET 2: Saturday Grid & Slot 3 ({schedule_name})")
    print(f"=======================================================")

    sat_lessons = [l for l in schedule if l.day == 5]
    print(f"Total Saturday lessons: {len(sat_lessons)}")

    slot_counts = Counter(l.slot for l in sat_lessons)
    print(f"Saturday slot distribution: {dict(sorted(slot_counts.items()))}")

    # Check 1: Slot 4 prohibition on Saturday
    slot4_lessons = [l for l in sat_lessons if l.slot == 4]
    print(f"Check 1: Lessons in Slot 4 (Pair 5) on Saturday (expected 0): {len(slot4_lessons)}")
    assert len(slot4_lessons) == 0, f"VIOLATION: Slot 4 used on Saturday: {slot4_lessons}"

    # Check 2: Saturday daily pair cap <= 4 for all groups
    by_group = defaultdict(set)
    for l in sat_lessons:
        by_group[l.group].add(l.slot)

    over_cap_groups = {g: len(slots) for g, slots in by_group.items() if len(slots) > 4}
    print(f"Check 2: Groups exceeding 4 pairs on Saturday (expected 0): {len(over_cap_groups)}")
    assert len(over_cap_groups) == 0, f"VIOLATION: Groups exceeding 4 pairs on Saturday: {over_cap_groups}"

    # Check 3: Slot 3 relief behavior (soft penalty)
    groups_in_slot3 = [g for g, slots in by_group.items() if 3 in slots]
    print(f"Check 3: Groups utilizing Slot 3 on Saturday: {len(groups_in_slot3)} / {len(by_group)} active groups")
    print(f"         Groups in Slot 3: {sorted(groups_in_slot3)}")
    
    # Check 4: Check slots strictly <= 3 for every Saturday lesson
    for l in sat_lessons:
        assert l.slot <= 3, f"VIOLATION: Lesson on Saturday with slot > 3: {l}"

    print(f"==> SATURDAY GRID AUDIT PASSED for {schedule_name}!")
    return {
        "total_sat_lessons": len(sat_lessons),
        "slot_distribution": dict(sorted(slot_counts.items())),
        "slot4_violations": len(slot4_lessons),
        "over_cap_violations": len(over_cap_groups),
        "slot3_groups_count": len(groups_in_slot3),
    }


def audit_shift2_starts(groups_list, items, schedule, schedule_name="Baseline"):
    print(f"\n=======================================================")
    print(f"AUDIT TARGET 3: Shift 2 Afternoon Start ({schedule_name})")
    print(f"=======================================================")

    shift2_groups = {g.name: g for g in groups_list if g.shift == 2}
    print(f"Shift 2 groups defined ({len(shift2_groups)}): {sorted(shift2_groups.keys())}")

    # Inspect weekly loads of Shift 2 groups
    print("\nCurriculum weekly loads for Shift 2 groups:")
    group_items = defaultdict(list)
    for it in items:
        if it.group in shift2_groups and it.subgroup in (0, 1):
            group_items[it.group].append(it)

    for g_name in sorted(shift2_groups.keys()):
        tot_hrs = sum(it.weekly_pairs for it in group_items[g_name])
        max_possible_starting_at_slot2 = 5 * 3 + 2  # 3 pairs Mon-Fri (slots 2..4), 2 pairs Sat (slots 2..3)
        print(f"  Group {g_name:7s}: {tot_hrs:2d} weekly pairs | Max capacity starting >= slot 2: {max_possible_starting_at_slot2} pairs | Deficit: {max(0, tot_hrs - max_possible_starting_at_slot2)}")

    # Audit actual start slots in schedule
    by_g_d = defaultdict(set)
    for l in schedule:
        if l.group in shift2_groups:
            by_g_d[(l.group, l.day)].add(l.slot)

    start_slots = Counter()
    early_start_days = []
    slot2_plus_start_days = []

    for (g_name, d), slots in sorted(by_g_d.items()):
        min_s = min(slots)
        start_slots[min_s] += 1
        if min_s < 2:
            early_start_days.append((g_name, d, min_s, sorted(slots)))
        else:
            slot2_plus_start_days.append((g_name, d, min_s, sorted(slots)))

    total_shift2_group_days = len(by_g_d)
    print(f"\nActual Shift 2 start slot distribution across {total_shift2_group_days} group-days:")
    for slot, cnt in sorted(start_slots.items()):
        pct = 100.0 * cnt / max(1, total_shift2_group_days)
        print(f"  Start at Slot {slot}: {cnt} group-days ({pct:.1f}%)")

    early_cnt = len(early_start_days)
    early_pct = 100.0 * early_cnt / max(1, total_shift2_group_days)
    slot2_cnt = len(slot2_plus_start_days)
    slot2_pct = 100.0 * slot2_cnt / max(1, total_shift2_group_days)

    print(f"\nSummary for Shift 2:")
    print(f"  Starting at Slot >= 2 (Target: 100%): {slot2_cnt}/{total_shift2_group_days} ({slot2_pct:.1f}%)")
    print(f"  Starting early at Slot 0 or 1 (Violations/Defects): {early_cnt}/{total_shift2_group_days} ({early_pct:.1f}%)")

    return {
        "total_group_days": total_shift2_group_days,
        "start_slot_distribution": dict(sorted(start_slots.items())),
        "slot2_plus_starts": slot2_cnt,
        "slot2_plus_pct": round(slot2_pct, 1),
        "early_starts": early_cnt,
        "early_pct": round(early_pct, 1),
        "early_start_details": early_start_days,
    }


def main():
    groups, rooms, items, baseline = load_data()

    # Target 2 Audit
    sat_res = audit_saturday_grid(baseline, "Baseline Solved Schedule")

    # Target 3 Audit
    shift2_res = audit_shift2_starts(groups, items, baseline, "Baseline Solved Schedule")

    print("\n================== SUMMARY ==================")
    print(f"Target 2 (Saturday Grid): PASSED (0 slot 4 lessons, 0 daily cap violations)")
    print(f"Target 3 (Shift 2 Start): slot >= 2 achieved in {shift2_res['slot2_plus_pct']}% of group-days, early starts in {shift2_res['early_pct']}% of group-days")


if __name__ == "__main__":
    main()
