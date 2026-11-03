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

#### Campus Days and Whitelist of Hybrid Groups
While groups are primarily based at their home campus, specific groups have scheduled whole-day campus visit days ("выездные дни") to access specialized laboratories and faculty without intra-day travel:
- `107ТЭ`: Visits Kazintsa every Wednesday (day 2) and Friday (day 4); attends Knorina on Mon, Tue, Thu, Sat.
- `108ТЭ`: Visits Kazintsa every Tuesday (day 1) and Thursday (day 3); attends Knorina on Mon, Wed, Fri, Sat.
- `167ТП`: OPFR group permanently studying at Knorina (room `Кн.1-109`).
- **Zero Intra-Day Travel Invariant**: Neither students nor teachers ever travel between campuses within the same calendar day. Every campus visit encompasses the entire academic day.

#### Unified Academic Schedule (No Shifts)
The college operates on a single unified academic schedule starting at 09:00:
- **No Division into Shifts**: All 35 academic groups start deterministically at Pair 1 (Slot 0, 09:00) on weekdays, ensuring a 100% first pair start rate across both campuses.
- **Compact Mornings**: Upper-course groups and first-year groups alike attend classes starting from Pair 1 without afternoon shift delays.

---

### 2.2 Time Grid and Bell Schedule

The college operates on a unified bell schedule starting at 09:00 across all campuses:
- **Academic Grid**: Slots 0..4 (Pairs 1 through 5).
- **Bell Schedule (Official)**:
  - **1-я пара**: `09:00–10:40` (09:00 - 09:45 | 09:55 - 10:40)
  - **2-я пара**: `10:50–12:40` (10:50 - 11:35 | 11:55 - 12:40)
  - **3-я пара**: `13:00–14:40` (13:00 - 13:45 | 13:55 - 14:40)
  - **4-я пара**: `14:50–16:30` (14:50 - 15:35 | 15:45 - 16:30)
  - **5-я пара**: `16:40–18:20` (16:40 - 17:25 | 17:35 - 18:20)
  - **6-я пара**: `18:30–20:10` (18:30 - 19:15 | 19:25 - 20:10)

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
2. **Daily Lesson Limits & Subgroup Cap**:
   - Course 1: $\le 4$ pairs per day (Monday–Friday), strictly starting at Pair 1 (Slot 0, 09:00).
   - Courses 2–4: $\le 4$ academic pairs per day for any subgroup and group ($\le 5$ total only on the day of Informational Hour). Groups can study up to Pair 5 (Slot 4, 16:40–18:20) by starting at Pair 2 (Slot 1, 10:50, slots 1..4), strictly forbidding studying 1st through 5th pair in a single day.
   - Saturday Cap: $\le 3$ pairs for all groups; slots 3 and 4 (4th and 5th pairs) are prohibited on Saturday.
   - Teachers: $\le 5$ pairs per day across all courses and campuses.
3. **No Student Gaps ("Окна") at Group and Subgroup Levels**:
   Lessons for any group AND for every individual subgroup ($k \in \{1, 2, 3\}$) in a single day must form a strictly contiguous sequence without idle slots:
   $$\text{act}_{g, k, d, s} = \sum_{i \in \text{Items}(g, \text{subgroup} \in \{0, k\})} x_{i, d, s} \le 1$$
   $$\text{start}_{g, k, d, s} \ge \text{act}_{g, k, d, s} - \text{act}_{g, k, d, s-1}$$
   $$\sum_{s=0}^{4} \text{start}_{g, k, d, s} \le 1, \quad \forall g, k, d$$
4. **Physical Education Whole-Group Integrity & Single-Slot Bound**:
   When physical education (`ФЗКиЗ`) is scheduled for a group $g$, it must occupy the entire group simultaneously. No scenario is permitted where one or two subgroups have PE while another subgroup has a different subject:
   - All PE subgroups of group $g$ are bound to identical time slots:
     $$x_{i_{\text{pe}, 1}, d, s} = x_{i_{\text{pe}, k}, d, s}, \quad \forall k > 1$$
   - Non-PE subjects for any subgroup of group $g$ cannot occur in a slot where PE is scheduled:
     $$x_{i_{\text{pe}}, d, s} + x_{i_{\text{non}}, d, s} \le 1, \quad \forall i_{\text{non}} \in \text{Items}(g, \text{non-PE}), \forall d, s$$
   - A group cannot have physical education scheduled across multiple time slots on the same day:
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
9. **Morning Start & Late Pair Scheduling**:
   - On weekdays ($d < 5$), Course 1 groups strictly start at Pair 1 (Slot 0, 09:00).
   - Courses 2–4 preferentially start at Pair 1 (Slot 0); when scheduled up to Pair 5 (Slot 4), they start at Pair 2 (Slot 1) to respect the $\le 4$ daily pair cap (never studying 1st through 5th pair). Starting at slots 2..4 on weekdays is prohibited.
   - On Saturday ($d = 5$), starting at slots 2..4 is prohibited ($\text{start}_{g, 5, s} = 0, \forall s \ge 2$), with soft penalties guiding groups to compact early finishes.
10. **Belarus Public Holidays Absolute Ban**:
    For any calendar day $d$ recognized as an official non-working public holiday of the Republic of Belarus (Decree of the President No. 157 & Labour Code Art. 147: 1-2 Jan, 7 Jan, 8 Mar, Radunitsa, 1 May, 9 May, 3 Jul, 7 Nov, 25 Dec), student lessons are strictly prohibited across all groups and slots:
    $$x_{i, d, s} = 0, \quad \forall i, s$$
    $$\text{act}_{g, d, s} = 0, \quad \forall g, s$$
    The engine computes both fixed secular/religious holidays and the floating Easter-derived Radunitsa using the astronomical Meeus algorithm.

---

### 3.2 Soft Constraints & Objective Penalties

The objective function minimizes $\sum \text{penalties}$:

| Rule | Mathematical Mechanism | Weight / Penalty | Rationale |
| :--- | :--- | :---: | :--- |
| **Saturday Early Start & 5-Day Week** | $(\text{day\_has\_les}_{g, 5} - \text{act}_{g, 5, 0}) \times 1500 + \text{start}_{g, 5, 1} \times 800 + \text{day\_has\_les}_{g, 5} \times 350$ | 350 / 800 / 1500 | Guides Saturday to slot 0 and incentivizes 5-day week when load permits. |
| **Teacher Windows Penalty** | $\text{extra\_starts}_{t, d} \times 1200$ | 1200 | Strong penalty practically eliminating idle windows in faculty daily schedules. |
| **Late Slot Weight** | $\text{active}_{g, d, s} \times W_s$, where $W = [0, 2, 6, 18, 40]$ | 2 to 40 | Prioritizes compact days and early completion. |
| **Saturday Relief** | Additional penalty on slot 2 (+20), slot 1 (+5); slots 3 and 4 prohibited | 5 to 20 | Promotes early release on Saturdays with strict 3-pair cap. |
| **Information Hour Placement** | Slots 0, 1 penalized (+1000); non-Thu/Fri penalized (+200) | 200 / 1000 | Places formal curator hours at end of day, preferentially on Thu/Fri. |
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
│       ├── holidays.py        # Belarus public holidays calendar (fixed + Meeus astronomical Radunitsa)
│       ├── parser.py          # Live scraper for official MGKCT portal weekly timetables
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
