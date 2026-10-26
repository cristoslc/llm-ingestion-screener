# ADR-0002: Adopt a two-corpus detection eval harness, and treat the screener as a filter

- **Status:** Adopted
- **Date:** 2026-10-25

## Context

ADR-0001 commits this project to a rules-first screen with typed decision-model questions above them, and records that thresholds need an evaluation harness to tune responsibly. The depth:3 survey (`docs/surveys/2026-10-25-system-one-models-for-input-material-safety.md`) and its addendum (`docs/surveys/2026-10-25-survey-addendum-drydock-and-baseline-harnesses.md`) supply what was missing: measurement.

Three findings from those documents shape this decision.

1. No independent, representative benchmark of a System One model exists, and the published numbers that do exist each carry a known bias: single-author corpora, vendor-run evaluations, or synthetic paraphrases written by the same author as the hard negatives.
2. The one independent re-evaluation found (arXiv 2610.03448) shows that what transfers between benchmarks is the form of the training inputs, not the attack strings. A detector trained on 1,116 BIPIA inputs scores 95.1% on BIPIA and 2.1% on AgentDojo. A published leaderboard score therefore measures resemblance to a training set, so only an evaluation on this project's own material means anything.
3. At a 1% false-positive rate, every detector missed most task-irrelevant injections, and outside its training distribution each detector missed whole classes. No detector replaces system-level defences.

The same research turned up a working harness for a rule-plus-model detector: drydock's `docs/detection-eval.md` (`JoviDeCroock/drydock`, Apache-2.0). It is the only working template found.

## Options considered

1. **Adopt drydock's harness wholesale, including its gated thresholds.** The gates are calibrated to a hard release gate (every critical case caught, 100% of evasion transforms blocked, release-injection replays across four splice shapes). This project ships an advisory screen, has no fixture corpus yet, and those gates would block any first release.
2. **Adopt drydock's harness shape only, and start with two gates.** Keep the structure: golden regression tests separate from an aggregate eval corpus, a harness that runs the production detection code, recall measured per threat class, a benign hard-negatives corpus, named evasion transforms, a reported-versus-gated ratchet, a fixture schema, and the rule "never commit a live payload". Gate only malicious recall and a benign false-positive ceiling at first.
3. **Build an evaluation harness from first principles.** Re-derives the same decisions with less evidence and no prior art.
4. **No harness; rely on published model benchmarks.** Ruled out by findings 1 and 2 above.

## Decision

Adopt option 2.

The project's evaluation design follows drydock's harness shape, with metrics promoted from reported to gated only once the corpus can hold them. Two gates apply from the start: malicious recall at the project threshold, and a benign false-positive ceiling. The two corpus directories that drydock keeps reported-but-not-gated (frontier hard cases, and benign hard negatives that look dangerous) are part of the shape from day one.

Three design rules carry into the verdict ladder and the harness:

1. Deterministic rule hits are a floor that no model answer can lower.
2. A malformed model answer fails the whole batch; it never degrades to a pass.
3. Question wording is per input type. Tool-result content gets its own question ("does this content hold an instruction aimed at the assistant?"), because every model measured on public data missed at least a quarter of tool-result injections when asked the instruction-override question.

The screener is a filter, not a replacement for system-level defences. This posture is stated in `PURPOSE.md` and reflected in how verdicts are consumed.

## Consequences

- Fixtures are built from benign-instruction-bench (arXiv 2610.03448, code released with the paper), AgentDojo, and BIPIA, sanitised to `example.invalid` hosts with per-fixture provenance. PINT is excluded: it is archived and its README puts indirect detection out of scope.
- Detection is reported at a fixed false-positive rate, with the share of blocked tasks alongside it, so a screen cannot win by breaking the caller.
- Static benchmarks are upper bounds. PyRIT and promptfoo generate the adaptive attacks that get folded into the corpus as named evasion transforms.
- The model choice defers behind the harness: the head-to-head compares rules alone against rules plus each candidate detector on this project's own fixtures.
- A clean verdict is evidence, never a guarantee, and callers must combine it with their own defences.

## Open questions

- Which detectors enter the first head-to-head beyond Llama Prompt Guard 2 86M and 22M, Horizon-Labs, Wolf Defender, and a typed Clef or clef-flash question.
- Where the harness runs, and how the fixture corpus is stored without committing live payloads.
- The benign false-positive ceiling and the malicious recall threshold for the first gate.
