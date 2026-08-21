# Importing Domain

Follow the backend instructions in `../../AGENTS.md`. This domain owns external-source collection, normalization, runtime job state, and catalog reconciliation. Catalog writes must continue through Catalog services.

## Source-Neutral Business Data

External provider details may remain in protected importing code, runtime files, and internal provenance records. Newly written Catalog and Files business data must not expose provider branding in customer-facing names, descriptions, specifications, variant labels, alt text, slugs, SKUs, filenames, or public metadata.

Do not rewrite existing imported rows without an explicit data-migration request.

## Deferred Work

- Generate neutral variant SKUs for new imports, including when legacy source-prefixed options are reused.
- Use neutral imported filenames and remove provider names and source URLs from exposed file metadata.
- Add private normalized-URL fingerprints with dual-read compatibility for legacy media deduplication.
- Add concurrency, collision, legacy re-import, and media compatibility tests for the neutral identity design.
