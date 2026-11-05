# Test coverage matrix

Master coverage matrix for `llm-ingestion-screener`. Each row is a behaviour; each column says which test covers it and at which kind (happy, sad, edge, corner).

## CLI

| Behaviour | Test | Kind |
|---|---|---|
| CLI reports its version | `tests/test_cli.py::test_version_flag_prints_version` | happy |
| CLI with no arguments prints usage and exits zero | `tests/test_cli.py::test_no_args_prints_help_and_exits_zero` | edge |

## Rule engine

| Behaviour | Test | Kind |
|---|---|---|
| Default rule ids are stable and unique | `tests/test_rules.py::test_default_rule_ids_are_stable_and_unique` | happy |
| Every default rule fires on its shortest sanitised proof | `tests/test_rules.py::test_each_default_rule_fires_on_its_shortest_proof` | happy |
| Benign prose does not fire a rule | `tests/test_rules.py::test_benign_prose_does_not_fire_a_rule` | edge |
| A rule hit records the verbatim excerpt and offsets | `tests/test_rules.py::test_rule_hit_records_the_verbatim_excerpt_and_offsets` | happy |
| Hits are returned in document order | `tests/test_rules.py::test_scan_returns_hits_in_document_order` | edge |
| Duplicate rule ids are rejected | `tests/test_rules.py::test_rule_engine_rejects_duplicate_rule_ids` | sad |
| An empty rule engine is rejected | `tests/test_rules.py::test_rule_engine_requires_at_least_one_rule` | sad |
| A rule cannot imply clean | `tests/test_rules.py::test_rule_cannot_imply_clean` | sad |
| Rule ids must use the stable prefix | `tests/test_rules.py::test_rule_ids_must_use_the_stable_prefix` | sad |

## Typed questions and answers

| Behaviour | Test | Kind |
|---|---|---|
| `noul`, `choice`, and `score` serialise to the System One wire shape | `tests/test_questions.py::test_noul_question_serialises_to_the_systemone_wire_shape`, `test_choice_question_serialises_criteria_as_a_mapping`, `test_score_question_serialises_criteria_as_an_ordered_list` | happy |
| Question invariants reject bad criteria, counts, and duplicate labels | `tests/test_questions.py::test_noul_rejects_criteria`, `test_choice_requires_at_least_two_options`, `test_choice_rejects_duplicate_labels`, `test_score_requires_between_two_and_ten_levels`, `test_score_rejects_duplicate_levels` | sad |
| Empty question ids and instructions are rejected | `tests/test_questions.py::test_question_rejects_empty_id_or_instructions` | sad |
| Question ids are unique in a set, and a set cannot be empty | `tests/test_questions.py::test_question_ids_are_unique_in_a_question_set`, `test_a_question_set_cannot_be_empty` | sad |
| The default set covers all three kinds | `tests/test_questions.py::test_default_question_set_covers_all_three_kinds` | happy |
| Tool-output material gets its own instruction question | `tests/test_questions.py::test_tool_output_uses_its_own_instruction_question` | happy |
| Surface selection returns the right set and rejects an unknown surface | `tests/test_questions.py::test_questions_for_surface_selects_the_right_set`, `test_questions_for_surface_rejects_an_unknown_surface` | happy, sad |
| `noul` derives probabilities and confidence | `tests/test_answers.py::test_noul_derives_probabilities_and_confidence` | happy |
| `choice` keeps label probabilities and confidence | `tests/test_answers.py::test_choice_answer_keeps_label_probabilities_and_confidence` | happy |
| `score` maps indices to labels | `tests/test_answers.py::test_score_answer_maps_indices_to_labels` | happy |
| Missing, extra, truncated, and wrong-kind answers fail the batch | `tests/test_answers.py::test_missing_answer_fails_the_batch`, `test_extra_answer_fails_the_batch`, `test_truncated_answer_fails_the_batch`, `test_wrong_answer_kind_fails_the_batch` | sad |
| Probabilities must sum to one, match labels, and have a known chosen label | `tests/test_answers.py::test_probabilities_must_sum_to_one`, `test_probabilities_must_match_the_choice_labels`, `test_chosen_choice_must_be_a_known_label` | sad |
| Confidence must be a probability, and booleans and non-finite numbers are rejected | `tests/test_answers.py::test_confidence_must_be_a_probability`, `test_booleans_are_not_numbers`, `test_non_finite_numbers_are_rejected` | sad |
| A score legend must match the question criteria | `tests/test_answers.py::test_score_legend_must_match_the_question_criteria` | sad |
| Answer probabilities are read-only and answers follow question order | `tests/test_answers.py::test_answer_probabilities_are_read_only`, `test_answers_are_returned_in_question_order` | edge |

## Policy

| Behaviour | Test | Kind |
|---|---|---|
| Default thresholds are explicit and recorded | `tests/test_policy.py::test_default_thresholds_are_explicit_and_recorded` | happy |
| `noul` and `score` threshold boundaries hold | `tests/test_policy.py::test_noul_threshold_boundaries`, `test_score_threshold_boundaries` | edge |
| A rule hit is a floor no answer can lower | `tests/test_policy.py::test_rule_hit_is_a_floor_no_answer_can_lower` | happy |
| The verdict takes the maximum of rule and answer levels | `tests/test_policy.py::test_verdict_takes_the_maximum_of_rule_and_answer_levels` | happy |
| A choice answer is diagnostic and does not escalate | `tests/test_policy.py::test_choice_is_diagnostic_and_does_not_escalate` | edge |
| A clean result is possible when nothing fires | `tests/test_policy.py::test_clean_when_nothing_fires` | happy |
| Thresholds must be ordered and probabilities bounded | `tests/test_policy.py::test_thresholds_must_be_ordered`, `test_noul_thresholds_must_be_probabilities` | sad |
| The policy records the answer threshold that crossed | `tests/test_policy.py::test_policy_records_the_answer_threshold_that_crossed` | happy |

## Verdict assembly and screening log

| Behaviour | Test | Kind |
|---|---|---|
| The screen assembles a rule-driven quarantine with hits, answers, and a log entry | `tests/test_screen.py::test_screen_assembles_a_rule_driven_quarantine` | happy |
| Rule-driven passages are the verbatim matched spans | `tests/test_screen.py::test_rule_driven_passages_are_the_verbatim_matched_spans` | happy |
| Answer-driven quarantine quotes the whole material verbatim | `tests/test_screen.py::test_answer_driven_quarantine_quotes_the_whole_material_verbatim` | edge |
| Passage source falls back to the retriever when there is no URL | `tests/test_screen.py::test_passage_source_falls_back_to_the_retriever_when_no_url` | edge |
| A clean screen has no passages and exactly one log entry | `tests/test_screen.py::test_a_clean_screen_has_no_passages_and_exactly_one_log_entry` | happy |
| A run is immutable once the verdict is issued | `tests/test_screen.py::test_the_run_is_immutable_once_the_verdict_is_issued` | happy |
| A missing answer fails the batch and never becomes clean | `tests/test_screen.py::test_missing_answer_fails_the_whole_batch_and_is_never_clean` | sad |
| A model failure propagates instead of producing a verdict | `tests/test_screen.py::test_model_failure_propagates_instead_of_producing_a_verdict` | sad |
| A screen with no questions is an error | `tests/test_screen.py::test_a_screen_with_no_questions_is_an_error` | sad |
| A naive clock is an error | `tests/test_screen.py::test_a_naive_clock_is_an_error` | sad |
| A failed screen appends nothing to the log | `tests/test_screen.py::test_a_failed_screen_appends_nothing_to_the_log` | sad |
| A recorded screen is byte-deterministic across runs | `tests/test_screen.py::test_the_recorded_screen_is_byte_deterministic_across_runs` | happy |
| A different screen time produces a different run id | `tests/test_screen.py::test_a_different_screen_time_produces_a_different_run_id` | edge |
| The screening log rejects duplicate runs and writes one JSON line per run | `tests/test_screen.py::test_screening_log_is_append_only_and_rejects_duplicate_runs`, `test_screening_log_writes_one_json_line_per_run` | sad, happy |
| The screen appends exactly one log entry per run | `tests/test_screen.py::test_screen_appends_exactly_one_log_entry_per_run` | happy |
| A verdict refuses to drop below its own implied level | `tests/test_screen.py::test_verdict_refuses_to_drop_below_its_own_implied_level` | sad |
| A quarantine verdict requires a quarantined passage | `tests/test_screen.py::test_a_quarantine_verdict_requires_a_quarantined_passage` | sad |

## Decision-model clients

| Behaviour | Test | Kind |
|---|---|---|
| The System One request uses the documented wire shape | `tests/test_decision_model.py::test_build_systemone_request_uses_the_documented_wire_shape` | happy |
| An empty question set is rejected before a request | `tests/test_decision_model.py::test_build_systemone_request_rejects_an_empty_question_set` | sad |
| The response envelope is parsed and errors fail loudly | `tests/test_decision_model.py::test_parse_systemone_envelope_returns_the_answers_mapping`, `test_parse_systemone_envelope_raises_on_an_endpoint_error`, `test_parse_systemone_envelope_raises_when_answers_are_missing`, `test_parse_systemone_envelope_raises_on_a_non_mapping_answer` | happy, sad |
| Live configuration fails loudly on a missing model or bad endpoint | `tests/test_decision_model.py::test_live_configuration_fails_loudly` | sad |
| Cassette keys are stable and sensitive to the material and question | `tests/test_decision_model.py::test_cassette_key_is_stable_and_sensitive_to_inputs` | edge |
| The recorded client replays the committed cassette deterministically | `tests/test_decision_model.py::test_recorded_client_replays_the_committed_cassette`, `test_recorded_client_is_deterministic` | happy |
| A missing cassette key or stored-question mismatch fails loudly | `tests/test_decision_model.py::test_recorded_client_raises_when_a_key_is_missing`, `test_recorded_client_raises_when_the_stored_question_does_not_match` | sad |
| The cassette declares its synthetic status and format | `tests/test_decision_model.py::test_cassette_requires_the_synthetic_flag`, `test_cassette_rejects_an_unknown_format`, `test_committed_cassette_is_explicitly_synthetic` | sad, happy |
| Every fault-injection mode fails the typed parse | `tests/test_decision_model.py::test_fault_injection_fails_the_typed_parse` | sad |
| An unknown fault mode is rejected | `tests/test_decision_model.py::test_fault_injection_rejects_an_unknown_mode` | sad |
| The inquiry returns typed answers and rejects a non-mapping response | `tests/test_decision_model.py::test_decision_inquiry_returns_typed_answers`, `test_decision_inquiry_rejects_a_non_mapping_response` | happy, sad |
| The opt-in live client answers against clef-flash, or fails loudly | `tests/test_live_decision_model.py::test_live_clef_flash_answers_a_noul_question` | happy, opt-in `model` |


## Eval fixture loader and validator

| Behaviour | Test | Kind |
|---|---|---|
| The committed starter corpus loads with a stable fingerprint | `tests/test_eval_fixtures.py::test_loads_the_committed_starter_corpus` | happy |
| An unknown verdict level is rejected | `tests/test_eval_fixtures.py::test_rejects_an_unknown_verdict` | sad |
| A missing label is rejected | `tests/test_eval_fixtures.py::test_rejects_a_missing_label` | sad |
| A duplicate fixture id is rejected | `tests/test_eval_fixtures.py::test_rejects_a_duplicate_id` | sad |
| A derived source without provenance is rejected | `tests/test_eval_fixtures.py::test_rejects_missing_provenance_for_a_derived_source` | sad |
| A non-`example.invalid` host in an exfiltration position is rejected, while an ordinary URL is allowed | `tests/test_eval_fixtures.py::test_rejects_a_non_example_host_in_an_exfiltration_position`, `test_allows_a_non_example_host_with_no_exfiltration_context` | sad, edge |
| An empty or missing corpus directory is rejected | `tests/test_eval_fixtures.py::test_rejects_an_empty_corpus_directory`, `test_rejects_a_missing_corpus_directory` | sad |
| Label and expected verdict cannot contradict | `tests/test_eval_fixtures.py::test_rejects_a_benign_fixture_expecting_a_non_clean_verdict`, `test_rejects_a_malicious_fixture_expecting_clean` | sad |
| Transform derivations must be complete and point at a malicious base | `tests/test_eval_fixtures.py::test_rejects_a_transform_without_derived_from`, `test_rejects_a_transform_derived_from_an_unknown_fixture` | sad |
| Unknown rule ids, fields, and malformed YAML are rejected | `tests/test_eval_fixtures.py::test_rejects_an_unknown_expected_rule_id`, `test_rejects_an_unknown_field`, `test_rejects_a_malformed_yaml_file` | sad |

## Eval runner

| Behaviour | Test | Kind |
|---|---|---|
| The runner records verdicts, rule ids, answers, and evidence | `tests/test_eval_runner.py::test_the_runner_records_verdicts_and_evidence` | happy |
| The screen never receives the truth label | `tests/test_eval_runner.py::test_the_screen_never_sees_the_truth_label` | edge |
| Two recorded batches are byte-identical | `tests/test_eval_runner.py::test_two_recorded_batches_are_byte_identical` | happy |
| A malformed answer fails the batch | `tests/test_eval_runner.py::test_a_malformed_answer_fails_the_batch` | sad |

## Eval metrics

| Behaviour | Test | Kind |
|---|---|---|
| Recall, false-positive rate, frontier recall, and per-class arithmetic are correct | `tests/test_eval_metrics.py::test_recall_false_positives_and_frontier_arithmetic` | happy |
| Transform blocked rate and rule retention are correct | `tests/test_eval_metrics.py::test_transform_blocked_rate_and_rule_retention` | happy |
| Every plan metric is present and every not-applicable row carries a reason | `tests/test_eval_metrics.py::test_every_plan_metric_is_present_and_na_rows_carry_a_reason` | edge |
| A short corpus fails its coverage floor | `tests/test_eval_metrics.py::test_coverage_floor_fails_when_a_directory_is_short` | sad |
| Malformed coverage floors are rejected | `tests/test_eval_metrics.py::test_coverage_floor_requires_a_mapping_per_section` | sad |
| A non-failing malformed-answer probe is reported as a failure | `tests/test_eval_metrics.py::test_a_malformed_answer_that_does_not_fail_is_reported_and_gated` | sad |

## Eval gates

| Behaviour | Test | Kind |
|---|---|---|
| The committed registry tags all 19 metrics with the operator's gated set | `tests/test_eval_gates.py::test_committed_gate_registry_tags_every_metric` | happy |
| Unknown metrics, missing metrics, and bad statuses are rejected | `tests/test_eval_gates.py::test_rejects_an_unknown_metric`, `test_rejects_a_missing_metric`, `test_rejects_an_unknown_status` | sad |
| Gated metrics need thresholds, reported metrics must not carry one, and boolean gates are thresholdless | `tests/test_eval_gates.py::test_rejects_a_gated_metric_without_a_threshold`, `test_rejects_a_reported_metric_with_a_threshold`, `test_rejects_a_boolean_gate_with_a_threshold` | sad |
| Coverage floors reject unknown keys and negative values | `tests/test_eval_gates.py::test_rejects_an_unknown_coverage_key`, `test_rejects_a_negative_coverage_floor` | sad |
| A deliberately broken recall gate fails | `tests/test_eval_gates.py::test_a_deliberately_broken_recall_gate_fails` | sad |

## Eval harness, baseline, and report

| Behaviour | Test | Kind |
|---|---|---|
| The default run passes every gate and writes both reports with evidence | `tests/test_eval_harness.py::test_the_default_run_passes_every_gate` | happy |
| The report is byte-deterministic across runs | `tests/test_eval_harness.py::test_the_report_is_byte_deterministic` | happy |
| A broken gate fails the run but still writes the report | `tests/test_eval_harness.py::test_a_broken_gate_fails_the_run` | sad |
| A report-write failure raises | `tests/test_eval_harness.py::test_a_report_write_failure_raises` | sad |
| An ordinary run never updates the baseline | `tests/test_eval_harness.py::test_a_normal_run_does_not_update_the_baseline` | edge |
| A golden output change is an exact-output regression | `tests/test_eval_harness.py::test_a_golden_output_change_is_a_regression` | sad |
| A gated metric regression is distinguished from a corpus change | `tests/test_eval_harness.py::test_a_gated_metric_regression_is_distinguished_from_a_corpus_change`, `test_a_corpus_change_is_not_a_metric_regression` | sad, edge |
| A missing baseline is an error, and updating it is deliberate | `tests/test_eval_harness.py::test_a_missing_baseline_is_an_error`, `test_updating_the_baseline_is_deliberate` | sad, happy |
| A deleted corpus directory is caught end to end | `tests/test_eval_harness.py::test_a_deleted_corpus_directory_is_caught` | sad |
| The eval CLI exits zero, one, or two for pass, gate failure, and validation error | `tests/test_eval_cli.py::test_cli_runs_recorded_mode`, `test_cli_returns_nonzero_when_a_gate_fails`, `test_cli_returns_two_on_validation_error` | happy, sad, sad |

The default run deselects `model`-marked tests through `pyproject.toml`; the live row is exercised only by `uv run pytest -q -m model`. The eval-harness rows run in the same default gate and assert the committed baseline; no test rewrites it.
