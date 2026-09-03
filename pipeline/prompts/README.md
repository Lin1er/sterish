# Pipeline prompts

Every prompt the pipeline sends to a model lives here as a `.md` file and is read from disk at
runtime (`sterish_pipeline.llm.load_prompt`). Nothing is hardcoded in a `.py`.

The reason is review, not tidiness: a prompt is the part of an audit system most likely to be
tweaked and least likely to be noticed in a diff. As files, a wording change shows up in the PR
next to the code and the tests, and `git log -- pipeline/prompts/` is a complete history of what
the auditor was ever told to do.

## Contract shared by all prompts

| | |
|---|---|
| Model | `PipelineConfig.llm_model` (default `claude-sonnet-5`) |
| Key | `ANTHROPIC_API_KEY` environment variable **only**. Never a config file, never a literal. |
| Output | Structured, via tool use with `strict: true` — the model cannot return prose |
| On failure | Fail-soft. The deterministic baseline stands; the reason is recorded in the internal report (`AuditReport.llm_notes`), never in the verdict document |
| Authority | **Advisory only.** `policy.tighten` lets a model raise a verdict, never lower one |

## Files

### `stage1_injection_scan.md`

*Second opinion on the text scan.* Input: a JSON object with the skill's `skill_id`, the
declared capabilities, and every scanned text field (`field_path` + `text`), plus the
deterministic findings already raised. Output: tool call `report_injection_findings` with
`findings[]`, each `{field_path, pattern_id, severity, description, evidence}` and
`pattern_id` drawn from the deterministic detector list (or `other`).

Purpose: catch phrasings the regexes miss — paraphrase, another language, an instruction split
across sentences. It cannot clear a finding the deterministic scanner raised; the merge is
union, not replacement.

### `stage3_synthesis.md`

*Verdict synthesis.* Input: a JSON object with the manifest summary, the stage-1 findings
(declared + injection), the stage-2 result, and the deterministic baseline verdict/risk/score.
Output: tool call `emit_verdict` with `{verdict, risk, score, recommendation, rationale}`.

Purpose: a judgement over the whole picture, in the frozen vocabulary. The output is merged
with `policy.tighten`, so `SAFE` over a deterministic `DANGEROUS` changes nothing at all.

## Editing rules

1. Keep the output contract paragraph in sync with the tool schema in `llm.py`. The schema is
   what the API enforces; the prompt is what makes the model's answer useful.
2. Never put an example that contains a real credential, key, or host you do not control.
3. A prompt change that alters the verdict of a fixture must arrive with the test update in the
   same commit.
