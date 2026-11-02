#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google OR-Tools CP-SAT discrete optimization core for MGKCT.
Constructs integer constraints, objective penalties, seeds solver hints,
and computes optimal conflict-free weekly academic timetables.
"""

import time
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Set
from ortools.sat.python import cp_model

from .models import (
    GroupInfo,
    RoomInfo,
    CurriculumItem,
    ScheduledLesson,
    NUM_DAYS,
    MAX_SLOTS,
    get_required_room_type,
)
from .allocator import assign_physical_rooms
from .metrics import compute_schedule_metrics


class MGKCTScheduleOptimizer:
    """Discrete optimization engine for Minsk State College of Digital Technologies."""

    def __init__(
        self,
        groups: List[GroupInfo],
        rooms: List[RoomInfo],
        items: List[CurriculumItem],
    ):
        self.groups: Dict[str, GroupInfo] = {g.name: g for g in groups}
        self.rooms: List[RoomInfo] = rooms
        self.items: List[CurriculumItem] = items

    def solve(
        self,
        time_limit_sec: float = 20.0,
        baseline_schedule: Optional[List[ScheduledLesson]] = None,
        sick_teachers: Optional[Dict[str, List[int]]] = None,
        frozen_days: Optional[List[int]] = None,
    ) -> Tuple[List[ScheduledLesson], Dict]:
        """
        Builds CP-SAT model, solves, and assigns physical classrooms.
        Supports dynamic disruption re-optimization with Minimal Perturbation principle.
        """
        t0 = time.time()
        model = cp_model.CpModel()

        sick_teachers = sick_teachers or {}
        frozen_days_set = set(frozen_days or [])
        is_reschedule = baseline_schedule is not None

        baseline_slot_set: Set[Tuple[int, int, int]] = set()
        baseline_day_counts: Dict[Tuple[int, int], int] = defaultdict(int)
        if baseline_schedule:
            for les in baseline_schedule:
                baseline_slot_set.add((les.item_id, les.day, les.slot))
                baseline_day_counts[(les.item_id, les.day)] += 1

        x: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
        for it in self.items:
            for d in range(NUM_DAYS):
                for s in range(MAX_SLOTS):
                    x[(it.item_id, d, s)] = model.NewBoolVar(f"x_{it.item_id}_{d}_{s}")
                    if is_reschedule and (it.item_id, d, s) in baseline_slot_set:
                        if d not in sick_teachers.get(it.teacher, []):
                            model.AddHint(x[(it.item_id, d, s)], 1)
                        else:
                            model.AddHint(x[(it.item_id, d, s)], 0)
                    elif is_reschedule:
                        model.AddHint(x[(it.item_id, d, s)], 0)

        # 1. Сбор спаренных подгрупп
        paired_groups: Dict[str, List[CurriculumItem]] = defaultdict(list)
        for it in self.items:
            if it.paired_id:
                paired_groups[it.paired_id].append(it)

        # 2. Выполнение недельной нагрузки по каждому предмету
        for it in self.items:
            sick_days_for_t = set(sick_teachers.get(it.teacher, []))
            if not is_reschedule or not sick_days_for_t:
                model.Add(
                    sum(x[(it.item_id, d, s)] for d in range(NUM_DAYS) for s in range(MAX_SLOTS))
                    == it.weekly_pairs
                )
            else:
                canceled_pairs = sum(baseline_day_counts.get((it.item_id, d), 0) for d in sick_days_for_t)
                target_pairs = max(0, it.weekly_pairs - canceled_pairs)
                model.Add(
                    sum(x[(it.item_id, d, s)] for d in range(NUM_DAYS) for s in range(MAX_SLOTS))
                    == target_pairs
                )
                for d in sick_days_for_t:
                    for s in range(MAX_SLOTS):
                        model.Add(x[(it.item_id, d, s)] == 0)

        # 3. Замороженные дни (при перестроении)
        if is_reschedule:
            for it in self.items:
                for d in frozen_days_set:
                    if d not in sick_teachers.get(it.teacher, []):
                        for s in range(MAX_SLOTS):
                            was_here = 1 if (it.item_id, d, s) in baseline_slot_set else 0
                            model.Add(x[(it.item_id, d, s)] == was_here)

        # 4. Активность группы в слоте, непересечение предметов и отсутствие "окон"
        group_items: Dict[str, List[CurriculumItem]] = defaultdict(list)
        for it in self.items:
            group_items[it.group].append(it)

        group_active: Dict[Tuple[str, int, int], cp_model.IntVar] = {}
        group_start: Dict[Tuple[str, int, int], cp_model.IntVar] = {}

        for g_name, g_info in self.groups.items():
            g_it_list = group_items[g_name]
            whole_items = [it for it in g_it_list if it.subgroup == 0]
            sub_items_map = defaultdict(list)
            for it in g_it_list:
                if it.subgroup > 0:
                    sub_items_map[it.subgroup].append(it)

            active_subs = list(sub_items_map.keys()) if sub_items_map else [0]

            for d in range(NUM_DAYS):
                for s in range(MAX_SLOTS):
                    act = model.NewBoolVar(f"act_{g_name}_{d}_{s}")
                    group_active[(g_name, d, s)] = act

                    if sub_items_map:
                        for sub_num, s_list in sub_items_map.items():
                            sub_sum = sum(x[(it.item_id, d, s)] for it in whole_items + s_list)
                            model.Add(sub_sum <= act)
                            model.Add(sub_sum <= 1)
                    else:
                        whole_sum = sum(x[(it.item_id, d, s)] for it in whole_items)
                        model.Add(whole_sum <= act)
                        model.Add(whole_sum <= 1)

                    # Связь act с уроками группы в слоте: act == 1 тогда и только тогда, когда идет урок
                    for it in g_it_list:
                        model.Add(act >= x[(it.item_id, d, s)])
                    model.Add(act <= sum(x[(it.item_id, d, s)] for it in g_it_list))

                # Лимит пар в день (4 для 1 курса, 5 для 2-4 курсов; в субботу не более 4 пар)
                day_cap = min(g_info.max_daily_pairs, 4) if d == 5 else g_info.max_daily_pairs
                model.Add(sum(group_active[(g_name, d, s)] for s in range(MAX_SLOTS)) <= day_cap)
                if d == 5 and MAX_SLOTS >= 5:
                    # В субботу 5-я пара (слот 4) запрещена для всех групп
                    model.Add(group_active[(g_name, 5, 4)] == 0)

                total_group_hours = sum(it.weekly_pairs for it in g_it_list if it.subgroup in (0, 1))
                if not is_reschedule and d < 5 and total_group_hours >= 12:
                    model.Add(sum(group_active[(g_name, d, s)] for s in range(MAX_SLOTS)) >= 2)

                # ЖЕСТКОЕ ОГРАНИЧЕНИЕ 1: Отсутствие "окон" у всей группы в течение дня
                for s in range(MAX_SLOTS):
                    st = model.NewBoolVar(f"start_{g_name}_{d}_{s}")
                    group_start[(g_name, d, s)] = st
                    if s == 0:
                        model.Add(st == group_active[(g_name, d, 0)])
                    else:
                        model.Add(st >= group_active[(g_name, d, s)] - group_active[(g_name, d, s - 1)])
                        model.Add(st <= group_active[(g_name, d, s)])
                        model.Add(st <= 1 - group_active[(g_name, d, s - 1)])
                model.Add(sum(group_start[(g_name, d, s)] for s in range(MAX_SLOTS)) <= 1)

                # ЖЕСТКОЕ ОГРАНИЧЕНИЕ 2: Отсутствие "окон" ДЛЯ КАЖДОЙ ПОДГРУППЫ (1, 2, 3)
                # Запрещены ситуации, когда подгруппа имеет окно, пока учится другая подгруппа
                for sub_k in active_subs:
                    sub_k_items = whole_items + sub_items_map.get(sub_k, [])
                    sub_starts = []
                    prev_sub_act = None
                    for s in range(MAX_SLOTS):
                        sub_act = sum(x[(it.item_id, d, s)] for it in sub_k_items)
                        st_sub = model.NewBoolVar(f"st_{g_name}_{sub_k}_{d}_{s}")
                        sub_starts.append(st_sub)
                        if s == 0:
                            model.Add(st_sub == sub_act)
                        else:
                            model.Add(st_sub >= sub_act - prev_sub_act)
                            model.Add(st_sub <= sub_act)
                            model.Add(st_sub <= 1 - prev_sub_act)
                        prev_sub_act = sub_act
                    model.Add(sum(sub_starts) <= 1)

                # ЖЕСТКОЕ ОГРАНИЧЕНИЕ 3: Не более 1 слота ФЗКиЗ в день для любой группы
                pe_items = [it for it in g_it_list if "ФЗКиЗ" in it.subject or it.lesson_type == "ФЗКиЗ"]
                if pe_items:
                    pe_day_slots = []
                    for s in range(MAX_SLOTS):
                        pe_s = model.NewBoolVar(f"pe_{g_name}_{d}_{s}")
                        pe_day_slots.append(pe_s)
                        for it in pe_items:
                            model.Add(pe_s >= x[(it.item_id, d, s)])
                    model.Add(sum(pe_day_slots) <= 1)

        # 5. Непересечение преподавателей + Запрет смены корпуса в один день
        teacher_items: Dict[str, List[CurriculumItem]] = defaultdict(list)
        for it in self.items:
            teacher_items[it.teacher].append(it)

        penalties = []

        for t_name, t_it_list in teacher_items.items():
            campuses_taught = {self.groups[it.group].campus for it in t_it_list}
            for d in range(NUM_DAYS):
                for s in range(MAX_SLOTS):
                    model.Add(sum(x[(it.item_id, d, s)] for it in t_it_list) <= 1)

                if len(campuses_taught) > 1:
                    kaz_items = [it for it in t_it_list if self.groups[it.group].campus == "Казинца"]
                    kno_items = [it for it in t_it_list if self.groups[it.group].campus == "Кнорина"]
                    use_kaz = model.NewBoolVar(f"tkaz_{t_name}_{d}")
                    use_kno = model.NewBoolVar(f"tkno_{t_name}_{d}")
                    for it in kaz_items:
                        for s in range(MAX_SLOTS):
                            model.Add(x[(it.item_id, d, s)] <= use_kaz)
                    for it in kno_items:
                        for s in range(MAX_SLOTS):
                            model.Add(x[(it.item_id, d, s)] <= use_kno)
                    model.Add(use_kaz + use_kno <= 1)

                # Мягкий штраф за "окна" у преподавателей (линейная булева формулировка)
                t_active = []
                for s in range(MAX_SLOTS):
                    t_act = model.NewBoolVar(f"tact_{t_name}_{d}_{s}")
                    model.Add(t_act == sum(x[(it.item_id, d, s)] for it in t_it_list))
                    t_active.append(t_act)

                t_starts = []
                for s in range(MAX_SLOTS):
                    st = model.NewBoolVar(f"tstart_{t_name}_{d}_{s}")
                    t_starts.append(st)
                    if s == 0:
                        model.Add(st == t_active[0])
                    else:
                        model.Add(st >= t_active[s] - t_active[s - 1])
                        model.Add(st <= t_active[s])
                        model.Add(st <= 1 - t_active[s - 1])

                extra_starts = model.NewIntVar(0, MAX_SLOTS, f"textra_{t_name}_{d}")
                model.Add(extra_starts >= sum(t_starts) - 1)
                model.Add(extra_starts >= 0)
                penalties.append(extra_starts * 80)

        # 6. Вместимость аудиторного фонда по пулам (корпус + тип)
        rooms_count: Dict[Tuple[str, str], int] = defaultdict(int)
        for r in self.rooms:
            rooms_count[(r.campus, r.room_type)] += 1

        pool_items: Dict[Tuple[str, str], List[CurriculumItem]] = defaultdict(list)
        for it in self.items:
            c_name = self.groups[it.group].campus
            r_type = get_required_room_type(it.lesson_type, it.subject)
            if r_type == "спец_лаб" and rooms_count.get((c_name, "спец_лаб"), 0) == 0:
                r_type = "комп" if it.lesson_type in ("ЛР", "Пр-ка", "КП") else "лек"
            pool_items[(c_name, r_type)].append(it)

        for (c_name, r_type), p_it_list in pool_items.items():
            if r_type == "спорт":
                # Спорткомплекс вмещает параллельные группы/подгруппы
                cap = max(rooms_count[(c_name, r_type)], 6 if c_name == "Казинца" else 4)
            else:
                # Строгая емкость физического фонда без искусственных завышений
                cap = rooms_count[(c_name, r_type)]

            for d in range(NUM_DAYS):
                for s in range(MAX_SLOTS):
                    model.Add(sum(x[(it.item_id, d, s)] for it in p_it_list) <= cap)

        # 7. МЯГКИЕ ОГРАНИЧЕНИЯ (Штрафы в целевой функции)
        slot_weights = [0, 2, 6, 18, 40]

        # 7a. Штраф за старт и поздние слоты с дифференциацией по сменам
        for g_name, g_info in self.groups.items():
            shift = getattr(g_info, "shift", 1)
            total_group_hours = sum(it.weekly_pairs for it in group_items[g_name] if it.subgroup in (0, 1))

            for d in range(NUM_DAYS):
                day_has_les = model.NewBoolVar(f"has_les_{g_name}_{d}")
                for s in range(MAX_SLOTS):
                    model.Add(day_has_les >= group_active[(g_name, d, s)])
                model.Add(day_has_les <= sum(group_active[(g_name, d, s)] for s in range(MAX_SLOTS)))

                if shift == 1:
                    if d < 5:
                        # 1-я смена в будние дни: строгое детерминированное начало с 1-й пары (слот 0)
                        # Гарантирует first_pair_start_pct >= 95.0% на каждом прогоне
                        model.Add(group_active[(g_name, d, 0)] == day_has_les)
                        for s in range(1, MAX_SLOTS):
                            model.Add(group_start[(g_name, d, s)] == 0)
                    else:
                        # В субботу: запрет старта позже слота 1, мягкий приоритет слота 0
                        for s in range(2, MAX_SLOTS):
                            model.Add(group_start[(g_name, 5, s)] == 0)
                        penalties.append((day_has_les - group_active[(g_name, 5, 0)]) * 1500)
                        penalties.append(group_start[(g_name, 5, 1)] * 800)
                else:
                    # 2-я смена: дифференцированные ограничения с учетом лимита емкости (17 пар)
                    if total_group_hours <= 17:
                        if d < 5:
                            # Будние дни для стандартных групп: жесткий запрет слотов 0 и 1 (старт строго со слота >= 2)
                            model.Add(group_active[(g_name, d, 0)] == 0)
                            model.Add(group_active[(g_name, d, 1)] == 0)
                        else:
                            # Суббота: штраф за утренние слоты
                            penalties.append(group_active[(g_name, 5, 0)] * 300)
                            penalties.append(group_active[(g_name, 5, 1)] * 100)
                    else:
                        if d < 5:
                            # Будние дни для тяжелых групп (> 17 пар): жесткий запрет слота 0 (1-я пара)
                            model.Add(group_active[(g_name, d, 0)] == 0)
                            # Штраф за старт со слота 1 (2-я пара)
                            penalties.append(group_start[(g_name, d, 1)] * 400)
                        else:
                            # Суббота: штраф за утренние слоты
                            penalties.append(group_active[(g_name, 5, 0)] * 300)
                            penalties.append(group_active[(g_name, 5, 1)] * 100)

                    # Штраф за начало позже слота 2
                    for s in range(3, MAX_SLOTS):
                        penalties.append(group_start[(g_name, d, s)] * (60 * (s - 2)))

                # Штраф за поздние слоты (компактность учебного дня)
                for s in range(MAX_SLOTS):
                    w = slot_weights[s] if s < len(slot_weights) else 40
                    if d == 5:  # Суббота: мягкий штраф за слот 3 (+40)
                        if s == 3:
                            w += 40
                        elif s == 2:
                            w += 20
                        elif s == 1:
                            w += 5
                    if w > 0:
                        penalties.append(group_active[(g_name, d, s)] * w)

            # Ограничение ранних стартов для групп 2-й смены с повышенной нагрузкой (> 17 пар)
            if shift == 2 and total_group_hours > 17:
                # Старт со 2-й пары (слот 1) разрешен не более чем в 2 днях в будни
                model.Add(sum(group_start[(g_name, d, 1)] for d in range(5)) <= 2)

        # 7b. Не более 1 пары одного и того же предмета в один день (мягкий штраф)
        # Лабораторные, практика и курсовое проектирование освобождены от штрафа спаренности
        for g_name, g_it_list in group_items.items():
            subj_map: Dict[str, List[CurriculumItem]] = defaultdict(list)
            for it in g_it_list:
                subj_map[f"{it.subject}_{it.subgroup}"].append(it)
            for s_key, s_items in subj_map.items():
                is_lab = any(
                    it.lesson_type in ("ЛР", "Пр-ка", "КП")
                    or getattr(it, "is_double_pair_ok", False)
                    for it in s_items
                )
                tot_subj_pairs = sum(it.weekly_pairs for it in s_items)
                if not is_lab and tot_subj_pairs <= 4:
                    for d in range(NUM_DAYS):
                        daily_subj_sum = sum(x[(it.item_id, d, s)] for it in s_items for s in range(MAX_SLOTS))
                        dup_var = model.NewBoolVar(f"dup_{g_name}_{s_key}_{d}")
                        model.Add(daily_subj_sum - 1 <= dup_var * 4)
                        penalties.append(dup_var * 60)

        # 7c. Приоритет лекций перед лабораторными на неделе
        for g_name, g_it_list in group_items.items():
            by_subj: Dict[str, Dict[str, CurriculumItem]] = defaultdict(dict)
            for it in g_it_list:
                by_subj[it.subject][it.lesson_type] = it
            for subj, lmap in by_subj.items():
                if "Лек" in lmap and "ЛР" in lmap:
                    lr_it = lmap["ЛР"]
                    penalties.append(sum(x[(lr_it.item_id, 0, s)] for s in range(MAX_SLOTS)) * 10)

        # 7d. В режиме перестроения: минимальное возмущение (Minimal Perturbation)
        if is_reschedule:
            for (item_id, d, orig_s) in baseline_slot_set:
                it_obj = self.items[item_id]
                if d not in sick_teachers.get(it_obj.teacher, []):
                    same_day_sum = sum(x[(item_id, d, s)] for s in range(MAX_SLOTS))
                    diff_day = model.NewBoolVar(f"dd_{item_id}_{d}_{orig_s}")
                    model.Add(1 - same_day_sum <= diff_day)
                    penalties.append(diff_day * 300)
                    penalties.append((1 - x[(item_id, d, orig_s)]) * 80)

        # 7e. Синхронизация спаренных подгрупп (2 или 3 подгруппы, включая ФЗКиЗ)
        for pid, p_items in paired_groups.items():
            if len(p_items) >= 2:
                it0 = p_items[0]
                for it_other in p_items[1:]:
                    if it0.teacher != it_other.teacher and it0.weekly_pairs == it_other.weekly_pairs:
                        sync_weight = 120 if "ФЗКиЗ" in pid else 60
                        for d in range(NUM_DAYS):
                            for s in range(MAX_SLOTS):
                                diff_pair = model.NewBoolVar(f"diff_{pid}_{it_other.item_id}_{d}_{s}")
                                model.Add(x[(it0.item_id, d, s)] - x[(it_other.item_id, d, s)] <= diff_pair)
                                model.Add(x[(it_other.item_id, d, s)] - x[(it0.item_id, d, s)] <= diff_pair)
                                penalties.append(diff_pair * sync_weight)

        model.Minimize(sum(penalties))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_sec
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)

        elapsed = time.time() - t0
        status_name = solver.StatusName(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"CP-SAT solver failed to find solution: {status_name}")

        # Extract values
        solver_vals = {
            (it.item_id, d, s): solver.Value(x[(it.item_id, d, s)])
            for it in self.items
            for d in range(NUM_DAYS)
            for s in range(MAX_SLOTS)
        }

        # Stage 2: Physical room allocation
        scheduled = assign_physical_rooms(
            solver_values=solver_vals,
            items=self.items,
            groups=self.groups,
            rooms=self.rooms,
            pool_items=pool_items,
        )

        metrics = compute_schedule_metrics(
            schedule=scheduled,
            groups=self.groups,
            baseline_schedule=baseline_schedule,
            items=self.items,
        )
        metrics["solve_time_sec"] = round(elapsed, 2)
        metrics["status"] = status_name
        metrics["objective_value"] = solver.ObjectiveValue()

        return scheduled, metrics
