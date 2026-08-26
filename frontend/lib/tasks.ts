import type { Role } from "@/lib/api";

/**
 *  What each task type is called, in one place.
 *
 *  There were three of these -- in the runner, the result page and the
 *  simulation browser -- and all three were different. The runner's had six
 *  of the sixteen task types the server can serve, because it was written
 *  when speaking was the only thing here and the ten added in Phase 4 were
 *  never added to it.
 *
 *  A missing entry is not a missing label. Each of these maps ends in
 *  `?? key`, so an unlisted type renders as its own enum: a candidate part
 *  way through a hiring assessment was shown the words
 *  `reading_comprehension` where the name of the section should be.
 *
 *  One map, and a test that walks the server's own list of task types and
 *  fails on anything absent from it -- because keeping three copies in step
 *  by hand is what produced this.
 */
export const TASK_LABEL: Record<string, string> = {
  // Spoken.
  read_aloud: "Read Aloud",
  repeat_sentence: "Repeat Sentence",
  spoken_completion: "Fill in the Blanks (spoken)",
  spoken_correction: "Correct the Sentence (spoken)",
  short_answer: "Short Answer",
  sentence_build: "Sentence Build",
  story_retell: "Story Retell",
  open_response: "Open Response",
  conversation_question: "Conversation Question",
  passage_question: "Passage Question",
  // Answered by choosing.
  listening_comprehension: "Listening Comprehension",
  reading_comprehension: "Reading Comprehension",
  response_selection: "Choose the Reply",
  vocabulary_in_context: "Word in Context",
  // Answered by typing.
  dictation: "Dictation",
  sentence_completion: "Sentence Completion",
  voice_change: "Change the Voice",
  email_writing: "Email Writing",
  passage_reconstruction: "Passage Reconstruction",
  typing: "Timed Typing",
  // Older practice kinds, which are not assessment sections but do appear in
  // the simulation browser.
  mcq: "Grammar / Vocabulary",
  audio_comprehension: "Audio Comprehension",
};

export const taskLabel = (key: string): string => TASK_LABEL[key] ?? key;

/**
 *  What a candidate is told to expect, before an item they cannot go back to.
 *
 *  The runner said "You will have N seconds to read, then N seconds to speak"
 *  for every task type. On a reading-comprehension item -- untimed, and
 *  answered by clicking an option -- that came out as "You will have 0
 *  seconds to read, then 0 seconds to speak", which is wrong twice over and
 *  reads as a fault in the test.
 *
 *  `responseMode` is `speak`, `select` or `write`, and it is the only thing
 *  that decides whether speaking is involved at all.
 */
export function whatToExpect(
  responseMode: string, prepSeconds: number, responseSeconds: number,
  promptPlays: number,
): string {
  const heard = promptPlays > 0;
  const timed = responseSeconds > 0;

  if (responseMode === "select" || responseMode === "write") {
    const doing = responseMode === "select" ? "choose your answer" : "type your answer";
    if (heard) {
      return timed
        ? `You will hear each item once, then have ${responseSeconds} seconds to ${doing}.`
        : `You will hear each item once, then ${doing}. There is no timer on each item.`;
    }
    return timed
      ? `You will have ${responseSeconds} seconds to ${doing} on each item.`
      : `Read each item and ${doing}. There is no timer on each item.`;
  }

  // A spoken section with no answer clock should not exist -- the builder
  // floors it at five seconds -- but the sentence must not promise zero if
  // one ever does. "0 seconds to speak" reads as a broken test, not as a
  // generous one.
  if (heard) {
    return timed
      ? `You will hear each item once. You then have ${responseSeconds} `
        + `seconds to answer.`
      : "You will hear each item once, then answer out loud.";
  }
  if (!timed) {
    return prepSeconds > 0
      ? `You will have ${prepSeconds} seconds to read, then answer out loud.`
      : "Read each item, then answer out loud.";
  }
  if (prepSeconds > 0) {
    return `You will have ${prepSeconds} seconds to read, then `
      + `${responseSeconds} seconds to speak.`;
  }
  return `You will have ${responseSeconds} seconds to speak.`;
}

// Re-exported so a caller needing both does not import from two places.
/** What to do now, on the answer screen of a heard prompt.
 *
 *  The unskinned runner said "Say it back now" for every heard item --
 *  right for Repeat Sentence, wrong for a question, a situation, a gapped
 *  or flawed sentence, a story or a topic (portfolio audit, shared P2). */
export function answerLine(taskType: string): string {
  switch (taskType) {
    case "repeat_sentence": return "Repeat the sentence you heard.";
    case "short_answer": return "Answer the question.";
    case "conversation_question": return "Respond to what you heard.";
    case "passage_question": return "Answer the question about what you heard.";
    case "spoken_completion": return "Say the complete sentence with the missing word.";
    case "spoken_correction": return "Say the corrected sentence.";
    case "story_retell": return "Retell the story in your own words.";
    case "open_response": return "Speak about the topic.";
    case "sentence_build": return "Rearrange the words into a correct sentence and say it.";
    case "read_aloud": return "Read it out loud.";
    case "typing": return "Type the passage exactly as shown. Speed and accuracy both count.";
    default: return "Give your answer now.";
  }
}

export type { Role };
