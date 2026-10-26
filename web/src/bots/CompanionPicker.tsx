import { useId } from "react";

import { TextField } from "../components/Field";
import {
  ACCESSORIES,
  CHARACTERS,
  COLORS,
  GLOWS,
  surprise,
  type Avatar,
} from "./avatar";
import { BotFigure } from "./BotFigure";

/**
 * Choose a bot: character, colour, glow, what it wears and its name, with a live 3D preview to
 * play with. Every choice is a native radio button, so it works by keyboard and screen reader.
 */
export function CompanionPicker({
  value,
  onChange,
}: {
  value: Avatar;
  onChange: (avatar: Avatar) => void;
}) {
  const id = useId();
  const set = <K extends keyof Avatar>(key: K, next: Avatar[K]) =>
    onChange({ ...value, [key]: next });
  const nameProblem = value.name.trim() ? null : "Give your bot a name.";

  return (
    <div className="companion">
      <div className="companion-preview">
        <BotFigure mode="greeting" avatar={value} interactive />
        <p className="companion-tip muted">
          Tap {value.name.trim() || "your bot"}, or drag it to spin.
        </p>
      </div>
      <div className="companion-options stack">
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
        <fieldset className="choice-group">
          <legend>Colour</legend>
          <div className="swatches">
            {(Object.keys(COLORS) as Avatar["color"][]).map((key) => (
              <label
                key={key}
                className="swatch"
                style={{ "--swatch": COLORS[key].hex } as React.CSSProperties}
              >
                <input
                  type="radio"
                  name={`${id}-color`}
                  value={key}
                  checked={value.color === key}
                  onChange={() => set("color", key)}
                />
                <span className="sr-only">{COLORS[key].label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="choice-group">
          <legend>Glow</legend>
          <div className="swatches">
            {(Object.keys(GLOWS) as Avatar["glow"][]).map((key) => (
              <label
                key={key}
                className="swatch swatch-glow"
                style={{ "--swatch": GLOWS[key].hex } as React.CSSProperties}
              >
                <input
                  type="radio"
                  name={`${id}-glow`}
                  value={key}
                  checked={value.glow === key}
                  onChange={() => set("glow", key)}
                />
                <span className="sr-only">{GLOWS[key].label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="choice-group">
          <legend>Wears</legend>
          <div className="segmented">
            {ACCESSORIES.map((accessory) => (
              <label key={accessory.value} className="choice-pill">
                <input
                  type="radio"
                  name={`${id}-accessory`}
                  value={accessory.value}
                  checked={value.accessory === accessory.value}
                  onChange={() => set("accessory", accessory.value)}
                />
                <span>{accessory.label}</span>
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
        <div>
          <button
            type="button"
            className="link-button"
            onClick={() => onChange(surprise(value))}
          >
            Surprise me
          </button>
        </div>
      </div>
    </div>
  );
}
