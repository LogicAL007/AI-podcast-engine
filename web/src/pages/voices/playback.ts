import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE } from "../../api/client";
import { decode } from "../../audio/wav";

const FRAMES_PER_SECOND = 50;

/** Start playback; a browser that refuses (autoplay rules) or has no media support just stays
 * paused. */
function start(element: HTMLAudioElement, onRefused: () => void): void {
  try {
    const result = element.play() as Promise<void> | undefined;
    if (result && typeof result.catch === "function") result.catch(onRefused);
  } catch {
    onRefused();
  }
}

/** The clip's loudness, 50 times a second, scaled 0 to 1: what the octagon follows. Worked out
 * from the file itself, so playback is never routed through Web Audio (which would need a user
 * gesture to start, and would go silent if the browser blocked it). */
export function envelopeOf(samples: Float32Array, rate: number): Float32Array {
  const frame = Math.max(1, Math.round(rate / FRAMES_PER_SECOND));
  const out = new Float32Array(Math.ceil(samples.length / frame));
  let loudest = 1e-6;
  for (let n = 0; n < out.length; n++) {
    let sum = 0;
    const end = Math.min(samples.length, (n + 1) * frame);
    for (let i = n * frame; i < end; i++) sum += samples[i] * samples[i];
    out[n] = Math.sqrt(sum / Math.max(1, end - n * frame));
    loudest = Math.max(loudest, out[n]);
  }
  for (let n = 0; n < out.length; n++) out[n] = Math.min(1, out[n] / loudest);
  return out;
}

/** Plays one clip (an API path) and reports what the octagon needs. With `autoPlay`, it starts
 * as soon as a new clip is ready (the person just asked for it). */
export function useClipPlayer(src: string | null, autoPlay = false) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const envelope = useRef<Float32Array | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    envelope.current = null;
    setPlaying(false);
    setTime(0);
    setDuration(0);
    if (!src || typeof Audio === "undefined") return;
    const url = `${API_BASE}${src}`;
    const element = new Audio(url);
    element.preload = "auto";
    audio.current = element;
    const onPlay = () => setPlaying(true);
    const onStop = () => setPlaying(false);
    const onTime = () => setTime(element.currentTime);
    const onMeta = () =>
      setDuration(Number.isFinite(element.duration) ? element.duration : 0);
    element.addEventListener("play", onPlay);
    element.addEventListener("pause", onStop);
    element.addEventListener("ended", onStop);
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("loadedmetadata", onMeta);
    let cancelled = false;
    (async () => {
      try {
        const decoded = await decode(await (await fetch(url)).blob());
        if (!cancelled)
          envelope.current = envelopeOf(
            decoded.getChannelData(0),
            decoded.sampleRate,
          );
      } catch {
        envelope.current = null; // the octagon falls back to a gentle pulse
      }
    })();
    if (autoPlay) start(element, () => setPlaying(false));
    return () => {
      cancelled = true;
      element.pause();
      element.removeEventListener("play", onPlay);
      element.removeEventListener("pause", onStop);
      element.removeEventListener("ended", onStop);
      element.removeEventListener("timeupdate", onTime);
      element.removeEventListener("loadedmetadata", onMeta);
      audio.current = null;
    };
  }, [src, autoPlay]);

  const toggle = useCallback(() => {
    const element = audio.current;
    if (!element) return;
    if (element.paused) start(element, () => setPlaying(false));
    else element.pause();
  }, []);

  const level = useCallback(() => {
    const element = audio.current;
    if (!element || element.paused) return 0;
    const shape = envelope.current;
    if (!shape)
      return 0.45 + 0.35 * Math.abs(Math.sin(element.currentTime * 6));
    return (
      shape[
        Math.min(
          shape.length - 1,
          Math.floor(element.currentTime * FRAMES_PER_SECOND),
        )
      ] ?? 0
    );
  }, []);

  return { playing, time, duration, toggle, level };
}

/** One player for a list of tracks: starting one stops the other. */
export function useTrackPlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(
    () => () => {
      audio.current?.pause();
    },
    [],
  );

  const toggle = useCallback(
    (id: string, src: string) => {
      if (typeof Audio === "undefined") return;
      if (playing === id) {
        audio.current?.pause();
        setPlaying(null);
        return;
      }
      audio.current?.pause();
      const element = new Audio(`${API_BASE}${src}`);
      element.addEventListener("ended", () => setPlaying(null));
      audio.current = element;
      setPlaying(id);
      start(element, () => setPlaying(null));
    },
    [playing],
  );

  return { playing, toggle };
}

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
