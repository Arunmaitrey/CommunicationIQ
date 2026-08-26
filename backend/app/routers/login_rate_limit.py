"""In-memory rate limiter for login attempts.

Tracks failed login attempts per IP address. After MAX_ATTEMPTS failures
within the window, the IP is blocked for BLOCK_SECONDS.

This is NOT a replacement for proper rate limiting (e.g., nginx, Cloudflare).
It is a cheap in-process guard that slows down credential stuffing from a
single IP during development.
"""
from __future__ import annotations

import time
from collections import defaultdict

# Configuration
MAX_ATTEMPTS = 10       # max failed attempts per window
WINDOW_SECONDS = 300    # 5 minute sliding window
BLOCK_SECONDS = 600     # 10 minute block after exceeding limit

# State: ip -> list of failure timestamps
_failures: dict[str, list[float]] = defaultdict(list)
_blocked_until: dict[str, float] = {}


def is_blocked(ip: str) -> float | None:
    """Check if an IP is rate-limited. Returns seconds remaining, or None."""
    now = time.time()
    
    # Check if currently blocked
    until = _blocked_until.get(ip, 0)
    if until > now:
        return until - now
    
    # Clean old failures outside the window
    cutoff = now - WINDOW_SECONDS
    _failures[ip] = [t for t in _failures[ip] if t > cutoff]
    
    if len(_failures[ip]) >= MAX_ATTEMPTS:
        _blocked_until[ip] = now + BLOCK_SECONDS
        return BLOCK_SECONDS
    
    return None


def record_failure(ip: str) -> None:
    """Record a failed login attempt from this IP."""
    _failures[ip].append(time.time())


def reset(ip: str) -> None:
    """Clear failures for an IP (e.g., after successful login)."""
    _failures.pop(ip, None)
    _blocked_until.pop(ip, None)


LOGIN_RATE_LIMIT_MESSAGE = (
    "Too many failed login attempts. Please wait a few minutes and try again."
)
