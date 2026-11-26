import { useCallback, useEffect, useRef, useState } from "react";

import { decode, MAX_SECONDS, toVoiceWav } from "./wav";

export type RecorderState =
  "idle" | "asking" | "recording" | "processing" | "ready" | "error";

export interface Recording {
  wav: Blob;
  seconds: number;
}

function explain(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError")
    return "Microphone access was blocked. Allow it from the address bar, then try again.";
  if (name === "NotFoundError")
    return "No microphone was found. Plug one in, or upload a file.";
  return "Recording did not work in this browser. Try again, or upload a file instead.";
}

/**
 * Record from the microphone. While recording it exposes an analyser for a live waveform; when
 * stopped, the recording is converted to the voice format (24 kHz mono WAV). Stops by itself at
 * the longest allowed length.
 */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null);
  const parts = useRef<{
    recorder: MediaRecorder;
    stream: MediaStream;
    context: AudioContext;
    timer: number;
  } | null>(null);

  const release = useCallback(() => {
    const current = parts.current;
    if (!current) return;
    window.clearInterval(current.timer);
    current.stream.getTracks().forEach((track) => track.stop());
    void current.context.close();
    parts.current = null;
    setAnalyser(null);
  }, []);

  useEffect(() => release, [release]); // never leave the microphone on

  const stop = useCallback(() => {
    if (parts.current?.recorder.state === "recording")
      parts.current.recorder.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setRecording(null);
    if (
      typeof MediaRecorder === "undefined" ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      setState("error");
      setError("This browser cannot record. Upload a file instead.");
      return;
    }
    setState("asking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });
      const context = new AudioContext();
      const meter = context.createAnalyser();
      meter.fftSize = 1024;
      context.createMediaStreamSource(stream).connect(meter);
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) =>
        event.data.size && chunks.push(event.data);
      recorder.onstop = async () => {
        release();
        setState("processing");
        try {
          const converted = await toVoiceWav(
            await decode(new Blob(chunks, { type: recorder.mimeType })),
          );
          setRecording({ wav: converted.wav, seconds: converted.seconds });
          setState("ready");
        } catch (caught) {
          setError(explain(caught));
          setState("error");
        }
      };
      const began = performance.now();
      const timer = window.setInterval(() => {
        const elapsed = (performance.now() - began) / 1000;
        setSeconds(elapsed);
        if (elapsed >= MAX_SECONDS) recorder.stop();
      }, 200);
      parts.current = { recorder, stream, context, timer };
      setAnalyser(meter);
      setSeconds(0);
      recorder.start();
      setState("recording");
    } catch (caught) {
      release();
      setError(explain(caught));
      setState("error");
    }
  }, [release]);

  const reset = useCallback(() => {
    release();
    setRecording(null);
    setSeconds(0);
    setError(null);
    setState("idle");
  }, [release]);

  return { state, seconds, analyser, recording, error, start, stop, reset };
}
