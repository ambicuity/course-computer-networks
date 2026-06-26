# Contributing

Thanks for helping improve Course: Computer Networks. This repository is a curriculum, so contributions should preserve the course shape: each lesson is readable on its own, ties a protocol rule to observable network evidence, and fits the phase it belongs to.

## What to Contribute

Good contributions include:

- Fixing factual errors, broken links, typos, and unclear explanations.
- Improving a lesson's runnable code or quiz explanations.
- Adding missing glossary references to `glossary/terms.md`.
- Filling or extending a lesson using `LESSON_TEMPLATE.md`.
- Improving the generated site by updating the source Markdown, then rebuilding.

Avoid unrelated rewrites. If a change affects the curriculum structure, update `README.md`, `ROADMAP.md`, and the relevant phase `README.md` together — the website status badges are parsed from `ROADMAP.md`.

## Reporting Issues & Finding Work

Open an issue describing the problem and where it appears: the phase and lesson
path (e.g. `phases/05-medium-access-protocols/10-...`), what you expected, and
what you saw. For content fixes, a link to the lesson page or the `docs/en.md`
file is enough.

Please comment to claim an issue before starting so we avoid duplicate work.

## Lesson Standard

Every lesson lives in `phases/<NN-phase>/<MM-lesson>/` and should include:

- `docs/en.md` with the standard lesson sections (see the template).
- Runnable code in `code/` (Python by default) when the lesson requires implementation.
- `quiz.json` with a `stage` (`pre`/`post`), `options`, a 0-based `correct` index, and an `explanation` for each question.
- `outputs/` with the lesson's reusable Ship-It artifact (a study prompt, runbook, parser, or generated data file).
- `assets/` for any diagrams the lesson references.

Use `LESSON_TEMPLATE.md` as the canonical structure. Replace every placeholder with real content; do not leave `TODO`, placeholder prose, or a `raise NotImplementedError` stub behind.

## Workflow

1. Fork the repository and create a focused branch.
2. Make the smallest coherent change that completes the contribution.
3. Run the relevant checks:

```bash
# Scaffold a new lesson folder (idempotent)
scripts/scaffold-lesson.sh phases/03-data-link-foundations my-new-lesson "My New Lesson"

# Run the lesson's code — it must exit 0
python3 phases/<phase>/<lesson>/code/main.py

# Validate the quiz parses as JSON
python3 -c "import json; json.load(open('phases/<phase>/<lesson>/quiz.json'))"

# Rebuild the static site (regenerates site/data.js from README + ROADMAP)
node site/build.js
```

4. Open a pull request with a short summary, the files changed, and the checks you ran.

## Style

- Write directly and concretely.
- Prefer runnable examples and real packet/trace evidence over abstract description.
- Link terms to `glossary/terms.md` when a concept is reused across lessons.
- Keep code comments for non-obvious constraints and invariants.
- Use ASCII in new files unless the surrounding file already uses non-ASCII notation.

## Required Project Docs

| Goal | Read |
|---|---|
| Contribute a lesson or fix | `CONTRIBUTING.md` |
| Fork for your team or school | `FORKING.md` |
| Lesson template | `LESSON_TEMPLATE.md` |
| Track progress | `ROADMAP.md` |
| Glossary | `glossary/terms.md` |
| Code of conduct | `CODE_OF_CONDUCT.md` |
