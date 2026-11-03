#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial and Empirical Audit Test Suite for MGKCT Timetable Optimization Engine.
Tests generated baseline schedule and solver constraints against domain rules.
"""

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_PATH = os.path.join(PROJECT_ROOT, "data", "mgkct_solved_schedule.json")
CURRICULUM_PATH = os.path.join(PROJECT_ROOT, "data", "mgkct_curriculum.json")

OPFR_GROUPS = {"101ТП", "109ТП", "93МНЭ", "94ТП", "169ТП", "167ТП", "168МНЭ"}
SHIFT2_GROUPS = {
    "79ТЭ", "84МНЭ", "93МНЭ", "168МНЭ", "90МНЭ", "91МНЭ",
    "85М", "81ТП", "82ТП", "83МНЭ", "88ТП"
}


def load_data():
    with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
        schedule_data = json.load(f)
    with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
        curriculum_data = json.load(f)
    return schedule_data, curriculum_data


try:
    import pytest

    @pytest.fixture(scope="module")
    def _data_bundle():
        return load_data()

    @pytest.fixture(scope="module")
    def lessons(_data_bundle):
        return _data_bundle[0]["schedule"]

    @pytest.fixture(scope="module")
    def rooms_catalog(_data_bundle):
        return _data_bundle[1]["rooms"]

    @pytest.fixture(scope="module")
    def groups_catalog(_data_bundle):
        return _data_bundle[1]["groups"]

    @pytest.fixture(scope="module")
    def curriculum_catalog(_data_bundle):
        return _data_bundle[1]["curriculum_items"]

    @pytest.fixture(scope="module")
    def metadata(_data_bundle):
        return _data_bundle[1].get("metadata", {})
except ImportError:
    pass


def test_1_room_double_booking(lessons, rooms_catalog):
    """
    Challenge 1: Room Double-Booking Challenge
    Verify that NO non-sports room has 2 or more lessons assigned at the exact same campus, day, and slot.
    """
    print("\n[CHALLENGE 1] Auditing Room Double-Booking...")
    room_occupancy = defaultdict(list)
    sports_occupancy = defaultdict(list)

    catalog_rooms = {(r["campus"], r["name"]): r["room_type"] for r in rooms_catalog}

    unknown_rooms = []
    type_mismatches = []

    for l in lessons:
        campus = l["campus"]
        room = l["room"]
        day = l["day"]
        slot = l["slot"]
        key = (campus, room, day, slot)

        if "спорт" in room.lower() or room == "-":
            sports_occupancy[key].append(l)
        else:
            room_occupancy[key].append(l)

        # Check room exists in catalog (skip external practice marked as '-')
        if room == "-":
            continue
        elif (campus, room) not in catalog_rooms:
            unknown_rooms.append((campus, room, l["group"], day, slot))
        else:
            rtype = catalog_rooms[(campus, room)]
            # If lab or comp, verify not placed in basic lecture if comp required
            l_type = l.get("lesson_type", "")
            subj = l.get("subject", "")
            if l_type in ("ЛР", "Пр-ка", "КП") and rtype == "лек" and "информат" in subj.lower():
                type_mismatches.append((campus, room, rtype, l_type, subj, l["group"]))

    conflicts = {k: v for k, v in room_occupancy.items() if len(v) > 1}
    conflict_count = sum(len(v) - 1 for v in conflicts.values())

    print(f"  Non-sports room-slot assignments checked: {len(lessons) - sum(len(v) for v in sports_occupancy.values())}")
    print(f"  Unique non-sports room-day-slot keys: {len(room_occupancy)}")
    print(f"  Room conflicts count: {conflict_count}")
    print(f"  Unknown rooms count: {len(unknown_rooms)}")
    print(f"  Type mismatches count: {len(type_mismatches)}")

    if conflicts:
        for (c, r, d, s), l_list in list(conflicts.items())[:5]:
            print(f"  CONFLICT in {c} {r} at day {d}, slot {s}:")
            for cl in l_list:
                print(f"    Group: {cl['group']}, Subgroup: {cl['subgroup']}, Subj: {cl['subject']}, Teacher: {cl['teacher']}")

    assert conflict_count == 0, f"Expected 0 room conflicts, found {conflict_count}!"
    assert len(unknown_rooms) == 0, f"Found unknown rooms assigned: {unknown_rooms[:3]}"
    print("  [PASS] Zero room conflicts across all non-sports rooms.")
    return conflict_count


def test_2_student_gaps(lessons, groups_catalog):
    """
    Challenge 2: Student Gap ('Окна') Challenge
    Check continuity of active slots for each group and each individual subgroup on every day.
    """
    print("\n[CHALLENGE 2] Auditing Student Gaps ('Окна')...")
    
    # 1. Whole group active slots
    group_days = defaultdict(set)
    # 2. Individual subgroups active slots
    # Identify which subgroups exist for each group
    group_subgroups = defaultdict(set)
    for l in lessons:
        if l["subgroup"] > 0:
            group_subgroups[l["group"]].add(l["subgroup"])

    subgroup_days = defaultdict(set)

    for l in lessons:
        g = l["group"]
        d = l["day"]
        s = l["slot"]
        sub = l["subgroup"]

        group_days[(g, d)].add(s)

        existing_subs = group_subgroups.get(g, set())
        if sub == 0:
            if existing_subs:
                for k in existing_subs:
                    subgroup_days[(g, k, d)].add(s)
            else:
                subgroup_days[(g, 0, d)].add(s)
        else:
            subgroup_days[(g, sub, d)].add(s)

    group_windows = 0
    group_window_details = []
    for (g, d), slots in group_days.items():
        if not slots:
            continue
        min_s, max_s = min(slots), max(slots)
        expected_count = max_s - min_s + 1
        actual_count = len(slots)
        w = expected_count - actual_count
        if w > 0:
            group_windows += w
            group_window_details.append((g, d, sorted(slots), w))

    subgroup_windows = 0
    subgroup_window_details = []
    for (g, k, d), slots in subgroup_days.items():
        if not slots:
            continue
        min_s, max_s = min(slots), max(slots)
        expected_count = max_s - min_s + 1
        actual_count = len(slots)
        w = expected_count - actual_count
        if w > 0:
            subgroup_windows += w
            subgroup_window_details.append((g, k, d, sorted(slots), w))

    print(f"  Group-days evaluated: {len(group_days)}")
    print(f"  Subgroup-days evaluated: {len(subgroup_days)}")
    print(f"  Whole-group windows: {group_windows}")
    print(f"  Subgroup-level windows: {subgroup_windows}")

    if group_window_details:
        for g, d, slots, w in group_window_details[:5]:
            print(f"  Group window detail: {g} day {d} slots={slots} (gap={w})")
    if subgroup_window_details:
        for g, k, d, slots, w in subgroup_window_details[:5]:
            print(f"  Subgroup window detail: {g} sub {k} day {d} slots={slots} (gap={w})")

    assert group_windows == 0, f"Expected 0 group windows, found {group_windows}!"
    assert subgroup_windows == 0, f"Expected 0 subgroup windows, found {subgroup_windows}!"
    print("  [PASS] Zero gaps ('окна') at both whole-group and subgroup levels.")
    return group_windows, subgroup_windows


def test_3_pe_single_slot(lessons):
    """
    Challenge 3: Physical Education Single-Slot Challenge
    Verify that no group has PE lessons scheduled in multiple distinct slots on the same day.
    """
    print("\n[CHALLENGE 3] Auditing Physical Education Single-Slot Bound...")
    pe_group_day_slots = defaultdict(set)
    pe_lessons_count = 0

    for l in lessons:
        if "ФЗКиЗ" in l["subject"] or l.get("lesson_type") == "ФЗКиЗ":
            pe_lessons_count += 1
            pe_group_day_slots[(l["group"], l["day"])].add(l["slot"])

    violations = []
    for (g, d), slots in pe_group_day_slots.items():
        if len(slots) > 1:
            violations.append((g, d, sorted(slots)))

    print(f"  Total PE lessons in schedule: {pe_lessons_count}")
    print(f"  Total group-days with PE: {len(pe_group_day_slots)}")
    print(f"  PE multi-slot violations: {len(violations)}")

    if violations:
        for g, d, slots in violations[:5]:
            print(f"  PE Violation: Group {g} on day {d} has PE in multiple slots: {slots}")

    assert len(violations) == 0, f"Expected 0 PE multi-slot violations, found {len(violations)}!"
    print("  [PASS] All PE classes scheduled strictly at most once per day per group.")
    return len(violations)


def test_4_opfr_integrity(lessons, groups_catalog):
    """
    Challenge 4: OPFR Inclusion Cohort Challenge
    Verify that groups 101ТП, 109ТП, 93МНЭ, 94ТП, 169ТП, 167ТП, 168МНЭ have strictly subgroup == 0.
    """
    print("\n[CHALLENGE 4] Auditing OPFR Inclusion Cohorts...")
    opfr_lessons = [l for l in lessons if l["group"] in OPFR_GROUPS]
    non_zero_subgroups = [l for l in opfr_lessons if l["subgroup"] != 0]
    wrong_campus = [l for l in opfr_lessons if l["campus"] != "Кнорина"]

    groups_map = {g["name"]: g for g in groups_catalog}
    catalog_opfr_flags = {g: groups_map[g].get("is_opfr", False) for g in OPFR_GROUPS if g in groups_map}

    print(f"  OPFR groups monitored: {sorted(OPFR_GROUPS)}")
    print(f"  Total lessons for OPFR groups: {len(opfr_lessons)}")
    print(f"  Non-zero subgroup occurrences: {len(non_zero_subgroups)}")
    print(f"  Non-Knorina campus occurrences: {len(wrong_campus)}")

    assert len(opfr_lessons) > 0, "No lessons found for OPFR groups!"
    assert len(non_zero_subgroups) == 0, f"OPFR lessons with subgroup != 0 found: {non_zero_subgroups[:3]}"
    assert len(wrong_campus) == 0, f"OPFR lessons on wrong campus found: {wrong_campus[:3]}"
    for g, flag in catalog_opfr_flags.items():
        assert flag is True, f"Group {g} is expected to have is_opfr=True in catalog!"

    print("  [PASS] Strict OPFR cohort integrity (100% undivided cohorts at Knorina).")
    return len(non_zero_subgroups)


def test_5_teacher_exclusivity_and_campuses(lessons):
    """
    Challenge 5: Teacher Exclusivity & Cross-Campus Challenge
    1. Verify no teacher teaches >1 lesson in the same slot.
    2. Verify no teacher teaches at both Kazintsa and Knorina on the same day.
    """
    print("\n[CHALLENGE 5] Auditing Teacher Exclusivity & Campus Mobility...")
    teacher_slot_lessons = defaultdict(list)
    teacher_day_campuses = defaultdict(set)

    for l in lessons:
        t = l["teacher"]
        d = l["day"]
        s = l["slot"]
        c = l["campus"]

        teacher_slot_lessons[(t, d, s)].append(l)
        if "инф час" not in l.get("subject", "").lower() and l.get("room") != "-":
            teacher_day_campuses[(t, d)].add(c)

    double_booked_teachers = {k: v for k, v in teacher_slot_lessons.items() if len(v) > 1}
    cross_campus_teachers = {k: v for k, v in teacher_day_campuses.items() if len(v) > 1}

    print(f"  Teacher-day-slot assignments checked: {len(teacher_slot_lessons)}")
    print(f"  Teacher slot double-bookings: {len(double_booked_teachers)}")
    print(f"  Teacher cross-campus travel violations: {len(cross_campus_teachers)}")

    if double_booked_teachers:
        for (t, d, s), l_list in list(double_booked_teachers.items())[:5]:
            print(f"  DOUBLE-BOOKING: Teacher {t} at day {d}, slot {s}:")
            for cl in l_list:
                print(f"    Group: {cl['group']}, Subj: {cl['subject']}, Room: {cl['room']}")

    if cross_campus_teachers:
        for (t, d), c_set in list(cross_campus_teachers.items())[:5]:
            print(f"  CROSS-CAMPUS VIOLATION: Teacher {t} at day {d} assigned to {c_set}")

    assert len(double_booked_teachers) == 0, f"Expected 0 teacher double-bookings, found {len(double_booked_teachers)}!"
    assert len(cross_campus_teachers) == 0, f"Expected 0 cross-campus violations, found {len(cross_campus_teachers)}!"
    print("  [PASS] Teacher exclusivity and single-campus daily integrity strictly preserved.")
    return len(double_booked_teachers), len(cross_campus_teachers)


def test_6_academic_limits_and_curriculum_volume(lessons, curriculum_catalog, groups_catalog):
    """
    Challenge 6: Stress-Testing Academic Limits, Daily Pair Caps, Saturday Caps, Curriculum Volume
    """
    print("\n[CHALLENGE 6] Auditing Daily Pair Caps, Saturday Bounds & Curriculum Volume...")
    groups_map = {g["name"]: g for g in groups_catalog}

    # Daily pairs per group
    group_day_slots = defaultdict(set)
    for l in lessons:
        group_day_slots[(l["group"], l["day"])].add(l["slot"])

    cap_violations = []
    sat_slot4_violations = []

    for (g_name, d), slots in group_day_slots.items():
        g_info = groups_map[g_name]
        course = g_info["course"]
        num_pairs = len(slots)

        if d == 5:  # Saturday
            if num_pairs > 4:
                cap_violations.append((g_name, d, num_pairs, "Sat > 4"))
            if 4 in slots:  # slot 4 is 5th pair (0-indexed: 0,1,2,3,4)
                sat_slot4_violations.append((g_name, d, slots))
        else:  # Weekday Mon-Fri
            acad_slots = {
                l["slot"] for l in lessons
                if l["group"] == g_name and l["day"] == d and "инф час" not in l["subject"].lower()
            }
            if len(acad_slots) > 4:
                cap_violations.append((g_name, d, len(acad_slots), f"Course {course} > 4 academic pairs"))
            elif num_pairs > 5:
                cap_violations.append((g_name, d, num_pairs, f"Course {course} > 5 total pairs"))

    # Curriculum volume check
    item_required = {it["item_id"]: it["weekly_pairs"] for it in curriculum_catalog}
    item_scheduled = defaultdict(int)
    for l in lessons:
        item_scheduled[l["item_id"]] += 1

    volume_mismatches = []
    for it_id, req in item_required.items():
        actual = item_scheduled.get(it_id, 0)
        if actual != req:
            volume_mismatches.append((it_id, req, actual))

    print(f"  Daily pair cap violations: {len(cap_violations)}")
    print(f"  Saturday 5th pair (slot 4) violations: {len(sat_slot4_violations)}")
    print(f"  Curriculum item volume mismatches: {len(volume_mismatches)}")

    assert len(cap_violations) == 0, f"Daily pair cap violations: {cap_violations[:3]}"
    assert len(sat_slot4_violations) == 0, f"Saturday slot 4 violations: {sat_slot4_violations[:3]}"
    assert len(volume_mismatches) == 0, f"Curriculum volume mismatches: {volume_mismatches[:3]}"
    print("  [PASS] Daily pair caps, Saturday constraints, and curriculum volume 100% satisfied.")


def test_7_shifts_starting_slots(lessons, groups_catalog):
    """
    Challenge 7: Auditing Shift 1 and Shift 2 Starting Slot Constraints
    """
    print("\n[CHALLENGE 7] Auditing Shift Starting Times...")
    groups_map = {g["name"]: g for g in groups_catalog}

    group_day_slots = defaultdict(set)
    for l in lessons:
        group_day_slots[(l["group"], l["day"])].add(l["slot"])

    shift1_days = 0
    shift1_slot0_starts = 0
    shift1_late_weekday_starts = []  # Starts at slot >= 2 on weekdays

    shift2_slot0_starts = []

    for (g_name, d), slots in group_day_slots.items():
        g_info = groups_map[g_name]
        shift = g_info.get("shift", 1)
        min_slot = min(slots)

        if shift == 1:
            shift1_days += 1
            if min_slot == 0:
                shift1_slot0_starts += 1
            elif d < 5 and min_slot >= 2:
                shift1_late_weekday_starts.append((g_name, d, min_slot))
        elif shift == 2:
            if min_slot == 0:
                shift2_slot0_starts.append((g_name, d, min_slot))

    shift1_pct = (100.0 * shift1_slot0_starts / max(1, shift1_days))
    print(f"  Shift 1 group-days evaluated: {shift1_days}")
    print(f"  Shift 1 starts at slot 0: {shift1_slot0_starts} ({shift1_pct:.1f}%)")
    print(f"  Shift 1 late weekday starts (slot >= 2): {len(shift1_late_weekday_starts)}")
    print(f"  Shift 2 starts at slot 0 (soft-penalized): {len(shift2_slot0_starts)}")

    assert shift1_pct >= 80.0, f"Shift 1 first pair start pct {shift1_pct:.1f}% < 80.0% threshold!"
    assert len(shift1_late_weekday_starts) == 0, f"Shift 1 started at slot >= 2 on weekday: {shift1_late_weekday_starts[:3]}"
    print("  [PASS] Shift starting constraints fully compliant (Shift 1 >= 80% slot 0, 0 late weekday starts >= slot 2).")


def test_8_belarus_public_holidays(lessons, metadata):
    """
    Challenge 8: Belarus Public Holidays Challenge
    Verifies that students are strictly prohibited from having lessons on official public holidays of Belarus.
    """
    print("\n[CHALLENGE 8] Auditing Belarus Public Holidays Rule...")
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
    from mgkct_optimizer.holidays import get_week_holidays

    week_date = metadata.get("week_start_date") or metadata.get("extracted_at") or "2026-11-02"
    holidays = get_week_holidays(week_date)
    print(f"  Target week: {week_date}, Detected Belarus Public Holidays: {holidays}")

    holiday_lessons = []
    for l in lessons:
        if l["day"] in holidays:
            holiday_lessons.append(l)

    print(f"  Student lessons on Belarus public holidays: {len(holiday_lessons)}")
    if holiday_lessons:
        for l in holiday_lessons[:5]:
            print(f"    VIOLATION on holiday day {l['day']} ({holidays[l['day']]}): group={l['group']} subj={l['subject']} slot={l['slot']}")

    assert len(holiday_lessons) == 0, f"Found {len(holiday_lessons)} student lessons scheduled on Belarus public holidays!"
    print("  [PASS] Zero student lessons scheduled on official Belarus public holidays.")
    return len(holiday_lessons)


def test_9_pe_whole_group_integrity(lessons, curriculum_catalog):
    """
    Challenge 9: Physical Education Whole-Group Integrity Challenge
    Rule: 'Пара физры если ставится, то на всю группу, не может быть такого, чтоб у двух подгрупп была физра, а у третьей английский.'
    Verifies:
    1. If PE is scheduled for a group in slot (d, s), NO non-PE subject can be scheduled for that group in that slot.
    2. All subgroups taking PE must be scheduled simultaneously in the same slot.
    """
    print("\n[CHALLENGE 9] Auditing Physical Education Whole-Group Integrity...")
    by_group_day_slot = defaultdict(list)
    for l in lessons:
        by_group_day_slot[(l["group"], l["day"], l["slot"])].append(l)

    # Count expected PE subgroups per group
    expected_pe_subs = defaultdict(set)
    for it in curriculum_catalog:
        if "ФЗКиЗ" in it.get("subject", "") or it.get("lesson_type") == "ФЗКиЗ":
            if it.get("subgroup", 0) > 0:
                expected_pe_subs[it["group"]].add(it["subgroup"])

    co_occurrence_violations = []
    desync_violations = []

    for (g_name, d, s), l_list in by_group_day_slot.items():
        has_pe = any("ФЗКиЗ" in l["subject"] or l.get("lesson_type") == "ФЗКиЗ" for l in l_list)
        if has_pe:
            non_pe = [l for l in l_list if "ФЗКиЗ" not in l["subject"] and l.get("lesson_type") != "ФЗКиЗ"]
            if non_pe:
                co_occurrence_violations.append((g_name, d, s, [l["subject"] for l in non_pe]))

            subs = expected_pe_subs.get(g_name, set())
            if len(subs) >= 2:
                present_pe_subs = {
                    l["subgroup"]
                    for l in l_list
                    if ("ФЗКиЗ" in l["subject"] or l.get("lesson_type") == "ФЗКиЗ") and l.get("subgroup", 0) > 0
                }
                if present_pe_subs != subs:
                    desync_violations.append((g_name, d, s, subs, present_pe_subs))

    print(f"  PE + non-PE co-occurrence violations: {len(co_occurrence_violations)}")
    print(f"  PE subgroup desynchronization violations: {len(desync_violations)}")

    if co_occurrence_violations:
        for g_name, d, s, other_subjs in co_occurrence_violations[:5]:
            print(f"    CO-OCCURRENCE VIOLATION in group {g_name} day {d} slot {s}: co-occurred with {other_subjs}")

    if desync_violations:
        for g_name, d, s, exp, act in desync_violations[:5]:
            print(f"    DESYNC VIOLATION in group {g_name} day {d} slot {s}: expected subs {exp}, found {act}")

    assert len(co_occurrence_violations) == 0, f"Found {len(co_occurrence_violations)} PE + non-PE co-occurrence violations!"
    assert len(desync_violations) == 0, f"Found {len(desync_violations)} PE subgroup desynchronization violations!"
    print("  [PASS] Physical Education strictly scheduled for the whole group without co-occurrence.")
    return len(co_occurrence_violations) + len(desync_violations)


def main():
    print("=" * 70)
    print("EMPIRICAL CHALLENGER INDEPENDENT SCHEDULE AUDIT SUITE")
    print("Target: data/mgkct_solved_schedule.json")
    print("=" * 70)

    sched_data, curr_data = load_data()
    lessons = sched_data["schedule"]
    metrics = sched_data["metrics"]
    groups = curr_data["groups"]
    rooms = curr_data["rooms"]
    curriculum = curr_data["curriculum_items"]

    print(f"Loaded schedule with {len(lessons)} lessons.")
    print(f"Loaded curriculum with {len(groups)} groups, {len(rooms)} rooms, {len(curriculum)} items.")

    test_1_room_double_booking(lessons, rooms)
    test_2_student_gaps(lessons, groups)
    test_3_pe_single_slot(lessons)
    test_4_opfr_integrity(lessons, groups)
    test_5_teacher_exclusivity_and_campuses(lessons)
    test_6_academic_limits_and_curriculum_volume(lessons, curriculum, groups)
    test_7_shifts_starting_slots(lessons, groups)
    test_8_belarus_public_holidays(lessons, curr_data.get("metadata", {}))
    test_9_pe_whole_group_integrity(lessons, curriculum)

    print("\n" + "=" * 70)
    print("ALL 9 AUDIT SUITES PASSED STRICT ASSERTIONS EMPIRICALLY!")
    print("VERDICT: APPROVE")
    print("=" * 70)


if __name__ == "__main__":
    main()
