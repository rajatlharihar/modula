"""Writes Modula-SKU.xlsx: every module SKU, plus the best build for each test persona.

    python tools/make_sku_sheet.py [output.xlsx]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modula import engine
from modula.catalogue import DIMS, MODULE_BY_ID
from modula.data import load_personas
from modula.sku import build_workbook

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Modula-SKU.xlsx"
personas = load_personas()
named = []
for split in ("dev", "test"):
    for p in personas[split]:
        need = {d: p["needs"].get(d, 0.1) for d in DIMS}
        builds, _ = engine.recommend(need, p.get("budget"), tuple(p.get("mustHave", [])), top_n=1)
        if builds:
            named.append((f"{p['id']} {p['name']}", "Best", builds[0]))
wb = build_workbook(named)
wb.save(out)
print(f"wrote {out}: {len(wb['Module SKUs']['A'])} rows in Module SKUs, {len(named)} builds")
