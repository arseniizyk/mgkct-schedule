#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Command-line interface for the MGKCT Timetable Optimization Engine.
Supports solving baseline schedule, dynamic disruption rescheduling,
and JSON serialization.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from typing import List, Dict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .loader import load_curriculum_data, get_default_curriculum_path
from .solver import MGKCTScheduleOptimizer
from .models import ScheduledLesson


def export_solved_schedule(
    schedule: List[ScheduledLesson],
    metrics: Dict,
    file_path: str,
):
    """Exports solved schedule and metrics to JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics,
        "schedule": [asdict(l) for l in schedule],
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Schedule successfully exported to {file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="MGKCT Timetable Optimization Engine (Google OR-Tools CP-SAT)"
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=20.0,
        help="Solver maximum search time in seconds (default: 20.0)",
    )
    parser.add_argument(
        "--curriculum",
        type=str,
        default=None,
        help="Path to mgkct_curriculum.json (default: data/mgkct_curriculum.json)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Path to export solved schedule JSON (default: data/mgkct_solved_schedule.json)",
    )
    parser.add_argument(
        "--demo-reschedule",
        action="store_true",
        default=True,
        help="Run dynamic disruption simulation demonstration (default: True)",
    )
    args = parser.parse_args()

    curriculum_path = args.curriculum or get_default_curriculum_path()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    export_path = args.export or os.path.join(project_root, "data", "mgkct_solved_schedule.json")

    print(f"Loading curriculum data from: {curriculum_path}")
    groups, rooms, items = load_curriculum_data(curriculum_path)
    print(f"Loaded: {len(groups)} groups, {len(rooms)} classrooms, {len(items)} curriculum items.")

    optimizer = MGKCTScheduleOptimizer(groups, rooms, items)
    print(f"\nSolving baseline schedule (time limit: {args.time_limit}s)...")
    sched, metrics = optimizer.solve(time_limit_sec=args.time_limit)

    print("\n=== БАЗОВОЕ ОПТИМИЗИРОВАННОЕ РАСПИСАНИЕ (35 ГРУПП) ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    export_solved_schedule(sched, metrics, export_path)

    if args.demo_reschedule:
        active_teachers = [l.teacher for l in sched if l.day in (2, 3)]
        demo_teacher = active_teachers[0] if active_teachers else "Преподаватель Химии"
        print(f"\nSimulating dynamic disruption: sick leave for {demo_teacher} on Wed-Thu (frozen: Mon-Tue)...")

        resched, r_metrics = optimizer.solve(
            time_limit_sec=10.0,
            baseline_schedule=sched,
            sick_teachers={demo_teacher: [2, 3]},
            frozen_days=[0, 1],
        )

        print(f"\n=== ПЕРЕСТРОЕННОЕ РАСПИСАНИЕ (БОЛЕЗНЬ {demo_teacher} В СР-ЧТ) ===")
        for k, v in r_metrics.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
