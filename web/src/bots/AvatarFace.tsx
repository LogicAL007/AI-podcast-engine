import { accentHex, bodyHex, faceHex, glowHex, type Avatar } from "./avatar";

const OUTLINE = "#57534e";
const DARK = "#2a2522";

/** The head's outline in the 26-unit box: its corner radius and width. */
function headShape(avatar: Avatar): { x: number; w: number; rx: number } {
  if (avatar.character === "rex") return { x: 3, w: 20, rx: 5 };
  if (avatar.character === "pod") return { x: 3, w: 20, rx: 8 };
  switch (avatar.head) {
    case "cube":
      return { x: 3.5, w: 19, rx: 4.5 };
    case "screen":
      return { x: 2, w: 22, rx: 2.5 };
    case "dome":
      return { x: 3, w: 20, rx: 9 };
    default:
      return { x: 3, w: 20, rx: 8 };
  }
}

function Eyes({ avatar, glow }: { avatar: Avatar; glow: string }) {
  const style = avatar.character === "toy" ? avatar.eyes : "dots";
  return (
    <>
      {[10, 16].map((x) => {
        switch (style) {
          case "visor":
            return (
              <rect
                key={x}
                x={x - 2}
                y="12.6"
                width="4"
                height="1.8"
                rx="0.9"
                fill={glow}
              />
            );
          case "pixel":
            return (
              <rect
                key={x}
                x={x - 1.3}
                y="12.2"
                width="2.6"
                height="2.6"
                fill={glow}
              />
            );
          case "sleepy":
            return (
              <rect
                key={x}
                x={x - 1.2}
                y="13.4"
                width="2.4"
                height="1.2"
                rx="0.6"
                fill={glow}
              />
            );
          case "star":
            return (
              <path
                key={x}
                d={`M${x} 11.6 l0.7 1.3 1.4 0.2 -1 1 0.25 1.4 -1.35 -0.7 -1.35 0.7 0.25 -1.4 -1 -1 1.4 -0.2 z`}
                fill={glow}
              />
            );
          default:
            return (
              <rect
                key={x}
                x={x - 1}
                y="12"
                width="2"
                height="3"
                rx="1"
                fill={glow}
              />
            );
        }
      })}
    </>
  );
}

/** What it wears on its head, drawn small. */
function Hat({
  avatar,
  glow,
  accent,
}: {
  avatar: Avatar;
  glow: string;
  accent: string;
}) {
  switch (avatar.hat) {
    case "antenna":
      return (
        <>
          <line
            x1="13"
            y1="2.5"
            x2="13"
            y2="6"
            stroke={OUTLINE}
            strokeWidth="1.6"
          />
          <circle cx="13" cy="2.5" r="1.8" fill={glow} />
        </>
      );
    case "headphones":
      return (
        <>
          <path
            d="M4 12 a9 9 0 0 1 18 0"
            fill="none"
            stroke={DARK}
            strokeWidth="1.8"
          />
          <rect x="1" y="11" width="4" height="7" rx="2" fill={accent} />
          <rect x="21" y="11" width="4" height="7" rx="2" fill={accent} />
        </>
      );
    case "cap":
      return (
        <>
          <path d="M5 8 a8 6 0 0 1 16 0 z" fill={accent} />
          <rect x="12" y="7" width="11" height="2" rx="1" fill={accent} />
        </>
      );
    case "beanie":
      return (
        <>
          <path d="M5 8 a8 7 0 0 1 16 0 z" fill={accent} />
          <rect x="4.5" y="7" width="17" height="2.4" rx="1.2" fill={accent} />
          <circle
            cx="13"
            cy="1.8"
            r="1.6"
            fill="#fafaf9"
            stroke={OUTLINE}
            strokeWidth="0.5"
          />
        </>
      );
    case "crown":
      return (
        <path
          d="M7 7.5 l1 -5 3 3 2 -4 2 4 3 -3 1 5 z"
          fill="#f2c14e"
          stroke="#a16207"
          strokeWidth="0.6"
        />
      );
    case "halo":
      return (
        <ellipse
          cx="13"
          cy="2.8"
          rx="6"
          ry="1.6"
          fill="none"
          stroke={glow}
          strokeWidth="1.4"
        />
      );
    default:
      return null;
  }
}

/** A small flat face of the person's bot, in its colours, for buttons and the header. */
export function AvatarFace({
  avatar,
  size = 26,
}: {
  avatar: Avatar;
  size?: number;
}) {
  const shell = bodyHex(avatar);
  const glow = glowHex(avatar);
  const accent = accentHex(avatar);
  const head = headShape(avatar);
  const behind = avatar.hat === "headphones" || avatar.hat === "halo";
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true">
      {behind ? <Hat avatar={avatar} glow={glow} accent={accent} /> : null}
      {avatar.extra === "ears" ? (
        <>
          <path
            d="M4 9 l1.5 -5 3 4 z"
            fill={shell}
            stroke={OUTLINE}
            strokeWidth="1"
          />
          <path
            d="M22 9 l-1.5 -5 -3 4 z"
            fill={shell}
            stroke={OUTLINE}
            strokeWidth="1"
          />
        </>
      ) : null}
      <rect
        x={head.x}
        y="6"
        width={head.w}
        height="16"
        rx={head.rx}
        fill={shell}
        stroke={OUTLINE}
        strokeWidth="1.4"
      />
      <rect
        x="6.5"
        y="10"
        width="13"
        height="7"
        rx={avatar.character === "rex" || avatar.head === "screen" ? 2 : 3.5}
        fill={faceHex(avatar)}
      />
      <Eyes avatar={avatar} glow={glow} />
      {avatar.extra === "glasses" ? (
        <g fill="none" stroke={DARK} strokeWidth="0.9">
          <circle cx="10" cy="13.5" r="2.6" />
          <circle cx="16" cy="13.5" r="2.6" />
          <line x1="12.6" y1="13.5" x2="13.4" y2="13.5" />
        </g>
      ) : null}
      {!behind ? <Hat avatar={avatar} glow={glow} accent={accent} /> : null}
      {avatar.neck === "bowtie" ? (
        <path
          d="M9 23 l4 -1.6 l4 1.6 l0 -3.2 l-4 1.6 l-4 -1.6 z"
          fill={accent}
        />
      ) : avatar.neck === "scarf" ? (
        <rect x="6" y="21" width="14" height="3" rx="1.5" fill={accent} />
      ) : avatar.neck === "medal" ? (
        <circle
          cx="13"
          cy="23.5"
          r="2"
          fill="#f2c14e"
          stroke="#a16207"
          strokeWidth="0.6"
        />
      ) : null}
    </svg>
  );
}
