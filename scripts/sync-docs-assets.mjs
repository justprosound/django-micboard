// Copies the canonical application icons into the documentation site's public directory.
// The docs site references the same artwork as the app instead of committing a second
// copy, so `public/` is generated output and stays untracked.
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, "micboard", "static", "micboard");
const destination = join(root, "public");

await mkdir(destination, { recursive: true });
for (const asset of ["favicon.png", "logo.png"]) {
  await copyFile(join(source, asset), join(destination, asset));
}
