"""
MGKCT Timetable Optimization Engine.
Discrete optimization and dynamic disruption rescheduling for academic timetables
using Google OR-Tools CP-SAT solver.
"""

from .models import (
    GroupInfo,
    RoomInfo,
    CurriculumItem,
    ScheduledLesson,
    DAYS,
    DAYS_SHORT,
    NUM_DAYS,
    MAX_SLOTS,
    CAMPUSES,
    ROOM_TYPES,
    BELL_SCHEDULE,
    get_required_room_type,
)
from .loader import load_curriculum_data, load_curriculum_with_metadata, get_default_curriculum_path
from .solver import MGKCTScheduleOptimizer
from .allocator import assign_physical_rooms
from .metrics import compute_schedule_metrics
from .holidays import get_belarus_holidays, is_belarus_holiday, get_week_holidays
from .parser import scrape_and_update_curriculum, parse_schedule_html

__version__ = "1.1.0"

__all__ = [
    "MGKCTScheduleOptimizer",
    "GroupInfo",
    "RoomInfo",
    "CurriculumItem",
    "ScheduledLesson",
    "DAYS",
    "DAYS_SHORT",
    "NUM_DAYS",
    "MAX_SLOTS",
    "CAMPUSES",
    "ROOM_TYPES",
    "BELL_SCHEDULE",
    "get_required_room_type",
    "load_curriculum_data",
    "load_curriculum_with_metadata",
    "get_default_curriculum_path",
    "assign_physical_rooms",
    "compute_schedule_metrics",
    "get_belarus_holidays",
    "is_belarus_holiday",
    "get_week_holidays",
    "scrape_and_update_curriculum",
    "parse_schedule_html",
]
