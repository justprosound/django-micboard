import { docsSchema } from "@astrojs/starlight/schema";
import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";

// Pages stay in `docs/` rather than moving to `src/content/docs/` so that the tree keeps
// rendering on GitHub, existing relative links keep resolving, and the migration away from
// MkDocs required no file moves.
export const collections = {
  docs: defineCollection({
    loader: glob({ base: "./docs", pattern: "**/[^_]*.{md,mdx}" }),
    schema: docsSchema(),
  }),
};
