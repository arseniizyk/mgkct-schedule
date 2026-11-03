import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from mgkct_optimizer.loader import load_curriculum_data, get_default_curriculum_path
from mgkct_optimizer.solver import MGKCTScheduleOptimizer

def test_stability():
    curriculum_path = get_default_curriculum_path()
    groups, rooms, items = load_curriculum_data(curriculum_path)

    results = []
    for i in range(1, 6):
        opt = MGKCTScheduleOptimizer(groups, rooms, items)
        sched, m = opt.solve(time_limit_sec=15.0)
        pct = m["first_pair_start_pct"]
        win = m["student_windows"]
        rc = m["room_conflicts"]
        obj = m["objective_value"]
        print(f"Run {i}: status={m['status']}, shift1_start_pct={pct}%, windows={win}, room_conf={rc}, obj={obj}")
        assert pct >= 85.0, f"Run {i} failed threshold: {pct}%"
        assert win == 0, f"Run {i} has windows: {win}"
        assert rc == 0, f"Run {i} has room conflicts: {rc}"
        results.append(pct)

    print("All 5 runs passed! Shift 1 start percentages:", results)

if __name__ == "__main__":
    test_stability()
