// The bot's voice: the browser's own speech synthesis (free, works offline on most devices). It
// speaks only when the person asks it to, and the same words are always on screen too.
import { useEffect, useState } from "react";

import type { Avatar } from "./avatar";

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** The voices this device offers, updated when the browser finishes loading them. */
export function useVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() =>
    canSpeak() ? window.speechSynthesis.getVoices() : [],
  );
  useEffect(() => {
    if (!canSpeak()) return;
    const update = () => setVoices(window.speechSynthesis.getVoices());
    update();
    window.speechSynthesis.addEventListener("voiceschanged", update);
    return () =>
      window.speechSynthesis.removeEventListener("voiceschanged", update);
  }, []);
  return voices;
}

/**
 * Say `text` in the bot's voice. `onMouth` gets how far its mouth should open (0..1) as each
 * word starts, and 0 when it is done, so the face can talk along. Returns a function that stops it.
 */
export function speak(
  text: string,
  voice: Avatar["voice"],
  onMouth: (open: number) => void = () => {},
): () => void {
  if (!canSpeak()) return () => {};
  const synth = window.speechSynthesis;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const chosen = synth.getVoices().find((v) => v.name === voice.name);
  if (chosen) utterance.voice = chosen;
  utterance.rate = voice.rate;
  utterance.pitch = voice.pitch;
  let close: number | undefined;
  utterance.onboundary = () => {
    onMouth(0.6 + Math.random() * 0.4);
    window.clearTimeout(close);
    close = window.setTimeout(() => onMouth(0.15), 140);
  };
  const done = () => {
    window.clearTimeout(close);
    onMouth(0);
  };
  utterance.onend = done;
  utterance.onerror = done;
  onMouth(0.4);
  synth.speak(utterance);
  return () => {
    synth.cancel();
    done();
  };
}
