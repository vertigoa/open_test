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

## Generate image/PDF directly (answer to “how do I generate image?”)

Use these flags on the same command:

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --out output \
  --export-print-png --export-social-png --export-print-pdf
```

Outputs created:

- `output/flyer_print.png`
- `output/flyer_social.png`
- `output/flyer_print.pdf`

If Playwright is not installed:

```bash
pip install playwright
python -m playwright install chromium
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
3. Share generated PNG/PDF directly for print and socials.

This makes the design process repeatable and mostly data-driven instead of manual dragging in design tools.
