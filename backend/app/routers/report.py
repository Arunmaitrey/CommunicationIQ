"""Exam report — generates a printable HTML report that can be saved as PDF.

The report includes:
- Institution branding (name, logo)
- Student details (name, email, roll number)
- Exam details (profile name, attempt number, timing, mode)
- Score breakdown by dimension and section
- Skills radar (text-based)
- Response-level evidence
- Diagnosis and recommendations
- CEFR level if available
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from app.deps import Principal, TenantModels, require_roles
from app import formats

router = APIRouter(prefix="/report", tags=["report"],
                   dependencies=[Depends(require_roles("student", "tenant_admin", "trainer"))])


def _skill_bar(label: str, score: float, scale_max: float = 80, width: int = 40) -> str:
    """A text-based horizontal bar for a score."""
    if score is None:
        return f"{label}: —"
    pct = min(score / scale_max, 1.0)
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{label}: {bar} {score:.1f}/{scale_max:.0f}"


def _html_report(
    student_name: str,
    student_email: str,
    student_roll: str,
    student_branch: str,
    tenant_name: str,
    tenant_logo: str | None,
    profile_name: str,
    profile_style: str,
    attempt_number: int,
    mode: str,
    is_baseline: bool,
    started_at: datetime | None,
    submitted_at: datetime | None,
    scored_at: datetime | None,
    overall: float | None,
    band: str,
    scale_min: float,
    scale_max: float,
    dimensions: dict,
    confidence: dict,
    unscored: dict,
    skills: list,
    sections: list,
    summary: str,
    strengths: list,
    weaknesses: list,
    recommendations: list,
    primary_diagnosis: dict | None,
    cefr_level: str,
    cefr_descriptor: str,
    verdict: dict | None,
    environment_note: str,
    attempt_id: str,
) -> str:
    """Build a self-contained HTML report."""

    def _fmt_dt(dt: datetime | None) -> str:
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d %b %Y, %I:%M %p UTC")

    duration_str = "—"
    if started_at and submitted_at:
        s = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        e = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=timezone.utc)
        mins = int((e - s).total_seconds() / 60)
        duration_str = f"{mins} min"

    overall_str = f"{overall:.1f}" if overall is not None else "—"

    # Dimension rows
    dim_rows = ""
    for dim, score in sorted(dimensions.items()):
        conf = confidence.get(dim, 0)
        conf_str = f"{conf:.0%}" if conf else "—"
        unscored_reason = unscored.get(dim, "")
        score_str = f"{score:.1f}" if score is not None else "—"
        note = f' <span class="unscored">({unscored_reason})</span>' if unscored_reason else ""
        dim_rows += f"""
        <tr>
          <td class="dim-name">{dim.replace('_', ' ').title()}</td>
          <td class="dim-score">{score_str}{note}</td>
          <td class="dim-conf">{conf_str}</td>
        </tr>"""

    # Section rows
    section_rows = ""
    for sec in sections:
        sec_score = sec.get("score")
        sec_str = f"{sec_score:.1f}" if sec_score is not None else "—"
        section_rows += f"""
        <tr>
          <td>{sec.get('title', '')}</td>
          <td>{sec.get('task_type', '').replace('_', ' ').title()}</td>
          <td>{sec.get('items_answered', 0)}/{sec.get('items_total', 0)}</td>
          <td class="dim-score">{sec_str}</td>
        </tr>"""

    # Skills rows
    skill_rows = ""
    for sk in skills:
        sk_score = sk.get("score")
        sk_str = f"{sk_score:.1f}" if sk_score is not None else "—"
        skill_rows += f"""
        <tr>
          <td>{sk.get('skill', '').replace('_', ' ').title()}</td>
          <td class="dim-score">{sk_str}</td>
        </tr>"""

    # Highlights
    def _highlight_list(items: list) -> str:
        if not items:
            return "<p class='muted'>None identified yet.</p>"
        html = "<ul>"
        for h in items:
            if isinstance(h, dict):
                label = h.get("label", h.get("text", ""))
                detail = h.get("detail", h.get("note", ""))
            else:
                label = str(h)
                detail = ""
            html += f"<li><strong>{label}</strong>"
            if detail:
                html += f" — {detail}"
            html += "</li>"
        html += "</ul>"
        return html

    # Recommendations
    rec_html = ""
    for rec in recommendations:
        if isinstance(rec, dict):
            label = rec.get("label", rec.get("text", ""))
            detail = rec.get("detail", rec.get("note", ""))
            surface = rec.get("surface", "")
            rec_html += f'<div class="rec"><strong>{label}</strong>'
            if detail:
                rec_html += f'<br><span class="muted">{detail}</span>'
            if surface:
                rec_html += f'<br><a href="/{surface}" class="rec-link">Start practising →</a>'
            rec_html += "</div>"

    # Diagnosis
    diag_html = ""
    if primary_diagnosis:
        diag_html = f"""
        <div class="diagnosis-box">
          <h3>Primary Focus</h3>
          <p><strong>{primary_diagnosis.get('dimension', '').replace('_', ' ').title()}</strong>
          — {primary_diagnosis.get('explanation', '')}</p>
        </div>"""

    # Verdict (company rounds)
    verdict_html = ""
    if verdict:
        outcome = verdict.get("outcome", "")
        detail = verdict.get("detail", "")
        color = "var(--rag-green)" if "pass" in outcome.lower() else "var(--rag-amber)"
        verdict_html = f"""
        <div class="verdict-box" style="border-left-color: {color}">
          <h3>Assessment Verdict</h3>
          <p class="verdict-outcome">{outcome}</p>
          <p class="muted">{detail}</p>
        </div>"""

    # CEFR
    cefr_html = ""
    if cefr_level:
        cefr_html = f"""
        <div class="cefr-box">
          <strong>CEFR Level: {cefr_level}</strong>
          <span class="muted"> — {cefr_descriptor}</span>
        </div>"""

    logo_html = ""
    if tenant_logo:
        logo_html = f'<img src="{tenant_logo}" alt="{tenant_name}" class="logo" />'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Exam Report — {student_name} — {profile_name}</title>
<style>
  @page {{ margin: 1.5cm; size: A4; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
         font-size: 11pt; color: #1a1a1a; line-height: 1.5; padding: 0; }}
  .report {{ max-width: 700px; margin: 0 auto; }}
  .header {{ display: flex; align-items: center; gap: 16px;
             border-bottom: 3px solid #2563eb; padding-bottom: 12px; margin-bottom: 16px; }}
  .logo {{ height: 40px; object-fit: contain; }}
  .header-text h1 {{ font-size: 16pt; font-weight: 700; color: #1a1a1a; }}
  .header-text .sub {{ font-size: 10pt; color: #666; }}
  .section {{ margin-bottom: 16px; }}
  .section h2 {{ font-size: 11pt; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 0.05em; color: #2563eb; border-bottom: 1px solid #e5e7eb;
                 padding-bottom: 4px; margin-bottom: 8px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px;
                font-size: 10pt; }}
  .meta-grid dt {{ color: #666; }}
  .meta-grid dd {{ font-weight: 600; }}
  .overall {{ text-align: center; padding: 16px; background: #f8fafc;
              border-radius: 8px; margin-bottom: 16px; }}
  .overall .score {{ font-size: 36pt; font-weight: 700; color: #2563eb; }}
  .overall .label {{ font-size: 10pt; color: #666; }}
  .overall .band {{ font-size: 12pt; font-weight: 600; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th {{ text-align: left; padding: 4px 8px; background: #f1f5f9;
       font-weight: 600; border-bottom: 2px solid #e5e7eb; }}
  td {{ padding: 4px 8px; border-bottom: 1px solid #f1f5f9; }}
  .dim-name {{ font-weight: 600; }}
  .dim-score {{ text-align: right; font-weight: 600; }}
  .dim-conf {{ text-align: right; color: #666; }}
  .unscored {{ color: #d97706; font-size: 9pt; font-style: italic; }}
  .muted {{ color: #666; font-size: 10pt; }}
  ul {{ padding-left: 16px; }}
  li {{ margin-bottom: 4px; font-size: 10pt; }}
  .diagnosis-box {{ background: #eff6ff; border-left: 4px solid #2563eb;
                    padding: 12px; border-radius: 0 8px 8px 0; margin: 12px 0; }}
  .verdict-box {{ background: #f0fdf4; border-left: 4px solid #16a34a;
                  padding: 12px; border-radius: 0 8px 8px 0; margin: 12px 0; }}
  .verdict-outcome {{ font-size: 14pt; font-weight: 700; }}
  .cefr-box {{ background: #fef3c7; padding: 10px 12px; border-radius: 6px;
               margin: 12px 0; font-size: 10pt; }}
  .rec {{ padding: 8px; background: #f8fafc; border-radius: 6px;
          margin-bottom: 6px; font-size: 10pt; }}
  .rec-link {{ color: #2563eb; font-size: 9pt; text-decoration: none; }}
  .footer {{ border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 24px;
             font-size: 8pt; color: #999; text-align: center; }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>
<div class="report">

  <div class="header">
    {logo_html}
    <div class="header-text">
      <h1>Exam Report</h1>
      <div class="sub">{tenant_name} — CommunicationIQ</div>
    </div>
  </div>

  <!-- Student & Exam Details -->
  <div class="section">
    <h2>Details</h2>
    <dl class="meta-grid">
      <dt>Student</dt><dd>{student_name}</dd>
      <dt>Email</dt><dd>{student_email}</dd>
      {"<dt>Roll Number</dt><dd>" + student_roll + "</dd>" if student_roll else ""}
      {"<dt>Branch</dt><dd>" + student_branch + "</dd>" if student_branch else ""}
      <dt>Assessment</dt><dd>{profile_name}{" (Baseline)" if is_baseline else ""}</dd>
      <dt>Attempt</dt><dd>#{attempt_number} — {mode.title()}</dd>
      <dt>Started</dt><dd>{_fmt_dt(started_at)}</dd>
      <dt>Submitted</dt><dd>{_fmt_dt(submitted_at)}</dd>
      <dt>Duration</dt><dd>{duration_str}</dd>
      <dt>Scored</dt><dd>{_fmt_dt(scored_at)}</dd>
    </dl>
  </div>

  {verdict_html}

  <!-- Overall Score -->
  <div class="overall">
    <div class="label">Overall Score</div>
    <div class="score">{overall_str}</div>
    {"<div class='band'>" + band + "</div>" if band else ""}
    <div class="label">Scale: {scale_min:.0f}–{scale_max:.0f}</div>
    {cefr_html}
  </div>

  {diag_html}

  <!-- Dimensions -->
  <div class="section">
    <h2>Score Breakdown</h2>
    <table>
      <thead><tr><th>Dimension</th><th style="text-align:right">Score</th><th style="text-align:right">Confidence</th></tr></thead>
      <tbody>{dim_rows}</tbody>
    </table>
  </div>

  <!-- Skills -->
  {"" if not skills else """
  <div class="section">
    <h2>Skill Scores</h2>
    <table>
      <thead><tr><th>Skill</th><th style="text-align:right">Score</th></tr></thead>
      <tbody>""" + skill_rows + """</tbody>
    </table>
  </div>"""}

  <!-- Sections -->
  {"" if not sections else """
  <div class="section">
    <h2>Section Results</h2>
    <table>
      <thead><tr><th>Section</th><th>Type</th><th>Items</th><th style="text-align:right">Score</th></tr></thead>
      <tbody>""" + section_rows + """</tbody>
    </table>
  </div>"""}

  <!-- Summary -->
  {"" if not summary else """
  <div class="section">
    <h2>Summary</h2>
    <p>""" + summary + """</p>
  </div>"""}

  <!-- Strengths -->
  <div class="section">
    <h2>Strengths</h2>
    {_highlight_list(strengths)}
  </div>

  <!-- Weaknesses -->
  <div class="section">
    <h2>Areas to Improve</h2>
    {_highlight_list(weaknesses)}
  </div>

  <!-- Recommendations -->
  {"" if not recommendations else """
  <div class="section">
    <h2>Recommended Next Steps</h2>
    """ + rec_html + """
  </div>"""}

  <!-- Environment Note -->
  {"" if not environment_note else """
  <div class="section">
    <h2>Environment Note</h2>
    <p class="muted">""" + environment_note + """</p>
  </div>"""}

  <div class="footer">
    Generated by CommunicationIQ — {datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")}<br/>
    Attempt ID: {attempt_id}
  </div>

</div>

<!-- Print button (hidden when printed) -->
<div class="no-print" style="text-align:center; padding:20px;">
  <button onclick="window.print()" style="padding:10px 24px; background:#2563eb; color:white;
          border:none; border-radius:6px; font-size:12pt; cursor:pointer; font-weight:600;">
    Print / Save as PDF
  </button>
  <p style="font-size:9pt; color:#999; margin-top:8px;">
    Click the button above, then choose "Save as PDF" in the print dialog.
  </p>
</div>

</body>
</html>"""


@router.get("/{attempt_id}", response_class=HTMLResponse)
async def report_html(attempt_id: str, principal: Principal,
                      models: TenantModels) -> HTMLResponse:
    """A self-contained HTML report for one attempt. Prints cleanly as PDF."""
    attempt = await models.Attempt.get(attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")

    # Students can only see their own reports
    if principal.role == "student" and attempt.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")

    # For trainers, check they teach this student
    if principal.role in ("trainer", "tenant_admin"):
        user = await models.User.get(attempt.user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    from app.routers.attempts import _result
    result = await _result(models, attempt)

    # Get student info
    user = await models.User.get(attempt.user_id)
    profile = await models.SimulationProfile.get(attempt.profile_id)

    # Get tenant info
    tenant_name = ""
    tenant_logo = None
    if principal.tenant_id:
        from app.db import platform_sessionmaker
        from app.models.platform import Tenant
        async with platform_sessionmaker()() as platform:
            tenant = await platform.get(Tenant, principal.tenant_id)
            if tenant:
                tenant_name = tenant.name
                tenant_logo = getattr(tenant, "logo_url", None)

    html = _html_report(
        student_name=user.full_name if user else "Unknown",
        student_email=user.email if user else "",
        student_roll=getattr(user, "roll_number", "") or "",
        student_branch=getattr(user, "branch", "") or "",
        tenant_name=tenant_name,
        tenant_logo=tenant_logo,
        profile_name=profile.name if profile else "",
        profile_style=profile.style if profile else "",
        attempt_number=attempt.attempt_number,
        mode=attempt.mode,
        is_baseline=attempt.is_baseline,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        scored_at=attempt.scored_at,
        overall=result.overall,
        band=result.band,
        scale_min=result.scale_min,
        scale_max=result.scale_max,
        dimensions=result.dimensions,
        confidence=result.confidence,
        unscored=result.unscored,
        skills=[s.model_dump() for s in result.skills] if result.skills else [],
        sections=[s.model_dump() for s in result.sections] if result.sections else [],
        summary=result.summary,
        strengths=[h.model_dump() if hasattr(h, 'model_dump') else h for h in result.strengths],
        weaknesses=[h.model_dump() if hasattr(h, 'model_dump') else h for h in result.weaknesses],
        recommendations=[r.model_dump() if hasattr(r, 'model_dump') else r for r in result.recommendations],
        primary_diagnosis=result.primary_diagnosis.model_dump() if result.primary_diagnosis else None,
        cefr_level=result.cefr_level,
        cefr_descriptor=result.cefr_descriptor,
        verdict=result.verdict,
        environment_note=result.environment_note,
        attempt_id=attempt.id,
    )

    return HTMLResponse(content=html)
