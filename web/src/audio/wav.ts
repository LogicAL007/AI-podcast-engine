// Audio helpers for voice recordings and waveforms. The server keeps voices as 24 kHz mono 16-bit
// WAV (what the pipeline and Chatterbox read), so recordings and uploads are converted here, in
// the browser: anything it can decode (WebM, MP3, M4A, WAV...) becomes that one format.

export const VOICE_RATE = 24_000;
export const MIN_SECONDS = 5;
export const MAX_SECONDS = 90;

/** 16-bit PCM WAV bytes for mono samples in -1..1. */
export function encodeWav(
  samples: Float32Array,
  rate: number = VOICE_RATE,
): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++)
      view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(
      44 + i * 2,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true,
    );
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/** The loudest point in each of `count` equal slices, 0..1: the bars of a waveform. */
export function peaks(samples: Float32Array, count: number): number[] {
  const out: number[] = [];
  const size = samples.length / count;
  for (let bar = 0; bar < count; bar++) {
    const start = Math.floor(bar * size);
    const end = Math.max(start + 1, Math.floor((bar + 1) * size));
    let max = 0;
    for (let i = start; i < end && i < samples.length; i++)
      max = Math.max(max, Math.abs(samples[i]));
    out.push(max);
  }
  const loudest = Math.max(...out, 1e-6);
  return out.map((value) => value / loudest); // scaled so quiet recordings still show their shape
}

/** Decode any audio the browser understands. Throws if it cannot. */
export async function decode(data: Blob | ArrayBuffer): Promise<AudioBuffer> {
  const bytes = data instanceof Blob ? await data.arrayBuffer() : data;
  const context = new AudioContext();
  try {
    return await context.decodeAudioData(bytes.slice(0));
  } finally {
    void context.close();
  }
}

/** Mix to mono and resample to 24 kHz: the format voices are stored in. */
export async function toVoiceWav(
  audio: AudioBuffer,
): Promise<{ wav: Blob; seconds: number }> {
  const frames = Math.ceil(audio.duration * VOICE_RATE);
  const offline = new OfflineAudioContext(1, Math.max(1, frames), VOICE_RATE);
  const source = offline.createBufferSource();
  source.buffer = audio; // channels are mixed down to the one output channel
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return {
    wav: encodeWav(rendered.getChannelData(0)),
    seconds: rendered.duration,
  };
}

export function formatTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
