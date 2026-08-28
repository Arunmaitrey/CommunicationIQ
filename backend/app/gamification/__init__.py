"""Gamification service — XP ledger, quests, streaks, seasons, badges.

Empty at M0 by design. The tables exist (``app/models/tenant.py``) and the
economy is already configurable from the platform console, but the engine that
awards anything arrives in M4, once there are real scores to reward.

Two properties are structural rather than policy, and are worth stating here
because they constrain what may ever be added to this package:

* The ledger is append-only and server-authoritative. No endpoint accepts an
  XP amount from a client (NFR-15).

"""
