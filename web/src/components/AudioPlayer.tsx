import { API_BASE } from "../api/client";
import { WaveformPlayer } from "./WaveformPlayer";

/** An episode's audio as a full-width waveform you can play, scrub and download. */
export function AudioPlayer({ src, title }: { src: string; title: string }) {
  return (
    <WaveformPlayer
      src={src}
      title={title}
      download={`${API_BASE}${src}?download=true`}
    />
  );
}
