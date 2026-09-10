"""Close the per-company listening content gap for the 5 "Group B" companies
(ADP, Deloitte, Virtusa, LTIMindtree, IBM).

Live verification (2026-09-11) found each of these five had exactly one
company-tagged audio_comprehension item, far short of the 10-item Listening
section every company round now configures. This adds five new listening
passages per company (two questions each = 10 new items), bringing each
company's pool to 11 -- enough to fill the section with a little rotation
room for repeat practice attempts.

Idempotent: skips a company already at or above the target pool size.

    python -m app.seed_company_listening_gap
"""
from __future__ import annotations

import asyncio

TARGET_POOL = 11

# (title, transcript, [(stem, options, correct_index, explanation)])
PASSAGES_BY_COMPANY = {
    "ADP": [
        (
            "Payroll Cycle Update",
            "This month we're moving the payroll cutoff two days earlier so the tax "
            "filing team has enough time to reconcile before the deadline. Managers "
            "should submit timesheet approvals by the 26th instead of the 28th. "
            "Employees paid hourly will see no change to their pay date, only to "
            "when their hours need to be logged.",
            [
                ("Why is the payroll cutoff moving earlier?",
                 ["To increase employee pay", "To give the tax filing team more reconciliation time",
                  "Because of a system outage", "To reduce manager workload"], 1,
                 "The passage says the change gives the tax filing team more time to reconcile."),
                ("What changes for hourly employees?",
                 ["Their pay date moves", "Their hourly rate increases",
                  "Only when their hours must be logged", "Nothing changes for them"], 2,
                 "The passage states only the hours-logging deadline changes for hourly employees."),
            ],
        ),
        (
            "Benefits Enrollment Reminder",
            "Open enrollment for health and retirement benefits closes at the end of "
            "next week. Employees who don't actively make a selection will be "
            "automatically re-enrolled in their current plan, but any changes to "
            "dependents must be submitted manually through the portal before the "
            "deadline.",
            [
                ("What happens if an employee makes no selection?",
                 ["They lose coverage", "They are automatically re-enrolled in their current plan",
                  "They must call HR", "Their pay is affected"], 1,
                 "The passage says no selection means automatic re-enrollment in the current plan."),
                ("What must be done manually before the deadline?",
                 ["Choosing a new plan", "Submitting dependent changes through the portal",
                  "Filing taxes", "Requesting a pay raise"], 1,
                 "Dependent changes must be submitted manually through the portal."),
            ],
        ),
        (
            "Client Onboarding Call",
            "Thanks for joining. Once your company's data is migrated into our "
            "payroll platform, you'll get a dedicated implementation specialist for "
            "the first ninety days. After that, support moves to our standard "
            "helpdesk, but you can request an extension if your rollout is more "
            "complex than usual.",
            [
                ("How long does the dedicated specialist support last?",
                 ["Thirty days", "Sixty days", "Ninety days", "One year"], 2,
                 "The passage states the dedicated specialist supports the first ninety days."),
                ("What can a client do if their rollout is complex?",
                 ["Cancel the contract", "Request an extension",
                  "Switch platforms", "Skip the helpdesk entirely"], 1,
                 "The passage says clients can request an extension for complex rollouts."),
            ],
        ),
        (
            "Compliance Training Briefing",
            "Starting this quarter, all client-facing staff must complete an annual "
            "data privacy refresher before accessing payroll records. The training "
            "takes about forty minutes and must be completed within thirty days of "
            "the reminder email. Managers will be notified if their team members "
            "haven't finished on time.",
            [
                ("Who must complete the refresher training?",
                 ["Only new hires", "All client-facing staff", "Only managers", "Only IT staff"], 1,
                 "The passage says all client-facing staff must complete it."),
                ("How long do employees have after the reminder email?",
                 ["Ten days", "Thirty days", "Sixty days", "No deadline"], 1,
                 "The passage states employees have thirty days after the reminder."),
            ],
        ),
        (
            "System Downtime Notice",
            "The payroll platform will be unavailable this Saturday from 10pm to "
            "2am for scheduled maintenance. Any pending approvals should be "
            "completed by Friday evening. If an urgent issue comes up during the "
            "window, contact the emergency support line instead of the regular "
            "helpdesk.",
            [
                ("When will the platform be unavailable?",
                 ["Friday 10pm to 2am", "Saturday 10pm to 2am", "Sunday all day", "Monday morning"], 1,
                 "The passage specifies Saturday 10pm to 2am."),
                ("What should be done for an urgent issue during the maintenance window?",
                 ["Wait until Monday", "Contact the emergency support line",
                  "Email the CEO", "Restart the platform"], 1,
                 "The passage says to contact the emergency support line for urgent issues."),
            ],
        ),
    ],
    "Deloitte": [
        (
            "Audit Kickoff Meeting",
            "Before we begin fieldwork, I want to confirm the scope with the client. "
            "We'll be testing controls across procurement and revenue recognition "
            "this cycle, with a sample period covering the last two quarters. Any "
            "findings will be documented in the interim report before the final "
            "opinion is issued.",
            [
                ("Which two areas will controls testing cover?",
                 ["Payroll and IT", "Procurement and revenue recognition",
                  "Marketing and sales", "Legal and compliance"], 1,
                 "The passage names procurement and revenue recognition."),
                ("Where will findings be documented first?",
                 ["The final opinion", "The interim report", "A client email", "The engagement letter"], 1,
                 "The passage says findings go into the interim report before the final opinion."),
            ],
        ),
        (
            "Risk Advisory Debrief",
            "Our assessment found the client's third-party vendor risk process was "
            "largely manual, which increases the chance of missed reviews. We're "
            "recommending a centralized vendor register and an annual re-certification "
            "cycle for any vendor handling sensitive data.",
            [
                ("What problem did the assessment find?",
                 ["Too many vendors", "A largely manual vendor risk process",
                  "Missing contracts", "Excessive spending"], 1,
                 "The passage says the vendor risk process was largely manual."),
                ("What is being recommended for sensitive-data vendors?",
                 ["Immediate termination", "An annual re-certification cycle",
                  "A price renegotiation", "No changes"], 1,
                 "The passage recommends an annual re-certification cycle."),
            ],
        ),
        (
            "Tax Advisory Update",
            "With the new cross-border reporting requirement taking effect next "
            "year, clients with overseas subsidiaries should start gathering "
            "transfer pricing documentation now. Waiting until the filing deadline "
            "significantly increases the risk of penalties.",
            [
                ("What should clients with overseas subsidiaries start doing now?",
                 ["Closing subsidiaries", "Gathering transfer pricing documentation",
                  "Filing early taxes", "Hiring more staff"], 1,
                 "The passage advises gathering transfer pricing documentation now."),
                ("What increases if clients wait until the filing deadline?",
                 ["Tax refunds", "Risk of penalties", "Profit margins", "Staff morale"], 1,
                 "The passage says waiting increases the risk of penalties."),
            ],
        ),
        (
            "Engagement Team Standup",
            "We're behind on the fieldwork schedule because two client documents "
            "haven't arrived yet. I've asked the client relationship partner to "
            "follow up directly. If we don't have them by Wednesday, we'll need to "
            "push the review meeting to next week.",
            [
                ("Why is the team behind schedule?",
                 ["Staff shortage", "Two client documents haven't arrived",
                  "A system outage", "Budget cuts"], 1,
                 "The passage says two client documents haven't arrived yet."),
                ("What happens if the documents aren't received by Wednesday?",
                 ["The audit is cancelled", "The review meeting is pushed to next week",
                  "The client is billed extra", "Nothing changes"], 1,
                 "The passage states the review meeting would be pushed to next week."),
            ],
        ),
        (
            "Consulting Proposal Review",
            "The client wants a phased rollout rather than a single big-bang "
            "implementation, mainly to reduce disruption to their finance team "
            "during quarter-end close. We'll structure the proposal around three "
            "phases, each with its own success criteria before moving forward.",
            [
                ("Why does the client want a phased rollout?",
                 ["To save money", "To reduce disruption during quarter-end close",
                  "Because of a legal requirement", "To hire more consultants"], 1,
                 "The passage says the reason is reducing disruption during quarter-end close."),
                ("How many phases will the proposal include?",
                 ["Two", "Three", "Four", "Five"], 1,
                 "The passage states the proposal will have three phases."),
            ],
        ),
    ],
    "Virtusa": [
        (
            "Sprint Planning Call",
            "This sprint we're prioritising the checkout API fixes over the new "
            "reporting feature, since the client flagged the checkout bugs as "
            "customer-facing. The reporting feature will roll into next sprint "
            "instead, assuming QA doesn't find anything major this week.",
            [
                ("What is being prioritised this sprint?",
                 ["The reporting feature", "The checkout API fixes",
                  "A new hire onboarding", "Server migration"], 1,
                 "The passage says the checkout API fixes are prioritised."),
                ("When will the reporting feature likely be worked on?",
                 ["This sprint", "Next sprint", "It's cancelled", "In six months"], 1,
                 "The passage says the reporting feature rolls into next sprint."),
            ],
        ),
        (
            "Digital Engineering Briefing",
            "Our client's legacy monolith is being broken into microservices in "
            "stages, starting with the authentication module since it has the "
            "fewest dependencies. Later phases will tackle the order processing "
            "and inventory modules, which are more tightly coupled.",
            [
                ("Which module is being migrated first?",
                 ["Order processing", "Inventory", "Authentication", "Reporting"], 2,
                 "The passage says authentication is first due to fewest dependencies."),
                ("Why are order processing and inventory being done later?",
                 ["They're not important", "They are more tightly coupled",
                  "The client asked for it randomly", "They don't need migration"], 1,
                 "The passage says those modules are more tightly coupled."),
            ],
        ),
        (
            "QA Automation Update",
            "We've automated about sixty percent of the regression suite so far. "
            "The remaining tests involve UI flows that change frequently, so we're "
            "holding off automating those until the design is finalised, to avoid "
            "rewriting scripts every sprint.",
            [
                ("What percentage of the regression suite is automated?",
                 ["Thirty percent", "Sixty percent", "Ninety percent", "One hundred percent"], 1,
                 "The passage states sixty percent is automated so far."),
                ("Why haven't the remaining UI tests been automated yet?",
                 ["Lack of budget", "The design isn't finalised yet",
                  "The team lacks skills", "The client refused"], 1,
                 "The passage explains they're waiting for the design to be finalised."),
            ],
        ),
        (
            "Client Escalation Call",
            "The client is concerned about the delay in the payments integration. "
            "We've identified the root cause as a mismatch in API versions between "
            "our sandbox and their production environment, and we expect a fix "
            "within two business days.",
            [
                ("What caused the delay in the payments integration?",
                 ["A staffing issue", "A mismatch in API versions", "A budget dispute",
                  "A security breach"], 1,
                 "The passage identifies an API version mismatch as the cause."),
                ("When is the fix expected?",
                 ["Same day", "Within two business days", "Next month", "No timeline given"], 1,
                 "The passage says a fix is expected within two business days."),
            ],
        ),
        (
            "Talent Development Session",
            "We're launching an internal certification track for cloud "
            "architecture, since client demand for cloud migration work has grown "
            "significantly. Engineers who complete it will be prioritised for "
            "upcoming cloud engagements.",
            [
                ("Why is the certification track being launched?",
                 ["To cut costs", "Because client demand for cloud migration has grown",
                  "Because of a compliance rule", "To reduce headcount"], 1,
                 "The passage says growing client demand for cloud migration is the reason."),
                ("What benefit do engineers get from completing the certification?",
                 ["A pay cut", "Priority for upcoming cloud engagements",
                  "Mandatory relocation", "Nothing"], 1,
                 "The passage says they'll be prioritised for cloud engagements."),
            ],
        ),
    ],
    "LTIMindtree": [
        (
            "Cloud Migration Review",
            "The client's data warehouse migration is on track, but we found that "
            "some legacy reports rely on stored procedures that don't have a "
            "direct cloud equivalent. We're rewriting those as scheduled jobs "
            "instead, which should be transparent to end users.",
            [
                ("What issue was found with some legacy reports?",
                 ["They were deleted", "They rely on stored procedures without a cloud equivalent",
                  "They were duplicated", "They failed security review"], 1,
                 "The passage says the stored procedures lack a direct cloud equivalent."),
                ("How is the issue being resolved?",
                 ["Cancelling the reports", "Rewriting them as scheduled jobs",
                  "Ignoring the issue", "Reverting the migration"], 1,
                 "The passage states they're being rewritten as scheduled jobs."),
            ],
        ),
        (
            "Project Status Standup",
            "We're two days behind on the integration testing phase because the "
            "test environment kept losing connectivity to the client's staging "
            "server. Infrastructure has escalated it as a priority ticket, so we "
            "expect to catch up by the end of the week.",
            [
                ("Why is the team behind on integration testing?",
                 ["A staffing shortage", "The test environment lost connectivity to staging",
                  "A budget freeze", "A scope change"], 1,
                 "The passage attributes the delay to lost connectivity to the staging server."),
                ("What is expected by the end of the week?",
                 ["Project cancellation", "Catching up on the schedule",
                  "A new contract", "A client complaint"], 1,
                 "The passage says they expect to catch up by the end of the week."),
            ],
        ),
        (
            "Application Modernization Call",
            "The client wants to retire their mainframe system within eighteen "
            "months. Our recommendation is a phased approach, moving the batch "
            "jobs first since they're easier to validate, and leaving the "
            "interactive transactions for the final phase.",
            [
                ("What is the client's timeline for retiring the mainframe?",
                 ["Six months", "Eighteen months", "Five years", "No timeline"], 1,
                 "The passage states eighteen months."),
                ("What will be moved first in the phased approach?",
                 ["Interactive transactions", "Batch jobs", "User interfaces", "Databases only"], 1,
                 "The passage says batch jobs are moved first since they're easier to validate."),
            ],
        ),
        (
            "Support Desk Metrics Review",
            "Ticket volume dropped fifteen percent after we introduced the "
            "self-service knowledge base last quarter. However, average resolution "
            "time for the remaining tickets increased slightly, since the simpler "
            "issues are now being deflected before they reach an agent.",
            [
                ("What happened to ticket volume after the knowledge base launched?",
                 ["It increased", "It dropped fifteen percent", "It stayed the same",
                  "It doubled"], 1,
                 "The passage says ticket volume dropped fifteen percent."),
                ("Why did average resolution time increase slightly?",
                 ["Agents were understaffed", "Simpler issues are now deflected before reaching an agent",
                  "The knowledge base failed", "Clients complained more"], 1,
                 "The passage explains simpler issues are deflected, leaving harder ones for agents."),
            ],
        ),
        (
            "Client Governance Meeting",
            "We proposed a monthly steering committee instead of the current "
            "weekly check-ins, since most weekly updates had little new "
            "information to report. The client agreed, but asked that any major "
            "risk still be escalated immediately rather than waiting for the "
            "monthly meeting.",
            [
                ("What change to the meeting cadence was proposed?",
                 ["Moving from monthly to weekly", "Moving from weekly to monthly",
                  "Cancelling meetings entirely", "Adding a daily meeting"], 1,
                 "The passage says the proposal was to move from weekly to monthly."),
                ("What did the client still want to happen immediately?",
                 ["All status updates", "Escalation of any major risk",
                  "Budget approvals", "Contract renewals"], 1,
                 "The passage says major risks should still be escalated immediately."),
            ],
        ),
    ],
    "IBM": [
        (
            "Hybrid Cloud Strategy Briefing",
            "The client is running workloads across three different cloud "
            "providers and wants a single control plane to manage them "
            "consistently. We're proposing a hybrid cloud platform that can "
            "orchestrate deployments across all three without vendor lock-in.",
            [
                ("Why does the client want a single control plane?",
                 ["To reduce the number of cloud providers", "To manage workloads across providers consistently",
                  "To cut all cloud spending", "To eliminate cloud usage entirely"], 1,
                 "The passage says the client wants consistent management across providers."),
                ("What is a key benefit of the proposed platform?",
                 ["Vendor lock-in", "No vendor lock-in", "Higher cost", "Slower deployments"], 1,
                 "The passage highlights avoiding vendor lock-in."),
            ],
        ),
        (
            "AI Governance Workshop",
            "Before deploying the new model into production, the client's "
            "compliance team wants documented evidence of how training data was "
            "sourced and how bias testing was performed. We're building that "
            "documentation into the deployment pipeline itself.",
            [
                ("What does the compliance team want before production deployment?",
                 ["A marketing plan", "Documented evidence of data sourcing and bias testing",
                  "A price reduction", "A new vendor contract"], 1,
                 "The passage states they want documentation on data sourcing and bias testing."),
                ("Where is this documentation being built into?",
                 ["A separate spreadsheet", "The deployment pipeline itself",
                  "An external audit firm", "A press release"], 1,
                 "The passage says it's being built into the deployment pipeline."),
            ],
        ),
        (
            "Mainframe Modernization Call",
            "Rather than a full rewrite, we're recommending the client wrap "
            "existing COBOL services with modern APIs, letting new applications "
            "consume them without touching the underlying code. A full "
            "rewrite can be considered later once the API layer proves stable.",
            [
                ("What is being recommended instead of a full rewrite?",
                 ["Deleting the COBOL services", "Wrapping them with modern APIs",
                  "Outsourcing the mainframe", "Ignoring the issue"], 1,
                 "The passage recommends wrapping COBOL services with modern APIs."),
                ("When might a full rewrite be considered?",
                 ["Immediately", "Once the API layer proves stable", "Never",
                  "Only if the client insists"], 1,
                 "The passage says a rewrite could be considered once the API layer is stable."),
            ],
        ),
        (
            "Security Operations Update",
            "Our managed detection team identified unusual login activity "
            "originating from a region the client doesn't normally operate in. "
            "We've temporarily suspended the affected accounts and are working "
            "with the client's IT team to confirm whether it was a false "
            "positive.",
            [
                ("What triggered the security investigation?",
                 ["A missed invoice", "Unusual login activity from an unexpected region",
                  "A software update", "A client complaint"], 1,
                 "The passage says unusual login activity from an unexpected region triggered it."),
                ("What action was taken on the affected accounts?",
                 ["They were deleted", "They were temporarily suspended",
                  "Nothing was done", "Passwords were shared"], 1,
                 "The passage states the affected accounts were temporarily suspended."),
            ],
        ),
        (
            "Consulting Engagement Debrief",
            "The client's biggest pain point turned out to be inconsistent data "
            "definitions across departments rather than a lack of tooling. Our "
            "recommendation focuses on establishing a shared data glossary before "
            "investing in any new analytics platform.",
            [
                ("What was identified as the client's biggest pain point?",
                 ["A lack of tooling", "Inconsistent data definitions across departments",
                  "Insufficient staff", "Poor network speed"], 1,
                 "The passage says inconsistent data definitions were the biggest pain point."),
                ("What is recommended before investing in a new analytics platform?",
                 ["Hiring more analysts", "Establishing a shared data glossary",
                  "Buying more hardware", "Changing vendors"], 1,
                 "The passage recommends establishing a shared data glossary first."),
            ],
        ),
    ],
}


async def main() -> None:
    from app.db import init_mongo
    from app.models.tenant import ListeningPassage, QuizItem

    await init_mongo()

    total_added = 0
    for company, passages in PASSAGES_BY_COMPANY.items():
        current = await QuizItem.find(
            QuizItem.company == company, QuizItem.category == "audio_comprehension"
        ).count()
        if current >= TARGET_POOL:
            print(f"{company}: already at target ({current})")
            continue

        added = 0
        for title, transcript, questions in passages:
            existing = await ListeningPassage.find_one(
                ListeningPassage.company == company, ListeningPassage.title == title
            )
            if existing is not None:
                continue
            passage = await ListeningPassage(
                title=title,
                kind="short_talk",
                transcript=transcript,
                company=company,
                accent="indian",
                plays_allowed=1,
                approx_seconds=45,
                difficulty=0.5,
                status="published",
            ).insert()
            for stem, options, correct_index, explanation in questions:
                await QuizItem(
                    category="audio_comprehension",
                    stem=stem,
                    options=options,
                    correct_index=correct_index,
                    explanation=explanation,
                    passage_id=passage.id,
                    company=company,
                    seconds_allowed=30,
                    difficulty=0.5,
                    status="published",
                ).insert()
                added += 1
        total_added += added
        print(f"{company}: added {added} items (now {current + added})")

    print(f"done, {total_added} items added")


if __name__ == "__main__":
    asyncio.run(main())
