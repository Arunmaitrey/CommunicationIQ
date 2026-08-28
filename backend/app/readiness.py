"""Readiness banding.

One definition, used by the admin view, the cohort dashboard and every
export, so a student is never "placement ready" on one screen and "needs
training" on another.

The bands are on the presentation scale (20–80, Versant-style). They are a
*platform* judgement about practice progress — never a claim about a vendor
score, and never presented as a guarantee (MOT-04, DIAG-10).
"""
from __future__ import annotations

READY = "placement_ready"
NEEDS_TRAINING = "needs_training"
HIGH_RISK = "high_risk"
NOT_STARTED = "not_started"

READY_AT = 60.0
RISK_BELOW = 45.0


def band(overall: float | None) -> str:
    if overall is None:
        return NOT_STARTED
    if overall >= READY_AT:
        return READY
    if overall < RISK_BELOW:
        return HIGH_RISK
    return NEEDS_TRAINING


def label(band_key: str) -> str:
    return {
        READY: "Placement ready",
        NEEDS_TRAINING: "Needs training",
        HIGH_RISK: "High risk",
        NOT_STARTED: "Not started",
    }.get(band_key, band_key)
