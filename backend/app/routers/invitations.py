"""Inviting somebody who does not have an account, and letting them in.

Two audiences, two very different security postures, one file so the pair can
be read together.

**The admin half** is ordinary tenant-admin work behind the usual session.

**The candidate half is unauthenticated**, which is the part worth being
careful about. Three rules hold it together, and each exists because the
obvious implementation gets it wrong:

* *Looking is free, claiming is once.* ``GET`` tells a candidate what they
  have been invited to without consuming anything, so a preview, a reload or a
  link-scanner in a mail client cannot burn the invitation. ``POST`` is what
  redeems it, once, atomically.
* *A redeemed session is a key to one assessment.* Role ``candidate``, and
  every endpoint they can reach checks it. Not a student account with the
  practice screens, the drill history and every past result attached.
* *Refusals say which of the three things went wrong.* "Invalid link" is
  useless to somebody holding a link; expired, already-used and withdrawn each
  have a different next step.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo import ReturnDocument

from app import audit, invitations, ratelimit
from app.db import ensure_tenant_models
from app.deps import Principal, TenantModels, require_roles
from app.models.platform import InvitationDirectory, Tenant
from app.models.tenant import Invitation
from app.schemas import (AttemptResult, CandidateSession, InvitationOut,
                         InvitationRequest, InvitePreview, RedeemRequest)
from app.security import TokenPrincipal, create_token

router = APIRouter(prefix="/tenant/invitations", tags=["invitations"],
                   dependencies=[Depends(require_roles("tenant_admin"))])

# Unauthenticated on purpose. Nothing here reads a session, and everything it
# returns is about the invitation the caller already holds a token for.
public = APIRouter(prefix="/invite", tags=["invitations"])

# The one place in this application without a session in front of it, so the
# one place that needs a brake. See ``app.ratelimit`` for what it does and does
# not protect against.
_by_token = ratelimit.Limiter(limit=ratelimit.PER_TOKEN_LIMIT)
_by_caller = ratelimit.Limiter(limit=ratelimit.PER_CALLER_LIMIT)


def _not_flooding(request: Request, token: str) -> None:
    """Both limits, and the token one first.

    Order matters for what the caller learns: an address that has tripped the
    looser limit is doing something no candidate does, whereas a token being
    hammered may be one confused person with a broken connection. Neither
    refusal reveals whether the token is real -- the check runs before the
    lookup, so a 429 says the same thing for a token that exists and one that
    does not.
    """
    if not _by_token.allows(token) or not _by_caller.allows(
            ratelimit.caller_of(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            ratelimit.TOO_MANY_MESSAGE)


def _out(row: Invitation, profile_name: str = "") -> InvitationOut:
    return InvitationOut(
        id=row.id, token=row.token, profile_id=row.profile_id,
        profile_name=profile_name, invited_name=row.invited_name,
        invited_email=row.invited_email, reference=row.reference,
        status=row.status, expires_at=row.expires_at,
        redeemed_at=row.redeemed_at, attempt_id=row.attempt_id,
        created_at=row.created_at)


@router.get("/{invitation_id}/result", response_model=AttemptResult)
async def invitation_result(invitation_id: str, principal: Principal,
                            models: TenantModels) -> AttemptResult:
    """The report for the sitting this invitation produced.

    Without this the external-hiring flow stopped one step short of the point
    of it. An employer could build an assessment, invite somebody, watch the
    invitation turn "redeemed" -- and never see the result. The candidate's
    own report lives behind `/student/attempts/{id}/result`, which is scoped
    to the person who sat it, and every admin route is cohort-scoped, which
    a candidate is not in. There was no route at all.

    Authorised by the invitation rather than by the attempt: this admin's
    institution issued the link, and the database the query runs in is the
    one their token names, so an invitation from another institution is not
    merely forbidden -- it is not present to be asked for.
    """
    from app.routers.attempts import _result, finalise_attempt, pending_responses

    row = await models.Invitation.get(invitation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such invitation")

    attempt = None
    if row.attempt_id:
        attempt = await models.Attempt.get(row.attempt_id)
    if attempt is None and row.candidate_id:
        # Invitations redeemed before the attempt link was recorded. Falls
        # back to the candidate's own attempt rather than reporting nothing.
        attempt = await models.Attempt.find(
            models.Attempt.user_id == row.candidate_id,
            models.Attempt.profile_id == row.profile_id,
        ).sort(models.Attempt.attempt_number).first_or_none()

    if attempt is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nobody has sat this assessment yet, so there is no result.")

    if attempt.status == "scoring" and not await pending_responses(models, attempt.id):
        await finalise_attempt(models, attempt.id)
        attempt = await models.Attempt.get(attempt.id)

    return await _result(models, attempt)


@router.get("", response_model=list[InvitationOut])
async def list_invitations(principal: Principal,
                           models: TenantModels) -> list[InvitationOut]:
    rows = await models.Invitation.find_all().sort(
        -models.Invitation.created_at).limit(200).to_list()
    profiles = await models.SimulationProfile.all().to_list()
    names = {p.id: p.name for p in profiles}
    return [_out(row, names.get(row.profile_id, "")) for row in rows]


@router.post("", response_model=InvitationOut,
             status_code=status.HTTP_201_CREATED)
async def create_invitation(body: InvitationRequest, principal: Principal,
                            models: TenantModels) -> InvitationOut:
    """Issue a link for one person to sit one assessment."""
    profile = await models.SimulationProfile.get(body.profile_id)
    if profile is None or profile.status != "published":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That assessment is not published, so nobody can be invited to it "
            "yet.")

    token = invitations.new_token()
    row = models.Invitation(
        token=token, profile_id=profile.id,
        invited_name=body.invited_name.strip(),
        invited_email=body.invited_email.strip().lower(),
        reference=body.reference.strip(),
        expires_at=invitations.expiry_for(body.valid_days),
        created_by=principal.user_id,
    )
    await row.create()

    # The control-plane pointer, so redemption can find the database without a
    # session and without the slug appearing in the link.
    await InvitationDirectory(
        token=token, tenant_id=principal.tenant_id or "",
        tenant_slug=principal.tenant_slug or "").create()

    await audit.record(principal, "invitation.created", entity="Invitation",
                       entity_id=row.id,
                       after={"profile": profile.name,
                              "invited": row.invited_email})
    return _out(row, profile.name)


@router.post("/{invitation_id}/withdraw", response_model=InvitationOut)
async def withdraw(invitation_id: str, principal: Principal,
                   models: TenantModels) -> InvitationOut:
    """Cancel a link that has not been used.

    A redeemed invitation is left alone: the attempt behind it is somebody's
    work, and withdrawing the invitation afterwards would suggest the result
    can be withdrawn too. It cannot.
    """
    row = await models.Invitation.get(invitation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    if row.redeemed_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That invitation has already been used. The assessment behind it "
            "stands; withdrawing the link now would change nothing.")

    row.status = "withdrawn"
    await row.save()

    # Remove the pointer as well, so a withdrawn token stops resolving to an
    # institution at all rather than resolving and then being refused.
    pointer = await InvitationDirectory.find_one(
        InvitationDirectory.token == row.token)
    if pointer is not None:
        await pointer.delete()

    await audit.record(principal, "invitation.withdrawn", entity="Invitation",
                       entity_id=row.id)
    return _out(row)


# --------------------------------------------------------------------------
# The candidate's side. No session, no account, one token.
# --------------------------------------------------------------------------

async def _resolve(token: str):
    """Token -> (tenant, invitation row) or a refusal.

    Two lookups: the control plane says which institution database, the
    database says whether the invitation is usable. Neither reveals anything
    to somebody without a valid token -- an unknown one stops at the first.
    """
    pointer = await InvitationDirectory.find_one(
        InvitationDirectory.token == token)
    if pointer is None:
        return None, None, invitations.UNKNOWN
    tenant = await Tenant.get(pointer.tenant_id)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        return None, None, invitations.UNKNOWN
    slug = pointer.tenant_slug
    name = tenant.name
    tenant_id = tenant.id

    models = await ensure_tenant_models(slug)
    row = await models.Invitation.find_one(models.Invitation.token == token)
    refusal = invitations.check(row)
    if refusal is not None:
        return None, None, refusal
    profile = await models.SimulationProfile.get(row.profile_id)

    return ({"slug": slug, "id": tenant_id, "name": name},
            {"row": row, "profile": profile}, None)


@public.get("/{token}", response_model=InvitePreview)
async def preview(token: str, request: Request) -> InvitePreview:
    """What am I being asked to do, and by whom?

    A GET, and it consumes nothing. A preview that redeemed would mean a link
    scanner in a mail client -- or the candidate opening it on the train to
    check what it is -- burning the invitation before they ever sat down.
    """
    _not_flooding(request, token)
    tenant, found, refusal = await _resolve(token)
    if refusal is not None:
        return InvitePreview(ok=False, reason=refusal.reason,
                             message=refusal.message)

    profile = found["profile"]
    return InvitePreview(
        ok=True,
        tenant_name=tenant["name"],
        profile_name=profile.name if profile else "",
        description=profile.description if profile else "",
        estimated_minutes=profile.estimated_minutes if profile else 0,
        camera_check=bool(profile.camera_check) if profile else False,
        practice_item=bool(profile.practice_item) if profile else False,
        invited_name=found["row"].invited_name,
    )


@public.post("/{token}/claim", response_model=CandidateSession)
async def claim(token: str, body: RedeemRequest,
                request: Request) -> CandidateSession:
    """Take the invitation, and become somebody who can sit this one test.

    Burning the token is one atomic document update whose filter matches only
    an unused, unexpired, unwithdrawn invitation. Two people opening the same
    link at the same moment is the case this protects: exactly one of them can
    satisfy the update, so the second gets a refusal rather than a second
    account against a single invitation.
    """
    _not_flooding(request, token)
    tenant, found, refusal = await _resolve(token)
    if refusal is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, refusal.message)

    name = body.full_name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Please give the name your result should be in.")

    models = await ensure_tenant_models(tenant["slug"])

    email = invitations.candidate_email(token, body.email)
    existing = await models.User.find_one(models.User.email == email)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Somebody with that email address already has an account here. "
            "Sign in instead, or use a different address.")

    now = datetime.now(timezone.utc)
    claimed = await models.Invitation.get_motor_collection().find_one_and_update(
        {"token": token,
         "status": {"$ne": "withdrawn"},
         "redeemed_at": None,
         "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]},
        {"$set": {"status": "redeemed", "redeemed_at": now}},
        return_document=ReturnDocument.BEFORE)
    if claimed is None:
        # Re-checked inside the claim, not just before it. Between the
        # resolve above and this update somebody else may have claimed it.
        row_now = await models.Invitation.find_one(
            models.Invitation.token == token)
        again = invitations.check(row_now)
        raise HTTPException(status.HTTP_409_CONFLICT,
                            (again or invitations.USED).message)
    row = models.Invitation.model_validate(claimed)

    candidate = models.User(
        email=email, full_name=name,
        # No password. There is nothing to sign in to: the token was the
        # credential and it is now spent.
        password_hash="",
        role=invitations.CANDIDATE_ROLE, active=True)
    await candidate.create()

    row.candidate_id = candidate.id
    await row.save()

    candidate_id = candidate.id
    full_name = candidate.full_name

    principal = TokenPrincipal(
        user_id=candidate_id, email=email, full_name=full_name,
        role=invitations.CANDIDATE_ROLE, scope="tenant",
        tenant_id=tenant["id"], tenant_slug=tenant["slug"])

    return CandidateSession(
        token=create_token(principal),
        candidate_id=candidate_id,
        full_name=full_name,
        profile_id=row.profile_id,
        tenant_name=tenant["name"],
    )
