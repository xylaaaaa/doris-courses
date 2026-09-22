# Add Data Warehousing Level 1 core course materials

> Historical initial draft: the text below predates later extensions and PR #4.
> Current delivered scope and test results are maintained in [integration-backlog.md](integration-backlog.md) and [VALIDATION.md](VALIDATION.md); do not reuse the remaining-scope list below as current status.

Suggested state: **Draft**. This is a Level-sized initial materials package,
not a single-video PR and not a claim that all planned Level 1 labs are complete.

## Summary

- Add an independent `02-data-warehousing/level1` course, preserving the agreed
  D01/D02/D03/D04/D05/D06/D07 teaching order.
- Add seven course readings with numbered topic sections, seven Lab notebooks,
  seven interactive quiz notebooks and 35 questions.
- Add original synthetic order fixtures and independent expected results.
- Implement and validate the core order workflow: load, reject, clean,
  maintain current state, retain history and replay.
- Align numbered reading/quiz filenames, single-node environment layout, and
  notebook presentation with course 01; reuse its quiz and display components.
- Add explicit opt-in Docker preparation with a separate Compose project and volumes.
- Add offline tests, a notebook-cell runner and explicit integration gaps.
- Expand D01 into a learner-facing module: scenario, objectives, complete SQL,
  expected results, troubleshooting and an independent filtering exercise.
- Separate learning entry pages from maintainer validation/status details.
- Keep course 02's root focused on learner materials; move maintenance
  documents, scripts and tests to repository-level maintenance/02-data-warehousing.
- Add a shared Jupyter launch configuration that hides generated artifacts
  without deleting them.
- Align all seven readings with course 01's module structure using Chinese
  headings, standalone lab/summary/quiz sections and official references.

## WWI dataset integration (2026-09-18)

- Replace the D01–D04 historical baseline with an attributed WWI subset; D05 loads
  all 701,846 rows from ten local Parquet files with manifest checks.
- Keep new simulation orders in a separate ID range/source, referencing WWI
  customers and products. Add payment, refund and shipment ledgers for reconciliation.
- Update D06 to 13 inputs / 10 accepted / 3 rejected, and D07 to 11 current
  orders / 18 history events / 19 deliveries. Update readings and relevant quizzes.
- Include the validated ~10 MiB WWI archive with its manifest and Microsoft MIT
  license. D05 verifies and unpacks the archive locally; no cloud upload is needed.
- Add a local MinIO/Iceberg REST fixture, isolated namespaces and sample preparation
  for D04. Public fixture credentials are scoped to localhost-only teaching services.
- Add blank independent exercises and folded, executable reference solutions to
  all seven labs; validate answers with the notebook runner's `--solutions` flag.
- Use business result tables and distinguish intended quality-check failures from
  real errors. Keep lab connections available for independent work.
- Existing learner quiz outputs and course 01 changes remain excluded.

## Validation

See [VALIDATION.md](VALIDATION.md) for build IDs, observed results and limitations.
All seven labs and reference solutions ran on the course's single-container
Doris sandbox in an isolated test database, including a real Iceberg table.
The image is tagged all-in-one-4.1.3 and reports a 4.1.3-rc02 build; retain that
distinction when describing compatibility. Fresh D04/D06 Jupyter kernels
validated output HTML, expected-error feedback and absence of stderr output.
Pixel-level browser checks, macOS/ARM64 startup and human trial timing remain open.
Offline checks cover notebook structure, four-choice quiz feedback, fixture
integrity, local archive extraction and learner-facing runtime behavior.
Existing learner outputs are preserved in the worktree and excluded from commits.

## Remaining scope

Standalone file queries, Kafka, CDC, object-storage continuous loads,
Group Commit, larger performance demonstrations and recording remain open.
D04 now includes a self-service Iceberg lab. The remaining integration paths
are tracked in integration-backlog.md and are not claimed as validated labs.
All seven modules have readings and guided exercises; human trial sessions
should still check difficulty, pacing and whether learners can solve new tasks.

## Dependencies and review focus

Based on merged main, not dependent on PR #2 or #3. Existing display and quiz code is
loaded from this repository, so keep both course directories when installing.
Review the order/event contract, SQL learning sequence, assertions, explicit
reset scope, and separation between implemented and planned material.

No remote PR has been created by this local preparation.
