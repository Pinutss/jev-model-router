import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
await mkdir(here, { recursive: true });

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    const sibling = path.resolve(
      here,
      "../../../jev-memory-selector/docs/preview/node_modules/playwright/index.mjs",
    );
    return await import(pathToFileURL(sibling).href);
  }
}

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 3,
});
const html = pathToFileURL(path.join(here, "slides.html")).href;
await page.goto(html, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
const slides = await page.$$eval(".slide", (nodes) =>
  nodes.map((node) => ({
    id: node.getAttribute("data-slide"),
    file: node.getAttribute("data-file"),
  })),
);
for (const slide of slides) {
  await page.goto(`${html}?slide=${slide.id}`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(200);
  const dest = path.join(here, slide.file);
  await page.screenshot({ path: dest, type: "png" });
  console.log(dest);
}
await browser.close();
