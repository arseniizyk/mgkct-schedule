#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Empirical test suite for Teacher Disruption Rescheduling in MGKCT Optimizer.
Tests multi-day sick leaves across high-load, cross-campus, and Shift-2 faculty.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from mgkct_optimizer.loader import load_curriculum_data, get_default_curriculum_path
from mgkct_optimizer.solver import MGKCTScheduleOptimizer
from mgkct_optimizer.models import ScheduledLesson, NUM_DAYS, MAX_SLOTS


def load_baseline():
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


def run_disruption_scenario(optimizer, baseline, teacher_name, sick_days, frozen_days, time_limit_sec=15.0):
    print(f"\n=======================================================")
    print(f"TEST SCENARIO: Disruption for '{teacher_name}'")
    print(f"Sick Days: {sick_days}, Frozen Days: {frozen_days}")
    print(f"=======================================================")

    t0 = time.time()
    resched, r_metrics = optimizer.solve(
        time_limit_sec=time_limit_sec,
        baseline_schedule=baseline,
        sick_teachers={teacher_name: sick_days},
        frozen_days=frozen_days,
    )
    elapsed = time.time() - t0

    # 1. Assert Status
    status = r_metrics.get("status")
    print(f"1. Solver Status: {status} (time: {elapsed:.2f}s)")
    assert status in ("FEASIBLE", "OPTIMAL"), f"Expected FEASIBLE or OPTIMAL, got {status}"

    # 2. Assert Frozen Days strictly preserved: x_{i, d, s} == baseline_{i, d, s}
    # For frozen days, every lesson in baseline on that day (except if sick teacher taught it) must remain identical
    frozen_set = set(frozen_days)
    sick_days_set = set(sick_days)

    base_frozen = {(l.item_id, l.day, l.slot) for l in baseline if l.day in frozen_set}
    resched_frozen = {(l.item_id, l.day, l.slot) for l in resched if l.day in frozen_set}

    # Lessons of sick teacher on frozen days:
    sick_teacher_frozen_base = {(l.item_id, l.day, l.slot) for l in baseline if l.day in frozen_set and l.teacher == teacher_name and l.day in sick_days_set}
    expected_frozen = base_frozen - sick_teacher_frozen_base

    frozen_diff_missing = expected_frozen - resched_frozen
    frozen_diff_extra = resched_frozen - expected_frozen

    print(f"2. Frozen days check (Days {frozen_days}):")
    print(f"   Baseline lessons on frozen days: {len(base_frozen)}")
    print(f"   Rescheduled lessons on frozen days: {len(resched_frozen)}")
    print(f"   Missing from frozen: {len(frozen_diff_missing)}")
    print(f"   Unexpected extra on frozen: {len(frozen_diff_extra)}")
    assert len(frozen_diff_missing) == 0, f"Frozen day violation: missing lessons {frozen_diff_missing}"
    assert len(frozen_diff_extra) == 0, f"Frozen day violation: extra lessons {frozen_diff_extra}"

    # 3. Assert Sick Teacher cancelled on sick days:
    sick_teacher_resched_lessons = [l for l in resched if l.teacher == teacher_name and l.day in sick_days_set]
    print(f"3. Sick teacher lessons on sick days (expected 0): {len(sick_teacher_resched_lessons)}")
    assert len(sick_teacher_resched_lessons) == 0, f"Sick teacher {teacher_name} has lessons scheduled on sick days!"

    # 4. Assert Student Windows == 0
    student_windows = r_metrics.get("student_windows", -1)
    subgroup_windows = r_metrics.get("subgroup_windows", -1)
    print(f"4. Student windows: {student_windows}, Subgroup windows: {subgroup_windows}")
    assert student_windows == 0, f"Expected student_windows == 0, got {student_windows}"
    assert subgroup_windows == 0, f"Expected subgroup_windows == 0, got {subgroup_windows}"

    # 5. Assert Room Conflicts == 0
    room_conflicts = r_metrics.get("room_conflicts", -1)
    print(f"5. Room conflicts: {room_conflicts}")
    assert room_conflicts == 0, f"Expected room_conflicts == 0, got {room_conflicts}"

    # 6. Assert Minimal Perturbation
    unchanged_count = r_metrics.get("unchanged_lessons_count", 0)
    unchanged_pct = r_metrics.get("unchanged_lessons_pct", 0.0)
    print(f"6. Minimal Perturbation: {unchanged_count}/{len(resched)} lessons unchanged ({unchanged_pct}%)")
    assert unchanged_pct >= 60.0, f"Expected unchanged_lessons_pct >= 60.0%, got {unchanged_pct}%"

    # 7. Additional checks: daily caps and cross-campus
    max_daily = r_metrics.get("max_daily_violations", 0)
    cross_campus = r_metrics.get("cross_campus_violations", 0)
    pe_violations = r_metrics.get("pe_daily_slot_violations", 0)
    print(f"7. Sanity checks: max_daily_violations={max_daily}, cross_campus={cross_campus}, pe_violations={pe_violations}")
    assert max_daily == 0, f"max_daily_violations: {max_daily}"
    assert cross_campus == 0, f"cross_campus_violations: {cross_campus}"
    assert pe_violations == 0, f"pe_daily_slot_violations: {pe_violations}"

    print(f"==> SCENARIO '{teacher_name}' PASSED ALL ASSERTIONS!")
    return r_metrics


def main():
    groups, rooms, items, baseline = load_baseline()
    optimizer = MGKCTScheduleOptimizer(groups, rooms, items)

    # Dynamically select top active representative teachers from baseline schedule
    teacher_loads = {}
    for l in baseline:
        teacher_loads[l.teacher] = teacher_loads.get(l.teacher, 0) + 1
    sorted_teachers = [t for t, _ in sorted(teacher_loads.items(), key=lambda x: -x[1])]

    scenarios = [
        # (Teacher, Sick Days, Frozen Days)
        (sorted_teachers[0], [1, 2], [0]),
        (sorted_teachers[1], [1, 2], [0]),
        (sorted_teachers[2], [1, 2], [0]),
        (sorted_teachers[3], [1, 2], [0]),
        (sorted_teachers[4], [2, 3], [0, 1]),
    ]

    all_passed = True
    results = {}
    for teacher, sick_days, frozen_days in scenarios:
        try:
            m = run_disruption_scenario(optimizer, baseline, teacher, sick_days, frozen_days)
            results[teacher] = {"status": "PASS", "metrics": m}
        except Exception as e:
            print(f"FAILED scenario '{teacher}': {e}")
            results[teacher] = {"status": "FAIL", "error": str(e)}
            all_passed = False

    print("\n================== SUMMARY ==================")
    for t, res in results.items():
        print(f"{t}: {res['status']}")

    if not all_passed:
        sys.exit(1)


def test_disruptions():
    main()


if __name__ == "__main__":
    main()
