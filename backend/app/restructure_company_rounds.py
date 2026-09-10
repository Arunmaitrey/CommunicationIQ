"""Bring every company round to a consistent 10/10/10/10 four-skill shape.

Two groups existed before this ran:
  - Accenture, TCS, Cognizant, Wipro, Infosys, HCL, Tech Mahindra, Capgemini:
    six speaking sub-sections (30 items), no reading/listening/writing at all.
  - ADP, Deloitte, Virtusa, LTIMindtree, IBM: reading/listening/writing
    (30 items), no speaking at all.

Neither group's sections had a company filter, so what little matched was
drawn from the shared global bank rather than that company's own tagged
content -- confirmed: real, substantial company-tagged reading (17-155
items) and writing (17-50) sits under every one of the 13, and speaking
(41 items) and listening (87-100) sits under the "wrong" group of 5/8
respectively, all unused until now.

This adds the missing sections (speaking for group B, reading/listening/
writing for group A) drawing on each company's own real content, and
applies the company filter to every section so nothing generic leaks in.
Speaking stays at its existing 6-part structure for group A (Read Aloud,
Repeat Sentence, Short Answer, Open Response, Story Retell, Sentence
Build) rather than one flat section -- that per-task breakdown is the
realistic shape a communication round actually has, and the per-company
content shortage within it is a separate, tracked gap (content to author,
not a structural one this script can fix).

    python -m app.restructure_company_rounds
"""
from __future__ import annotations

import asyncio

# name -> (profile name, group)
GROUP_A = ["Accenture", "TCS", "Cognizant", "Wipro", "Infosys",
          "HCL", "Tech Mahindra", "Capgemini"]
GROUP_B = ["ADP", "Deloitte", "Virtusa", "LTIMindtree", "IBM"]

PROFILE_NAME = {
    "Accenture": "Accenture-style Communication Round",
    "TCS": "TCS-family Communication Practice",
    "Cognizant": "Cognizant Communication Assessment",
    "Wipro": "Wipro Communication Round",
    "Infosys": "Infosys Communication Practice",
    "HCL": "HCL Communication Assessment",
    "Tech Mahindra": "Tech Mahindra Communication Round",
    "Capgemini": "Capgemini Communication Assessment",
    "ADP": "ADP Communication Assessment",
    "Deloitte": "Deloitte Communication Assessment",
    "Virtusa": "Virtusa Communication Assessment",
    "LTIMindtree": "LTIMindtree Communication Assessment",
    "IBM": "IBM Communication Assessment",
}

SPEAKING_SECTIONS = [
    ("Read Aloud", "read_aloud", 2),
    ("Repeat Sentence", "repeat_sentence", 2),
    ("Short Answer", "short_answer", 2),
    ("Open Response", "open_response", 2),
    ("Story Retell", "story_retell", 1),
    ("Sentence Build", "sentence_build", 1),
]


async def main() -> None:
    from app.db import init_mongo
    from app.models.tenant import ProfileSection, SimulationProfile

    await init_mongo()

    for company in GROUP_A + GROUP_B:
        profile = await SimulationProfile.find_one(
            SimulationProfile.name == PROFILE_NAME[company])
        if profile is None:
            print(f"{company}: profile not found, skipping")
            continue
        sections = await ProfileSection.find(
            ProfileSection.profile_id == profile.id).to_list()
        by_title = {s.title: s for s in sections}
        next_position = max((s.position for s in sections), default=0) + 1

        # Every existing section gets the company filter -- no exceptions.
        for s in sections:
            s.selection = {"company": [company]}
            await s.save()

        if company in GROUP_A:
            # Company-filter the six existing speaking sections down to a
            # realistic 10 total (2/2/2/2/1/1) instead of the current 30 --
            # the per-company pool for each is thin (0-2 items right now),
            # so 30 was never going to be honoured anyway.
            for title, task_type, count in SPEAKING_SECTIONS:
                s = by_title.get(title)
                if s is not None:
                    s.item_count = count
                    await s.save()
            to_add = [
                ("Reading", "reading_comprehension"),
                ("Listening", "audio_comprehension"),
                ("Writing", "writing_task"),
            ]
        else:
            to_add = [("Speaking", "open_response")]

        for title, task_type in to_add:
            if title in by_title:
                continue
            await ProfileSection(
                profile_id=profile.id, position=next_position,
                title=title, task_type=task_type, item_count=10,
                prep_seconds=0 if task_type != "open_response" else 20,
                response_seconds=180 if task_type in
                ("writing_task",) else (45 if task_type == "open_response" else 30),
                selection={"company": [company]},
            ).insert()
            next_position += 1
        print(f"{company}: done")


if __name__ == "__main__":
    asyncio.run(main())
