# open_test

Automated flyer refresh starter for turning an old menu flyer into a modern, repeatable output.

## What it does

`flyer_automation.py` takes a CSV menu and optional brand settings and generates:

- `flyer_content.json` (normalized content)
- `flyer_print.html` (2-column print layout)
- `flyer_social.html` (single-column social layout)

If `OPENAI_API_KEY` is set and `--improve-copy` is used, it can run an LLM pass to polish copy while preserving pricing and section structure.

## Quick start

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --out output
```

Optional copy-improvement pass:

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --out output --improve-copy
```

## CSV schema

Required columns:

- `section`
- `item`
- `description`
- `price`

## API automation idea

Use this as a cron or CI job:

1. Friend edits `menu.csv` (or Google Sheet export).
2. Job runs this script.
3. Upload generated HTML to static hosting or convert HTML to PDF/image in a second step.

This makes the design process repeatable and mostly data-driven instead of manual dragging in design tools.
