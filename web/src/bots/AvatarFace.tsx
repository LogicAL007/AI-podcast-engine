import { COLORS, GLOWS, type Avatar } from "./avatar";

/** A small flat face of the person's bot, in its colours, for buttons and the header. */
export function AvatarFace({
  avatar,
  size = 26,
}: {
  avatar: Avatar;
  size?: number;
}) {
  const shell = COLORS[avatar.color].hex;
  const glow = GLOWS[avatar.glow].hex;
  const rex = avatar.character === "rex";
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true">
      {avatar.accessory === "antenna" ? (
        <>
          <line
            x1="13"
            y1="2.5"
            x2="13"
            y2="6"
            stroke="#57534e"
            strokeWidth="1.6"
          />
          <circle cx="13" cy="2.5" r="1.8" fill={glow} />
        </>
      ) : null}
      <rect
        x="3"
        y="6"
        width="20"
        height="16"
        rx={rex ? 5 : 8}
        fill={shell}
        stroke="#57534e"
        strokeWidth="1.4"
      />
      {avatar.accessory === "headphones" ? (
        <>
          <path
            d="M4 12 a9 9 0 0 1 18 0"
            fill="none"
            stroke="#2a2522"
            strokeWidth="1.8"
          />
          <rect x="1" y="11" width="4" height="7" rx="2" fill="#2a2522" />
          <rect x="21" y="11" width="4" height="7" rx="2" fill="#2a2522" />
        </>
      ) : null}
      <rect
        x="6.5"
        y="10"
        width="13"
        height="7"
        rx={rex ? 2 : 3.5}
        fill="#17120f"
      />
      <rect x="9" y="12" width="2" height="3" rx="1" fill={glow} />
      <rect x="15" y="12" width="2" height="3" rx="1" fill={glow} />
      {avatar.accessory === "bowtie" ? (
        <path
          d="M9 23 l4 -1.6 l4 1.6 l0 -3.2 l-4 1.6 l-4 -1.6 z"
          fill="#c2410c"
        />
      ) : null}
    </svg>
  );
}
