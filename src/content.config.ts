import { docsSchema } from "@astrojs/starlight/schema";
import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

// Pages stay in `docs/` rather than moving to `src/content/docs/` so that the tree keeps
// rendering on GitHub, existing relative links keep resolving, and the migration away from
// MkDocs required no file moves.
//
// Every page is exactly one Diátaxis type and says who it is for. Both fields are required, so
// a page without them fails the build instead of landing unsorted.
export const collections = {
  docs: defineCollection({
    loader: glob({ base: "./docs", pattern: "**/[^_]*.{md,mdx}" }),
    schema: docsSchema({
      extend: z.object({
        type: z.enum(["tutorial", "how-to", "reference", "explanation"]),
        audience: z.enum(["staff", "developer", "both"]),
      }),
    }),
  }),
};
