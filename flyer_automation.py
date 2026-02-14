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
import json
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


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
    return {
        "brand": brand,
        "sections": sections,
        "cta_size": cta_size,
        "title_size": "5.2rem" if not social else "3.8rem",
        "cols": "2" if not social else "1",
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
    body {{ margin:0; font-family: Inter, Arial, sans-serif; background:{p['bg']}; color:{p['fg']}; }}
    .page {{ max-width: 980px; margin: 0 auto; padding: 28px 28px 40px; }}
    .hero h1 {{ font-size:{ctx['title_size']}; margin:0; text-transform: uppercase; letter-spacing: 0.04em; }}
    .hero .name {{ color:{p['accent']}; font-weight:700; font-size:2rem; }}
    .hero .sub {{ color:{p['muted']}; margin-top:8px; }}
    .sections {{ display:grid; grid-template-columns: repeat({ctx['cols']}, minmax(0,1fr)); gap:20px; margin-top:20px; }}
    section {{ border:1px solid #ffffff2a; padding:14px; border-radius:12px; backdrop-filter: blur(1px); }}
    h2 {{ margin:0 0 10px; color:{p['accent']}; text-transform: uppercase; letter-spacing:0.03em; }}
    .item {{ margin-bottom:12px; }}
    .row {{ display:flex; justify-content:space-between; gap:10px; font-weight:700; }}
    .price {{ color:{p['price']}; }}
    .desc {{ color:{p['muted']}; font-size:0.96rem; margin-top:2px; line-height:1.3; }}
    .footer {{ margin-top:26px; border-top:1px solid #ffffff2a; padding-top:12px; color:{p['muted']}; }}
    .cta {{ color:{p['fg']}; font-weight:700; font-size:{ctx['cta_size']}; }}
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
    args = parser.parse_args()

    brand = load_brand(args.brand)
    items = read_menu(args.menu_csv)
    sections = normalize_items(items)
    payload = {"brand": brand, "sections": sections}
    if args.improve_copy:
        payload = maybe_improve_copy(payload)

    print_html = render_html(build_context(payload["brand"], payload["sections"], social=False))
    social_html = render_html(build_context(payload["brand"], payload["sections"], social=True))
    write_outputs(args.out, payload, print_html, social_html)
    print(f"Wrote flyer files to {args.out}")


if __name__ == "__main__":
    main()
