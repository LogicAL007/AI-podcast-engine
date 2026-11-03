import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useAskAssistant } from "../api/queries";
import type { AssistantAnswer } from "../api/types";
import type { BotAction, PageAssist } from "./assistant";

interface Message {
  from: "me" | "bot";
  text: string;
  actions?: BotAction[];
}

/**
 * Ask the bot about the page you are on. Answers arrive in a log that screen readers read out,
 * each with buttons for the next steps it suggests (they run only when pressed).
 */
export function ChatPanel({
  assist,
  name,
  resolve,
  onAction,
  onAnswer,
  onThinking,
}: {
  assist: PageAssist;
  name: string;
  resolve: (id: string) => BotAction | undefined;
  onAction: (action: BotAction) => void;
  onAnswer: (text: string) => void;
  onThinking: (thinking: boolean) => void;
}) {
  const ask = useAskAssistant();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [left, setLeft] = useState<number | null>(null);
  const inputId = useId();
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);
  useEffect(() => {
    log.current?.scrollTo?.({ top: log.current.scrollHeight });
  }, [messages, ask.isPending]);
  useEffect(() => onThinking(ask.isPending), [ask.isPending, onThinking]);

  function send(question: string) {
    const text = question.trim();
    if (!text || ask.isPending) return;
    setMessages((m) => [...m, { from: "me", text }]);
    setDraft("");
    ask.mutate(
      {
        question: text,
        page: assist.page,
        episode_id: assist.episodeId ?? null,
        show_id: assist.showId ?? null,
      },
      {
        onSuccess: (answer: AssistantAnswer) => {
          const actions = answer.actions
            .map((id) => resolve(id))
            .filter((a): a is BotAction => a !== undefined);
          setMessages((m) => [
            ...m,
            { from: "bot", text: answer.answer, actions },
          ]);
          setLeft(answer.remaining);
          onAnswer(answer.answer);
        },
        onError: (error) => {
          const text =
            error instanceof ApiError && error.status === 429
              ? "That's all my questions for this hour. Ask me again a little later!"
              : "Sorry, I couldn't answer just now. Try again in a moment.";
          setMessages((m) => [...m, { from: "bot", text }]);
          onAnswer(text);
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(draft);
  }

  return (
    <div className="chat">
      <div
        ref={log}
        className="chat-log"
        role="log"
        aria-live="polite"
        aria-label={`Chat with ${name}`}
      >
        {messages.length === 0 ? (
          <p className="chat-empty muted">Ask me anything about this page.</p>
        ) : null}
        {messages.map((message, index) => (
          <div key={index} className={`chat-message chat-${message.from}`}>
            <span className="sr-only">
              {message.from === "me" ? "You:" : `${name}:`}{" "}
            </span>
            <p>{message.text}</p>
            {message.actions?.length ? (
              <div className="chat-actions">
                {message.actions.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    className="choice-pill"
                    onClick={() => onAction(action)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {ask.isPending ? (
          <div
            className="chat-message chat-bot chat-thinking"
            aria-label={`${name} is thinking`}
          >
            <span className="progress-dots" aria-hidden="true">
              <span>.</span>
              <span>.</span>
              <span>.</span>
            </span>
          </div>
        ) : null}
      </div>
      {messages.length === 0 && assist.questions?.length ? (
        <div className="chat-suggestions" aria-label="Suggested questions">
          {assist.questions.slice(0, 3).map((question) => (
            <button
              key={question}
              type="button"
              className="choice-pill"
              onClick={() => send(question)}
            >
              {question}
            </button>
          ))}
        </div>
      ) : null}
      <form className="chat-form" onSubmit={submit}>
        <label htmlFor={inputId} className="sr-only">
          Ask {name}
        </label>
        <input
          ref={input}
          id={inputId}
          className="input"
          value={draft}
          maxLength={500}
          placeholder={`Ask ${name}…`}
          autoComplete="off"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!draft.trim() || ask.isPending}
        >
          Ask
        </button>
      </form>
      <p className="chat-note muted">
        Answers can use your Podcast Engine quota
        {left !== null
          ? ` · ${left} question${left === 1 ? "" : "s"} left this hour`
          : ""}
        .
      </p>
    </div>
  );
}
