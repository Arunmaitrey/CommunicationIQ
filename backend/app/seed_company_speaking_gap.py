"""Close the per-company speaking content gap for the 8 "Group A" companies
(Accenture, TCS, Cognizant, Wipro, Infosys, HCL, Tech Mahindra, Capgemini).

Live verification (2026-09-11) showed each company's speaking pool was too
thin to reliably fill its configured 2/2/2/2/1/1 (read_aloud/repeat_sentence/
short_answer/open_response/story_retell/sentence_build) section shape once
the company filter was made strict:
  - Accenture/TCS/Cognizant/Wipro/Infosys: 0-2 items per subtype.
  - HCL/Tech Mahindra/Capgemini: 0 items in every subtype.

This tops every subtype up to a small buffer above what each section needs
(3/3/3/3/2/2 = 16 total) so a company's round always fills and repeat
practice attempts see some rotation, not the same single item every time.
Idempotent: only adds items up to the target count, skips companies/subtypes
already at or above it.

    python -m app.seed_company_speaking_gap
"""
from __future__ import annotations

import asyncio

COMPANIES = [
    "Accenture", "TCS", "Cognizant", "Wipro", "Infosys",
    "HCL", "Tech Mahindra", "Capgemini",
]

TARGET = {
    "read_aloud": 3,
    "repeat_sentence": 3,
    "short_answer": 3,
    "open_response": 3,
    "story_retell": 2,
    "sentence_build": 2,
}

READ_ALOUD_SENTENCES = [
    "The client presentation covered three deliverables scheduled for the next sprint.",
    "Effective communication across time zones remains essential for distributed teams.",
    "Our onboarding process now includes a two-week shadowing period for new hires.",
    "The audit team flagged two discrepancies that required immediate follow-up.",
    "Migrating the legacy system took longer than the original estimate suggested.",
    "Customer feedback from the pilot rollout was overwhelmingly positive.",
    "The steering committee approved the revised budget for the fourth quarter.",
    "Cross-functional collaboration helped the team resolve the outage within an hour.",
    "The new dashboard gives managers real-time visibility into project status.",
    "Employees completing the certification will receive a pay-grade review in March.",
    "The vendor contract renewal negotiations concluded ahead of the deadline.",
    "Data privacy training is now mandatory for every employee handling client records.",
    "The regional office reported a steady increase in client retention this year.",
    "Automating the reconciliation process reduced manual errors significantly.",
    "The town hall addressed questions about the upcoming reorganisation.",
    "Quality assurance testing uncovered a critical bug before the release date.",
    "The mentorship programme paired senior engineers with recent graduates.",
    "Stakeholders requested a revised timeline after reviewing the risk assessment.",
    "The finance team streamlined the invoicing workflow using a new template.",
    "Remote employees now have access to the same benefits as on-site staff.",
    "The product roadmap was updated to reflect changing market conditions.",
    "Leadership emphasised the importance of transparent reporting during the review.",
    "The support team resolved the majority of tickets within the same business day.",
    "A revised code of conduct was distributed to all departments last week.",
]

REPEAT_SENTENCES = [
    "Please forward the meeting notes before end of day.",
    "The server maintenance window is scheduled for Saturday night.",
    "We need sign-off from legal before the contract is finalised.",
    "The training session has been moved to the main conference room.",
    "Our team missed the target by only two percentage points.",
    "The client asked for a follow-up call next Tuesday.",
    "Please update the ticket status once testing is complete.",
    "The new hires start their orientation on Monday morning.",
    "Escalate the issue if it isn't resolved within two hours.",
    "The budget review meeting has been pushed to next week.",
    "Make sure the backup completes before you shut down the server.",
    "The proposal needs one more round of revisions before submission.",
    "Our quarterly numbers were shared with the leadership team today.",
    "The access request is pending approval from your manager.",
    "Please double-check the figures before sending the final report.",
    "The client wants the demo rescheduled to Thursday afternoon.",
    "Our helpdesk received a record number of tickets this morning.",
    "The compliance checklist must be completed before go-live.",
    "Everyone on the project needs to attend the kickoff call.",
    "The system upgrade caused a brief delay in processing.",
    "Please share the updated slide deck with the whole team.",
    "The interview panel will meet to finalise their decision tomorrow.",
    "Our warranty policy was updated to cover software defects too.",
    "The release notes should be published alongside the update.",
]

SHORT_ANSWER_QUESTIONS = [
    "How would you prioritise tasks when everything is marked urgent?",
    "What steps would you take to onboard a new team member remotely?",
    "How do you decide when a bug is critical enough to delay a release?",
    "What would you do if a teammate consistently missed deadlines?",
    "How do you keep stakeholders informed when a project falls behind schedule?",
    "What factors would you weigh when choosing between two vendors?",
    "How would you explain a service outage to a non-technical client?",
    "What approach would you take to reduce recurring support tickets?",
    "How do you balance code quality with tight delivery timelines?",
    "What would you do if you disagreed with a manager's technical decision?",
    "How would you handle a client who keeps expanding project scope?",
    "What steps do you take to document a process before handing it off?",
]

OPEN_RESPONSE_QUESTIONS = [
    "Describe a time you had to give difficult feedback to a colleague. How did you approach it?",
    "Tell me about a project that didn't go as planned. What did you learn from it?",
    "Describe a situation where you had to persuade a skeptical stakeholder. What worked?",
    "Tell me about a time you identified a process that could be improved. What did you do?",
    "Describe how you handled a disagreement within your team. What was the outcome?",
    "Tell me about a time you had to quickly adapt to a change in priorities.",
    "Describe a project where you took the initiative without being asked. What happened?",
    "Tell me about a time you had to deliver results with limited resources.",
    "Describe how you handled receiving critical feedback on your work.",
    "Tell me about a time you mentored or trained someone less experienced than you.",
]

STORY_RETELL_STORIES = [
    "A young engineer noticed a small crack in a bridge during a routine inspection. "
    "Everyone told her it was too minor to report, but she filed it anyway. Months later, "
    "the crack was found to be a warning sign of a much larger structural issue, and her "
    "early report likely prevented a serious accident.",
    "A team was given six months to migrate an old system, but they finished in four by "
    "breaking the work into small weekly releases instead of one big launch. Their manager "
    "later said the smaller releases also caught bugs earlier than a single release would have.",
    "A customer support agent kept getting the same complaint about a confusing sign-up form. "
    "Instead of just answering each ticket, she recorded every complaint and shared the pattern "
    "with the product team, who redesigned the form and cut complaints by half.",
    "A new manager inherited a team that rarely spoke up in meetings. He started ending every "
    "meeting by asking each person directly for one thought, even a small one. Within weeks, "
    "the team was raising ideas on its own without being asked.",
]

SENTENCE_BUILD_WORDSETS = [
    ("deadline, client, deliver, priority",
     "We reorganised our priorities to deliver the client's work before the deadline."),
    ("feedback, improve, process, team",
     "The team used customer feedback to improve their onboarding process."),
    ("budget, approve, quarter, project",
     "Leadership approved the extra budget for the project this quarter."),
    ("remote, collaborate, tool, schedule",
     "Remote teams collaborate more effectively when everyone shares the same tool and schedule."),
    ("outage, resolve, quickly, escalate",
     "The support team had to escalate the outage so it could be resolved quickly."),
    ("mentor, confidence, guidance, career",
     "A good mentor offers guidance that builds confidence early in someone's career."),
    ("release, testing, delay, quality",
     "The release was delayed slightly so the testing team could protect quality."),
    ("audit, compliance, document, review",
     "Every document must pass a compliance review before the audit begins."),
]


async def _top_up(TaskItem, company: str, task_type: str, current: int, target: int,
                   pool: list, next_index: dict) -> int:
    added = 0
    while current + added < target:
        idx = next_index[task_type] % len(pool)
        next_index[task_type] += 1
        entry = pool[idx]
        if task_type == "sentence_build":
            words, reference = entry
            prompt_text = f"Build a sentence using these words: {words}."
        elif task_type == "story_retell":
            reference = entry
            prompt_text = f"Retell this story in your own words: {entry}"
        else:
            reference = ""
            prompt_text = entry
        await TaskItem(
            task_type=task_type,
            prompt_text=prompt_text,
            reference_text=reference,
            difficulty=0.4,
            prompt_accent="indian",
            word_count=len(reference.split()) if reference else 0,
            company=company,
            source="authored",
            status="published",
        ).insert()
        added += 1
    return added


async def main() -> None:
    from app.db import init_mongo
    from app.models.tenant import TaskItem

    await init_mongo()

    pools = {
        "read_aloud": READ_ALOUD_SENTENCES,
        "repeat_sentence": REPEAT_SENTENCES,
        "short_answer": SHORT_ANSWER_QUESTIONS,
        "open_response": OPEN_RESPONSE_QUESTIONS,
        "story_retell": STORY_RETELL_STORIES,
        "sentence_build": SENTENCE_BUILD_WORDSETS,
    }

    total_added = 0
    next_index = {t: 0 for t in TARGET}
    for company in COMPANIES:
        added_here = {}
        for task_type, target in TARGET.items():
            current = await TaskItem.find(
                TaskItem.company == company, TaskItem.task_type == task_type
            ).count()
            added = await _top_up(TaskItem, company, task_type, current, target,
                                   pools[task_type], next_index)
            if added:
                added_here[task_type] = added
                total_added += added
        print(f"{company}: {added_here or 'already at target'}")

    print(f"done, {total_added} items added")


if __name__ == "__main__":
    asyncio.run(main())
