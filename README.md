# MGKCT Timetable Optimization Engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![OR-Tools](https://img.shields.io/badge/solver-Google%20OR--Tools%20CP--SAT-red?style=flat)](https://developers.google.com/optimization/cp/cp_solver)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)
[![Format](https://img.shields.io/badge/code%20style-PEP%208-informational?style=flat)](https://peps.python.org/pep-0008/)

Discrete optimization engine and dynamic disruption rescheduling system for the Minsk State College of Digital Technologies (МГКЦТ), powered by Google OR-Tools CP-SAT solver.

---

## Overview

The engine formulates and solves a high-dimensional Constraint Satisfaction Problem (CSP) to construct optimal weekly academic timetables for 35 student groups distributed across two physically separated campuses in Minsk. It guarantees physical feasibility, eliminates student idle periods ("окна"), enforces pedagogical load distribution, and provides dynamic re-optimization capabilities under operational disruptions (e.g., teacher illness, emergency cancellations) using the Minimal Perturbation principle.

### Operational Context

| Dimension | Specification |
| :--- | :--- |
| **Campuses** | 2 detached sites: ул. Казинца, 91 (20 groups) and ул. Кнорина, 14 (15 groups) |
| **Academic Groups** | 35 groups (Courses 1 through 4, including specialized ОПФР inclusion streams) |
| **Time Grid** | 6 academic days (Monday = 0 to Saturday = 5), 4 pairs per day (slots 0..3) |
| **Daily Shift** | 1st shift only (2nd shift / slots 5–7 eliminated to ensure early student departure) |
| **Classroom Pools** | 3 non-interchangeable categories per campus: `лек` (lecture), `комп` (computer lab), `спорт` (gymnasium) |

---

## Mathematical Model Architecture

The scheduling problem is modeled as an exact Constraint Programming integer problem evaluated by the CP-SAT solver.

### Hard Constraints (Feasibility Boundary)

1. **Curriculum Volume Compliance**:
   Every group must receive exactly the required number of weekly pairs defined by official RIPO curriculum plans.
2. **Student Gap Elimination ("Окна")**:
   For any academic group on any day, all assigned lessons form a strictly contiguous time block:
   $$\sum_{s=0}^{3} \text{start}_{g, d, s} \le 1, \quad \forall g, d$$
3. **Daily Lesson Limits**:
   - Course 1: $\le 3$ pairs/day.
   - Courses 2–4: $\le 4$ pairs/day (Monday–Friday).
   - Saturday Cap: $\le 3$ pairs/day for all courses; pair 4 (slot 3) is strictly forbidden.
4. **Physical Education Whole-Group Integrity**:
   When physical education (`ФЗКиЗ`) is scheduled for an academic group, it must occupy the entire group simultaneously. Subgroups cannot have physical education concurrently with another subject (e.g., Foreign Language), and all PE subgroups are synchronized to the exact same slot:
   $$x_{i_{\text{pe}}, d, s} + x_{i_{\text{non}}, d, s} \le 1, \quad \forall d, s$$
5. **Belarus Public Holidays Absolute Ban**:
   Lessons are strictly prohibited across all groups on official non-working public holidays of the Republic of Belarus (Decree No. 157 & Labour Code Art. 147), including dynamically calculated floating holidays (Radunitsa via astronomical Meeus algorithm):
   $$x_{i, d, s} = 0, \quad \forall d \in \text{Holidays}, s$$
6. **Subgroup Synchronicity**:
   When a curriculum entry requires subgroup division (e.g., Informatics and Foreign Language), both subgroup lessons are bound to identical `(day, slot)` tuples.
7. **Teacher Uniqueness**:
   A teacher cannot be assigned to more than one pair in any given time slot.
8. **No Intra-Day Cross-Campus Travel**:
   Teachers assigned to both Kazintsa and Knorina campuses are strictly prohibited from teaching at both campuses within the same calendar day.
9. **Classroom Aggregate Pool Capacity**:
   Concurrent lessons in pool $r$ at campus $c$ cannot exceed the pool's room count $C_{c, r}$.

### Soft Constraints and Objective Penalties

The objective function minimizes total penalty points:

| Constraint | Penalty Formulation | Weight | Technical Purpose |
| :--- | :--- | :---: | :--- |
| **Late Start Penalty** | $\text{start}_{g, d, s} \times 45 \times s$ for $s \ge 1$ | $45 \times s$ | Forces daily schedules to begin at slot 0 (08:00 / 09:00). |
| **Late Slot Weight** | $\text{active}_{g, d, s} \times W_s$, where $W = [0, 2, 6, 18]$ | 2 to 18 | Prioritizes early release and compact schedules. |
| **Saturday Relief** | Additional penalty on slot 1 ($+5$) and slot 2 ($+20$) | $+5 / +20$ | Minimizes Saturday academic load. |
| **Duplicate Subject Cap** | $\max(0, \sum_s x_{i, d, s} - 1) \times 60$ | 60 | Prevents back-to-back double pairs unless necessary. |
| **Lecture Precedence** | Lab placed on Day 0 when lecture exists | 10 | Ensures theoretical foundation precedes lab work. |

### Dynamic Rescheduling (Disruption Handling)

When a teacher is placed on sick leave or classes are cancelled:
- **Zero Autonomous Substitution**: Unassigned pairs are removed from the schedule rather than randomly assigned to unfamiliar staff.
- **Frozen Period Preservation**: Completed days and immediate upcoming days remain strictly locked to baseline slots ($x_{i, d, s} = \text{baseline}_{i, d, s}$).
- **Minimal Perturbation Principle**: Re-optimization applies high penalties for moving unaffected classes to different days (penalty 300) or slots (penalty 80), seeded by solver hints from the baseline schedule.

---

## Repository Structure

```text
mgkct-timetable-optimizer/
├── .gitattributes             # Git normalization rules
├── .gitignore                 # Files excluded from version control
├── AGENTS.md                  # Comprehensive AI agents and solver guidelines
├── LICENSE                    # MIT License
├── README.md                  # Technical system documentation
├── pyproject.toml             # Project configuration and packaging metadata (PEP 621)
├── requirements.txt           # Python package dependencies
├── run.py                     # Convenience top-level solver runner
├── src/                       # Modular Python package
│   └── mgkct_optimizer/
│       ├── __init__.py        # Public package API exports
│       ├── models.py          # Dataclasses (GroupInfo, RoomInfo, CurriculumItem, Lesson)
│       ├── loader.py          # Curriculum data loader from data/mgkct_curriculum.json
│       ├── holidays.py        # Belarus public holidays calendar (fixed + Meeus astronomical Radunitsa)
│       ├── parser.py          # Live scraper for official MGKCT portal weekly timetables
│       ├── solver.py          # Google OR-Tools CP-SAT discrete optimization core
│       ├── allocator.py       # Two-stage classroom assignment heuristic
│       ├── metrics.py         # Independent verification audit engine
│       └── cli.py             # CLI parser and runner (`python -m mgkct_optimizer`)
├── web/                       # Client web application
│   └── index.html             # Interactive schedule visualizer and disruption simulator
└── data/                      # (Local only, .gitignore) Curriculum and solved schedules
```

---

## Installation & Requirements

### Prerequisites
- Python 3.10 or higher
- Modern web browser (to view `web/index.html`)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Arsenii/mgkct-timetable-optimizer.git
   cd mgkct-timetable-optimizer
   ```

2. Create and activate a virtual environment:
   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # Or install as editable package
   pip install -e .
   ```

---

## Usage

### Live Curriculum Scraper

To scrape real, live weekly schedule data from the official MGKCT portal:

```bash
# Scrape current week from the official portal
python -m mgkct_optimizer.parser data/mgkct_curriculum.json

# Or scrape and immediately optimize with the solver CLI
python -m mgkct_optimizer --scrape --time-limit 25.0
```

### Run Optimization Solver

To compute a baseline schedule and export the JSON solution:

```bash
# Using the top-level runner
python run.py

# Or via the Python module
python -m mgkct_optimizer

# Or via installed console script
mgkct-optimizer --time-limit 20.0
```

Execution stages:
1. Loads and validates curriculum data (`data/mgkct_curriculum.json`).
2. Constructs the CP-SAT integer programming model with hard and soft constraints.
3. Solves the CSP problem using parallel search workers.
4. Performs secondary post-processing room assignment (teacher home room anchoring + greedy capacity fill).
5. Executes an independent verification audit on 100% of constraints.
6. Serializes the final timetable to `data/mgkct_solved_schedule.json`.

### View Visual Schedule Dashboard

Open `web/index.html` in any modern web browser or run local server:

```bash
# Start local HTTP server
python -m http.server 8080 -d .
# Open in browser: http://127.0.0.1:8080/web/
```

Features included in the web interface:
- Campus and group filter dropdowns.
- Bell schedule alignment per campus.
- Subgroup indicators and classroom allocations.
- Real-time solver metrics and audit indicators.

---

## Verification Metrics

The solver includes a self-auditing metric suite executed after every run:

| Metric | Target | Description |
| :--- | :---: | :--- |
| `student_windows` | **0** | Idle gaps between pairs for any group on any day |
| `max_daily_violations` | **0** | Exceeding 3 pairs for Course 1 or 4 pairs for Courses 2–4 |
| `cross_campus_violations` | **0** | Teacher scheduled at both Kazintsa and Knorina on the same day |
| `pe_daily_slot_violations` | **0** | Multiple physical education slots on the same day for a group |
| `pe_split_violations` | **0** | PE desynchronization or concurrent non-PE subject with PE |
| `holiday_violations` | **0** | Lessons scheduled on official Republic of Belarus public holidays |
| `subgroup_sync_violations` | **0** | Desynchronized split subgroups |
| `first_pair_start_pct` | **$\ge$ 90.0%** | Percentage of group-days starting at pair 1 (slot 0) |

---

## Institutional References

- MGKCT Official Portal: [mgkct.minskedu.gov.by](https://mgkct.minskedu.gov.by/)
- Bell Schedule & Campus Distribution: [Announcements Document 70533](https://mgkct.minskedu.gov.by/about/announcements/document-70533.html)
- Weekly Group & Teacher Timetables: [Weekly Timetable Portal](https://mgkct.minskedu.gov.by/personnel/for-students/weekly-timetable)
- RIPO Educational Standards & Curriculum Plans: [ripo.unibel.by](http://ripo.unibel.by/index.php?id=1656)

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
