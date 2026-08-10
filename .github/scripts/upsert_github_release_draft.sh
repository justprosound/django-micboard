#!/usr/bin/env bash
# Helper script to create or verify GitHub release tag and upsert the draft release.
set -euo pipefail

NOTES_ARG="$1"
NOTES_VAL="$2"

TAG_STATE="$RUNNER_TEMP/release-tag.json"
if gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/$RELEASE_TAG" \
  > "$TAG_STATE" 2>/dev/null; then
  if ! jq --exit-status \
    --arg expected_sha "$RELEASE_SHA" \
    '.object.type == "commit" and .object.sha == $expected_sha' \
    "$TAG_STATE" >/dev/null; then
    echo "Release tag $RELEASE_TAG does not target $RELEASE_SHA"
    exit 1
  fi
else
  gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs" \
    --field ref="refs/tags/$RELEASE_TAG" \
    --field sha="$RELEASE_SHA" >/dev/null
fi
RELEASE_STATE="$RUNNER_TEMP/github-release.json"
if gh release view "$RELEASE_TAG" \
  --repo "$GITHUB_REPOSITORY" \
  --json isDraft > "$RELEASE_STATE" 2>/dev/null; then
  if [ "$(jq --raw-output '.isDraft' "$RELEASE_STATE")" != "true" ]; then
    PUBLISHED_ASSETS="$RUNNER_TEMP/published-release-assets"
    mkdir "$PUBLISHED_ASSETS"
    gh release download "$RELEASE_TAG" \
      --repo "$GITHUB_REPOSITORY" \
      --dir "$PUBLISHED_ASSETS"
    EXPECTED_ASSETS=(
      dist/*.whl
      dist/*.tar.gz
      dist/*.spdx.json
      dist/*.publish.attestation
      dist/SHA256SUMS
      dist/RELEASE-METADATA.json
    )
    test "$(find "$PUBLISHED_ASSETS" -maxdepth 1 -type f | wc -l)" \
      -eq "${#EXPECTED_ASSETS[@]}"
    for asset in "${EXPECTED_ASSETS[@]}"; do
      cmp --silent "$asset" "$PUBLISHED_ASSETS/$(basename "$asset")"
    done
    echo "Release $RELEASE_TAG is already published with the expected assets"
    exit 0
  fi
  gh release edit "$RELEASE_TAG" \
    --repo "$GITHUB_REPOSITORY" \
    --title "$RELEASE_TITLE" \
    "$NOTES_ARG" "$NOTES_VAL"
else
  gh release create "$RELEASE_TAG" "${RELEASE_FLAGS[@]}" \
    --repo "$GITHUB_REPOSITORY"
fi
