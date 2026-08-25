/**
 *  What each measured dimension is called on screen, in one place.
 *
 *  There were two of these -- the result page and the report components --
 *  and both were missing `completeness`, which was added to the engine in an
 *  earlier pass. Both maps end in "or the key itself", so the miss was not a
 *  blank: a candidate's report listed
 *
 *      Word accuracy   ...
 *      completeness    ...
 *      Hesitation      ...
 *
 *  with the raw column name sitting in the middle of two written ones.
 *
 *  The comment above the old map recorded the same bug happening once
 *  already, for `comprehension`, when the non-speaking modules landed. It
 *  said "Missing until now, so a listening section's score arrived on the
 *  report under its raw column name" -- and then it happened again with the
 *  very next dimension anybody added, because nothing checked.
 *
 *  `backend/tests/test_dimension_labels.py` now walks the engine's own
 *  dimensions and fails on any that is not named here.
 */
export const DIMENSION_LABEL: Record<string, string> = {
  // Scored from speech.
  fluency: "Fluency",
  latency: "Response speed",
  accuracy: "Word accuracy",
  disfluency: "Hesitation",
  pronunciation: "Pronunciation",
  grammar: "Grammar",
  content: "Content",
  completeness: "Completeness",
  // Produced by the modules answered by choosing or typing.
  comprehension: "Comprehension",
  vocabulary: "Vocabulary",
  appropriacy: "Choosing what to say",
};

export const dimensionLabel = (key: string): string =>
  DIMENSION_LABEL[key] ?? key;

/**
 *  One line saying what each dimension actually measures.
 *
 *  Lives beside the labels because the two go missing together: `completeness`
 *  had neither, so the report showed a score with no name and no explanation
 *  while every dimension around it had both.
 *
 *  `pronunciation` and `grammar` are deliberately absent -- both carry a
 *  longer caveat of their own on the report, and a short gloss above it would
 *  say the same thing worse.
 */
export const DIMENSION_MEANING: Record<string, string> = {
  fluency: "Your speaking rate, and how the pauses fell.",
  latency: "How long you took to start talking after the tone.",
  accuracy: "How much of each sentence came back correctly.",
  disfluency: "Fillers, repeated words and false starts.",
  completeness: "How much of the answer you were asked for actually arrived.",
  comprehension: "Whether you understood what you read or heard.",
  vocabulary: "The range of words you used, or the sense you picked.",
  appropriacy: "Whether your reply fitted what was said to you.",
  content: "How much of what the question asked for you actually covered.",
};
