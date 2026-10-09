# Claim rating guide

Thank you for rating. Your sheet (`rater_A.csv` or `rater_B.csv`) lists short factual statements
taken from podcast scripts about technical topics. For each one you fill in two columns. Please work
alone: do not compare answers with the other rater until you have both finished.

You will not be told how a script was written. Please don't try to guess. The rows are shuffled so
that statements from the same script are not next to each other.

## What you have

- **The sheet.** One row per statement. Fill in `accurate`, `in_source` and, if you like, `notes`.
  Leave the other columns as they are.
- **The `sources/` folder.** One file per topic (`sources/t01.md` and so on): the text of the web page
  the topic is about, as it was when the scripts were written. The `source_file` column tells you which
  one to use.

## The two questions

### `accurate`: is the statement true?

| Answer | When |
|---|---|
| `yes` | It is true. Its wording may be loose, as speech often is, but nothing in it is wrong. |
| `no` | Any part of it is false or misleading: a wrong number, name, date, cause or comparison. |
| `unsure` | You cannot tell, even after checking the source file and a quick look at the product's official documentation. |

Check the source file first. If the statement is not in it, you may check the official documentation
for the product named in the topic (for ClickHouse: clickhouse.com/docs). Do not use AI tools to
check statements. Spend at most about two minutes per statement. If you still can't tell, answer
`unsure`.

A statement that is mostly right but has one wrong detail is `no`. Opinions and vague praise ("it is
really popular") are `unsure` unless the source says so.

### `in_source`: does the source file say it?

| Answer | When |
|---|---|
| `yes` | The source file states it, or it follows directly from what the file says. |
| `no` | The source file does not say it, even if the statement is true. |

The two answers are independent. A statement can be accurate but not in the source (`yes`, `no`), or
in the source but stated wrongly (`no`, `no`).

## Notes

Use `notes` for anything that helps later: what was wrong, or where you found the answer. When both
raters have finished, the disagreements are discussed. The agreed answer is then written in rater A's
`notes` as `final: yes` or `final: no`.

## Examples

Source says: "ClickHouse is a column-oriented SQL database management system for online analytical
processing."

| Statement | accurate | in_source |
|---|---|---|
| ClickHouse stores data by column and is built for analytics. | yes | yes |
| ClickHouse is a row-oriented database. | no | no |
| ClickHouse is written in C++. | yes | no |
| ClickHouse was first released in 1987. | no | no |
