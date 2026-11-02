# AGENTS.md — MGKCT Timetable Optimization Engine

Instructions, architectural guidelines, and domain constraints for AI agents and developers working on the Minsk State College of Digital Technologies (MGKCT) timetable optimization system.

---

## 1. Project Overview

The objective of this project is to model, solve, and dynamically adapt weekly academic timetables for the Minsk State College of Digital Technologies (МГКЦТ). The core optimization engine is built on **Google OR-Tools (CP-SAT solver)** in Python.

### Core Capabilities
- **Automated Base Generation**: Computes conflict-free, globally optimized weekly schedules for 35 groups across 2 separate campuses.
- **Dynamic Rescheduling (Disruption Handling)**: Re-optimizes schedules in response to teacher sick leaves or emergencies while preserving frozen periods (e.g., current day/next day) and adhering to the **Minimal Perturbation** principle.
- **Physical Feasibility**: Guarantees classroom capacity limits by room type and prevents intra-day teacher travel between distant campuses.
- **Zero Room Double-Booking Guarantee**: Strict two-stage capacity modeling ensuring `room_conflicts == 0` across all academic hours.

---

## 2. Institutional Domain & College Infrastructure

### 2.1 Campuses, Groups Allocation, and Shifts
The college operates across two detached geographic campuses in Minsk:
- **Kazintsa Campus (ул. Казинца, 91)**: 20 academic groups.
- **Knorina Campus (ул. Кнорина, 14)**: 15 academic groups.

| Campus | Course | Daily Pair Cap (Mon–Fri) | Groups |
| :--- | :---: | :---: | :--- |
| **ул. Казинца** | 1 | 4 | `104РТК`, `105ТП`, `106МНЭ` |
| **ул. Казинца** | 2 | 5 | `96РТК`, `97РТК`, `98ТП`, `99ТП`, `100МНЭ` |
| **ул. Казинца** | 3 | 5 | `86РТК`, `87ТП`, `88ТП`, `89ТП`, `90МНЭ`, `91МНЭ`, `92МНЭ` |
| **ул. Казинца** | 4 | 5 | `80РТК`, `81ТП`, `82ТП`, `83МНЭ`, `84МНЭ` |
| **ул. Кнорина** | 1 | 4 | `102М`, `103М`, `107ТЭ`, `108ТЭ`, `109ТП` |
| **ул. Кнорина** | 2 | 5 | `95М`, `101ТП` |
| **ул. Кнорина** | 3 | 5 | `85М`, `9СР`, `93МНЭ`, `94ТП`, `169ТП` |
| **ул. Кнорина** | 4 | 5 | `79ТЭ`, `167ТП`, `168МНЭ` |

#### OPFR Inclusion Cohort Integrity
Groups marked with OPFR (`ОПФР`: `101ТП`, `109ТП`, `93МНЭ`, `94ТП`, `169ТП`, `167ТП`, `168МНЭ`) have specialized inclusive education tracks at the Knorina campus.
- **Undivided Cohorts**: OPFR groups comprise 6–12 students and **never split into subgroups** (`subgroup == 0`), even for computer laboratory classes.

#### Academic Shifts
- **Shift 1 (Morning Shift)**: 24 groups. Academic classes deterministically start at Pair 1 (Slot 0) on weekdays, ensuring $\ge 95\%$ first pair start rate.
- **Shift 2 (Afternoon Shift)**: 11 upper-course groups (`79ТЭ`, `84МНЭ`, `93МНЭ`, `168МНЭ`, `90МНЭ`, `91МНЭ`, `85М`, `81ТП`, `82ТП`, `83МНЭ`, `88ТП`).
  - **17-Pair Afternoon Ceiling**: In a 5-slot grid (`MAX_SLOTS = 5`, slots 0..4) with Saturday slot 4 prohibited (max 2 pairs starting slot $\ge 2$) and weekday daily capacity of 3 pairs (slots 2..4), the theoretical maximum weekly volume starting at slot $\ge 2$ across all days is $5 \times 3 + 2 = \mathbf{17 \text{ pairs}}$.
  - **Standard Load Groups ($\le 17$ pairs)**: Academic classes start strictly at Pair 3 (Slot 2) or later on weekdays ($d < 5$). Slots 0 and 1 are hard-prohibited.
  - **Heavy Upper-Course Groups ($> 17$ pairs)**: Four groups (`82ТП` [18], `84МНЭ` [18], `88ТП` [19], `90МНЭ` [20]) have loads exceeding 17 pairs. To prevent infeasibility, slot 0 is strictly prohibited on weekdays, while starting at Pair 2 (Slot 1) is permitted on at most 2 weekdays per week and is soft-penalized (+400).

---

### 2.2 Time Grid and Bell Schedule

The college operates on an extended 7-slot daily grid (`0..6`), where slots 0..4 cover academic classes and slots 5..6 support external/evening vocational practice:
- **Academic Grid**: 5 slots per day (`0..4`, Pairs 1 through 5).
- **Practice Shift Grid**: Slots 5..6 (Pairs 6..7) dedicated to vocational practice blocks (`Техн практика`, `Уч. пр. квалиф`).
- **Bell Times (Academic Grid)**:
  - **Казинца**: Slot 0 (08:00–09:40), Slot 1 (09:50–11:30), Slot 2 (11:50–13:30), Slot 3 (13:40–15:20), Slot 4 (15:30–17:00).
  - **Кнорина**: Slot 0 (09:00–10:40), Slot 1 (10:50–12:40), Slot 2 (13:00–14:40), Slot 3 (14:50–16:30), Slot 4 (16:40–18:10).

---

### 2.3 Classroom Categorization and Homeroom Anchoring

Classrooms are partitioned by campus into 5 non-interchangeable physical pools:
1. `лек` — Standard lecture classrooms (humanities, mathematics, fundamental sciences).
2. `комп` — Computer laboratories equipped with networked PC workstations (`(к)`: `2-105`, `3-205`, `3-208`, `3-212`, `401`, `501`, `503`, `504` and Knorina labs).
3. `маст` — Production and vocational workshops (`маст`: `Кн.2-011 маст`, `Кн.2-323 маст`, `Кн.2-413 маст`, `Кн.2-417 маст`, `3-201м`).
4. `спец_лаб` — Specialized hardware, microelectronics, vacuum tech, and electrical laboratories (`3-103 (лаб)`, `3-111`, `3-114`, `Кн.2-112 м`, `602`, `302`).
5. `спорт` — Physical education and sports halls (`ФЗКиЗ`).

#### Homeroom Anchoring (Закрепленные кабинеты)
Over 53% of teachers conduct $\ge 70\%$ of their classes in dedicated homerooms, and 18 teachers are 100% stationary. The Stage 2 allocator prioritizes designated `home_rooms` (+100) and teacher homerooms (+30).

---

## 3. Mathematical Model Specifications (CP-SAT)

All agents modifying optimization logic must preserve the division between Hard Constraints (satisfaction required) and Soft Constraints (penalties minimized in the objective).

### 3.1 Hard Constraints (Feasibility Boundary)

1. **Curriculum Volume Compliance**:
   $$\sum_{d=0}^{5} \sum_{s=0}^{4} x_{i, d, s} = \text{weekly\_pairs}_i$$
   *(Under teacher illness, target volume is reduced by the number of lessons scheduled on sick days).*
2. **Daily Lesson Limits**:
   - Course 1: $\le 4$ pairs per day (Monday–Friday).
   - Courses 2–4: $\le 5$ pairs per day (Monday–Friday).
   - Saturday Cap: $\le 4$ pairs for all groups; slot 4 (5th pair) is prohibited on Saturday.
3. **No Student Gaps ("Окна") at Group and Subgroup Levels**:
   Lessons for any group AND for every individual subgroup ($k \in \{1, 2, 3\}$) in a single day must form a strictly contiguous sequence without idle slots:
   $$\text{act}_{g, k, d, s} = \sum_{i \in \text{Items}(g, \text{subgroup} \in \{0, k\})} x_{i, d, s} \le 1$$
   $$\text{start}_{g, k, d, s} \ge \text{act}_{g, k, d, s} - \text{act}_{g, k, d, s-1}$$
   $$\sum_{s=0}^{4} \text{start}_{g, k, d, s} \le 1, \quad \forall g, k, d$$
4. **Physical Education Single-Slot Bound**:
   A group cannot have physical education (`ФЗКиЗ`) scheduled across multiple time slots on the same day:
   $$\text{pe\_slot}_{g, d, s} \ge x_{i, d, s}, \quad \forall i \in \text{Items}(g, \text{PE})$$
   $$\sum_{s=0}^{4} \text{pe\_slot}_{g, d, s} \le 1, \quad \forall g, d$$
5. **OPFR Cohort Integrity**:
   All curriculum items for OPFR groups must maintain $\text{subgroup} = 0$.
6. **Teacher Uniqueness**:
   A teacher cannot teach more than one lesson per time slot:
   $$\sum_{i \in \text{Items}(t)} x_{i, d, s} \le 1, \quad \forall t, d, s$$
7. **No Intra-Day Cross-Campus Travel for Teachers**:
   If a teacher is assigned courses in both Kazintsa and Knorina campuses, they must not teach in both campuses during the same calendar day:
   $$\text{use\_kaz}_{t, d} + \text{use\_kno}_{t, d} \le 1, \quad \forall t, d$$
8. **Classroom Capacity Bounds & Collision-Free Allocation**:
   For each campus $c$ and room type $r$, total concurrent lessons cannot exceed room count $C_{c, r}$:
   $$\sum_{i \in \text{Pool}(c, r)} x_{i, d, s} \le C_{c, r}, \quad \forall c, r, d, s$$
   No artificial capacity inflation hacks are permitted (`room_conflicts == 0`).
9. **Shift-Specific Start Boundaries**:
   - **Shift 1 Deterministic Morning Start**: On weekdays ($d < 5$), Shift 1 groups strictly start at Pair 1 (Slot 0):
     $$\text{act}_{g, d, 0} = \text{day\_has\_les}_{g, d}, \quad \text{start}_{g, d, s} = 0, \quad \forall d < 5, s \ge 1$$
     On Saturday ($d = 5$), starting at slots 2..4 is prohibited ($\text{start}_{g, 5, s} = 0, \forall s \ge 2$), with soft penalties on slot 1 start, guaranteeing $\ge 95.0\%$ overall first pair starts.
   - **Shift 2 ($\le 17$ pairs)**: Prohibited from using morning slots 0 and 1 on weekdays:
     $$\text{act}_{g, d, 0} = 0, \quad \text{act}_{g, d, 1} = 0, \quad \forall d < 5$$
   - **Shift 2 ($> 17$ pairs)**: Prohibited from using slot 0 on weekdays, and bounded to at most 2 slot 1 starts on weekdays:
     $$\text{act}_{g, d, 0} = 0, \quad \forall d < 5$$
     $$\sum_{d=0}^{4} \text{start}_{g, d, 1} \le 2$$

---

### 3.2 Soft Constraints & Objective Penalties

The objective function minimizes $\sum \text{penalties}$:

| Rule | Mathematical Mechanism | Weight / Penalty | Rationale |
| :--- | :--- | :---: | :--- |
| **Shift 1 Saturday Early Start** | $(\text{day\_has\_les}_{g, 5} - \text{act}_{g, 5, 0}) \times 1500 + \text{start}_{g, 5, 1} \times 800$ | 800 / 1500 | Guides Saturday morning shift groups to slot 0. |
| **Shift 2 Afternoon Preference** | Penalty on slot 1 start for heavy groups (+400); Saturday morning (+300, +100); start $> 2$ ($60 \times (s-2)$) | 60 to 400 | Directs 2nd shift to start at 3rd pair (slot 2) or later. |
| **Teacher Windows Penalty** | $\text{extra\_starts}_{t, d} \times 80$ | 80 | Minimizes idle windows in faculty daily schedules. |
| **Late Slot Weight** | $\text{active}_{g, d, s} \times W_s$, where $W = [0, 2, 6, 18, 40]$ | 2 to 40 | Prioritizes compact days and early completion. |
| **Saturday Relief** | Additional penalty on slot 3 (+40), slot 2 (+20), slot 1 (+5) | 5 to 40 | Promotes early release on Saturdays without hard prohibition. |
| **Duplicate Subject Limit** | $\text{max}(0, \sum_s x_{i, d, s} - 1) \times 60$ (Exempt: `ЛР`, `Пр-ка`, `КП`) | 60 | Discourages duplicate lectures; permits 2-hour lab/practice blocks. |
| **Subgroup Synchronicity** | $\lvert x_{i1, d, s} - x_{i2, d, s} \rvert \times W_{\text{sync}}$ (Exempt: sets where teachers are identical, avoiding deadweight penalty) | 60 / 120 | Encourages simultaneous labs while permitting sequential single-teacher teaching. |
| **Lecture-before-Lab Order** | Penalize lab on day 0 when lecture exists for subject | 10 | Promotes theoretical foundation before practical work. |

---

### 3.3 Dynamic Rescheduling & Disruption Handling

When handling teacher illness or emergency cancellations:
- **No Autonomous Substitution**: No automatic teacher reassignment. The sick teacher's scheduled pairs are dropped.
- **Frozen Period Enforcement**: Days designated as frozen (e.g., past days, current day, or next day) must remain strictly fixed to their baseline slots:
  $$x_{i, d, s} = \text{baseline}_{i, d, s}, \quad \forall d \in \text{FrozenDays}$$
- **Contiguity Preservation**: Remaining classes on affected days are shifted forward to eliminate any resulting student windows.
- **Minimal Perturbation Objective**:
  - Penalty for changing the day of a lesson: **300**.
  - Penalty for shifting slot within the same day: **80**.
  - Solver hints seeded from baseline schedule to guide search towards minimal diffs.

---

## 4. Repository Structure

```text
mgkct-timetable-optimizer/
├── .gitattributes             # Git line ending normalization
├── .gitignore                 # Files excluded from version control
├── AGENTS.md                  # System architecture, constraints, and operational manual (this file)
├── ANALYTICAL_REPORT.md       # Empirical dump discrepancy report and mathematical proofs
├── LICENSE                    # MIT License
├── README.md                  # Project overview and technical documentation
├── pyproject.toml             # Python package configuration and metadata (PEP 621)
├── requirements.txt           # Project dependencies (ortools)
├── run.py                     # Convenience top-level solver runner
├── src/                       # Modular Python package
│   └── mgkct_optimizer/
│       ├── __init__.py        # Public package API exports
│       ├── models.py          # Dataclasses (GroupInfo, RoomInfo, CurriculumItem, Lesson, MAX_SLOTS=5)
│       ├── loader.py          # Curriculum data loader with OPFR and shift metadata
│       ├── solver.py          # Google OR-Tools CP-SAT discrete optimization core
│       ├── allocator.py       # Prioritized bipartite matching room allocator
│       ├── metrics.py         # Independent verification audit engine
│       └── cli.py             # CLI parser and runner (`python -m mgkct_optimizer`)
├── web/                       # Client web application
│   └── index.html             # Visual schedule representation and metrics dashboard
└── data/
    ├── mgkct_curriculum.json       # Extracted curriculum requirements, shifts, and rooms
    ├── mgkct_solved_schedule.json  # Solved baseline schedule output
    └── exported/                   # Historical database and JSON export dumps
```

---

## 5. Development & Contribution Rules for AI Agents

1. **Strict CP-SAT Paradigm**:
   - Use integer arithmetic only. Never introduce floats into constraints or objective terms.
   - Prefer boolean indicator variables (`NewBoolVar`) over linear expressions inside reified constraints.
   - Maintain symmetry breaking where applicable (e.g., subgroup pair bindings).
2. **Verification Protocol**:
   - Every modification to solver rules must be validated by running:
     ```powershell
     python run.py
     ```
   - Validation criteria:
     - `student_windows == 0` (Zero student windows).
     - `max_daily_violations == 0` (Zero daily overload).
     - `cross_campus_violations == 0` (Zero teacher multi-campus days).
     - `room_conflicts == 0` (Zero physical room collisions).
     - `pe_daily_slot_violations == 0` (Zero multiple-PE days).
     - `first_pair_start_pct >= 90.0%` (Vast majority of shift 1 starting slot 0).
3. **Data Integrity**:
   - Group names, teacher names, and room numbers must strictly match MGKCT official nomenclatures (e.g. `Кн.` prefix for Knorina rooms, `(к)` for computer classes).
   - Never remove or alter curriculum hours without checking standard 20-pair limits.
4. **Git Policy Reminder**:
   - Never run `git commit` or `git push` autonomously. Provide diffs, test summaries, and conventional commit proposals to the user.
