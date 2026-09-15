---
name: Release Notes
description: Turn a list of merged pull requests into readable release notes.
version: 1.0.0
---

# Release Notes

Give it a list of merged pull requests and it groups them into Added, Changed,
Fixed and Removed, then writes the section in the tone the previous release used.

## Usage

"Write release notes for the 14 PRs merged since v0.9" returns a markdown section
you can paste into CHANGELOG.md.

## What it reads

Only the text you paste in. It opens no files, reaches no network, and keeps no
state between runs.

## Limitations

- Grouping is heuristic; a PR title that says nothing gets grouped as Changed.
- It does not read your repository, so it cannot check that a PR was really merged.
