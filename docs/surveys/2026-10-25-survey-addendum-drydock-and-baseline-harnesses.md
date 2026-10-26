# Addendum to the depth:3 survey: drydock, and baseline tooling to benchmark against

- **Date:** 2026-10-25
- **Author:** top-level workspace thread (`thr_t6uy5w4dmf`), answering the operator's question about drydock and existing baseline tooling
- **Status:** working note; held in the gitignored `.tmp/` tree until the survey and this addendum are landed as a docs pull request
- **Relation to the survey:** supplements `2026-10-25-system-one-models-for-input-material-safety.md`. It does not replace it. Where the two disagree, this addendum is newer.

---

## Screening log for this addendum's own fetches

Four pages fetched in full, scanned for agent-directed imperatives before use. Two flagged, both quoting attack material as research data; neither was followed. No page issued an instruction to this reading agent. In this committed copy the live payload strings are described by class instead of reproduced, under this project's rule that no raw hostile material is committed.

| # | Page URL | Verdict | Flagged N | Notes |
|---|---|---|---|---|
| 1 | https://github.com/JoviDeCroock/drydock | clean | 0 | Descriptive maintainer documentation |
| 2 | https://raw.githubusercontent.com/JoviDeCroock/drydock/main/docs/detection-eval.md | clean | 0 | Methodological documentation only |
| 3 | https://github.com/lakeraai/pint-benchmark | flagged | 1 | Dataset-format example carries a labelled instruction-override sample; quarantined as test data (payload text withheld from this copy) |
| 4 | https://arxiv.org/html/2610.03448v1 | flagged | 3 | Quotes AgentDojo attack templates and BIPIA attack goals as research data; quarantined, not followed (payload text withheld from this copy) |

Search-result snippets were used for pointers only (PyRIT, BIPIA, Vigil, the benchmark spread) and are marked unverified below where a claim rests on them.

---

## 1. What drydock actually is

**Repo:** `JoviDeCroock/drydock` — public, Apache-2.0, 32 stars, 2 forks, ~1,895 commits. Hosted service at drydock.org; self-hostable on your own Cloudflare account. Author is Jovi De Croock (Preact maintainer). The repo carries `.agents/`, `.claude/`, and `.codex/` directories, so it is agent-authored and agent-maintained.

**Product definition, from its own README:** "Drydock is pre-publish package security for maintainers. It reviews the exact npm, PyPI, or VS Code artifact before publication, compares it with a tag-aware published baseline, runs deterministic supply-chain checks, optionally sends changed-file evidence to Cloudflare Workers AI, and saves a review report."

It is **not** a prompt-injection screener product. It is a release gate for package maintainers that happens to include a prompt-injection screen as one advisory lane over the changed text inside a package. The AI lane was ported from an unmerged Jev screen branch, which is why the survey found it: a direct Jev to Clef migration on the same wire API.

**Two release modes with different authority:**

- **Workflow Gate (enforced)** — a GitHub deployment-protection rule holds the protected publish job until the maintainer accepts or rejects the review in Drydock. The same job then publishes the exact reviewed bytes.
- **Stage Watchtower (advisory, npm only)** — Drydock reviews the staged tarball and records advice; npm maintainers still approve or reject independently. Drydock never publishes and never collects npm approval codes.

**Sponsorship:** Aikido Security funds development. The README states sponsorship does not influence detection rules, findings, or risk scoring.

### Why it matters as prior art for this project

Drydock's stated security posture is almost line-for-line the posture `llm-ingestion-screener` is aiming at:

- "Package artifacts are **untrusted evidence and are never executed**."
- "**AI review is advisory** and on by default behind the `ai-review` killswitch, and **cannot downgrade deterministic findings**."
- The sandbox can fetch only through constrained brokers and gateways, and returns bounded metadata and text evidence.
- Raw tarballs are not retained by default; persisted reports use redacted summaries and canonical report JSON.

Two design rules worth copying outright:

1. **Deterministic findings are a floor the AI layer cannot lower.** This maps directly onto the planned verdict ladder: rules set a minimum severity, a model question can raise it, nothing can talk it down.
2. **The screen never quotes the span, never lowers a finding, never lifts a release gate, and discards the whole batch on a malformed answer.** The survey recorded the first three from PR #759; the "discard the batch on malformed answer" rule is the fail-loud behaviour this repo's `AGENTS.md` already mandates.

### The most valuable artifact found: drydock's detection eval harness

`docs/detection-eval.md` describes a working eval harness for a rule-plus-model detector. It is a directly reusable template for the harness this project needs. Its structure:

- **Two corpora with two different jobs.** Golden regression tests assert exact rule output and exist to catch regressions. The eval harness asserts aggregate quality metrics and fails only when a gated threshold regresses.
- **The harness runs the real production detection code**, so it cannot drift from what ships.
- **Corpus layout:** `cases/` (golden), `cases-pypi/`, `cases-atpm/`, `cases-vscode/`, plus two eval-only directories — `cases-frontier/` (truth-labelled hard cases the rules are expected to miss; reported but not gated) and `cases-benign/` (benign hard negatives that legitimately look scary; reported but not gated).
- **Fixture schema** carries `verdict` (malicious or benign), `threatClass`, `source` (`synthetic`, `synthetic-adversarial`, `real-sanitized`, `benign-popular`), `provenance` (required for `real-sanitized`), `intent`, `expectMinRisk`, and `expectAnyRule`.
- **Recall is measured per threat class**, so blind spots stay visible instead of averaging into one number.
- **Gated metrics:** malicious recall at or above 90%; every critical case caught; benign regression positives matching an acknowledged list exactly; benign false-positive rate under 10%; evasion transforms leaving 100% of samples blocked; release-injection replays with no misses across four splice shapes over at least 20 cases each.
- **Reported but not gated:** frontier recall and evasion code-rule retention. They are allowed to start red, and gating them is the next ratchet step.
- **The ratchet discipline:** a metric is promoted from reported to gated only once the corpus and the detector have improved enough to hold it. The false-positive gate landed together with weighted multi-signal scoring; full-bytes scanning landed before `pushPastWindow` was gated.
- **Evasion transforms are named individually** — string-splitting, bracketified member access, base64 wrapping, and pushing the payload past a 64 KB scan window — because real attacks evaded the regexes that way. Each transform exists to keep a specific past bug fixed.
- **Real-package false-positive sweep:** pulls consecutive releases of popular packages from the public registry, runs each pair through the production path with AI review off, and treats a flagged pair as a triage candidate. A confirmed false positive becomes a distilled fixture before the rule changes, "so the gated eval keeps the fix".
- **Fixture sanitation rule:** replace exfiltration and command-and-control hosts with `example.invalid`, strip real secrets and tokens, keep the behavioural shape of the technique, and record provenance naming the incident. Stated in the doc as **"Never commit a live payload."** That is the same rule this project's `AGENTS.md` needs for hostile text.
- **Reporting:** the eval writes a gitignored Markdown and JSON report, fails the command if the report cannot be written, and posts a sticky pull-request comment plus a CI artifact so reviewers see gated numbers, frontier misses, benign false positives, and evasion robustness.

### drydock's measured Clef numbers (from PR #759, already in the survey)

Restated here with the eval-harness context: a 127-span labelled corpus (73 injections, 54 benign, 44 hard negatives). Hazard AUROC 0.971 for Clef against 0.862 for clef-flash. Clef caught 40 of the 42 injections the phrase rules missed, with 4 of 44 hard-negative false fires. Rules union screen reached 89.9% precision and 97.3% recall, against 88.6% and 42.5% for rules alone. Three typed questions per span, thresholds 0.80 and 0.85 with severity 1.5, about 710 input tokens per span. The PR itself acknowledges that 38 of the 42 rule misses are synthetic paraphrases written by the same author as the hard negatives, and the flag ships default-off pending production fire-rate telemetry.

---

## 2. Baseline tooling to benchmark against

The survey named PINT, promptfoo, and Garak as complement tools. That was too narrow, and one of the named tools cannot do the job. Here is the inventory in three layers.

### 2.1 Benchmarks that score the screen as a classifier

| Instrument | What it measures | Status | Fit for this project |
|---|---|---|---|
| `lzwhehe/benign-instruction-bench` | Fifteen detectors and two judges on AgentDojo and τ-bench tool outputs plus BIPIA, with benign-by-construction and differential-replay labels | New (Oct 2026, arXiv 2610.03448), code released with the paper | **The closest fit found.** It reproduces every number in the paper from public benchmarks |
| AgentDojo (`ethz-spylab/agentdojo`) | Security and utility jointly, 629 security cases and 97 tasks; ships its own detector baseline | MIT, 914 stars, NeurIPS 2024 D&B, SafeBench prize | Strongest choice for tool-calling agents, because it stops a defence winning by breaking the agent |
| BIPIA (`microsoft/BIPIA`) | The first indirect-injection benchmark; 5 tasks, 250 attacker goals, 626,250 train and 86,250 test prompts | **Archived 2026-09-16, read-only** | The reference for injection through retrieved content. Still usable, no longer maintained |
| InjecAgent | 1,054 cases, 17 user tools, 62 attacker tools | ACL Findings 2024 | Closest to an agent-with-tools threat model |
| τ-bench | Customer-service agents over JSON databases; different authors, domains, tools, and format from AgentDojo | Open | The second agent benchmark any ranking claim should be checked against |
| Agent Security Bench | 10 scenarios, 13 backbones, 400+ tools; 84.30% peak attack success | ICLR 2025 | Broadest attack surface |
| MCPTox | 45 real MCP servers | Recent | Relevant if this project ever screens MCP tool output |
| Open-Prompt-Injection | Attack framework and benchmarking platform | USENIX Security 24 | Attack-side reference |
| CyberSecEval 2 | Meta's suite; 26 to 41% attack success on every model tested | Open | Vendor-neutral comparison point |
| Lakera PINT (`lakeraai/pint-benchmark`) | Direct prompt injection and jailbreak detection, 4,314 inputs across 28 languages | **Archived 2026-08-05; itself a fork of `CheckPointSW/pint-benchmark`** | **Cannot validate this job.** Its README states: "The Meta Prompt Guard score is based on Jailbreak detection. **Indirect detection scores are considered out of scope for this benchmark and have not been calculated**" |

PINT's published scores, for reference: Lakera Guard 95.22%, AWS Bedrock Guardrails 89.24%, Azure AI Prompt Shield 89.12%, `protectai/deberta-v3-base-prompt-injection-v2` 79.14%, Llama Prompt Guard 2 86M 78.76%, Google Model Armor 70.07%, Aporia Guardrails 66.44%, Llama Prompt Guard v1 61.82%. All measured 2025-05 to 2025-08.

### 2.2 Offensive generators, for building our own corpus

- **PyRIT** (`Azure/PyRIT`, Microsoft) — open-sourced 2026-09-10 under MIT; ~4k stars, 117 contributors, latest release v0.11.0 February 2026; Python 3.10 to 3.13; paper arXiv 2410.02828. Built by Microsoft's AI Red Team out of work on Bing Chat and Copilot. Orchestrates `PromptSendingAttack`, converters (`Base64Converter`, `TranslationConverter`), `CrescendoAttack`, Tree of Attacks with Pruning, and cross-domain prompt injection. It is an **offensive generator, not a measurement harness**: it produces attacks and sends them, and you supply the scorer.
- **Garak** (NVIDIA) — LLM vulnerability scanner with injection probes; already in the survey.
- **promptfoo** — the indirect-prompt-injection plugin plants adversarial instructions in retrieved content to test your own application; already in the survey.
- **AutoDojo** (arXiv 2606.15057) — adaptive, generative indirect injection built on AgentDojo and AgentDyn under a black-box setting. Relevant because the static benchmarks are static; an adaptive attacker lowers every detection number measured on them.

### 2.3 Reference detectors to run head-to-head, all CPU-viable

The survey's ranking missed a whole class of small **agent-oriented** detectors released in 2026. From the independent re-evaluation (arXiv 2610.03448), detection rate at 1% false-positive rate:

| Detector | Year | Params | Trained on agent inputs | AgentDojo matched | AgentDojo shifted | τ-bench | BIPIA |
|---|---|---|---|---|---|---|---|
| Horizon-Labs | 2026 | 308M | yes | **82.2%** | **87.9%** | **100.0%** | 37.7% |
| Wolf Defender | 2026 | 308M | evaluated on agent data | **73.8%** | **83.9%** | **90.8%** | 3.5% |
| Prismor | 2026 | 1.5B | no | 72.2% | 79.4% | 15.2% | 4.0% |
| Qualifire Sentinel | 2025 | 396M | no | 61.1% | 66.4% | 21.9% | 4.6% |
| Prompt Guard 2 86M | 2025 | 279M | no | 69.4% | 78.8% | 57.9% | 10.4% |
| Prompt Guard 2 22M | 2025 | 71M | no | 60.9% | 63.6% | 60.8% | 31.7% |
| Sentinel v2 | 2025 | 596M | no | 20.8% | 16.5% | 68.7% | 20.2% |
| Sheltron | 2026 | 68M | yes | 20.1% | 26.4% | 95.2% | 57.2% |
| PIGuard | 2025 | 184M | no | 2.1% | 7.9% | 52.7% | **95.1%** |
| ProtectAI v2 | 2024 | 184M | no | 0.5% | 0.8% | 10.1% | 0.7% |
| Qwen2.5-7B judge | — | 7B | — | 57.4% | 64.4% | 54.3% | 14.9% |
| Llama-3.1-8B judge | — | 8B | — | 55.3% | 61.9% | 78.3% | 8.3% |

Their false-positive rates at the default threshold, on benign tool outputs with no injection present, range from 0.0% (Horizon-Labs and Prompt Guard 2 22M on AgentDojo, Prompt Guard 2 86M and Wolf Defender on τ-bench) to 30.1% for ProtectAI v2 and 29.5% for PIGuard on AgentDojo. At its default threshold ProtectAI v2 would stop 69.1% of AgentDojo tasks and 80.3% of τ-bench tasks. False-positive rank transfers between the two agent benchmarks (Kendall τ = 0.67, p = 0.001); detection rank does not.

Also worth including: **Vigil** (Deadsimply, MIT) and **Qwen3Guard 0.6B**, both open and CPU-viable; `deepset/deberta-v3-base-injection` and `fmops/distilbert-prompt-injection`, which the re-evaluation excluded because they flagged **every** benign README chunk; and **Prompt Guard 1**, which remains the second-best detector on task-irrelevant injections at 39%.

---

## 3. What this forces us to revise

**The survey's number-one CPU pick does not survive scrutiny for this job.**

The survey ranked Meta's Llama Prompt Guard 2 86M first on the CPU floor, on the strength of Meta's own AgentDojo attack-prevention-rate of 81.2% at a 3% utility cost. The independent re-evaluation measures the same model at 69.4% detection at 1% false-positive rate on AgentDojo's matched tool outputs and 57.9% on τ-bench, against 82.2% and 100.0% for Horizon-Labs and 73.8% and 90.8% for Wolf Defender. Its explanation is that AgentDojo's own attack templates are explicit instructions addressed to the model, resembling direct prompt injections, while injecAgent's attacks inside product names and BIPIA's inside emails and tables do not. A detector high on one is often weak on the other.

Three consequences:

1. **Add Horizon-Labs and Wolf Defender to the CPU tier.** Both are roughly 308M parameters, both keep false positives near zero on benign tool outputs, and both beat Prompt Guard 2 on both agent benchmarks. Neither is a System One model, so they sit alongside the Clef/Kev question rather than replacing it.
2. **The survey's framing of Prompt Guard 2 needs a caveat, not a deletion.** It is still the strongest of the older-generation CPU classifiers, it is cheap and well-downloaded, and its 22M variant matches it closely at a quarter the size. It is just not the ceiling it looked like.
3. **PINT cannot be the validation instrument.** The survey called it "the natural instrument for the independent head-to-head". Its own README excludes indirect detection, which is the entire job here. Use `benign-instruction-bench`, AgentDojo, and BIPIA instead.

**The training-data finding is the sharpest lesson in the paper, and it validates this project's premise.** Detectors work on inputs whose form resembles their training inputs. PIGuard was trained on 1,116 full BIPIA inputs and scores 95.1% on BIPIA while landing at 2.1% on AgentDojo and ranking thirteenth of fifteen. It saw 53 of 62 InjecAgent attacks, but only as short prompts, and inside tool outputs it detects the attacks it saw no better than the ones it did not — 52.1% against 55.8%. Horizon-Labs shares no data with any benchmark and leads both agent benchmarks, because it was trained on agent-style inputs. So a benchmark score measures resemblance, and the only evaluation that means anything is one run on our own tool outputs.

**A free engineering win the paper hands us:** removing serialization markup or declaring the input type cuts default-threshold false positives by up to about twentyfold. Stripping HTML from benign READMEs took PIGuard's false-positive rate from 24.6% to 5.6%. Removing YAML keys from AgentDojo tool outputs took it from 20.0% to 6.7% at unchanged detection. Sheltron's `tool_result` source token took its clean-output false-positive rate from 28.6% to 10.6% on AgentDojo and from 85.6% to 4.4% on τ-bench. Format discipline is cheap and it belongs in our design, not in a later optimisation.

**And the ceiling to plan against:** at a 1% false-positive rate, the best detectors caught 82% of matched AgentDojo injections and 100% of τ-bench ones, but **every approach missed most task-irrelevant injections** — the class that asks the model to do something unrelated and harmless. Outside its training distribution, every detector misses whole classes. The paper's own conclusion is that a detector is a filter to combine with system-level defences, never a replacement for them. This project is a filter; it should say so in `PURPOSE.md`.

---

## 4. Recommended baseline plan

1. **Adopt drydock's eval-harness shape first, before choosing a model.** Golden regression corpus for exact rule output, a separate truth-labelled eval corpus, per-threat-class recall, a gated false-positive ceiling, named evasion transforms, and frontier cases that are allowed to start red. It is the one working template found, and it is free.
2. **Build the fixture corpus from `benign-instruction-bench`, AgentDojo, and BIPIA**, sanitised to `example.invalid` hosts with no live payloads, and record provenance per fixture the way drydock does.
3. **Run the head-to-head on our own fixtures**, not on a public leaderboard: rules alone, rules plus Prompt Guard 2 86M and 22M, rules plus Horizon-Labs, rules plus Wolf Defender, rules plus a typed Clef or clef-flash question, and rules plus a task-aware judge. Score detection at a fixed 1% false-positive rate, and report blocked-task share alongside it.
4. **Use PyRIT and promptfoo to generate attacks the static benchmarks do not contain**, then fold the survivors into the corpus as evasion transforms. Static benchmarks understate the attacker.
5. **Carry drydock's two design rules into the verdict ladder:** deterministic findings set a floor the model cannot lower, and a malformed model answer fails the whole batch rather than degrading to a pass.

## 5. Unverified in this addendum

- PyRIT's star count, contributor count, and 2026-09-10 open-source date come from third-party write-ups, not from the Microsoft repository itself.
- Vigil's licence and capability are search-snippet level; the repository was not fetched.
- Horizon-Labs, Wolf Defender, Sheltron, Prismor, Qualifire Sentinel, and Sentinel v2 were not fetched directly. Every number for them comes from the arXiv re-evaluation's Table 2, which is a single paper by one author, and their detector cards were not read.
- The re-evaluation itself is a single-author preprint. Its own stated limitations: both agent benchmarks are simulations with synthetic YAML and JSON records; the authors chose the τ-bench injection point and attack set themselves; and all attacks are static, so its detection numbers are upper bounds.
- InjecAgent, Agent Security Bench, MCPTox, Open-Prompt-Injection, CyberSecEval 2, and AutoDojo were reached through search snippets only.
