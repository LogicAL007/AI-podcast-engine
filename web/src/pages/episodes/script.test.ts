import { describe, expect, it } from "vitest";

import type { EpisodeScript } from "../../api/types";
import { citationsOf, editFor } from "./ScriptTab";

const script: EpisodeScript = {
  episode_id: "e1",
  segments: [
    {
      position: 1,
      title: "Opening",
      source_item_ids: [],
      lines: [
        { speaker: "Alex", text: "Welcome.", claims: [], delivery: "warm" },
        {
          speaker: "Sam",
          text: "Tides follow the moon.",
          delivery: "neutral",
          claims: [
            {
              text: "Tides follow the moon",
              chunk_ids: ["c1", "c2"],
              supported: true,
            },
            { text: "twice a day", chunk_ids: ["c2"], supported: true },
          ],
        },
      ],
    },
    {
      position: 2,
      title: "Why",
      source_item_ids: [],
      lines: [
        { speaker: "Alex", text: "Gravity.", claims: [], delivery: "neutral" },
      ],
    },
  ],
};

describe("script edits", () => {
  it("keep each line's citations, once each; framing lines stay uncited", () => {
    expect(citationsOf(script.segments[0].lines[1])).toEqual(["c1", "c2"]);
    expect(citationsOf(script.segments[0].lines[0])).toBeNull();
  });

  it("send only the segments that changed, with all their lines", () => {
    const edit = editFor(script, {
      "1:1": "  Tides follow the moon, mostly. ",
    });
    expect(edit.segments).toHaveLength(1);
    expect(edit.segments[0]).toEqual({
      position: 1,
      lines: [
        { speaker: "Alex", text: "Welcome.", chunk_ids: null, delivery: "warm" },
        {
          speaker: "Sam",
          text: "Tides follow the moon, mostly.",
          chunk_ids: ["c1", "c2"],
          delivery: "neutral",
        },
      ],
    });
  });
});
