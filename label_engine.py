"""
label_engine.py
Core label-generation logic — no file paths hardcoded.
Call generate_workbook(csv_files) where csv_files is a list of
(tab_name, dataframe) tuples.  Returns an openpyxl Workbook.
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
import pandas as pd
from datetime import datetime
import barcode
from barcode.writer import ImageWriter
import os, tempfile

# ── Constants ─────────────────────────────────────────────────────────────────
LABELS_PER_ROW = 4
ROWS_PER_LABEL = 6
ROW_H          = [8, 22, 10, 12, 16, 4]   # pt — sums to 72pt = 1 inch

ORANGE_FILL = PatternFill('solid', start_color='FF8000', end_color='FF8000')
WHITE = 'FFFFFF'
MED   = Side(style='medium')
THIN  = Side(style='thin')

BC_DIR = os.path.join(tempfile.gettempdir(), 'lbl_barcodes')
os.makedirs(BC_DIR, exist_ok=True)

today_str = datetime.now().strftime('%m/%d/%y')

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_uom(uom_raw, scale_raw):
    scale = str(scale_raw).strip().upper() == 'TRUE'
    if pd.isna(uom_raw) or str(uom_raw).strip() in ('', 'nan'):
        return 'PER POUND' if scale else 'EACH'
    u = str(uom_raw).strip().upper()
    mapping = {
        'LB': 'PER POUND',    'LBS': 'PER POUND',
        'OZ': 'PER OUNCE',    'OUNCE': 'PER OUNCE',   'OUNCES': 'PER OUNCE',
        'QT': 'PER QUART',    'QUART': 'PER QUART',
        'EA': 'EACH',         'EACH':  'EACH',
        'CT': 'PER 100 CT',
        'FLOZ': 'PER FLUID OUNCE', 'FL OZ': 'PER FLUID OUNCE',
    }
    try:
        float(u); return 'EACH'
    except ValueError:
        pass
    return mapping.get(u, f'PER {u}')

def fmt_upc(upc_raw):
    d = ''.join(filter(str.isdigit, str(upc_raw)))
    if len(d) >= 12:
        d = d.zfill(12)[-12:]
        return f'{d[0]}-{d[1:6]}-{d[6:11]}-{d[11]}'
    return str(upc_raw).strip()

def clean_size(raw):
    s = str(raw).strip() if pd.notna(raw) else ''
    if s in ('', 'nan'): return ''
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else f'{f:g}'
    except ValueError:
        return s

def make_barcode(upc_raw):
    digits = ''.join(filter(str.isdigit, str(upc_raw)))
    if not digits:
        return None
    path = os.path.join(BC_DIR, f'{digits}.png')
    if not os.path.exists(path):
        try:
            bc = barcode.get('code128', digits, writer=ImageWriter())
            bc.save(path.replace('.png', ''), options={
                'module_width': 0.38, 'module_height': 8.5,
                'quiet_zone': 2.0, 'font_size': 0,
                'write_text': False, 'dpi': 300,
                'background': 'white', 'foreground': 'black',
            })
        except Exception:
            return None
    return path if os.path.exists(path) else None

# ── Sheet setup ───────────────────────────────────────────────────────────────
def setup_sheet(ws):
    ws.sheet_view.showGridLines = False
    ws.page_setup.paperSize    = 1
    ws.page_setup.orientation  = 'landscape'
    ws.page_margins.left       = 0.25
    ws.page_margins.right      = 0.25
    ws.page_margins.top        = 0.35
    ws.page_margins.bottom     = 0.35
    ws.page_setup.fitToPage    = True
    ws.page_setup.fitToWidth   = 1
    for i in range(LABELS_PER_ROW):
        ws.column_dimensions[get_column_letter(i * 3 + 1)].width = 11
        ws.column_dimensions[get_column_letter(i * 3 + 2)].width = 16
        ws.column_dimensions[get_column_letter(i * 3 + 3)].width = 3

# ── Single label ──────────────────────────────────────────────────────────────
def draw_label(ws, r, oc, item):
    pc = oc + 1

    try:    price     = float(item['Price'])
    except: price     = 0.0
    pp = item.get('PricePer', '')
    try:    price_per = float(pp) if pd.notna(pp) and str(pp).strip() not in ('','nan') else None
    except: price_per = None

    uom       = get_uom(item.get('UnitOfMeasure',''), item.get('Scale','FALSE'))
    desc      = str(item.get('Description','')).upper().strip()
    size      = clean_size(item.get('Size',''))
    upc_raw   = str(item.get('Upc','')).strip()
    upc_fmt   = fmt_upc(upc_raw)
    ic        = str(item.get('ItemCode','')).strip()
    item_code = ic if ic not in ('nan','') else ''

    sd = item.get('StartDate','')
    try:    date_lbl = pd.to_datetime(sd).strftime('%m/%d/%y') if pd.notna(sd) and str(sd).strip() not in ('','nan') else today_str
    except: date_lbl = today_str

    abbr_map = {'PER POUND':'LB','PER OUNCE':'OZ','PER QUART':'QT',
                'PER 100 CT':'CT','PER FLUID OUNCE':'FL OZ'}
    if size:
        if any(c.isalpha() for c in size):
            size_display = size.upper()
        elif uom and uom != 'EACH':
            a = abbr_map.get(uom,'')
            size_display = f'{size} {a}' if a else size
        else:
            size_display = size
    else:
        size_display = ''

    for i, h in enumerate(ROW_H):
        ws.row_dimensions[r + i].height = h

    # Orange column
    for row, val, sz, bold in [
        (r,     'UNIT PRICE',                                             5.5, False),
        (r + 1, f'${price_per:.2f}' if price_per is not None else 'N/A', 11,  True),
        (r + 2, uom,                                                      6.5, True),
    ]:
        c = ws.cell(row, oc)
        c.value     = val
        c.fill      = ORANGE_FILL
        c.font      = Font(name='Arial', size=sz, bold=bold, color=WHITE)
        c.alignment = Alignment(horizontal='center', vertical='center')

    # Price column
    for row, val, sz, bold in [
        (r,     'RETAIL PRICE',                                5.5, False),
        (r + 1, f'${price:.2f}',                              22,  True),
        (r + 2, f'Item #: {item_code}' if item_code else '',  5.5, False),
    ]:
        c = ws.cell(row, pc)
        c.value     = val
        c.font      = Font(name='Arial', size=sz, bold=bold)
        c.alignment = Alignment(horizontal='center', vertical='center')

    # Date row
    dc = ws.cell(r + 3, oc)
    dc.value = date_lbl;  dc.font = Font(name='Arial', size=6)
    dc.alignment = Alignment(horizontal='center', vertical='center')

    uc = ws.cell(r + 3, pc)
    uc.value = '   '.join(filter(None, [upc_fmt, size_display]))
    uc.font  = Font(name='Arial', size=6)
    uc.alignment = Alignment(horizontal='center', vertical='center')

    # Description + barcode
    desc_c = ws.cell(r + 4, oc)
    desc_c.value     = desc[:28]
    desc_c.font      = Font(name='Arial', bold=True, size=6.5)
    desc_c.alignment = Alignment(horizontal='left', vertical='center', indent=1)

    bc_path = make_barcode(upc_raw)
    if bc_path:
        try:
            img = XLImage(bc_path)
            img.width = 108;  img.height = 19
            ws.add_image(img, f'{get_column_letter(pc)}{r + 4}')
        except Exception:
            pass
    else:
        c = ws.cell(r + 4, pc)
        c.value = upc_fmt;  c.font = Font(name='Arial', size=5)
        c.alignment = Alignment(horizontal='center', vertical='center')

    # Borders
    ws.cell(r,     oc).border = Border(top=MED, left=MED, right=THIN)
    ws.cell(r + 1, oc).border = Border(left=MED, right=THIN)
    ws.cell(r + 2, oc).border = Border(left=MED, right=THIN, bottom=THIN)
    ws.cell(r,     pc).border = Border(top=MED, right=MED)
    ws.cell(r + 1, pc).border = Border(right=MED)
    ws.cell(r + 2, pc).border = Border(right=MED, bottom=THIN)
    ws.cell(r + 3, oc).border = Border(left=MED)
    ws.cell(r + 3, pc).border = Border(right=MED, bottom=THIN)
    ws.cell(r + 4, oc).border = Border(left=MED, bottom=MED)
    ws.cell(r + 4, pc).border = Border(right=MED, bottom=MED)

# ── Populate one sheet from a dataframe ───────────────────────────────────────
def populate_sheet(ws, df):
    items      = df.to_dict('records')
    col_starts = [1 + i * 3 for i in range(LABELS_PER_ROW)]
    cur_row    = 1
    for i in range(0, len(items), LABELS_PER_ROW):
        for j in range(LABELS_PER_ROW):
            idx = i + j
            if idx < len(items):
                draw_label(ws, cur_row, col_starts[j], items[idx])
        cur_row += ROWS_PER_LABEL
    last_col = col_starts[-1] + 1
    ws.print_area = f'A1:{get_column_letter(last_col)}{cur_row}'
    return len(items)

# ── Public API ────────────────────────────────────────────────────────────────
READ_DTYPES = {'Upc': str, 'Size': str, 'ItemCode': str, 'PLU': str}

def generate_workbook(csv_files):
    """
    csv_files: list of (tab_name: str, file_obj: file-like or path)
    Returns an openpyxl Workbook (not yet saved).
    """
    wb = Workbook()
    wb.remove(wb.active)
    summary = []

    for tab_name, file_obj in csv_files:
        tab_name = tab_name[:31]
        try:
            df = pd.read_csv(file_obj, dtype=READ_DTYPES)
            ws = wb.create_sheet(title=tab_name)
            setup_sheet(ws)
            n = populate_sheet(ws, df)
            summary.append((tab_name, n, None))
        except Exception as e:
            summary.append((tab_name, 0, str(e)))

    return wb, summary
