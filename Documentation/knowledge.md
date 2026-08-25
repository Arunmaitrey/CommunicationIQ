Here's the full model inventory, layered by what each one contributes to "intelligent." The honest framing first: *no single model makes this smart — the intelligence is a stack of ~12 models, half of which aren't deep learning at all.* Buy/build and wave timing marked for each.

## Layer 1 — Hearing (speech → signal)

| # | Capability | Model class | Buy vs Build | Wave |
|---|---|---|---|---|
| 1 | *ASR (transcription)* | Whisper / WhisperX-class, later fine-tuned on Indian-English audio (Telugu/Hindi/Tamil L1) | Vendor/off-shelf first → fine-tune W3 | W1→W3 |
| 2 | *Voice activity detection* | Silero-VAD class | Off-shelf, tiny | W1 |
| 3 | *Forced alignment* | WhisperX / MFA (word & phoneme timestamps) | Off-shelf | W1 |

VAD + alignment look boring but power your best features: response latency, pause structure, speech rate — the things that actually fail students.

## Layer 2 — Judging speech quality (the assessment core)

| # | Capability | Model class | Buy vs Build | Wave |
|---|---|---|---|---|
| 4 | *Pronunciation scoring* | GOP (Goodness of Pronunciation) on wav2vec2/HuBERT embeddings, fine-tuned SpeechOcean762-style | Vendor API W1 → in-house W3 (shadow mode, per SRS E17) | W1→W3 |
| 5 | *Fluency & prosody scoring* | Feature-based regressor (gradient boosting on pause/rate/pitch features) — not a neural end-to-end model | Build (cheap, interpretable) | W1–2 |
| 6 | *Disfluency/filler detection* | Token classification on transcript + acoustic cues ("um," repetitions, self-corrections) | Build (small model) | W1–2 |
| 7 | *Intelligibility model* ⭐ | Regressor predicting human intelligibility ratings, trained per L1 group on your own labelled panel data | *Build — this is your moat model.* Nobody has Indian-L1 intelligibility labels at your scale | W2–3 |
| 8 | *L1/accent identification* | Small classifier on speech embeddings (ECAPA-class) | Build later — routes L1-specific feedback and powers L1-difficulty stats | W3 |

\#7 is the differentiator: everyone scores "accuracy vs native reference"; you score "would a hiring panel understand this" — which requires collecting human intelligibility ratings from Indian raters on your own audio. Budget for a labelling panel; it's the dataset competitors can't shortcut.

## Layer 3 — Judging language content

| # | Capability | Model class | Buy vs Build | Wave |
|---|---|---|---|---|
| 9 | *Grammar error detection* | GEC model (T5/LLM-based) on transcripts, error-typed | Off-shelf + tune | W1–2 |
| 10 | *Content relevance & retell recall* | Sentence embeddings for key-point coverage + rubric-constrained LLM grading as one signal (never sole judge, per SRS) | Build thin layer on APIs | W1–2 |

## Layer 4 — The intelligence nobody sees (this is where "really intelligent" lives)

| # | Capability | Model class | Buy vs Build | Wave |
|---|---|---|---|---|
| 11 | *Item calibration* | IRT (2-parameter logistic): difficulty + discrimination per item, L1-split | Build — classical psychometrics, your speech-ML consultant + a psychometrics reference implement this | W2 (E14) |
| 12 | *Skill mastery tracking* | Bayesian Knowledge Tracing first; Deep Knowledge Tracing only if data volume justifies | Build — drives the drill loop's "next weakness" | W2 |
| 13 | *Adaptive item selection* | IRT-information-based selection (computer-adaptive testing), later contextual bandits | Build on top of #11 | W2–3 |
| 14 | *Crosswalk readiness prediction* | Gradient-boosted trees / regularized logistic on the feature record → outcome band, with isotonic/Platt calibration for honest confidence intervals | Build — gated per E15 (≥300 paired records, ≥75% band accuracy) | W2–3 |

*This layer is the answer to your question.* Layers 1–3 exist in some form at every competitor. #11–14 — calibrated items, mastery tracking, adaptive selection, outcome…


The Versant English Test, SVAR (AMCAT/SHL), and Mercer Mettl SpeechX are automated AI-driven spoken-English and listening assessments. They take roughly 15 to 45 minutes and evaluate pronunciation, fluency, grammar, and vocabulary using identical question types. [1, 2, 3, 4, 5]  
Versant (Pearson) – 6 Parts (~20 Mins, 63 Questions) 

* Part A: Reading: Read printed sentences aloud as prompted. 
* Part B: Repeat: Hear a sentence and repeat it back word-for-word. 
* Part C: Short Questions: Answer a direct general-knowledge question using one or a few words (e.g., "What opens a lock?" → "Key"). 
* Part D: Sentence Builds: Rearrange jumbled word groups into a proper sentence. 
* Part E: Story Retelling: Listen to a short narrative and retell it in your own words. 
* Part F: Open Questions: Speak continuously for 40 seconds sharing your opinion on a familiar topic. [6, 7, 8, 9]  

SVAR (SHL/Aspiring Minds) – 6 Sections (16–20 Mins, ~45 Questions) 

* Section 1 (Reading): Read text snippets shown on screen. 
* Section 2 (Listen & Repeat): Listen to audio sentences (up to 40 words) and repeat them accurately. 
* Section 3 (Listening Deductions): Comprehend short audio prompts or dialogues. 
* Section 4 & 5 (Grammar & Error ID): Spot structural errors or choose correct phrasing from audio cues. 
* Section 6 (Free Speech / Extempore): Speak for 30–45 seconds on an assigned prompt. [10, 11, 12]  

SpeechX (Mercer Mettl) – 4 Sections (~45 Mins) 

* Section A (Read Aloud): Read displayed sentences and short passages clearly. 
* Section B (Open Speech): Speak on a general topic or scenario for up to 60 seconds. 
* Section C (Grammar & Vocabulary): Multiple-choice or fill-in-the-blank items testing tenses, prepositions, and word choice. 
* Section D (Audio Comprehension): Listen to longer audio clips and answer multi-choice comprehension questions. [4, 5, 13]  

Where to Find Simulations and Practice 

* Interactive AI Simulators: Try practice mock interfaces with instant scoring on platforms like Versant Pro which mimic automated audio grading. 
* Video Walkthroughs: Search YouTube for mock tests containing real audio pacing like the Versant Complete Guide Mock Test or SVAR Practice Modules to practice live with a stopwatch. [7, 11, 15]  

Would you like me to share a 7-day daily practice routine or a structured template for the open-speech/extempore rounds to help you score higher? 
AI responses may include mistakes.

[1] https://faceprep.in/article/communication-assessments-compared-svar-versant-and-company-rounds-2026/
[2] https://faceprep.in/article/svar-test-complete-guide-2026/
[3] https://www.talkdrill.com/blog/svar-test-questions-answers/
[4] https://www.scribd.com/document/690006439/SpeechX-Preparation-Manual
[5] https://www.geeksforgeeks.org/interview-experiences/cognizant-hexaware-interview-experience-speechx-test/
[6] https://www.youtube.com/watch?v=hoykMKMnJL8
[7] https://www.youtube.com/watch?v=ekfq6W3cD6E
[8] https://www.youtube.com/watch?v=VxOLWNzs65U
[9] https://www.youtube.com/watch?v=_ijwutrY7_I
[10] https://faceprep.in/article/svar-test-practice-question-types-with-sample-answers-2026/
[11] https://www.youtube.com/watch?v=GHmDoYjgBiA
[12] https://faceprep.in/article/amcat-svar-test-pattern-questions-and-important-tips-to-answer/
[13] https://www.youtube.com/watch?v=ZfsqzN_Fxso
[14] https://versantpro.com/
[15] https://www.youtube.com/watch?v=TslQDeJLgYo


https://faceprep.in/article/communication-assessments-compared-svar-versant-and-company-rounds-2026/