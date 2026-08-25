"""Tier 1 — local open models.

Runs on CPU with no API key and no data leaving the machine, which is what
makes it compatible with the India-residency requirement without a hosting
decision attached.

One model is shared across every provider here (``model.py``): loading
faster-whisper twice would double the memory for no benefit, and the first
load is the only slow part.
"""
