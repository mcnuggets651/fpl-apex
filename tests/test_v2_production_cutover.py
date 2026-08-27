"""Regression harness for the pre-root cutover transaction engine.

These tests intentionally exercise the private transaction implementation. Production callers
must use ``apex_fpl.control.production_cutover.execute_production_cutover``, whose rooted
authority contract is tested separately.
"""

from __future__ import annotations

import importlib

import apex_fpl.control.production_cutover as public_cutover
from apex_fpl.control import _production_cutover_legacy as legacy_cutover


_original_execute = public_cutover.execute_production_cutover
public_cutover.execute_production_cutover = legacy_cutover.execute_production_cutover
try:
    _legacy = importlib.import_module("_legacy_v2_production_cutover")
finally:
    public_cutover.execute_production_cutover = _original_execute

for _name, _value in vars(_legacy).items():
    if _name.startswith("test_"):
        globals()[_name] = _value
