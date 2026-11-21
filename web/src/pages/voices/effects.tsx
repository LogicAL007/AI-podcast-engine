import { useId } from "react";

import type { VoiceEffects } from "../../api/types";

/** No effects: the voice as it was voiced. */
export const NATURAL: VoiceEffects = { deepen: 0, warmth: 0, broadcast: false };

/** The same presets as the server's (podcast_engine.common.voice_fx.PRESETS). */
export const PRESETS: { id: string; label: string; effects: VoiceEffects }[] = [
  { id: "natural", label: "Natural", effects: NATURAL },
  {
    id: "deeper",
    label: "Deeper",
    effects: { deepen: 40, warmth: 20, broadcast: false },
  },
  {
    id: "warm",
    label: "Warm",
    effects: { deepen: 0, warmth: 60, broadcast: false },
  },
  {
    id: "broadcast",
    label: "Broadcast",
    effects: { deepen: 0, warmth: 30, broadcast: true },
  },
  {
    id: "deep_broadcast",
    label: "Deep broadcast",
    effects: { deepen: 40, warmth: 40, broadcast: true },
  },
];

export function full(effects: Partial<VoiceEffects> | undefined): VoiceEffects {
  return { ...NATURAL, ...effects };
}

export function isNatural(effects: VoiceEffects): boolean {
  return !effects.deepen && !effects.warmth && !effects.broadcast;
}

/** The preset these settings match, or null for custom settings. */
export function presetOf(effects: VoiceEffects): string | null {
  const match = PRESETS.find(
    (preset) =>
      preset.effects.deepen === effects.deepen &&
      preset.effects.warmth === effects.warmth &&
      preset.effects.broadcast === effects.broadcast,
  );
  return match?.id ?? null;
}

/** A short name for effects: the preset's, or "Custom". */
export function effectName(effects: VoiceEffects): string {
  const id = presetOf(effects);
  return PRESETS.find((preset) => preset.id === id)?.label ?? "Custom";
}

/**
 * The effect picker: preset chips (a radio group), with the three settings behind "Adjust".
 * Used in Type to speech and for each host in Show sound.
 */
export function EffectPicker({
  value,
  onChange,
  label = "Effect",
}: {
  value: VoiceEffects;
  onChange: (effects: VoiceEffects) => void;
  label?: string;
}) {
  const name = useId();
  const chosen = presetOf(value);
  return (
    <fieldset className="effect-picker">
      <legend className="studio-label">{label}</legend>
      <div className="chips">
        {PRESETS.map((preset) => (
          <label key={preset.id} className="chip">
            <input
              type="radio"
              name={name}
              className="sr-only"
              checked={chosen === preset.id}
              onChange={() => onChange(preset.effects)}
            />
            <span>{preset.label}</span>
          </label>
        ))}
        {chosen === null ? (
          <label className="chip">
            <input
              type="radio"
              name={name}
              className="sr-only"
              checked
              readOnly
            />
            <span>Custom</span>
          </label>
        ) : null}
      </div>
      <details className="effect-adjust">
        <summary>Adjust</summary>
        <div className="effect-sliders">
          <label className="range-field">
            <span>Deepen {value.deepen ? `${value.deepen}%` : "off"}</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={value.deepen}
              aria-valuetext={value.deepen ? `${value.deepen}%` : "off"}
              onChange={(event) =>
                onChange({ ...value, deepen: Number(event.target.value) })
              }
            />
          </label>
          <label className="range-field">
            <span>Warmth {value.warmth ? `${value.warmth}%` : "off"}</span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={value.warmth}
              aria-valuetext={value.warmth ? `${value.warmth}%` : "off"}
              onChange={(event) =>
                onChange({ ...value, warmth: Number(event.target.value) })
              }
            />
          </label>
          <label className="check-inline">
            <input
              type="checkbox"
              checked={value.broadcast}
              onChange={(event) =>
                onChange({ ...value, broadcast: event.target.checked })
              }
            />
            Broadcast
          </label>
        </div>
      </details>
    </fieldset>
  );
}
