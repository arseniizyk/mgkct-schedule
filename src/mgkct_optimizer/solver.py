#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google OR-Tools CP-SAT discrete optimization core for MGKCT.
Constructs integer constraints, objective penalties, seeds solver hints,
and computes optimal conflict-free weekly academic timetables.
Supports Belarus public holidays and whole-group physical education integrity.
"""

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from ortools.sat.python import cp_model

from .allocator import assign_physical_rooms
from .holidays import get_week_holidays
from .metrics import compute_schedule_metrics
from .models import (
    MAX_SLOTS,
    NUM_DAYS,
    CurriculumItem,
    GroupInfo,
    RoomInfo,
    ScheduledLesson,
    get_required_room_type,
    get_group_campus_for_day,
)


class MGKCTScheduleOptimizer:
    """Discrete optimization engine for Minsk State College of Digital Technologies."""

    def __init__(
        self,
        groups: List[GroupInfo],
        rooms: List[RoomInfo],
        items: List[CurriculumItem],
        holidays: Optional[List[int]] = None,
        week_start_date: Optional[Union[str, Any]] = None,
        metadata: Optional[Dict] = None,
    ):
        self.groups: Dict[str, GroupInfo] = {g.name: g for g in groups}
        self.rooms: List[RoomInfo] = rooms
        self.items: List[CurriculumItem] = items
        self.holidays: Optional[List[int]] = holidays
        self.week_start_date: Optional[Union[str, Any]] = week_start_date
        self.metadata: Dict = metadata or {}

    def solve(
        self,
        time_limit_sec: float = 20.0,
        baseline_schedule: Optional[List[ScheduledLesson]] = None,
        sick_teachers: Optional[Dict[str, List[int]]] = None,
        frozen_days: Optional[List[int]] = None,
        holidays: Optional[List[int]] = None,
        week_start_date: Optional[Union[str, Any]] = None,
    ) -> Tuple[List[ScheduledLesson], Dict]:
        """
        Builds CP-SAT model, solves, and assigns physical classrooms.
        Supports dynamic disruption re-optimization with Minimal Perturbation principle,
        Belarus public holidays, and whole-group physical education rules.
        """
        t0 = time.time()
        model = cp_model.CpModel()

        sick_teachers = sick_teachers or {}
        frozen_days_set = set(frozen_days or [])
        is_reschedule = baseline_schedule is not None

        # Определение праздничных нерабочих дней (гос. праздники Республики Беларусь)
        effective_holidays = holidays if holidays is not None else self.holidays
        effective_date = (
            week_start_date
            or self.week_start_date
            or self.metadata.get("week_start_date")
            or self.metadata.get("extracted_at")
        )
        if effective_holidays is None and effective_date:
            h_map = get_week_holidays(effective_date)
            effective_holidays = list(h_map.keys())
        elif effective_holidays is None and self.metadata.get("belarus_holidays"):
            effective_holidays = [int(k) for k in self.metadata["belarus_holidays"].keys()]

        holidays_set: Set[int] = set(effective_holidays or [])

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
                    if d in holidays_set:
                        # Правило: по государственным праздникам студентам запрещено ставить пары
                        model.Add(x[(it.item_id, d, s)] == 0)
                        continue
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
        pe_group_sick_days: Dict[str, Set[int]] = defaultdict(set)
        for it in self.items:
            if "ФЗКиЗ" in it.subject or it.lesson_type == "ФЗКиЗ":
                for d in sick_teachers.get(it.teacher, []):
                    pe_group_sick_days[it.group].add(d)

        for it in self.items:
            is_pe = "ФЗКиЗ" in it.subject or it.lesson_type == "ФЗКиЗ"
            sick_days_for_it = pe_group_sick_days.get(it.group, set()) if is_pe else set(sick_teachers.get(it.teacher, []))

            if not is_reschedule or not sick_days_for_it:
                model.Add(
                    sum(x[(it.item_id, d, s)] for d in range(NUM_DAYS) for s in range(MAX_SLOTS))
                    == it.weekly_pairs
                )
            else:
                canceled_pairs = sum(baseline_day_counts.get((it.item_id, d), 0) for d in sick_days_for_it)
                target_pairs = max(0, it.weekly_pairs - canceled_pairs)
                model.Add(
                    sum(x[(it.item_id, d, s)] for d in range(NUM_DAYS) for s in range(MAX_SLOTS))
                    == target_pairs
                )
                for d in sick_days_for_it:
                    for s in range(MAX_SLOTS):
                        model.Add(x[(it.item_id, d, s)] == 0)

        # 3. Замороженные дни (при перестроении)
        if is_reschedule:
            for it in self.items:
                is_pe = "ФЗКиЗ" in it.subject or it.lesson_type == "ФЗКиЗ"
                sick_days_for_it = pe_group_sick_days.get(it.group, set()) if is_pe else set(sick_teachers.get(it.teacher, []))
                for d in frozen_days_set:
                    if d not in sick_days_for_it:
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
                if d in holidays_set:
                    for s in range(MAX_SLOTS):
                        act = model.NewBoolVar(f"act_{g_name}_{d}_{s}")
                        group_active[(g_name, d, s)] = act
                        model.Add(act == 0)
                        st = model.NewBoolVar(f"start_{g_name}_{d}_{s}")
                        group_start[(g_name, d, s)] = st
                        model.Add(st == 0)
                    continue

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

                # Лимит пар в день (не более 4 пар; 5 пар допускается ТОЛЬКО если в этот день стоит Инф час)
                # Группы могут учиться по 5-ю пару (слоты 1..4), но с 1 по 5 пару в один день запрещено!
                inf_items_g = [
                    it for it in g_it_list
                    if "инф час" in it.subject.lower() or "информацион" in it.subject.lower()
                ]
                if inf_items_g:
                    has_inf_day = model.NewBoolVar(f"has_inf_{g_name}_{d}")
                    model.Add(sum(x[(it.item_id, d, s)] for it in inf_items_g for s in range(MAX_SLOTS)) == has_inf_day)
                    day_cap = 3 if d == 5 else (4 + has_inf_day)

                    # ЖЕСТКОЕ ОГРАНИЧЕНИЕ: Информационный час строго завершает учебный день группы
                    # Запрещено ставить любые пары после информационного часа (нельзя делать окна / разрыв инф. часом)
                    for it in inf_items_g:
                        for s in range(MAX_SLOTS):
                            for s_after in range(s + 1, MAX_SLOTS):
                                model.Add(group_active[(g_name, d, s_after)] == 0).OnlyEnforceIf(x[(it.item_id, d, s)])
                else:
                    day_cap = 3 if d == 5 else 4
                model.Add(sum(group_active[(g_name, d, s)] for s in range(MAX_SLOTS)) <= day_cap)
                if d == 5 and MAX_SLOTS >= 5:
                    # В субботу 4-я и 5-я пары (слоты 3 и 4) запрещены для всех групп (короткий день)
                    model.Add(group_active[(g_name, 5, 3)] == 0)
                    model.Add(group_active[(g_name, 5, 4)] == 0)

                # ЖЕСТКОЕ ОГРАНИЧЕНИЕ: Максимум 4 пары в день для любой подгруппы (Инф час не считается)
                # Ни одна подгруппа не может иметь больше 4 пар в день (например, с 1 по 5 запрещено)
                subs_to_check = active_subs if active_subs else [0]
                for sub_k in subs_to_check:
                    sub_k_academic = [
                        it for it in g_it_list
                        if it.subgroup in (0, sub_k)
                        and "инф час" not in it.subject.lower()
                        and "информацион" not in it.subject.lower()
                    ]
                    academic_cap = 3 if d == 5 else 4
                    model.Add(sum(x[(it.item_id, d, s)] for it in sub_k_academic for s in range(MAX_SLOTS)) <= academic_cap)

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

            # ЖЕСТКОЕ ОГРАНИЧЕНИЕ: Физкультура (ФЗКиЗ) на всю группу
            # 1. Синхронизация всех подгрупп ФЗКиЗ: все подгруппы занимаются строго одновременно
            # 2. Неделимость группы: запрещено ставить физру одной/двум подгруппам, а третьей другой предмет
            # 3. Не более 1 слота ФЗКиЗ в день для любой группы
            pe_items = [it for it in g_it_list if "ФЗКиЗ" in it.subject or it.lesson_type == "ФЗКиЗ"]
            non_pe_items = [it for it in g_it_list if it not in pe_items]
            if pe_items:
                it0 = pe_items[0]
                if len(pe_items) >= 2:
                    for it_other in pe_items[1:]:
                        for d in range(NUM_DAYS):
                            if d in holidays_set:
                                continue
                            for s in range(MAX_SLOTS):
                                model.Add(x[(it0.item_id, d, s)] == x[(it_other.item_id, d, s)])

                for it_non in non_pe_items:
                    for d in range(NUM_DAYS):
                        if d in holidays_set:
                            continue
                        for s in range(MAX_SLOTS):
                            model.Add(x[(it0.item_id, d, s)] + x[(it_non.item_id, d, s)] <= 1)

                for d in range(NUM_DAYS):
                    if d in holidays_set:
                        continue
                    model.Add(sum(x[(it0.item_id, d, s)] for s in range(MAX_SLOTS)) <= 1)

        # 5. Непересечение преподавателей + Запрет смены корпуса в один день
        teacher_items: Dict[str, List[CurriculumItem]] = defaultdict(list)
        for it in self.items:
            teacher_items[it.teacher].append(it)

        penalties = []

        for t_name, t_it_list in teacher_items.items():
            academic_items = [
                it for it in t_it_list
                if "инф час" not in it.subject.lower() and "информацион" not in it.subject.lower()
            ]
            for d in range(NUM_DAYS):
                if d in holidays_set:
                    continue

                for s in range(MAX_SLOTS):
                    model.Add(sum(x[(it.item_id, d, s)] for it in t_it_list) <= 1)

                # Запрет смены корпуса преподавателем в один день (с учетом выездных дней групп)
                # Внешняя практика на предприятиях без аудиторий (home_rooms: []) не привязана к корпусу
                kaz_items_d = [
                    it for it in academic_items
                    if not (it.lesson_type == "Пр-ка" and not it.home_rooms)
                    and get_group_campus_for_day(it.group, d, self.groups[it.group].campus) == "Казинца"
                ]
                kno_items_d = [
                    it for it in academic_items
                    if not (it.lesson_type == "Пр-ка" and not it.home_rooms)
                    and get_group_campus_for_day(it.group, d, self.groups[it.group].campus) == "Кнорина"
                ]
                if kaz_items_d and kno_items_d:
                    use_kaz = model.NewBoolVar(f"tkaz_{t_name}_{d}")
                    use_kno = model.NewBoolVar(f"tkno_{t_name}_{d}")
                    for it in kaz_items_d:
                        for s in range(MAX_SLOTS):
                            model.Add(x[(it.item_id, d, s)] <= use_kaz)
                    for it in kno_items_d:
                        for s in range(MAX_SLOTS):
                            model.Add(x[(it.item_id, d, s)] <= use_kno)
                    model.Add(use_kaz + use_kno <= 1)

                # Активность преподавателя в слотах
                t_active = []
                for s in range(MAX_SLOTS):
                    t_act = model.NewBoolVar(f"tact_{t_name}_{d}_{s}")
                    model.Add(t_act == sum(x[(it.item_id, d, s)] for it in t_it_list))
                    t_active.append(t_act)

                # Дневной лимит преподавателя: не более 5 пар в день
                model.Add(sum(t_active) <= 5)

                # Устранение "окон" у преподавателей: сверхвысокий штраф за разрывы в расписании
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
                penalties.append(extra_starts * 1200)

        # 6. Вместимость аудиторного фонда по пулам (корпус + тип) с учетом выездных дней
        rooms_count: Dict[Tuple[str, str], int] = defaultdict(int)
        for r in self.rooms:
            rooms_count[(r.campus, r.room_type)] += 1

        for d in range(NUM_DAYS):
            if d in holidays_set:
                continue
            pool_items_d: Dict[Tuple[str, str], List[CurriculumItem]] = defaultdict(list)
            for it in self.items:
                c_name = get_group_campus_for_day(it.group, d, self.groups[it.group].campus)
                r_type = get_required_room_type(it.lesson_type, it.subject)
                if r_type == "спец_лаб" and rooms_count.get((c_name, "спец_лаб"), 0) == 0:
                    r_type = "комп" if it.lesson_type in ("ЛР", "Пр-ка", "КП") else "лек"
                pool_items_d[(c_name, r_type)].append(it)

            for (c_name, r_type), p_it_list in pool_items_d.items():
                if r_type == "спорт":
                    # Спорткомплекс вмещает параллельные группы/подгруппы
                    cap = max(rooms_count[(c_name, r_type)], 6 if c_name == "Казинца" else 4)
                else:
                    cap = rooms_count[(c_name, r_type)]

                for s in range(MAX_SLOTS):
                    model.Add(sum(x[(it.item_id, d, s)] for it in p_it_list) <= cap)

        # 7. МЯГКИЕ ОГРАНИЧЕНИЯ (Штрафы в целевой функции)
        slot_weights = [0, 2, 6, 18, 40]

        # 7a. Детерминированное начало с 1-й пары (слот 0, 09:00) для всех групп и штраф за поздние слоты
        for g_name, g_info in self.groups.items():
            for d in range(NUM_DAYS):
                if d in holidays_set:
                    continue

                day_has_les = model.NewBoolVar(f"has_les_{g_name}_{d}")
                for s in range(MAX_SLOTS):
                    model.Add(day_has_les >= group_active[(g_name, d, s)])
                model.Add(day_has_les <= sum(group_active[(g_name, d, s)] for s in range(MAX_SLOTS)))

                if d < 5:
                    if g_info.course == 1:
                        # В будние дни 1 курс строго начинает с 1-й пары (слот 0, 09:00)
                        model.Add(group_active[(g_name, d, 0)] == day_has_les)
                        for s in range(1, MAX_SLOTS):
                            model.Add(group_start[(g_name, d, s)] == 0)
                    else:
                        # 2-4 курсы: могут учиться по 5-ю пару (слот 4), но не более 4 пар в день
                        # При наличии 5-й пары группа начинает со 2-й пары (слот 1, 10:50, без окон)
                        for s in range(2, MAX_SLOTS):
                            model.Add(group_start[(g_name, d, s)] == 0)
                        penalties.append(group_start[(g_name, d, 1)] * 500)
                else:
                    # В субботу: запрет старта позже слота 1, мягкий приоритет слота 0
                    for s in range(2, MAX_SLOTS):
                        model.Add(group_start[(g_name, 5, s)] == 0)
                    penalties.append((day_has_les - group_active[(g_name, 5, 0)]) * 1500)
                    penalties.append(group_start[(g_name, 5, 1)] * 800)
                    # Мягкий приоритет 5-дневки (выходной в субботу, если нагрузка укладывается в будни)
                    penalties.append(day_has_les * 350)

                # Штраф за поздние слоты (компактность учебного дня)
                for s in range(MAX_SLOTS):
                    w = slot_weights[s] if s < len(slot_weights) else 40
                    if d == 5:
                        if s == 3:
                            w += 40
                        elif s == 2:
                            w += 20
                        elif s == 1:
                            w += 5
                    if w > 0:
                        penalties.append(group_active[(g_name, d, s)] * w)

        # 7b. Не более 1 пары одного и того же предмета в один день (мягкий штраф)
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
                        if d in holidays_set:
                            continue
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
                    if 0 not in holidays_set:
                        penalties.append(sum(x[(lr_it.item_id, 0, s)] for s in range(MAX_SLOTS)) * 10)

        # 7d. Приоритетное размещение информационного / кураторского часа
        # "Инф час" ставится на последние слоты дня (слот 3 или 4), преимущественно в чт (3) или пт (4)
        for it in self.items:
            if "инф час" in it.subject.lower():
                for d in range(NUM_DAYS):
                    if d in holidays_set:
                        continue
                    # Запрет / штраф за утренние слоты 0, 1 для Инф часа
                    for s in range(min(2, MAX_SLOTS)):
                        penalties.append(x[(it.item_id, d, s)] * 1000)
                    # Приоритет четверга (3) и пятницы (4)
                    if d not in (3, 4):
                        penalties.append(sum(x[(it.item_id, d, s)] for s in range(MAX_SLOTS)) * 200)

        # 7e. В режиме перестроения: минимальное возмущение (Minimal Perturbation)
        if is_reschedule:
            for (item_id, d, orig_s) in baseline_slot_set:
                it_obj = self.items[item_id]
                is_pe = "ФЗКиЗ" in it_obj.subject or it_obj.lesson_type == "ФЗКиЗ"
                sick_days_for_it = pe_group_sick_days.get(it_obj.group, set()) if is_pe else set(sick_teachers.get(it_obj.teacher, []))
                if d not in sick_days_for_it and d not in holidays_set:
                    same_day_sum = sum(x[(item_id, d, s)] for s in range(MAX_SLOTS))
                    diff_day = model.NewBoolVar(f"dd_{item_id}_{d}_{orig_s}")
                    model.Add(1 - same_day_sum <= diff_day)
                    penalties.append(diff_day * 300)
                    penalties.append((1 - x[(item_id, d, orig_s)]) * 80)

        # 7e. Синхронизация спаренных подгрупп (2 или 3 подгруппы)
        for pid, p_items in paired_groups.items():
            if len(p_items) >= 2:
                # ФЗКиЗ уже строго синхронизирована жестким ограничением
                if "ФЗКиЗ" in pid:
                    continue
                it0 = p_items[0]
                for it_other in p_items[1:]:
                    if it0.teacher != it_other.teacher and it0.weekly_pairs == it_other.weekly_pairs:
                        sync_weight = 60
                        for d in range(NUM_DAYS):
                            if d in holidays_set:
                                continue
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
        )

        metrics = compute_schedule_metrics(
            schedule=scheduled,
            groups=self.groups,
            baseline_schedule=baseline_schedule,
            items=self.items,
            holidays=list(holidays_set),
        )
        metrics["solve_time_sec"] = round(elapsed, 2)
        metrics["status"] = status_name
        metrics["objective_value"] = solver.ObjectiveValue()

        return scheduled, metrics
