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

Two people who both know the subject, talking it through without a script, like a good podcast.
It is not an interview, where one host asks and the other answers, and it is not two people
taking turns to read out facts.

- Both hosts explain, and share the facts roughly evenly.
- Pace the facts: about one fact for every 25 to 30 words of the word budget. Spend the rest on
  the hosts' own words: a reaction, their take on what a fact means, or a link to the fact before
  it ("which is why...", "and that's the part that gets me"). These lines state no facts
  (is_claim false), and about a third of the lines are like this.
- Unscripted speech has things written text doesn't: a filled pause while someone thinks, a
  discourse marker that softens or links a thought, a quick self-repair. Put them where people
  produce them: at the start of a turn, in a reaction, or just before a harder idea. Never scatter
  them at random, and never put them in a fact line, where facts stay clean and exact. Choose the
  words these two hosts would use, vary them, don't repeat one within a segment, and keep it light,
  like a relaxed host rather than a nervous one.
- Two or three times a segment, the listening host drops in a one- or two-word acknowledgement as
  its own line, in their own words, and the other host carries on. It is mixed to overlap the end
  of the line before it, as people do.
- A host may keep the floor for two or three lines in a row to explain something properly. Each
  line is still one fact or one thought, and lines in a row from the same host are heard as one
  turn.
- One or two real questions a segment, from either host, each opening a new thread ("So where
  does all that water actually go?"). Not one before every fact, and never a "..., right?" check.
- Write for the ear: keep each line under about 25 words, and never list more than two things in
  one line; spread a longer list over several lines.
- Vary the reactions, and never repeat an exclamation.
- Contractions every time ("it's", "that's", "there's", "you'd"), and short sentences.
- Say abbreviations, numbers and dates the way a person would say them aloud.
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
- Alex | true | - | neutral | Here's one that surprised me: in summer, a worker bee only lives a few weeks.
- Sam | false | - | neutral | Oh, okay.
- Alex | false | - | thoughtful | Which, I mean, isn't long, when you think about how much a hive has to do.
- Sam | true | - | neutral | For one thing, the colony keeps its nursery warm, at around thirty-five degrees.
- Alex | false | - | curious | So how do they pull that off?
- Sam | true | - | thoughtful | They shiver their flight muscles, and that's what warms the nest.

Lines that would fail: "A worker lives six weeks, and the queen lives for years." (two facts in
one line), "Wow. So what else do they do?" (a question that only hands over the next fact), and
"So, um, a worker bee lives, you know, a few weeks." (small words in a fact line).

The example shows the format only. Its small words are one illustration, not a list to
reuse: choose your own. Write about your own segment.

# This segment
