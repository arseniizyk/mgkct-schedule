#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Top-level convenience runner for the MGKCT Timetable Optimization Engine."""

import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mgkct_optimizer.cli import main

if __name__ == "__main__":
    main()
