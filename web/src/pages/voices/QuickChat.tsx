import { useEffect, useMemo, useState } from "react";

import { Button } from "../../components/Button";

/** Casual questions to answer out loud. Talking, not reading, gives a voice its natural rhythm,
 * and the cloned voice copies the style of the recording it learns from. */
export const CHAT_QUESTIONS = [
  "What's a place you love, and why?",
  "What's the best thing you've eaten lately?",
  "How has your day been so far?",
  "What's a show or film you'd recommend, and why?",
  "What would a perfect day off look like?",
  "What's something you'd like to learn, and why?",
  "What's the last thing that made you laugh?",
  "What's a small thing that makes your week better?",
  "Where would you go on a trip next, and what would you do?",
  "What's something you changed your mind about?",
] as const;

export const CHAT_LENGTH = 3;

/** A different set of questions for each take, so nobody reads the same lines twice. */
export function pickQuestions(random: () => number = Math.random): string[] {
  const pool: string[] = [...CHAT_QUESTIONS];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, CHAT_LENGTH);
}

/** The record step's prompt: a few questions, one after another, while one recording runs. */
export function QuickChat({
  recording,
  round,
}: {
  recording: boolean;
  round: number;
}) {
  const questions = useMemo(() => pickQuestions(), [round]);
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [round]);
  const last = index === questions.length - 1;

  return (
    <div className="quick-chat">
      <p className="consent-label">Have a quick chat</p>
      <p className="muted">
        Answer out loud, like talking to a friend. No need to be perfect.
      </p>
      <div className="quick-chat-head">
        <span className="quick-chat-dots" aria-hidden="true">
          {questions.map((_, n) => (
            <span key={n} className={n <= index ? "on" : undefined} />
          ))}
        </span>
        <span className="muted">
          Question {index + 1} of {questions.length}
        </span>
      </div>
      <p className="quick-chat-question" aria-live="polite">
        {questions[index]}
      </p>
      {!recording ? (
        <p className="muted">
          Start recording, then answer each question in a few sentences. Start
          talking right away: the first answer shapes the voice most.
        </p>
      ) : last ? (
        <p className="muted">Last one. Stop when you&apos;re done.</p>
      ) : (
        <Button variant="secondary" onClick={() => setIndex((n) => n + 1)}>
          Next question →
        </Button>
      )}
    </div>
  );
}
