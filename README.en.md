# AX Literacy Assessment (axst)

[한국어 README](README.md)

**A 35-minute paper-based assessment of whether employees can actually use AI well at work — and a method for turning the results into training prescriptions.**

All test content and design documents are written in Korean. This page is a short English overview.

> [!IMPORTANT]
> **This is a public reference implementation.** Form A is published together with its answer key and rationales, so it must **not** be used for any scored assessment. To run a real assessment, reuse the method here and write a new, private form ([details, in Korean](docs/08-administration.md#폼-분리-공개-참조-폼과-시행-폼)).

> [!NOTE]
> **Status: pre-pilot.** Linting, scoring rehearsals and a synthetic pilot with 10 LLM agents are done. A pilot with real test-takers and timing measurements are still pending — see [open issues](docs/12-open-issues.md).

## What it is

Not just an item bank, but the whole chain: **sponsor agreement → test → scoring → axis flags and level → individual/organization reports → training prescription.**

- **Items:** 24 multiple-choice (20 deployed + 4 reserve), 2 open-response tasks, 4 shared stimuli, 6 job personas
- **Scoring:** automatic MC scoring; open responses use a 4-dimension × 5-point rubric plus risk penalties, with an LLM scoring protocol that grades each dimension in an independent pass
- **Outputs:** total score as a ±5 band, one of four levels, and a three-state flag per axis; cohort reports only when n ≥ 10
- **Tooling:** item-bank linter, web form generator, scorer — **Python standard library only**

## Design choices

- **No tool-trivia questions** ("Which of these is not a Claude model?"). Only situational judgement, output critique, and best–worst items are allowed.
- **"What should be delegated to AI" is the first axis.** The five axes are Delegation, Task Design, Verification & Trust Calibration, Workflow Redesign, and Risk & Governance.
- **Report only what the measurement supports.** With 4 items per axis, 2/4 and 3/4 are statistically indistinguishable, so individuals get a flag (strength / undetermined / needs work) instead of a number, and no radar charts.
- **Never use one form for both training design and HR evaluation.**

## Quick start

```bash
git clone https://github.com/yohan-work/axst.git && cd axst
python3 scripts/lint_items.py                        # item bank consistency checks
python3 scripts/build_web_form.py                    # items/ -> forms/form-A.web.html
python3 scripts/score.py responses/*.json            # score exported responses
python3 scripts/score.py responses/*.json --cohort   # cohort summary (n >= 10)
python3 -m unittest discover -s tests                # scorer tests
```

Responses are personal data. Keep them in `pilot/responses/`, which is git-ignored.

## Contributing

Defect reports are the most valuable contribution: ambiguous keys, items that span two axes, rubric levels no answer can reach. See [CONTRIBUTING.md](CONTRIBUTING.md) (Korean). Please open an issue before proposing rubric or scoring-rule changes. Issues in English are welcome.

## License

- Code (`scripts/`, `tests/`, `.github/`): [MIT](LICENSE)
- All other content (items, rubrics, personas, docs): [CC BY 4.0](LICENSE-CONTENT)
