"""Active/passive voice change: choose the correct rewrite.

Original content. A sentence is given in one voice and the candidate chooses
the correct rewrite in the other. Every wrong option is grammatically shaped
like a real answer — a wrong tense, a dropped agent, a mangled word order —
so it cannot be eliminated on sight; the item measures whether the candidate
controls the transformation, not whether they can spot nonsense.

Workplace and everyday material, matching the other banks.

(prompt shown to the candidate, options, correct index, why)
"""
from __future__ import annotations

ITEMS: list[tuple[str, list[str], int, str]] = [
    ("Change to passive voice: \"The manager approved the proposal.\"",
     ["The proposal was approved by the manager.",
      "The proposal is approved by the manager.",
      "The proposal has approving by the manager.",
      "The manager was approved the proposal."],
     0, "Past simple active -> was/were + past participle."),
    ("Change to passive voice: \"The team has completed the project.\"",
     ["The project has been completed by the team.",
      "The project was completed by the team.",
      "The project has completed by the team.",
      "The project is being completed by the team."],
     0, "Present perfect passive -> has been + past participle."),
    ("Change to passive voice: \"Someone has stolen my wallet.\"",
     ["My wallet has been stolen.",
      "My wallet was stolen by someone.",
      "My wallet is stolen.",
      "My wallet has stolen."],
     0, "Present perfect; the agent 'someone' is dropped."),
    ("Change to passive voice: \"The company will launch the product next month.\"",
     ["The product will be launched by the company next month.",
      "The product will launched by the company next month.",
      "The product is launched by the company next month.",
      "The product will been launched next month."],
     0, "Future simple passive -> will be + past participle."),
    ("Change to passive voice: \"They are building a new office.\"",
     ["A new office is being built.",
      "A new office is built.",
      "A new office was being built.",
      "A new office has been building."],
     0, "Present continuous passive -> is/are being + past participle."),
    ("Change to active voice: \"The report was written by Priya.\"",
     ["Priya wrote the report.",
      "Priya was written the report.",
      "Priya has wrote the report.",
      "Priya writes the report."],
     0, "Past passive -> past simple active."),
    ("Change to active voice: \"The decision has been made by the committee.\"",
     ["The committee has made the decision.",
      "The committee made the decision.",
      "The committee has make the decision.",
      "The committee is making the decision."],
     0, "Present perfect passive -> present perfect active."),
    ("Change to passive voice: \"The teacher explains the lesson clearly.\"",
     ["The lesson is explained clearly by the teacher.",
      "The lesson was explained clearly by the teacher.",
      "The lesson explains clearly by the teacher.",
      "The lesson is explaining clearly."],
     0, "Present simple passive -> is/are + past participle."),
    ("Change to passive voice: \"Workers repaired the road yesterday.\"",
     ["The road was repaired by workers yesterday.",
      "The road is repaired by workers yesterday.",
      "The road were repaired yesterday.",
      "The road repaired by workers yesterday."],
     0, "Past simple passive; keep the time marker."),
    ("Change to active voice: \"The contract will be signed by the client tomorrow.\"",
     ["The client will sign the contract tomorrow.",
      "The client signs the contract tomorrow.",
      "The client will signed the contract tomorrow.",
      "The client is signing the contract tomorrow."],
     0, "Future passive -> future simple active."),
]
