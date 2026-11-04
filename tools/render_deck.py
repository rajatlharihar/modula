"""One-off: renders the deck's slide files to a PDF and a contact-sheet PNG with headless Edge."""
import json, re, subprocess, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(); pdf = Path(sys.argv[2]).resolve(); png = Path(sys.argv[3]).resolve()
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
deck = json.loads((root / "project/deck.json").read_text(encoding="utf-8"))
slides = [re.sub(r"<aside>.*?</aside>", "", (root / f"project/slides/{i}.html").read_text(encoding="utf-8"), flags=re.S) for i in deck["order"]]
fonts = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values())
css = """@page{size:1920px 1080px;margin:0}*{box-sizing:border-box;margin:0}html,body{background:#E8EBE6;-webkit-print-color-adjust:exact;print-color-adjust:exact}
section{position:relative;width:1920px;height:1080px;overflow:hidden;break-after:page}section:last-child{break-after:auto}
table{border-collapse:collapse;width:100%}th,td{padding:.35em .6em;border-bottom:1px solid #B7C0B8;font-weight:400}th{font-weight:600;border-bottom:2px solid #2F4A47}
td:not(:first-child){text-align:right}"""
html = root / "print.html"
html.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{deck["title"]}</title>{fonts}<style>{css}</style></head><body>{"".join(slides)}</body></html>', encoding="utf-8")
base = [EDGE, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000"]
url = html.as_uri()
subprocess.run(base + ["--no-pdf-header-footer", f"--print-to-pdf={pdf}", url], capture_output=True)
subprocess.run(base + ["--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1920,4320", f"--screenshot={png}", url], capture_output=True)
print("pages:", len(re.findall(rb"/Type\s*/Page\b", pdf.read_bytes())), "pdf bytes:", pdf.stat().st_size)
