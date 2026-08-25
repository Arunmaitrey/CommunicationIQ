"""Layer 4 — the intelligence nobody sees.

Item calibration, mastery tracking and adaptive selection. Layers 1 to 3 turn
audio into numbers; this turns numbers into a decision about what to put in
front of the student next, and how sure to be about them.

Everything here is classical psychometrics rather than deep learning, and
everything here is gated on having enough data to justify it. An uncalibrated
item bank is not a reason to fake calibration — it is a reason to keep saying
"random selection" until the responses exist.
"""
from app.engine.psychometrics import bkt, irt

__all__ = ["bkt", "irt"]
