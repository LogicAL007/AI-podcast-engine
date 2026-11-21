import { useCallback, useEffect, useRef, useState } from "react";

// Talking to the companion: the browser's own speech recognition (the Web Speech API), where it
// has one. Chrome sends the audio to its speech service; Safari recognises on the device. Where
// there is none, the microphone button is simply not offered.

interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult:
    | ((event: {
        results: ArrayLike<
          ArrayLike<{ transcript: string }> & { isFinal: boolean }
        >;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
}

type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function canListen(): boolean {
  return recognitionClass() !== null;
}

/** Listen for one question. `heard` is what has been recognised so far; `onDone` gets the whole
 * question when the person stops talking (nothing if they said nothing). */
export function useSpeechInput(onDone: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const final = useRef("");
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => () => recognition.current?.abort(), []);

  const start = useCallback(() => {
    const Recognition = recognitionClass();
    if (!Recognition) return;
    recognition.current?.abort();
    const r = new Recognition();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;
    final.current = "";
    setHeard("");
    setProblem(null);
    r.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i++)
        text += event.results[i][0].transcript;
      setHeard(text);
      final.current = text;
    };
    r.onerror = (event) => {
      setProblem(
        event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Allow the microphone to talk to me."
          : event.error === "no-speech"
            ? "I didn't hear anything."
            : null,
      );
    };
    r.onend = () => {
      setListening(false);
      const text = final.current.trim();
      if (text) done.current(text);
    };
    recognition.current = r;
    setListening(true);
    try {
      r.start();
    } catch {
      setListening(false);
    }
  }, []);

  const stop = useCallback(() => recognition.current?.stop(), []);
  const cancel = useCallback(() => {
    final.current = "";
    recognition.current?.abort();
    setListening(false);
  }, []);

  return {
    supported: canListen(),
    listening,
    heard,
    problem,
    start,
    stop,
    cancel,
  };
}
