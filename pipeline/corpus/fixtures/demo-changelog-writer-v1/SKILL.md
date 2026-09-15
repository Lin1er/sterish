---
name: Changelog Writer
description: Keep CHANGELOG.md tidy — sort entries, fix headings, and date each release.
version: 1.0.0
---

# Changelog Writer

Reads the CHANGELOG.md text you paste in, normalises the headings to Keep a
Changelog order, and dates the release from what you tell it.

## Usage

Paste the file, say which version is being cut, and it returns the tidied text.

## What it reads

Only the text you paste in. No files are opened and nothing leaves the machine.

## Limitations

- It will not invent entries for commits it was not shown.
- Dates come from you, not from a clock.
