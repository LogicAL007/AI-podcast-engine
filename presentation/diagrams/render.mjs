// Export every diagram in svg/ to a 2x PNG in png/, and all of them to one PDF.
//
//   python presentation/diagrams/build.py
//   NODE_PATH=<folder with playwright in node_modules> node presentation/diagrams/render.mjs
//
// Needs Playwright with Chromium (npm install playwright && npx playwright install chromium).
import { readdirSync, readFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const here = dirname(fileURLToPath(import.meta.url));
const svgDir = join(here, "svg");
const pngDir = join(here, "png");
mkdirSync(pngDir, { recursive: true });

const files = readdirSync(svgDir).filter((f) => f.endsWith(".svg")).sort();
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });
const pages = [];

for (const file of files) {
  const svg = readFileSync(join(svgDir, file), "utf8");
  const [, w, h] = svg.match(/width="(\d+)" height="(\d+)"/);
  await page.setViewportSize({ width: Number(w), height: Number(h) });
  await page.setContent(`<!doctype html><html><body style="margin:0">${svg}</body></html>`);
  await page.screenshot({ path: join(pngDir, file.replace(".svg", ".png")), clip: { x: 0, y: 0, width: Number(w), height: Number(h) } });
  pages.push({ svg, w: Number(w), h: Number(h) });
  console.log("png", file.replace(".svg", ".png"));
}

// One PDF, one diagram per page, each page the diagram's own size (16:9 or a little taller).
const pdf = await browser.newPage();
const body = pages
  .map(({ svg, w, h }) => `<section style="width:${w}px;height:${h}px;page-break-after:always">${svg}</section>`)
  .join("");
await pdf.setContent(`<!doctype html><html><head><style>@page{size:1600px 1000px;margin:0}body{margin:0}
section{display:flex;align-items:flex-start}</style></head><body>${body}</body></html>`);
await pdf.pdf({ path: join(here, "architecture-diagrams.pdf"), width: "1600px", height: "1000px", printBackground: true });
console.log("pdf architecture-diagrams.pdf");
await browser.close();
