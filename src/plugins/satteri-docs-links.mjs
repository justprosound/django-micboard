// Rewrites relative Markdown links (for example `../adr/011-introduce-eventbus.md`) to the
// page URLs Starlight generates. Authors keep writing file-relative links, so `docs/` still
// renders correctly on GitHub and no page needed editing during the MkDocs migration.
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { slug as githubSlug } from "github-slugger";

const MARKDOWN_EXTENSION = /\.mdx?$/;
const EXTERNAL_URL = /^[a-z][a-z0-9+.-]*:/i;

/**
 * Convert a docs-relative file path into the site URL Starlight serves it from. This
 * mirrors Astro's content-collection slug generation: slugify each path segment, then
 * treat a trailing `index` as the directory itself.
 */
function pageUrl(docsRelativePath, base) {
  const slug = docsRelativePath
    .replace(MARKDOWN_EXTENSION, "")
    .split("/")
    .map((segment) => githubSlug(segment))
    .join("/")
    .replace(/\/index$/, "");
  const prefix = base.replace(/\/$/, "");
  return slug === "index" ? `${prefix}/` : `${prefix}/${slug}/`;
}

/**
 * Sätteri mdast plugin factory.
 *
 * @param {{ docsDir: string, base?: string }} options
 */
export default function docsLinks({ docsDir, base = "" }) {
  const docsRoot = resolve(docsDir);
  return {
    name: "micboard-docs-links",
    link(node, context) {
      const url = node.url;
      if (!context.fileURL || !url) return;
      if (EXTERNAL_URL.test(url) || url.startsWith("/") || url.startsWith("#")) return;

      const hashIndex = url.indexOf("#");
      const target = hashIndex === -1 ? url : url.slice(0, hashIndex);
      const hash = hashIndex === -1 ? "" : url.slice(hashIndex);
      if (!MARKDOWN_EXTENSION.test(target)) return;

      const documentPath = fileURLToPath(context.fileURL);
      const resolved = resolve(dirname(documentPath), target);
      const docsRelative = relative(docsRoot, resolved).split("\\").join("/");
      // Links that escape `docs/` point at repository files, not pages; leave them alone.
      if (docsRelative.startsWith("..")) return;
      context.setProperty(node, "url", pageUrl(docsRelative, base) + hash);
    },
  };
}
