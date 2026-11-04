"""SKU sheet export.

Writes the module catalogue and any recommended builds as an Excel workbook, one row
per SKU, so a build can be costed, ordered or checked line by line. Prices, masses and
power draws are the same illustrative design assumptions as the catalogue.
"""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .catalogue import (BASE_ATTRS, BASE_MASS, BASE_PRICE, CATEGORY_LABELS, DIMS, DIM_LABELS,
                        MODULES, MODULE_BY_ID, PLACEMENT_RULES)

COBALT = "0047AB"
HEAD_FILL = PatternFill("solid", fgColor=COBALT)
HEAD_FONT = Font(bold=True, color="FFFFFF", name="Calibri")
THIN = Side(style="thin", color="D5D8DF")
BORDER = Border(bottom=THIN)


def sku_code(module):
    """MOD-CAM-1IN style code from the catalogue id."""
    return "MOD-" + module.id.upper()


def _style_header(ws, row=1):
    for cell in ws[row]:
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 32
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _module_sheet(wb):
    ws = wb.active
    ws.title = "Module SKUs"
    head = ["SKU", "Category", "Name", "Short name", "Width (cells)", "Height (cells)", "Cells",
            "Price (INR)", "Mass (g)", "Power (W)", "Battery (Wh)", "Requires"] + \
           [DIM_LABELS[d] for d in DIMS] + ["Placement rule"]
    ws.append(head)
    for m in MODULES:
        ws.append([sku_code(m), CATEGORY_LABELS[m.cat], m.name, m.short, m.w, m.h, m.w * m.h,
                   m.price, m.mass, m.draw, m.wh or None,
                   ", ".join(sku_code(MODULE_BY_ID[r]) for r in m.requires) or None]
                  + [m.attrs.get(d) for d in DIMS] + [PLACEMENT_RULES.get(m.cat)])
    last = ws.max_row
    ws.append([])
    ws.append(["BASE", "Frame", "Base frame, display and shell", None, 2, 6, 12, BASE_PRICE, BASE_MASS])
    _style_header(ws)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.border = BORDER
        row[7].number_format = '"₹"#,##0'
    _widths(ws, [16, 16, 32, 18, 9, 9, 8, 12, 9, 9, 11, 16] + [11] * len(DIMS) + [38])
    ws.auto_filter.ref = f"A1:{get_column_letter(len(head))}{last}"
    return ws


def _builds_sheet(wb, named_builds):
    ws = wb.create_sheet("Builds")
    ws.append(["Build", "Option", "SKU", "Module", "Category", "Qty", "Unit price (INR)", "Line total (INR)",
               "Column", "Row", "Cells wide", "Cells high"])
    for name, option, build in named_builds:
        first = True
        for placed in build.placed:
            m = placed.mod
            ws.append([name, option, sku_code(m), m.name, CATEGORY_LABELS[m.cat], 1, m.price, m.price,
                       placed.x + 1, placed.y + 1, placed.w, placed.h])
            first = False
        ws.append([name, option, "BASE", "Base frame, display and shell", "Frame", 1, BASE_PRICE, BASE_PRICE])
        ws.append([name, option, "TOTAL", f"Fit {build.score:.2f}", None, None, None, build.config.price])
        ws.append([])
    _style_header(ws)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.border = BORDER
            if cell.column in (7, 8):
                cell.number_format = '"₹"#,##0'
        if row[2].value == "TOTAL":
            for cell in row:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="FFE9A8")
    _widths(ws, [24, 10, 16, 34, 16, 6, 14, 14, 8, 6, 10, 10])
    return ws


def build_workbook(named_builds=()):
    """named_builds: iterable of (label, option, Build). Returns an openpyxl Workbook."""
    wb = Workbook()
    _module_sheet(wb)
    if named_builds:
        _builds_sheet(wb, named_builds)
    return wb


def workbook_bytes(named_builds=()):
    buffer = BytesIO()
    build_workbook(named_builds).save(buffer)
    return buffer.getvalue()
