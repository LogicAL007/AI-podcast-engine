import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import { API_BASE } from "../api/client";
import { decode, formatTime, peaks } from "../audio/wav";

const BAR_SPACE = 5; // px per bar, gap included

/**
 * An audio player drawn as the recording's waveform: the played part fills in, and clicking or
 * dragging anywhere on it jumps there. The waveform is a slider for keyboards and screen readers
 * (arrows move 5 s, Page Up/Down 30 s, Home/End, Space plays or pauses). `src` is an API path;
 * `blob` plays audio held in the page (a fresh recording).
 */
export function WaveformPlayer({
  src,
  blob,
  title,
  download,
}: {
  src?: string;
  blob?: Blob;
  title: string;
  download?: string;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const wave = useRef<HTMLDivElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [samples, setSamples] = useState<Float32Array | null>(null);
  const [bars, setBars] = useState(96);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [failed, setFailed] = useState(false);
  const dragging = useRef(false);

  // Fetch the audio once: the same bytes feed the player and the waveform.
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setSamples(null);
    setFailed(false);
    (async () => {
      try {
        const data = blob ?? (await (await fetch(`${API_BASE}${src}`)).blob());
        if (cancelled) return;
        objectUrl = URL.createObjectURL(data);
        setUrl(objectUrl);
        const decoded = await decode(data);
        if (!cancelled) setSamples(decoded.getChannelData(0));
      } catch {
        if (!cancelled) {
          setFailed(true); // still playable from the URL; the waveform stays flat
          if (!objectUrl && src) setUrl(`${API_BASE}${src}`);
        }
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, blob]);

  // As many bars as fit: the waveform is as long as its row.
  useEffect(() => {
    const element = wave.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) =>
      setBars(
        Math.max(
          32,
          Math.min(320, Math.floor(entry.contentRect.width / BAR_SPACE)),
        ),
      ),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const heights = samples
    ? peaks(samples, bars)
    : Array.from({ length: bars }, () => 0.12);
  const progress = duration ? time / duration : 0;

  function toggle() {
    const player = audio.current;
    if (!player) return;
    if (player.paused) void player.play();
    else player.pause();
  }

  function seekTo(seconds: number) {
    const player = audio.current;
    if (!player || !duration) return;
    player.currentTime = Math.max(0, Math.min(duration, seconds));
    setTime(player.currentTime);
  }

  function seekFromPointer(event: PointerEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    seekTo(((event.clientX - box.left) / box.width) * duration);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = {
      ArrowRight: time + 5,
      ArrowUp: time + 5,
      ArrowLeft: time - 5,
      ArrowDown: time - 5,
      PageUp: time + 30,
      PageDown: time - 30,
      Home: 0,
      End: duration,
    };
    if (event.key === " ") {
      event.preventDefault();
      toggle();
    } else if (event.key in moves) {
      event.preventDefault();
      seekTo(moves[event.key]);
    }
  }

  return (
    <div className="waveform-player">
      <audio
        ref={audio}
        src={url ?? undefined}
        preload="metadata"
        onLoadedMetadata={(event) =>
          setDuration(event.currentTarget.duration || 0)
        }
        onDurationChange={(event) =>
          setDuration(event.currentTarget.duration || 0)
        }
        onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <button
        type="button"
        className="waveform-play"
        onClick={toggle}
        disabled={!url}
        aria-label={playing ? `Pause ${title}` : `Play ${title}`}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          {playing ? (
            <path d="M4 3h3.5v12H4zM10.5 3H14v12h-3.5z" fill="currentColor" />
          ) : (
            <path d="M5 2.5v13l11-6.5z" fill="currentColor" />
          )}
        </svg>
      </button>
      <div
        ref={wave}
        className={failed ? "waveform waveform-flat" : "waveform"}
        role="slider"
        tabIndex={0}
        aria-label={`${title}: position`}
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={`${formatTime(time)} of ${formatTime(duration)}`}
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          dragging.current = true;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          seekFromPointer(event);
        }}
        onPointerMove={(event) => dragging.current && seekFromPointer(event)}
        onPointerUp={() => {
          dragging.current = false;
        }}
      >
        {heights.map((height, index) => (
          <span
            key={index}
            className={
              index / heights.length < progress ? "bar bar-played" : "bar"
            }
            style={{ height: `${Math.max(6, height * 100)}%` }}
          />
        ))}
      </div>
      <span className="waveform-time" aria-hidden="true">
        {formatTime(time)} / {formatTime(duration)}
      </span>
      {download ? (
        <a className="waveform-download muted" href={download}>
          Download
        </a>
      ) : null}
    </div>
  );
}
