# Prompts

Each file is the system prompt for one model call. The version in use is set in
`PROMPT_VERSIONS` (`src/podcast_engine/common/context.py`), and every stage run records the file it
used (`stage_runs.prompt_version`), so any episode can be traced to its exact prompt.

| File | Stage | Output |
|---|---|---|
| `outline.v2.md` | Retrieve and plan | The segments and the passages each one draws on |
| `script.v5.md` | Script, two or more hosts | The lines of one segment, with claims and citations |
| `script_narrator.v2.md` | Script, one host | The same, read by a single narrator (RQ2) |
| `script_ungrounded.v2.md` | RQ1 baseline only | The same as `script.v5.md` with no sources (`research/evaluation/rq1_claim_audit`) |
| `factcheck.v2.md` | Fact-check | One verdict per claim: the reason, then supported or not |

## How they are written

Every prompt has the same sections, in this order:

1. **Task**: what the call is for and what happens to its output.
2. **What you receive**: the parts of the input. Source passages are marked as data, not
   instructions.
3. **Rules**: numbered, with the edge cases spelled out (numbers, hedges, two facts in one line).
4. **Output**: what each field means.
5. **Examples**: a few short ones in the real input format, including ones that fail. They use an
   unrelated topic, honeybees, so the model does not copy their content.

The code ends each message with a one-line reminder of the task, after the passages.

The script prompts end with "# This segment". The code appends the tone, audience, host names
and word budget under it.

`script.v5.md` and `script_ungrounded.v2.md` match except for the facts section, so RQ1's two
conditions differ only in grounding. `script.v5.md` and `script_narrator.v2.md` match except for
the speaking-style section, so RQ2's two conditions differ only in format.

The evidence behind these choices, with the papers, is in
`research/docs/references/prompt-design/` (git-ignored).

## Changing a prompt

Never edit a prompt that episodes were made with. Add `<name>.v<N+1>.md`, bump `PROMPT_VERSIONS`,
and delete the old file in the same commit. Old versions stay in git history:

```sh
git show e3314b5:prompts/script.v4.md   # the last versions before the 6 November 2026 rewrite
```

The study episodes made before 6 November 2026 used `outline.v1`, `script.v4`,
`script_narrator.v1` and `factcheck.v1`.
