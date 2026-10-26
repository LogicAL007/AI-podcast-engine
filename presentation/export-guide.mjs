// Export presentation/README.md (the presenter's guide) to Presenter_Guide.pdf.
//
//   NODE_PATH=<folder whose node_modules has playwright and marked> node presentation/export-guide.mjs
//
// Each slide's script becomes a shaded box with its estimated speaking time (about 150 words
// a minute), so the guide can be read from while rehearsing.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const { marked } = require("marked");

const here = dirname(fileURLToPath(import.meta.url));
const markdown = readFileSync(join(here, "README.md"), "utf8");
const WPM = 150;

const slug = (text) =>
  text.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

// Split off the title and the intro (everything before the first "##").
const [, title] = markdown.match(/^# (.+)$/m);
const body = markdown.replace(/^# .+$/m, "");
let html = marked.parse(body, { gfm: true });

// Headings get ids, for the contents list.
const contents = [];
html = html.replace(/<h2>(.+?)<\/h2>/g, (_, text) => {
  const id = slug(text);
  contents.push({ id, text });
  return `<h2 id="${id}">${text}</h2>`;
});

let totalWords = 0;
// "Script." followed by a quote becomes one shaded script box with its speaking time.
html = html.replace(/<p><strong>Script\.<\/strong><\/p>\s*<blockquote>([\s\S]*?)<\/blockquote>/g, (_, inner) => {
  const words = inner.replace(/<[^>]+>/g, " ").trim().split(/\s+/).length;
  const seconds = Math.round(((words / WPM) * 60) / 5) * 5;
  totalWords += words;
  return `<div class="script"><div class="script-label">Script <span>· ${words} words · about ${seconds} s</span></div>${inner}</div>`;
});
// Keep each slide's heading, description and script on one page (the research may flow on).
html = html
  .split(/(?=<h2 )/)
  .map((part) => {
    const at = part.indexOf('<div class="script">');
    if (!part.startsWith('<h2 id="page') || at < 0) return part;
    const labelEnd = part.indexOf("</div>", at) + 6; // the script box holds one inner div
    const end = part.indexOf("</div>", labelEnd) + 6;
    return `<div class="keep">${part.slice(0, end)}</div>${part.slice(end)}`;
  })
  .join("");
// Lead-in labels ("What it shows.", "Research behind it.") stand out a little.
html = html.replace(/<p><strong>(What it shows|What they show|Research behind it)\.<\/strong>/g,
  '<p class="lead"><strong>$1.</strong>');
html = html.replace(/<hr>/g, "");

const minutes = (totalWords / WPM).toFixed(1);
const toc = contents
  .map(({ id, text }) => `<li><a href="#${id}">${text}</a></li>`)
  .join("");

const page = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title>
<style>
  @page { size: Letter; margin: 18mm 18mm 20mm; }
  :root { --ink:#1c1917; --muted:#57534e; --rule:#e7e2dd; --accent:#2e6b5e; --tint:#f1f6f4; --orange:#c2410c; }
  * { box-sizing: border-box; }
  body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink); font-size: 10.5pt; line-height: 1.5; margin: 0; }
  .cover { height: 230mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
  .kicker { color: var(--accent); font-weight: 700; letter-spacing: 0.14em; font-size: 9pt; text-transform: uppercase; }
  .cover h1 { font-size: 30pt; line-height: 1.12; margin: 10px 0 14px; }
  .cover .sub { font-size: 13pt; color: var(--muted); margin: 0 0 40px; }
  .cover .who { font-size: 11.5pt; font-weight: 700; margin: 0 0 4px; }
  .cover .where { color: var(--muted); margin: 0; }
  .cover .facts { margin-top: 46px; display: flex; gap: 40px; }
  .cover .facts div { font-size: 9pt; color: var(--muted); }
  .cover .facts b { display: block; font-size: 18pt; color: var(--ink); }
  .toc { page-break-after: always; }
  .toc h2 { margin-top: 0; }
  .toc ol { columns: 2; column-gap: 28px; padding-left: 28px; margin: 0; font-size: 10pt; }
  .toc li { margin: 0 0 5px; break-inside: avoid; }
  a { color: var(--accent); text-decoration: none; }
  h2 { font-size: 15pt; margin: 26px 0 8px; padding-top: 4px; break-after: avoid; page-break-after: avoid; }
  h2 + * { break-before: avoid; }
  h3 { font-size: 12pt; break-after: avoid; }
  p { margin: 0 0 8px; }
  ul, ol { margin: 0 0 10px; padding-left: 20px; }
  li { margin-bottom: 4px; }
  .lead strong { color: var(--accent); }
  .keep { break-inside: avoid; page-break-inside: avoid; }
  .blank { display: inline-block; width: 90px; border-bottom: 1px solid var(--muted); margin: 0 3px; }
  .script { background: var(--tint); border: 1px solid #c9ddd5; border-radius: 8px; padding: 10px 14px 4px; margin: 6px 0 10px;
            break-inside: avoid; page-break-inside: avoid; font-size: 11pt; line-height: 1.55; }
  .script-label { font-size: 8pt; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent); margin-bottom: 4px; }
  .script-label span { color: var(--muted); font-weight: 400; letter-spacing: 0; text-transform: none; font-size: 8.5pt; }
  table { width: 100%; border-collapse: collapse; margin: 6px 0 14px; font-size: 9.5pt; break-inside: auto; }
  th, td { border-bottom: 1px solid var(--rule); padding: 6px 8px; text-align: left; vertical-align: top; }
  th { color: var(--muted); font-weight: 700; }
  tr { break-inside: avoid; }
  code { font-family: Menlo, Consolas, monospace; font-size: 9pt; }
  h2#references ~ ol li { font-size: 9.5pt; }
</style></head><body>
<section class="cover">
  <div class="kicker">COMP 5112 · Research methodology proposal</div>
  <h1>AI-powered podcast creation with dynamic content</h1>
  <p class="sub">Presenter's guide: what each slide shows, what to say, and the research behind it</p>
  <p class="who">Omotosho Ayomide (1357152) and Saidul Alam (<span class="blank"></span>)</p>
  <p class="where">MSc Computer Science · Lakehead University · Fall 2026</p>
  <div class="facts">
    <div><b>25</b>slides (22 presented)</div>
    <div><b>${minutes} min</b>of script at ${WPM} words a minute</div>
    <div><b>30</b>references</div>
  </div>
</section>
<section class="toc"><h2>Contents</h2><ol>${toc}</ol></section>
${html}
</body></html>`;

if (process.env.GUIDE_HTML) (await import("node:fs")).writeFileSync(process.env.GUIDE_HTML, page);
const browser = await chromium.launch();
const tab = await browser.newPage();
await tab.setContent(page, { waitUntil: "load" });
await tab.pdf({
  path: join(here, "Presenter_Guide.pdf"),
  format: "Letter",
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: `<div style="width:100%;font-family:Helvetica,Arial,sans-serif;font-size:8px;color:#57534e;padding:0 18mm;display:flex;justify-content:space-between">
    <span>AI-Powered Podcast Creation · Presenter's guide</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin: { top: "18mm", bottom: "20mm", left: "18mm", right: "18mm" },
});
await browser.close();
console.log(`wrote Presenter_Guide.pdf (${contents.length} sections, ${totalWords} script words, ${minutes} min)`);
