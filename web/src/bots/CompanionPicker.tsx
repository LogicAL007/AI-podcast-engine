import {
  useId,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { SelectField, TextField } from "../components/Field";
import { Tabs } from "../components/Tabs";
import {
  ACCENTS,
  accentHex,
  BODIES,
  bodyHex,
  CHARACTERS,
  COLORS,
  contrast,
  DEFAULT_AVATAR,
  EXTRAS,
  EYES,
  faceHex,
  FINISHES,
  GLOWS,
  glowHex,
  HATS,
  HEADS,
  MOUTHS,
  NECKS,
  PERSONALITIES,
  surprise,
  type Avatar,
  type Option,
} from "./avatar";
import { AvatarFace } from "./AvatarFace";
import { BotFigure } from "./BotFigure";
import type { BotMode } from "./botMode";
import { canSpeak, speak, useVoices } from "./speech";

/** The eyes must stand out from the face plate: 3:1, the WCAG contrast for graphics. */
const EYE_CONTRAST = 3;

const POSES: { mode: BotMode; label: string }[] = [
  { mode: "greeting", label: "Wave" },
  { mode: "working", label: "Work" },
  { mode: "reviewing", label: "Think" },
  { mode: "celebrating", label: "Cheer" },
];

const TABS = [
  { id: "character", label: "Character" },
  { id: "shape", label: "Shape" },
  { id: "face", label: "Face" },
  { id: "colours", label: "Colours" },
  { id: "outfit", label: "Outfit" },
  { id: "voice", label: "Voice" },
];
/** The short version, for onboarding. */
const COMPACT_TABS = ["character", "colours", "outfit"];

/** A row of labelled radio pills; `preview` draws a small picture of the bot with that choice. */
function OptionGroup<T extends string>({
  legend,
  options,
  value,
  onChange,
  preview,
}: {
  legend: string;
  options: Option<T>[];
  value: T;
  onChange: (next: T) => void;
  preview?: (option: T) => ReactNode;
}) {
  const name = useId();
  return (
    <fieldset className="choice-group">
      <legend>{legend}</legend>
      <div className="segmented">
        {options.map((option) => (
          <label
            key={option.value}
            className={preview ? "choice-pill choice-thumb" : "choice-pill"}
            title={option.about}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            {preview ? preview(option.value) : null}
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Preset swatches plus "Custom", a native colour picker for any colour. */
function ColourGroup({
  legend,
  presets,
  value,
  hex,
  glow = false,
  storeHex = false,
  onChange,
}: {
  legend: string;
  presets: Record<string, { label: string; hex: string }>;
  value: string;
  hex: string;
  glow?: boolean;
  /** Store a preset as its colour rather than its name (the API knows accents only as #rrggbb). */
  storeHex?: boolean;
  onChange: (next: string) => void;
}) {
  const name = useId();
  const custom =
    !(value in presets) && !Object.values(presets).some((p) => p.hex === value);
  return (
    <fieldset className="choice-group">
      <legend>{legend}</legend>
      <div className="swatches">
        {Object.entries(presets).map(([key, preset]) => {
          const stored = storeHex ? preset.hex : key;
          return (
            <label
              key={key}
              className={glow ? "swatch swatch-glow" : "swatch"}
              style={{ "--swatch": preset.hex } as CSSProperties}
            >
              <input
                type="radio"
                name={name}
                value={stored}
                checked={value === stored}
                onChange={() => onChange(stored)}
              />
              <span className="sr-only">{preset.label}</span>
            </label>
          );
        })}
        <label
          className={`swatch swatch-custom${custom ? " swatch-custom-on" : ""}`}
          style={{ "--swatch": hex } as CSSProperties}
        >
          <span className="sr-only">Custom {legend.toLowerCase()} colour</span>
          <input
            type="color"
            className="swatch-picker"
            value={hex}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
      </div>
    </fieldset>
  );
}

/** Undo and redo over the creator's changes; typing a name counts as one change. */
function useHistory(value: Avatar, onChange: (next: Avatar) => void) {
  const past = useRef<Avatar[]>([]);
  const future = useRef<Avatar[]>([]);
  const [, rerender] = useState(0);
  const apply = (next: Avatar) => {
    const last = past.current.at(-1);
    const onlyName =
      last &&
      JSON.stringify({ ...last, name: "" }) ===
        JSON.stringify({ ...value, name: "" }) &&
      JSON.stringify({ ...value, name: "" }) ===
        JSON.stringify({ ...next, name: "" });
    if (!onlyName) past.current.push(value);
    future.current = [];
    onChange(next);
    rerender((n) => n + 1);
  };
  const undo = () => {
    const previous = past.current.pop();
    if (!previous) return;
    future.current.push(value);
    onChange(previous);
    rerender((n) => n + 1);
  };
  const redo = () => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(value);
    onChange(next);
    rerender((n) => n + 1);
  };
  return {
    apply,
    undo,
    redo,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
  };
}

/** The preset glow that stands out best on this bot's face, to fix a hard-to-see choice. */
function bestGlow(avatar: Avatar): string {
  const plate = faceHex(avatar);
  return Object.entries(GLOWS).sort(
    ([, a], [, b]) => contrast(b.hex, plate) - contrast(a.hex, plate),
  )[0][0];
}

/**
 * Build a bot: character, shape, face, colours, finish, outfit, personality, voice and name, with
 * a live 3D preview that can strike each pose. Every choice is a native radio button or input,
 * so it works by keyboard and screen reader. `compact` keeps three tabs, for onboarding.
 */
export function CompanionPicker({
  value,
  onChange,
  compact = false,
}: {
  value: Avatar;
  onChange: (avatar: Avatar) => void;
  compact?: boolean;
}) {
  const id = useId();
  const history = useHistory(value, onChange);
  const set = <K extends keyof Avatar>(key: K, next: Avatar[K]) =>
    history.apply({ ...value, [key]: next });
  const [tab, setTab] = useState("character");
  const [pose, setPose] = useState<BotMode>("greeting");
  const [talk, setTalk] = useState(0);
  const voices = useVoices();
  const nameProblem = value.name.trim() ? null : "Give your bot a name.";
  const toy = value.character === "toy";
  const eyeContrast = contrast(glowHex(value), faceHex(value));
  const tabs = compact ? TABS.filter((t) => COMPACT_TABS.includes(t.id)) : TABS;
  const thumb = (patch: Partial<Avatar>) => (
    <AvatarFace avatar={{ ...value, ...patch }} size={22} />
  );
  const fixedShape = (
    <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
      {value.character === "rex" ? "Rex" : "Pod"} keeps its own shape and face.
      Choose Toy on the Character tab to build your own.
    </p>
  );

  return (
    <div className="companion">
      <div className="companion-preview">
        <BotFigure mode={pose} avatar={value} interactive talk={talk} />
        <div
          className="segmented pose-buttons"
          role="group"
          aria-label="Try a pose"
        >
          {POSES.map((p) => (
            <button
              key={p.mode}
              type="button"
              className="choice-pill"
              aria-pressed={pose === p.mode}
              onClick={() => setPose(p.mode)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <p className="companion-tip muted">
          Tap {value.name.trim() || "your bot"}, or drag it to spin.
        </p>
      </div>
      <div className="companion-options stack">
        <div className="row creator-tools">
          <button
            type="button"
            className="link-button"
            onClick={() => history.apply(surprise(value))}
          >
            Surprise me
          </button>
          <button
            type="button"
            className="link-button"
            disabled={!history.canUndo}
            onClick={history.undo}
          >
            Undo
          </button>
          <button
            type="button"
            className="link-button"
            disabled={!history.canRedo}
            onClick={history.redo}
          >
            Redo
          </button>
          <button
            type="button"
            className="link-button"
            onClick={() =>
              history.apply({ ...DEFAULT_AVATAR, name: value.name })
            }
          >
            Start over
          </button>
        </div>
        <Tabs tabs={tabs} active={tab} onChange={setTab} label="Build your bot">
          {tab === "character" ? (
            <div className="stack">
              <fieldset className="choice-group">
                <legend>Character</legend>
                <div className="character-cards">
                  {CHARACTERS.map((character) => (
                    <label key={character.value} className="character-card">
                      <input
                        type="radio"
                        name={`${id}-character`}
                        value={character.value}
                        checked={value.character === character.value}
                        onChange={() => set("character", character.value)}
                      />
                      <span className="character-name">{character.label}</span>
                      <span className="muted">{character.about}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <TextField
                label="Name"
                maxLength={24}
                value={value.name}
                error={nameProblem}
                onChange={(event) => set("name", event.target.value)}
              />
              <OptionGroup
                legend="Personality"
                options={PERSONALITIES}
                value={value.personality}
                onChange={(next) => set("personality", next)}
              />
            </div>
          ) : null}
          {tab === "shape" ? (
            toy ? (
              <div className="stack">
                <OptionGroup
                  legend="Body"
                  options={BODIES}
                  value={value.body}
                  onChange={(next) => set("body", next)}
                />
                <OptionGroup
                  legend="Head"
                  options={HEADS}
                  value={value.head}
                  onChange={(next) => set("head", next)}
                  preview={(head) => thumb({ head, character: "toy" })}
                />
                <OptionGroup
                  legend="Finish"
                  options={FINISHES}
                  value={value.finish}
                  onChange={(next) => set("finish", next)}
                />
              </div>
            ) : (
              <div className="stack">
                {fixedShape}
                <OptionGroup
                  legend="Finish"
                  options={FINISHES}
                  value={value.finish}
                  onChange={(next) => set("finish", next)}
                />
              </div>
            )
          ) : null}
          {tab === "face" ? (
            toy ? (
              <div className="stack">
                <OptionGroup
                  legend="Eyes"
                  options={EYES}
                  value={value.eyes}
                  onChange={(next) => set("eyes", next)}
                  preview={(eyes) => thumb({ eyes, character: "toy" })}
                />
                <OptionGroup
                  legend="Mouth"
                  options={MOUTHS}
                  value={value.mouth}
                  onChange={(next) => set("mouth", next)}
                />
              </div>
            ) : (
              fixedShape
            )
          ) : null}
          {tab === "colours" ? (
            <div className="stack">
              <ColourGroup
                legend="Body"
                presets={COLORS}
                value={value.color}
                hex={bodyHex(value)}
                onChange={(next) => set("color", next)}
              />
              <ColourGroup
                legend="Glow"
                presets={GLOWS}
                value={value.glow}
                hex={glowHex(value)}
                glow
                onChange={(next) => set("glow", next)}
              />
              {eyeContrast < EYE_CONTRAST ? (
                <p className="contrast-warning" role="status">
                  These eyes are hard to see on its face (
                  {eyeContrast.toFixed(1)}:1).{" "}
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => set("glow", bestGlow(value))}
                  >
                    Use a brighter glow
                  </button>
                </p>
              ) : null}
              <ColourGroup
                legend="Trim"
                presets={ACCENTS}
                value={value.accent}
                hex={accentHex(value)}
                storeHex
                onChange={(next) => set("accent", next)}
              />
            </div>
          ) : null}
          {tab === "outfit" ? (
            <div className="stack">
              <OptionGroup
                legend="On its head"
                options={HATS}
                value={value.hat}
                onChange={(next) => set("hat", next)}
                preview={(hat) => thumb({ hat })}
              />
              <OptionGroup
                legend="At its neck"
                options={NECKS}
                value={value.neck}
                onChange={(next) => set("neck", next)}
              />
              <OptionGroup
                legend="Extra"
                options={EXTRAS}
                value={value.extra}
                onChange={(next) => set("extra", next)}
              />
            </div>
          ) : null}
          {tab === "voice" ? (
            <div className="stack">
              <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
                {value.name.trim() || "Your bot"} reads its tips aloud only when
                you turn speech on. Your device's own voices are free; the words
                are always on screen too.
              </p>
              {canSpeak() ? (
                <>
                  <SelectField
                    label="Voice"
                    value={value.voice.name}
                    options={[
                      { value: "", label: "Device default" },
                      ...voices.map((v) => ({
                        value: v.name,
                        label: `${v.name} (${v.lang})`,
                      })),
                    ]}
                    onChange={(event) =>
                      set("voice", { ...value.voice, name: event.target.value })
                    }
                  />
                  <label className="field range-field">
                    <span>Speed: {value.voice.rate.toFixed(1)}×</span>
                    <input
                      type="range"
                      min={0.5}
                      max={2}
                      step={0.1}
                      value={value.voice.rate}
                      onChange={(event) =>
                        set("voice", {
                          ...value.voice,
                          rate: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label className="field range-field">
                    <span>Pitch: {value.voice.pitch.toFixed(1)}</span>
                    <input
                      type="range"
                      min={0}
                      max={2}
                      step={0.1}
                      value={value.voice.pitch}
                      onChange={(event) =>
                        set("voice", {
                          ...value.voice,
                          pitch: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <div>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() =>
                        speak(
                          `Hi! I'm ${value.name.trim() || "your bot"}. Ready when you are.`,
                          value.voice,
                          setTalk,
                        )
                      }
                    >
                      Hear it
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted">
                  This browser cannot speak, so your bot will stay text only.
                </p>
              )}
            </div>
          ) : null}
        </Tabs>
      </div>
    </div>
  );
}
