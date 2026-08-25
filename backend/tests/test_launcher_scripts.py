"""The launcher scripts have to survive Windows PowerShell 5.1.

This exists because of a real failure found during the microphone smoke-test
preflight. ``run-smoke-test.ps1`` was UTF-8 without a BOM, which PowerShell
5.1 decodes as Windows-1252. An em dash (E2 80 94) came back as ``a EUR "``,
and that last byte is U+201D -- a smart right quote, which the PowerShell
parser accepts as a *string delimiter*. Every string containing an em dash
terminated early and the parse quietly derailed from there.

The visible symptom was that ``-Network`` was honoured for the certificate and
ignored for the servers: HTTP instead of HTTPS, bound to localhost instead of
the LAN. A tester on a phone would have been handed an address that cannot
work, and the microphone would never have been offered.

Nothing about that failure is loud. Hence a test.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted(REPO_ROOT.glob("*.ps1")) + sorted(REPO_ROOT.glob("scripts/*.ps1"))


def test_there_are_launcher_scripts_to_check() -> None:
    """Guard the guard: a glob that matches nothing passes vacuously."""
    assert SCRIPTS, f"no .ps1 files found under {REPO_ROOT}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_are_ascii(script: Path) -> None:
    raw = script.read_bytes()
    offenders = {b for b in raw if b > 0x7F}
    assert not offenders, (
        f"{script.name} contains non-ASCII bytes "
        f"{sorted(hex(b) for b in offenders)}. PowerShell 5.1 reads a "
        "BOM-less file as Windows-1252, and 0x94 in particular becomes a "
        "smart quote that silently terminates a string mid-parse. Use ASCII."
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_have_no_utf16_bom(script: Path) -> None:
    """A UTF-16 BOM would make the ASCII check above meaningless."""
    head = script.read_bytes()[:2]
    assert head not in (b"\xff\xfe", b"\xfe\xff"), (
        f"{script.name} is UTF-16; the ASCII guarantee does not apply"
    )
