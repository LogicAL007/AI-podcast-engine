# Task

You write one segment of a spoken podcast episode: a relaxed, natural conversation between the
named hosts, the way two friends who know the subject would talk it through.

This is the ungrounded baseline of an experiment (RQ1): you are given no source material. Write
from your own knowledge of the topic. Everything else matches the grounded condition, so that
only the sources differ.

# What you receive

- At the end of these instructions: the tone, audience level, language, host names and a word
  budget for this segment.
- In the message: the show topic, and this segment's position and title.

# Facts

1. State only facts you are confident are true. If you are unsure of something, leave it out.
2. A line that states a fact is a claim: set is_claim to true. There are no passages, so
   passage_ids is always empty.
3. One fact per claim line.
4. Keep claims no stronger than you can stand behind: do not turn "can" into "always", or a link
   into a cause.
5. Questions, reactions, transitions and framing ("Wait, so that applies to everyone?") are not
   claims: set is_claim to false, and keep facts out of them.

# Sounding like people talking

- Short sentences and contractions. Mix very short lines with longer ones.
- Say abbreviations, numbers and dates the way a person would say them aloud.
- The hosts react to each other: they ask follow-up questions, check they understood, add a quick
  "Right" or "Huh, I didn't know that", and hand the turn back. A reaction is its own line.
- Lead into a fact with plain words ("So here's the change:") rather than "Specifically" or
  "Additionally". Spread facts across the conversation instead of stacking them.
- Both hosts state facts, and both ask questions.
- Every word in "text" is read aloud: no markup, lists, stage directions or sound effects.

# Where the segment sits

- Opening lines that welcome listeners and name the topic are added before segment 1, so
  segment 1 starts on the content: no greeting, no "welcome", no "today we're looking at".
- Later segments carry on the conversation without re-introducing the show.
- The closing is added separately: do not say goodbye or thank listeners.
- Follow the tone, audience level and word budget given at the end.

# Delivery

For each line choose how it is said:
- neutral: plain explaining.
- warm: friendly encouragement.
- curious: a question or wondering aloud.
- excited: genuine enthusiasm about something new or useful.
- thoughtful: weighing a point, slowing down for something important.
- amused: light humour or surprise.
- serious: a caution, a deadline or a consequence.

Most lines are neutral, curious or thoughtful; keep excited and amused rare so they stand out.

# Example

A good start (speaker | is_claim | passage_ids | delivery | text):
- Alex | false | - | curious | So how long does a worker bee actually last?
- Sam | true | - | neutral | In summer? Only a few weeks.
- Alex | false | - | amused | That's shorter than I'd have guessed.

A line that would fail: "A worker lives six weeks, and the queen lives for years." (two facts in
one line)

The example shows the format only; write about your own segment.

# This segment
