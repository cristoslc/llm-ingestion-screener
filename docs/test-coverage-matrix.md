# Test coverage matrix

Master coverage matrix for `llm-ingestion-screener`. Each row is a behaviour; each column says which test covers it and at which kind (happy, sad, edge, corner).

| Behaviour | Test | Kind |
|---|---|---|
| CLI reports its version | `tests/test_cli.py::test_version_flag_prints_version` | happy |
| CLI with no arguments prints usage and exits zero | `tests/test_cli.py::test_no_args_prints_help_and_exits_zero` | edge |

The suite is intentionally tiny: the screening contract is not yet built, so there is nothing to cover beyond the CLI entry point. Rows are added as each requirement lands, and at least one failure-expecting test is written before each fix.
