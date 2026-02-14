#!/usr/bin/env python3
"""Automated flyer refresh pipeline.

Turns a CSV menu + brand settings into:
1) normalized content JSON
2) print-friendly HTML flyer
3) social-friendly HTML flyer

Optional: if OPENAI_API_KEY is set, you can run with --improve-copy to rewrite
item descriptions and flyer headline/subhead with an LLM.
"""

from __future__ import annotations

import argparse
import csv
import functools
import json
import os
import subprocess
import threading
from collections import OrderedDict
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

@dataclass
class MenuItem:
    section: str
    item: str
    description: str
    price: float


DEFAULT_BRAND = {
    "business_name": "Smokey Legend Colorado BBQ",
    "headline": "Barbecue",
    "subhead": "Slow smoked. Big flavor. Saturdays at noon.",
    "cta": "Scan to preorder • While supplies last",
    "location": "Grand Junction Elks Lodge #575 • 249 South 4th Street",
    "palette": {
        "bg": "#0b0d10",
        "fg": "#f5f7fa",
        "muted": "#cdd4de",
        "accent": "#f4c542",
        "price": "#f5a24c",
    },
}


def load_brand(path: Path | None) -> Dict:
    if not path:
        return DEFAULT_BRAND.copy()
    with path.open("r", encoding="utf-8") as f:
        user = json.load(f)
    merged = DEFAULT_BRAND.copy()
    merged.update(user)
    merged["palette"] = {**DEFAULT_BRAND["palette"], **user.get("palette", {})}
    return merged


def load_styles(path: Path) -> Dict[str, Dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["id"]: entry for entry in data}


def apply_style_to_brand(base: Dict, style: Dict) -> Dict:
    styled = base.copy()
    for key in ("headline", "subhead", "cta"):
        if style.get(key):
            styled[key] = style[key]
    if "palette" in style:
        styled["palette"] = {**styled.get("palette", {}), **style["palette"]}
    styled["style_id"] = style.get("id")
    styled["target_audience"] = style.get("target_audience")
    styled["type"] = style.get("type", {})
    styled["layout_notes"] = style.get("layout")
    styled["visual_notes"] = style.get("visual_notes", [])
    return styled


def serve_directory(directory: Path, port: int, open_relative: Optional[Path]) -> None:
    directory = directory.resolve()
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    address = ("0.0.0.0", port)
    try:
        httpd = ThreadingHTTPServer(address, handler)
    except OSError as exc:
        raise RuntimeError(f"Unable to start preview server on port {port}: {exc}") from exc

    url_root = f"http://localhost:{port}"
    target_url = url_root
    if open_relative:
        safe_path = quote(open_relative.as_posix(), safe="/")
        target_url = f"{url_root}/{safe_path}" if safe_path else url_root

    print(f"Serving {directory} at {url_root}. Press Ctrl+C to stop.")
    if open_relative:
        print(f"Preview: {target_url}")

    browser = os.environ.get("BROWSER")

    def launch_browser() -> None:
        if not browser or not open_relative:
            return
        try:
            subprocess.Popen([browser, target_url])
            print(f"Launched $BROWSER -> {target_url}")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Could not launch $BROWSER ({exc}). Open URL manually.")

    if browser and open_relative:
        threading.Timer(0.6, launch_browser).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview server stopped.")
    finally:
        httpd.server_close()


def read_menu(path: Path) -> List[MenuItem]:
    rows: List[MenuItem] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"section", "item", "description", "price"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for raw in reader:
            price_text = (raw.get("price") or "0").strip() or "0"
            rows.append(
                MenuItem(
                    section=(raw.get("section") or "Misc").strip(),
                    item=(raw.get("item") or "").strip(),
                    description=(raw.get("description") or "").strip(),
                    price=float(price_text),
                )
            )
    return rows


def normalize_items(items: List[MenuItem]) -> Dict[str, List[Dict]]:
    sections: Dict[str, List[Dict]] = OrderedDict()
    for i in items:
        if i.section not in sections:
            sections[i.section] = []
        sections[i.section].append(
            {
                "item": i.item,
                "description": tighten_copy(i.description),
                "price": format_price(i.price),
            }
        )
    return sections


def tighten_copy(text: str) -> str:
    if not text:
        return ""
    t = " ".join(text.split())
    replacements = {
        "and": "&",
        "Choice of 1 side": "choice of 1 side",
        "Smoked and pulled": "smoked & pulled",
    }
    for src, dst in replacements.items():
        t = t.replace(src, dst)
    return t[0].upper() + t[1:]


def format_price(price: float) -> str:
    if price <= 0:
        return "TBD"
    if price.is_integer():
        return f"${int(price)}"
    return f"${price:.2f}"


def build_context(brand: Dict, sections: Dict[str, List[Dict]], social: bool = False) -> Dict:
    cta_size = "0.95rem" if not social else "1rem"

    def font_stack(*candidates: Optional[str]) -> str:
        stack = [candidate for candidate in candidates if candidate]
        stack.extend(["Inter", "Arial", "sans-serif"])
        formatted: List[str] = []
        for candidate in stack:
            formatted.append(f'"{candidate}"' if " " in candidate else candidate)
        return ", ".join(dict.fromkeys(formatted))

    fonts = brand.get("type", {})
    return {
        "brand": brand,
        "sections": sections,
        "cta_size": cta_size,
        "title_size": "5.2rem" if not social else "3.8rem",
        "cols": "2" if not social else "1",
        "fonts": {
            "primary": font_stack(fonts.get("primary"), fonts.get("secondary")),
            "secondary": font_stack(fonts.get("secondary"), fonts.get("body")),
            "body": font_stack(fonts.get("body")),
        },
    }


def render_html(ctx: Dict) -> str:
    p = ctx["brand"]["palette"]
    section_blocks = []
    for sec, rows in ctx["sections"].items():
        items_html = "\n".join(
            (
                f"<div class=\"item\">"
                f"<div class=\"row\"><span class=\"name\">{r['item']}</span><span class=\"price\">{r['price']}</span></div>"
                f"<div class=\"desc\">{r['description']}</div>"
                f"</div>"
            )
            for r in rows
        )
        section_blocks.append(f"<section><h2>{sec}</h2>{items_html}</section>")

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>{ctx['brand']['business_name']} Flyer</title>
  <style>
    body {{ margin:0; font-family:{ctx['fonts']['body']}; background:{p['bg']}; color:{p['fg']}; }}
    .page {{ max-width: 980px; margin: 0 auto; padding: 28px 28px 40px; }}
    .hero h1 {{ font-family:{ctx['fonts']['primary']}; font-size:{ctx['title_size']}; margin:0; text-transform: uppercase; letter-spacing: 0.04em; }}
    .hero .name {{ font-family:{ctx['fonts']['secondary']}; color:{p['accent']}; font-weight:700; font-size:2rem; }}
    .hero .sub {{ font-family:{ctx['fonts']['secondary']}; color:{p['muted']}; margin-top:8px; }}
    .sections {{ display:grid; grid-template-columns: repeat({ctx['cols']}, minmax(0,1fr)); gap:20px; margin-top:20px; }}
    section {{ border:1px solid #ffffff2a; padding:14px; border-radius:12px; backdrop-filter: blur(1px); }}
    h2 {{ font-family:{ctx['fonts']['secondary']}; margin:0 0 10px; color:{p['accent']}; text-transform: uppercase; letter-spacing:0.03em; }}
    .item {{ margin-bottom:12px; }}
    .row {{ display:flex; justify-content:space-between; gap:10px; font-family:{ctx['fonts']['secondary']}; font-weight:700; }}
    .price {{ color:{p['price']}; }}
    .desc {{ font-family:{ctx['fonts']['body']}; color:{p['muted']}; font-size:0.96rem; margin-top:2px; line-height:1.3; }}
    .footer {{ margin-top:26px; border-top:1px solid #ffffff2a; padding-top:12px; color:{p['muted']}; }}
    .cta {{ font-family:{ctx['fonts']['secondary']}; color:{p['fg']}; font-weight:700; font-size:{ctx['cta_size']}; }}
  </style>
</head>
<body>
  <main class=\"page\">
    <header class=\"hero\">
      <div class=\"name\">{ctx['brand']['business_name']}</div>
      <h1>{ctx['brand']['headline']}</h1>
      <div class=\"sub\">{ctx['brand']['subhead']}</div>
    </header>
    <div class=\"sections\">{''.join(section_blocks)}</div>
    <footer class=\"footer\">
      <div>{ctx['brand']['location']}</div>
      <div class=\"cta\">{ctx['brand']['cta']}</div>
    </footer>
  </main>
</body>
</html>
"""


def maybe_improve_copy(payload: Dict, model: str = "gpt-4.1-mini") -> Dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return payload

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "Rewrite this BBQ flyer content to be clearer and more modern. "
            "Keep facts and prices, keep sections, output strict JSON with same schema only."
        )
        resp = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "You are a restaurant menu copy editor.",
                },
                {
                    "role": "user",
                    "content": prompt + "\n\n" + json.dumps(payload),
                },
            ],
        )
        text = resp.output_text
        return json.loads(text)
    except Exception:
        return payload




def render_assets_with_playwright(html_path: Path, out_path: Path, width: int = 1200, height: int = 1800, pdf: bool = False) -> None:
    """Render HTML flyer to PNG/PDF using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Playwright is required for image/pdf export. Install with: pip install playwright") from exc

    uri = html_path.resolve().as_uri()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(uri, wait_until="networkidle")
        if pdf:
            page.pdf(path=str(out_path), print_background=True, format="Letter")
        else:
            page.screenshot(path=str(out_path), full_page=True)
        browser.close()

def write_outputs(out_dir: Path, payload: Dict, print_html: str, social_html: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "flyer_content.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "flyer_print.html").write_text(print_html, encoding="utf-8")
    (out_dir / "flyer_social.html").write_text(social_html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate refreshed flyers from CSV")
    parser.add_argument("menu_csv", type=Path, help="Path to menu CSV")
    parser.add_argument("--brand", type=Path, default=None, help="Brand JSON overrides")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument("--improve-copy", action="store_true", help="Use OpenAI API to improve copy")
    parser.add_argument("--export-print-png", action="store_true", help="Render output/flyer_print.png with Playwright")
    parser.add_argument("--export-social-png", action="store_true", help="Render output/flyer_social.png with Playwright")
    parser.add_argument("--export-print-pdf", action="store_true", help="Render output/flyer_print.pdf with Playwright")
    parser.add_argument("--styles", type=Path, default=None, help="Path to flyer style variations JSON")
    parser.add_argument("--style-id", default=None, help="Generate a single style ID from the style JSON")
    parser.add_argument("--all-styles", action="store_true", help="Generate every style defined in the style JSON")
    parser.add_argument("--serve", action="store_true", help="Host the output folder with a simple HTTP server")
    parser.add_argument("--serve-port", type=int, default=8000, help="Port for the preview server (default: 8000)")
    args = parser.parse_args()

    if args.style_id and args.all_styles:
        parser.error("--style-id cannot be combined with --all-styles")
    if args.serve_port <= 0:
        parser.error("--serve-port must be a positive integer")

    brand = load_brand(args.brand)
    items = read_menu(args.menu_csv)
    sections = normalize_items(items)

    default_styles_path = Path("examples/flyer_style_variations.json")
    styles_index: Dict[str, Dict] = {}
    styles_path = args.styles or (default_styles_path if default_styles_path.exists() else None)
    if args.styles and not args.styles.exists():
        parser.error(f"Styles file '{args.styles}' was not found.")
    if (args.style_id or args.all_styles) and not styles_path:
        parser.error("No style variations file found. Provide one with --styles.")
    if styles_path and styles_path.exists():
        styles_index = load_styles(styles_path)

    variants: List[Optional[Dict]]
    if args.all_styles:
        if not styles_index:
            parser.error("Style variations file is empty or missing expected structure.")
        variants = list(styles_index.values())
    elif args.style_id:
        if args.style_id not in styles_index:
            parser.error(f"Unknown style id '{args.style_id}'.")
        variants = [styles_index[args.style_id]]
    else:
        variants = [None]

    generated_paths: List[Path] = []
    first_relative_html: Optional[Path] = None

    for style in variants:
        base_brand = brand.copy()
        if style:
            base_brand = apply_style_to_brand(base_brand, style)

        payload = {"brand": base_brand, "sections": sections}
        if args.improve_copy:
            improved = maybe_improve_copy({"brand": base_brand, "sections": sections})
            improved_brand = {**base_brand, **improved.get("brand", {})}
            improved_brand["palette"] = base_brand.get("palette", {})
            improved_brand["type"] = base_brand.get("type", {})
            improved_brand["style_id"] = base_brand.get("style_id")
            improved_brand["target_audience"] = base_brand.get("target_audience")
            improved_brand["layout_notes"] = base_brand.get("layout_notes")
            improved_brand["visual_notes"] = base_brand.get("visual_notes")
            payload = {
                "brand": improved_brand,
                "sections": improved.get("sections", sections),
            }
        if style:
            payload["style"] = style

        print_ctx = build_context(payload["brand"], payload["sections"], social=False)
        social_ctx = build_context(payload["brand"], payload["sections"], social=True)
        print_html = render_html(print_ctx)
        social_html = render_html(social_ctx)

        out_dir = args.out / style["id"] if style else args.out
        write_outputs(out_dir, payload, print_html, social_html)

        if style:
            relative_html = Path(style["id"]) / "flyer_print.html"
        else:
            relative_html = Path("flyer_print.html")
        if first_relative_html is None:
            first_relative_html = relative_html

        if args.export_print_png:
            render_assets_with_playwright(out_dir / "flyer_print.html", out_dir / "flyer_print.png")
        if args.export_social_png:
            render_assets_with_playwright(out_dir / "flyer_social.html", out_dir / "flyer_social.png", width=1080, height=1920)
        if args.export_print_pdf:
            render_assets_with_playwright(out_dir / "flyer_print.html", out_dir / "flyer_print.pdf", pdf=True)

        generated_paths.append(out_dir)

    if len(generated_paths) == 1:
        print(f"Wrote flyer files to {generated_paths[0]}")
    else:
        path_list = ", ".join(str(p) for p in generated_paths)
        print(f"Wrote flyer files to: {path_list}")

    if args.serve:
        try:
            serve_directory(args.out, args.serve_port, first_relative_html)
        except RuntimeError as exc:
            print(exc)


if __name__ == "__main__":
    main()
