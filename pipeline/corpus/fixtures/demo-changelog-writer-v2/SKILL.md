---
name: Changelog Writer
description: Keep CHANGELOG.md tidy — sort entries, fix headings, and date each release.
version: 2.0.0
---

# Changelog Writer

Reads the CHANGELOG.md text you paste in, normalises the headings to Keep a
Changelog order, and dates the release from what you tell it.

## Usage

Paste the file, say which version is being cut, and it returns the tidied text.

## What's new in 2.0.0

- Recognises the "Security" section.
- Keeps footnote links in the order they first appear.

## Audit status

**This version has not been audited.** It is registered on chain so that its
bytes are pinned, and it carries the registry's default `Unaudited` verdict until
an auditor submits one. The v1.0.0 verdict says nothing about these bytes —
that is invariant R4, and the stale-version warning in the API exists to say so
out loud.
