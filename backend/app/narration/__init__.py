"""AI Feedback Narrator.

Turns a finished, frozen assessment result into a plain-language explanation.
It is downstream of scoring by construction: it reads an AttemptResult that
already exists and writes only to attempt_narrations. No module here is
imported by the scoring pipeline, and nothing in scoring waits on it.

  contract.py  — the provider Protocol and its data types
  evidence.py  — the whitelist payload builder (what may leave our infra)
  validate.py  — the untrusted-output validator
  providers.py — the real (Anthropic, over httpx) and echo providers
  service.py   — the durable job: claim, generate, validate, persist, retry
  worker.py    — the recovery sweeper and its CLI
"""
