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

### Friendly walkthrough

1. Open a terminal in the repo root (`/workspaces/open_test` if you are in Codespaces).
2. Run the quick start command above. You will get `flyer_print.html`, `flyer_social.html`, and `flyer_content.json` inside `output/`.
3. Preview the flyer. In Codespaces + Chrome, add `--serve` (shown below) to spin up a local server and auto-open the page. Locally, you can double-click the HTML or serve it however you like.
4. Edit `examples/menu.csv` or `examples/brand.json` and re-run the command when you need new flyers.

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --out output --serve
```

By default `--serve` listens on port 8000 and opens `http://localhost:8000/flyer_print.html` through `$BROWSER`. Stop it with Ctrl+C.

### Generate every style variation

Five pre-made style profiles live in `examples/flyer_style_variations.json`. To render them all in one shot:

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --all-styles --out output --serve
```

Each variant gets its own folder (for example `output/tailgate_hype/`) with HTML and JSON. When `--serve` is set, your browser lands on the first variant (`family_block_party` by default).

Need just one style? Pick it by ID:

```bash
python3 flyer_automation.py examples/menu.csv --style-id college_night --out output --serve --serve-port 9000
```

Bring your own style file with `--styles path/to/styles.json` and keep `--serve` to preview quickly.

## Generate image/PDF directly (answer to “how do I generate image?”)

Use these flags on the same command:

```bash
# One-time setup
pip install playwright
python -m playwright install chromium

# Then add export flags to any run
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --all-styles --out output \
  --export-print-png --export-social-png --export-print-pdf
```

Exports land alongside each HTML file (for example `output/anytime_classic/flyer_print.png`). When using `--serve`, the server stays up so you can refresh the page after assets regenerate.

Optional copy-improvement pass:

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --out output --improve-copy
```

Tip: combine with styles to polish every variation in one go:

```bash
python3 flyer_automation.py examples/menu.csv --brand examples/brand.json --all-styles --out output --improve-copy
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

### Troubleshooting

- `FileNotFoundError: 'menu.csv'` → run the command from the repo root or point at the correct CSV (e.g. `examples/menu.csv`).
- `playwright.sync_api` import error → install Playwright as shown above.
- Need a different brand baseline → duplicate `examples/brand.json` and pass the new path with `--brand`.
- Want more styles → append new objects to `examples/flyer_style_variations.json` (IDs must be unique).
- Preview blocked in Codespaces Live Preview → use `--serve` or run `python3 -m http.server 8000` and open the forwarded port in the browser.

This makes the design process repeatable and mostly data-driven instead of manual dragging in design tools.
