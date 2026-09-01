"""The AI intelligence layer.

Two separate, single-purpose Claude calls -- deliberately NOT combined into one
prompt:

  * safety.py -- clinical review of a new prescription against the patient's
    existing medications and documented allergies.
  * fraud.py  -- cheap rule-based heuristics in plain Python first; Claude is
    only asked to *explain* a rule that already tripped.

Keeping them apart means each prompt has one job, one schema and one failure
mode, and the fraud path costs nothing when no rule fires.
"""
