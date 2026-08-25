"""The validation study.

Everything else in this codebase can be checked by reading it. This is the
part that can only be checked against people: whether the numbers the engine
produces line up with what a human listener hears.

Until this has been run, every score in the product is labelled uncalibrated,
and that labelling is enforced in `app/engine/calibration.py` rather than left
to whoever writes the sales deck.
"""
from app.validation import statistics, study

__all__ = ["statistics", "study"]
