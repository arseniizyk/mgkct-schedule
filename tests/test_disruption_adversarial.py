#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial Disruption and Stress Test Harness for MGKCT Timetable Optimization Engine.
Tests dynamic re-optimization under sick leave scenarios with frozen day constraints.
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
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from mgkct_optimizer.loader import load_curriculum_data, get_default_curriculum_path
from mgkct_optimizer.solver import MGKCTScheduleOptimizer
from mgkct_optimizer.metrics import compute_schedule_metrics
from mgkct_optimizer.models import ScheduledLesson


def run_disruption_test(teacher_name: str, sick_days: List[int], frozen_days: List[int], time_limit: float = 12.0):
    print(f"\n--- Testing Disruption: Teacher '{teacher_name}' Sick on Days {sick_days}, Frozen Days: {frozen_days} ---")

    groups, rooms, items = load_curriculum_data()
    optimizer = MGKCTScheduleOptimizer(groups, rooms, items)

    # 1. Baseline
    sched_path = os.path.join(PROJECT_ROOT, "data", "mgkct_solved_schedule.json")
    with open(sched_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    baseline_sched = [ScheduledLesson(**l) for l in data["schedule"]]
    groups_dict = {g.name: g for g in groups}

    # Lessons of sick teacher on sick days in baseline
    sick_teacher_baseline = [
        l for l in baseline_sched
        if l.teacher == teacher_name and l.day in sick_days
    ]
    print(f"  Baseline pairs for {teacher_name} on days {sick_days}: {len(sick_teacher_baseline)}")

    # 2. Re-optimize
    resched, metrics = optimizer.solve(
        time_limit_sec=time_limit,
        baseline_schedule=baseline_sched,
        sick_teachers={teacher_name: sick_days},
        frozen_days=frozen_days,
    )

    print(f"  Rescheduled lessons count: {len(resched)} (dropped: {len(baseline_sched) - len(resched)})")
    print(f"  Status: {metrics['status']}")
    print(f"  Student windows: {metrics['student_windows']}")
    print(f"  Subgroup windows: {metrics['subgroup_windows']}")
    print(f"  Room conflicts: {metrics['room_conflicts']}")
    print(f"  Teacher windows: {metrics['teacher_windows']}")
    print(f"  Cross-campus violations: {metrics['cross_campus_violations']}")
    print(f"  Unchanged lessons: {metrics.get('unchanged_lessons_count')} ({metrics.get('unchanged_lessons_pct')}%)")

    # 3. Assertions
    # a. Solver status
    assert metrics["status"] in ("OPTIMAL", "FEASIBLE"), f"Disruption solve failed: {metrics['status']}"

    # b. Hard constraints
    assert metrics["room_conflicts"] == 0, f"Room conflicts found in disruption: {metrics['room_conflicts']}"
    assert metrics["student_windows"] == 0, f"Student windows found in disruption: {metrics['student_windows']}"
    assert metrics["subgroup_windows"] == 0, f"Subgroup windows found in disruption: {metrics['subgroup_windows']}"
    assert metrics["cross_campus_violations"] == 0, f"Cross-campus violations: {metrics['cross_campus_violations']}"
    assert metrics["max_daily_violations"] == 0, f"Daily overload: {metrics['max_daily_violations']}"

    # c. Sick teacher lessons on sick days must be strictly 0
    resched_sick_teacher = [
        l for l in resched
        if l.teacher == teacher_name and l.day in sick_days
    ]
    assert len(resched_sick_teacher) == 0, f"Sick teacher {teacher_name} still has lessons on sick days: {resched_sick_teacher}"

    # d. Frozen days preservation: for any d in frozen_days, all non-sick lessons must match baseline exactly
    frozen_base = {
        (l.item_id, l.day, l.slot): l.room
        for l in baseline_sched
        if l.day in frozen_days and not (l.teacher == teacher_name and l.day in sick_days)
    }
    frozen_resched = {
        (l.item_id, l.day, l.slot): l.room
        for l in resched
        if l.day in frozen_days
    }
    # Check that every lesson in frozen_base exists in frozen_resched at the EXACT same day and slot
    missing_frozen = set(frozen_base.keys()) - set(frozen_resched.keys())
    assert len(missing_frozen) == 0, f"Frozen day lessons missing or moved: {len(missing_frozen)}"

    # e. Minimal perturbation check: high percentage of unchanged lessons (>= 70%)
    unchanged_pct = metrics.get("unchanged_lessons_pct", 0)
    assert unchanged_pct >= 70.0, f"Unchanged lessons percentage {unchanged_pct}% < 70% threshold!"

    print(f"  [PASS] Disruption for {teacher_name} strictly verified.")
    return metrics


def main():
    print("=" * 70)
    print("ADVERSARIAL DISRUPTION AND STRESS TEST HARNESS")
    print("=" * 70)

    import json
    sched_path = os.path.join(PROJECT_ROOT, "data", "mgkct_solved_schedule.json")
    data = json.load(open(sched_path, encoding="utf-8"))
    teacher_loads = {}
    for l in data["schedule"]:
        t = l["teacher"]
        teacher_loads[t] = teacher_loads.get(t, 0) + 1
    sorted_teachers = [t for t, _ in sorted(teacher_loads.items(), key=lambda x: -x[1])]
    t1 = sorted_teachers[0]
    t2 = sorted_teachers[1]

    # Test 1: High load teacher
    run_disruption_test(t1, sick_days=[2, 3], frozen_days=[0, 1], time_limit=12.0)

    # Test 2: Active teacher
    run_disruption_test(t2, sick_days=[2, 3], frozen_days=[0, 1], time_limit=12.0)

    print("\n" + "=" * 70)
    print("ALL DISRUPTION ADVERSARIAL STRESS TESTS PASSED EMPIRICALLY!")
    print("=" * 70)


def test_disruption_adversarial():
    main()


if __name__ == "__main__":
    main()
