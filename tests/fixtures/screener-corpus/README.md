# Screening corpus

This directory is the committed detection-eval corpus for `llm-ingestion-screener`. It is the durable product: each fixture is a sanitised, provenance-tagged sample with a truth label. The default eval run loads it offline, screens every fixture through the production code path, and measures recall and false positives.

The corpus is **committed-derived**, not verbatim upstream. A fixture keeps the behavioural shape of the upstream sample and removes the live material: hosts become `example.invalid`, email addresses become `user@example.invalid`, secrets and financial identifiers are stripped, and no working command-and-control or exfiltration target is stored. A reviewer can regenerate the fixtures from the pinned upstreams with [`scripts/corpus/fetch_and_distil.py`](../../../scripts/corpus/fetch_and_distil.py) and audit every row in [`manifest.yaml`](manifest.yaml) without the network.

## Directory jobs

| Directory | Job | Gated? |
|---|---|---|
| `golden/` | Exact-output regression: the verdict and rule set are expected to stay stable. | Yes, through the baseline comparison. |
| `eval/` | Truth-labelled quality set: feeds the gated malicious-recall metric. | Yes, recall at 90% or more. |
| `frontier/` | Hard cases the rules are expected to miss: non-English text, encoded payloads with no decoder, paraphrased task-irrelevant requests, and upstream templates the narrow rules do not match. | Reported, not gated. |
| `benign/` | Benign hard negatives that look dangerous but carry no instruction: imperative vocabulary, serialization markup, legitimate tool output, and quoted attack goals. | Yes, through the false-positive ceiling below 10%. |
| `transforms/` | Named evasion variants derived from a base fixture, with `derived_from` and `transform`. | Reported, not gated. |

The ingestion surface is a first-class field and a filename prefix, not a directory. That keeps recall-by-surface and false-positive-by-surface computable without twenty near-empty directories.

## Current shape

The Phase 4 corpus holds 145 fixtures: 5 golden, 56 eval, 20 frontier, 32 benign, and 32 transforms.

Malicious classes meet at least eight samples each: `agent-directed-imperative`, `instruction-override`, `tool-result-injection`, `exfiltration-request`, `tool-invocation-lure`, `task-irrelevant-injection`, `encoded-obfuscated`, and `non-english`. Benign classes meet at least six each: `benign-imperative-vocabulary`, `benign-serialization-markup`, `benign-legitimate-tool-output`, and `benign-quoted-instruction`.

Every fixture in the five directories is covered by exactly one manifest row. The loader rejects a corpus with a missing row, an extra row, a benchmark-derived fixture whose provenance does not name its pinned commit, or a row whose surface, label, class, or source disagrees with the fixture. It also rejects a transform fixture that names a transform outside the four, that sits in the wrong transform directory, or whose `derived_from` names a fixture that does not exist.

## Named evasion transforms

The plan's section 5.3 names four transforms. Each is a derived fixture with `derived_from` and `transform`, and each exists to keep a specific past bug fixed: when a rule stops catching its shape, that transform's blocked rate drops and the report says so. Every manifest row records the same `derived_from` and `transform` (null outside `transforms/`); the manifest format is `v2` for those fields. The floor is **eight derived fixtures per transform**, 32 in total, recorded as the `transforms` floor in [`tests/eval/gates.yaml`](../../../tests/eval/gates.yaml). Eight matches the malicious-class floor the Phase 3 corpus already holds, and it is the largest count the corpus can support: a transform base must carry the same threat class, and `exfiltration-request` and `encoded-obfuscated` each hold eight eval fixtures. `bracketify-member-access` needs a base with a call primitive; only five encoded fixtures carry one, so three samples repeat three bases with a different receiver name.

| Transform | Rewrite | Eight samples derived from |
|---|---|---|
| `split-string-literals` | The destination host becomes adjacent string pieces, `"http://" + "example" + ".invalid" + "/collect"`. | The eight exfiltration fixtures. |
| `bracketify-member-access` | A call primitive's member access becomes an index expression, `atob(` to `globalThis['atob'](`. | The five encoded fixtures with a call primitive, three repeated with a different receiver. |
| `base64-wrap` | The whole payload becomes `eval(atob("<base64 of the payload>"))`. | The eight encoded fixtures. |
| `push-past-window` | At least 64 KiB of filler sits ahead of the payload. | Four rule families: exfiltration, agent-directed, instruction-override, and tool-result. |

Two numbers are reported per transform, and neither is gated:

- **Blocked rate** is the share of a transform's derived fixtures that still reach their expected verdict. A fixture is blocked when its verdict is at or above the base fixture's `expect_min_verdict`.
- **Rule retention** is the share of the base fixtures' rule hits that still fire after the rewrite. A rule that no longer fires on any derived fixture is recorded as **defeated** for that transform.

The committed results, as measured by the current rules:

| Transform | Blocked rate | Rule retention | Rule defeated |
|---|---|---|---|
| `base64-wrap` | 8 of 8, 1.0000 | 1.0000 | none; the visible decoder keeps `rule.encoded-execution` firing. |
| `bracketify-member-access` | 0 of 8, 0.0000 | 0.0000 | `rule.encoded-execution`; the index expression hides the `atob(` and `eval(` primitives. |
| `push-past-window` | 8 of 8, 1.0000 | 1.0000 | none; the screen reads the whole material, so the filler changes nothing. |
| `split-string-literals` | 0 of 8, 0.0000 | 0.0000 | `rule.exfiltration-request`; the rule needs a contiguous URL. |

The overall reported values are a blocked rate of 16 of 32 (0.5000) and a rule retention of 18 of 34 (0.5294). The two misses are findings for the report and the PR, not a patch: no rule or threshold was changed to catch them. `push-past-window` is fully caught today and stays in the corpus as a guard, so a future scan-time truncation would drop its blocked rate and show up in the report.


## Upstreams and pins

| Upstream | Pin | Licence | What the corpus uses |
|---|---|---|---|
| [`ethz-spylab/agentdojo`](https://github.com/ethz-spylab/agentdojo) | `089ed468cf3ed0322acc66b0211f26d9d90dbf60` | MIT | Injection goals, attack frames, tool names, and benign environment data. |
| [`microsoft/BIPIA`](https://github.com/microsoft/BIPIA) | `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` | MIT for the repository, with dataset-specific terms for the `benchmark` contexts | Text attack goals and benign task prompts. |
| [`lzwhehe/benign-instruction-bench`](https://github.com/lzwhehe/benign-instruction-bench) | `5d0ae7c438a7b01be2ac0a2e8bc943e45c8f851f` | MIT | Method and imperative-density vocabulary; the repository rebuilds its data from public sources rather than redistributing it. |

BIPIA is archived (read-only since 2026-09-16). Its `benchmark/` tree splits into attack-goal JSON, which the repository licence covers, and task context data with separate terms. The WebQA and Summarization tasks require generating context data under the NewsQA and XSum terms, and the EmailQA and TableQA context data carry the WikiTableQuestions and Stack Exchange terms. None of those terms were read as permitting redistribution of derived fixtures, so **no BIPIA context task is included**. The corpus uses only the MIT-licensed attack-goal and benign-task JSON. This exclusion is recorded here and in the manifest's `pins` and `sanitisation` rows.

The `benign-instruction-bench` repository does not redistribute AgentDojo, tau-bench, InjecAgent, or BIPIA data. It ships code, analysis, and score files. The corpus therefore cites it for the benign-replay method and the imperative-density vocabulary, while the benign tool outputs themselves come from AgentDojo's MIT-licensed environment data.

The three upstreams are English-only, so the `non-english` class could not reach its eight-sample floor from upstream bytes. It is synthetic: eight translations of the direct-address shape across five surfaces, recorded as `synthetic-adversarial` and held in `frontier/`. The `benign-serialization-markup` class is also synthetic; it models the markup shape that produces false positives without quoting an upstream attack. Every other class uses upstream material.

## Sanitisation policy

Every generated fixture passes the same policy:

- Any URL is replaced with `http://example.invalid/collect` when the surrounding text is an exfiltration or command-and-control position, and with `https://example.invalid/page` otherwise.
- Any bare host is replaced with `example.invalid`.
- Email addresses become `user@example.invalid`.
- IBANs, card numbers, and phone numbers are replaced with inert placeholders.
- A benchmark-derived fixture never stores the verbatim upstream attack string in a live form. The fixture keeps the goal and the frame and drops the destination.
- A fixture whose upstream is not a benchmark carries a `provenance` line that says it is synthetic and names the shape it models.

The loader rejects a non-`example.invalid` host in an exfiltration or command-and-control position, and rejects a live IPv4 address in that position. It does not reject an ordinary documentation URL with no exfiltration context.

## Regenerating the corpus

The distiller is a maintenance tool. It is not part of the test gate and it makes no network call during `uv run pytest -q`.

```bash
python scripts/corpus/fetch_and_distil.py --check
python scripts/corpus/fetch_and_distil.py --prune
uv run python scripts/eval-build-cassette.py
uv run python -m llm_ingestion_screener.eval run --update-baseline
```

`--check` exits non-zero when the committed fixtures or manifest differ from what the pinned upstreams produce. `--prune` deletes stale fixtures that the recipe no longer produces. Transform fixtures are not hand-written: the recipe applies the named rewrite in `scripts/corpus/recipes.py` to a base fixture, so the distiller reproduces every derived file from its base. The cassette builder writes one neutral synthetic answer per fixture and question; it is test data, not measured model output. The baseline update is deliberate and must be reviewed.

For development without network, pass `--source-dir` pointing at verified local clones named `agentdojo`, `BIPIA`, and `benign-instruction-bench`. The script checks each checkout's `HEAD` against the pin and each fetched file against a recorded SHA-256.

## Known gaps recorded in `frontier/`

The deterministic rules are English-only, need a visible decoder for encoded payloads, need an http(s) URL for an exfiltration hit, and match a narrow agent-address frame. The frontier set records each gap: eight non-English injections, four encoded payloads with no decoder, four paraphrased task-irrelevant requests, two exfiltration requests with no URL, the upstream important-instructions template, and the upstream ignore-previous typo. The transform set records two more: a split destination host defeats the contiguous-URL rule, and an index expression defeats the visible-decoder rule. They are reported, not gated, and no rule or threshold was changed to catch them.
