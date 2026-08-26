// Copies the third-party runtime assets out of node_modules into the Django
// static tree, so the app serves everything itself: no CDN, no Google Fonts,
// nothing that phones home from a student's browser.
import { mkdir, copyFile, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const staticDir = join(root, "quested", "static");
const nm = join(root, "node_modules");

const files = [
  // Flowchart rendering for exercise statements.
  ["mermaid/dist/mermaid.min.js", "vendor/mermaid.min.js"],
  // Syntax highlighting for code submissions.
  ["prismjs/prism.js", "vendor/prism.js"],
  ["prismjs/components/prism-clike.min.js", "vendor/prism-clike.min.js"],
  ["prismjs/components/prism-c.min.js", "vendor/prism-c.min.js"],
  ["prismjs/components/prism-cpp.min.js", "vendor/prism-cpp.min.js"],
  ["prismjs/components/prism-python.min.js", "vendor/prism-python.min.js"],
  ["prismjs/components/prism-java.min.js", "vendor/prism-java.min.js"],
];

const fonts = [
  ["@fontsource-variable/bricolage-grotesque", "bricolage-grotesque-latin-wght-normal.woff2"],
  ["@fontsource-variable/bricolage-grotesque", "bricolage-grotesque-latin-ext-wght-normal.woff2"],
  ["@fontsource-variable/instrument-sans", "instrument-sans-latin-wght-normal.woff2"],
  ["@fontsource-variable/instrument-sans", "instrument-sans-latin-ext-wght-normal.woff2"],
  ["@fontsource-variable/instrument-sans", "instrument-sans-latin-wght-italic.woff2"],
  ["@fontsource-variable/jetbrains-mono", "jetbrains-mono-latin-wght-normal.woff2"],
  ["@fontsource-variable/jetbrains-mono", "jetbrains-mono-latin-ext-wght-normal.woff2"],
];

async function copy(from, to) {
  const dest = join(staticDir, to);
  await mkdir(dirname(dest), { recursive: true });
  await copyFile(from, dest);
  return to;
}

const copied = [];
for (const [src, dest] of files) {
  copied.push(await copy(join(nm, src), dest));
}
for (const [pkg, file] of fonts) {
  const src = join(nm, pkg, "files", file);
  try {
    copied.push(await copy(src, join("fonts", file)));
  } catch {
    console.warn(`skipped missing font: ${file}`);
  }
}
console.log(`copied ${copied.length} vendor files`);
