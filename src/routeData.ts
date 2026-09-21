import { execFileSync } from "node:child_process";

import { defineRouteMiddleware } from "@astrojs/starlight/route-data";

// Starlight's built-in `lastUpdated` support only inspects git history under
// `src/content/docs/`. Pages live in `docs/`, so the timestamps are resolved here from a
// single `git log` pass over that directory, keyed by the repository-relative file path
// Starlight already tracks as `entry.filePath`.
let commitDates: Map<string, number> | undefined;

function loadCommitDates(): Map<string, number> {
  const dates = new Map<string, number>();
  let output: string;
  try {
    output = execFileSync("git", ["log", "--format=t:%ct", "--name-status", "--", "docs"], {
      encoding: "utf-8",
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch {
    // A shallow clone or an export without git history simply has no timestamps.
    return dates;
  }

  let timestamp = 0;
  for (const line of output.split("\n")) {
    if (line.startsWith("t:")) {
      timestamp = Number.parseInt(line.slice(2), 10) * 1000;
      continue;
    }
    const separator = line.lastIndexOf("\t");
    if (separator === -1) continue;
    const path = line.slice(separator + 1);
    // `git log` is newest-first, so the first timestamp seen for a path is the newest.
    if (!dates.has(path)) dates.set(path, timestamp);
  }
  return dates;
}

export const onRequest = defineRouteMiddleware((context) => {
  const route = context.locals.starlightRoute;
  if (route.lastUpdated || !route.entry.filePath) return;
  commitDates ??= loadCommitDates();
  const timestamp = commitDates.get(route.entry.filePath);
  if (timestamp) route.lastUpdated = new Date(timestamp);
});
