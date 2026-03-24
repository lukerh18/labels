"""
label_engine.py
Core label-generation logic.
Call generate_workbook(csv_files, config) where csv_files is a list of
(tab_name, file_obj) tuples and config is a dict from build_config().
Returns (openpyxl Workbook, summary list).
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
import pandas as pd
from datetime import datetime, date
import barcode
from barcode.writer import ImageWriter
import os, tempfile

# ── Barcode cache dir ─────────────────────────────────────────────────────────
BC_DIR = os.path.join(tempfile.gettempdir(), 'lbl_barcodes')
os.makedirs(BC_DIR, exist_ok=True)

today_str = datetime.now().strftime('%m/%d/%y')
today_date = datetime.now().date()

# ── Label size presets (width_in, height_in) ──────────────────────────────────
SIZE_PRESETS = {
    '2" × 1"  — Standard Shelf':   (2.0, 1.0),
    '3" × 1"  — Wide Shelf':        (3.0, 1.0),
    '2" × 1.5" — Tall Shelf':       (2.0, 1.5),
    '4" × 2"  — Large Shelf':       (4.0, 2.0),
    '1.5" × 1" — Small Label':      (1.5, 1.0),
    'Custom':                        None,
}

# ── Default config ────────────────────────────────────────────────────────────
def build_config(
    label_width_in   = 2.0,
    label_height_in  = 1.0,
    # Orange box fields
    show_unit_price  = True,
    show_uom         = True,
    show_date        = True,
    # Right column fields
    show_special_price = False,
    show_item_number = True,
    show_upc         = True,
    show_size        = True,
    # Bottom bar
    show_description = True,
    show_barcode     = True,
    # Style
    orange_hex       = 'FF8000',
):
    return dict(
        label_width_in=label_width_in,
        label_height_in=label_height_in,
        show_unit_price=show_unit_price,
        show_uom=show_uom,
        show_date=show_date,
        show_special_price=show_special_price,
        show_item_number=show_item_number,
        show_upc=show_upc,
        show_size=show_size,
        show_description=show_description,
        show_barcode=show_barcode,
        orange_hex=orange_hex,
    )

DEFAULT_CONFIG = build_config()

# ── Layout calculator — scales everything from the base 2"×1" template ────────
#
#  Base row plan (72 pt = 1 inch):
#    row 0  8 pt   header:  "UNIT PRICE"  |  "RETAIL PRICE" / "SPECIAL PRICE"
#    row 1 22 pt   amounts: unit price $  |  main price $  (largest font)
#    row 2 10 pt   sub:     UOM           |  item # / was-price
#    row 3 12 pt   detail:  date          |  UPC + size
#    row 4 16 pt   bottom:  description   |  barcode
#    row 5  4 pt   gap
#
BASE_ROW_H   = [8, 22, 10, 12, 16, 4]   # pt, sums to 72
BASE_W       = 2.0
BASE_H       = 1.0
CHARS_PER_IN = 13.7    # Excel chars per inch (Arial 11pt @ 96 DPI)
LABELS_PER_ROW_BASE = 4

def get_layout(cfg):
    sw = cfg['label_width_in']  / BASE_W
    sh = cfg['label_height_in'] / BASE_H
    total_pt  = int(cfg['label_height_in'] * 72)
    base_sum  = sum(BASE_ROW_H)                      # 72
    row_h     = [max(4, round(h * total_pt / base_sum)) for h in BASE_ROW_H]
    # nudge last row so total is exact
    row_h[-1] += total_pt - sum(row_h)

    orange_chars = max(8,  round(11 * sw))
    price_chars  = max(10, round(16 * sw))
    gap_chars    = max(2,  round(3  * sw))

    # labels per row — fit as many 2"-wide labels as possible on 11" landscape
    usable_in = 11.0 - 0.5         # 0.25" margin each side
    labels_per_row = max(1, int(usable_in / cfg['label_width_in']))

    # font sizes scale with height
    def fs(base): return max(5, round(base * sh))

    return dict(
        row_h          = row_h,
        orange_chars   = orange_chars,
        price_chars    = price_chars,
        gap_chars      = gap_chars,
        labels_per_row = labels_per_row,
        rows_per_label = len(BASE_ROW_H),
        fs_hdr         = fs(5.5),   # "UNIT PRICE" / "RETAIL PRICE"
        fs_unit_price  = fs(11),    # unit price amount in orange
        fs_uom         = fs(6.5),   # PER POUND etc.
        fs_retail      = fs(22),    # retail/special price — largest
        fs_was         = fs(7),     # "WAS $X.XX" when special price shown
        fs_sub         = fs(5.5),   # item# / small sub-text
        fs_detail      = fs(6),     # date / UPC line
        fs_desc        = fs(6.5),   # description
    )

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_uom(uom_raw, scale_raw):
    scale = str(scale_raw).strip().upper() == 'TRUE'
    if pd.isna(uom_raw) or str(uom_raw).strip() in ('', 'nan'):
        return 'PER POUND' if scale else 'EACH'
    u = str(uom_raw).strip().upper()
    mapping = {
        'LB': 'PER POUND',    'LBS': 'PER POUND',
        'OZ': 'PER OUNCE',    'OUNCE': 'PER OUNCE',  'OUNCES': 'PER OUNCE',
        'QT': 'PER QUART',    'QUART': 'PER QUART',
        'EA': 'EACH',         'EACH': 'EACH',
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

def is_special_active(item):
    """True if item has a SpecialPrice and today falls within Start/End dates."""
    sp = item.get('SpecialPrice', '')
    try:
        sp_val = float(sp)
        if sp_val <= 0:
            return False, None
    except (TypeError, ValueError):
        return False, None

    # Check date window
    sd = item.get('StartDate', '')
    ed = item.get('EndDate', '')
    try:
        start = pd.to_datetime(sd).date() if pd.notna(sd) and str(sd).strip() not in ('','nan') else None
        end   = pd.to_datetime(ed).date() if pd.notna(ed) and str(ed).strip() not in ('','nan') else None
        if start and today_date < start:
            return False, None
        if end and today_date > end:
            return False, None
    except Exception:
        pass

    return True, sp_val

# ── Sheet setup ───────────────────────────────────────────────────────────────
def setup_sheet(ws, layout):
    ws.sheet_view.showGridLines = False
    ws.page_setup.paperSize    = 1
    ws.page_setup.orientation  = 'landscape'
    ws.page_margins.left       = 0.25
    ws.page_margins.right      = 0.25
    ws.page_margins.top        = 0.35
    ws.page_margins.bottom     = 0.35
    ws.page_setup.fitToPage    = True
    ws.page_setup.fitToWidth   = 1
    lpr = layout['labels_per_row']
    for i in range(lpr):
        ws.column_dimensions[get_column_letter(i * 3 + 1)].width = layout['orange_chars']
        ws.column_dimensions[get_column_letter(i * 3 + 2)].width = layout['price_chars']
        ws.column_dimensions[get_column_letter(i * 3 + 3)].width = layout['gap_chars']

# ── Single label renderer ─────────────────────────────────────────────────────
def draw_label(ws, r, oc, item, cfg, layout):
    pc  = oc + 1
    MED = Side(style='medium')
    THIN = Side(style='thin')
    ORANGE_FILL = PatternFill('solid',
                              start_color=cfg['orange_hex'],
                              end_color=cfg['orange_hex'])
    WHITE = 'FFFFFF'

    # ── Extract values ────────────────────────────────────────────────────────
    try:    price = float(item['Price'])
    except: price = 0.0

    pp = item.get('PricePer', '')
    try:    price_per = float(pp) if pd.notna(pp) and str(pp).strip() not in ('','nan') else None
    except: price_per = None

    uom      = get_uom(item.get('UnitOfMeasure',''), item.get('Scale','FALSE'))
    desc     = str(item.get('Description','')).upper().strip()
    size     = clean_size(item.get('Size',''))
    upc_raw  = str(item.get('Upc','')).strip()
    upc_fmt  = fmt_upc(upc_raw)
    ic       = str(item.get('ItemCode','')).strip()
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

    # Special price logic
    use_special, special_val = (False, None)
    if cfg['show_special_price']:
        use_special, special_val = is_special_active(item)

    # ── Row heights ───────────────────────────────────────────────────────────
    for i, h in enumerate(layout['row_h']):
        ws.row_dimensions[r + i].height = h

    # ── Helper setters ────────────────────────────────────────────────────────
    def oc_set(row, val, sz, bold=False):
        c = ws.cell(row, oc)
        c.value     = val
        c.fill      = ORANGE_FILL
        c.font      = Font(name='Arial', size=sz, bold=bold, color=WHITE)
        c.alignment = Alignment(horizontal='center', vertical='center')

    def pc_set(row, val, sz, bold=False, color='000000', align='center'):
        c = ws.cell(row, pc)
        c.value     = val
        c.font      = Font(name='Arial', size=sz, bold=bold, color=color)
        c.alignment = Alignment(horizontal=align, vertical='center')

    # ── ROW 0  — headers ──────────────────────────────────────────────────────
    oc_set(r, 'UNIT PRICE' if cfg['show_unit_price'] else '', layout['fs_hdr'])

    if use_special:
        pc_set(r, 'SPECIAL PRICE', layout['fs_hdr'], color='CC0000')
    else:
        pc_set(r, 'RETAIL PRICE', layout['fs_hdr'])

    # ── ROW 1  — main prices ──────────────────────────────────────────────────
    if cfg['show_unit_price']:
        oc_set(r+1, f'${price_per:.2f}' if price_per is not None else 'N/A',
               layout['fs_unit_price'], bold=True)
    else:
        oc_set(r+1, '', layout['fs_unit_price'])

    if use_special:
        pc_set(r+1, f'${special_val:.2f}', layout['fs_retail'], bold=True, color='CC0000')
    else:
        pc_set(r+1, f'${price:.2f}', layout['fs_retail'], bold=True)

    # ── ROW 2  — UOM (orange) | item# or "WAS" price (right) ─────────────────
    oc_set(r+2, uom if cfg['show_uom'] else '', layout['fs_uom'], bold=True)

    if use_special:
        # Show regular price as "WAS $X.XX" and item# if available
        was_parts = [f'WAS ${price:.2f}']
        if cfg['show_item_number'] and item_code:
            was_parts.append(f'Item #: {item_code}')
        pc_set(r+2, '   '.join(was_parts), layout['fs_was'])
    else:
        pc_set(r+2, f'Item #: {item_code}' if (cfg['show_item_number'] and item_code) else '',
               layout['fs_sub'])

    # ── ROW 3  — date (outside orange) | UPC + size ──────────────────────────
    dc = ws.cell(r+3, oc)
    dc.value     = date_lbl if cfg['show_date'] else ''
    dc.font      = Font(name='Arial', size=layout['fs_detail'])
    dc.alignment = Alignment(horizontal='center', vertical='center')

    upc_parts = []
    if cfg['show_upc']:        upc_parts.append(upc_fmt)
    if cfg['show_size']:       upc_parts.append(size_display)
    uc = ws.cell(r+3, pc)
    uc.value     = '   '.join(filter(None, upc_parts))
    uc.font      = Font(name='Arial', size=layout['fs_detail'])
    uc.alignment = Alignment(horizontal='center', vertical='center')

    # ── ROW 4  — description | barcode ───────────────────────────────────────
    desc_c = ws.cell(r+4, oc)
    max_desc_chars = max(10, layout['orange_chars'] - 2)
    desc_c.value     = desc[:max_desc_chars] if cfg['show_description'] else ''
    desc_c.font      = Font(name='Arial', bold=True, size=layout['fs_desc'])
    desc_c.alignment = Alignment(horizontal='left', vertical='center', indent=1)

    if cfg['show_barcode']:
        bc_path = make_barcode(upc_raw)
        if bc_path:
            try:
                img = XLImage(bc_path)
                # Scale barcode to fit price column width and row height
                px_per_char = 7
                px_per_pt   = 1.33
                img.width  = max(60, layout['price_chars']  * px_per_char - 4)
                img.height = max(14, layout['row_h'][4] * px_per_pt - 2)
                ws.add_image(img, f'{get_column_letter(pc)}{r+4}')
            except Exception:
                pass

    # ── Borders ───────────────────────────────────────────────────────────────
    ws.cell(r,   oc).border = Border(top=MED, left=MED, right=THIN)
    ws.cell(r+1, oc).border = Border(left=MED, right=THIN)
    ws.cell(r+2, oc).border = Border(left=MED, right=THIN, bottom=THIN)
    ws.cell(r,   pc).border = Border(top=MED, right=MED)
    ws.cell(r+1, pc).border = Border(right=MED)
    ws.cell(r+2, pc).border = Border(right=MED, bottom=THIN)
    ws.cell(r+3, oc).border = Border(left=MED)
    ws.cell(r+3, pc).border = Border(right=MED, bottom=THIN)
    ws.cell(r+4, oc).border = Border(left=MED, bottom=MED)
    ws.cell(r+4, pc).border = Border(right=MED, bottom=MED)

# ── Populate one sheet ────────────────────────────────────────────────────────
def populate_sheet(ws, df, cfg, layout):
    items      = df.to_dict('records')
    lpr        = layout['labels_per_row']
    col_starts = [1 + i * 3 for i in range(lpr)]
    cur_row    = 1
    for i in range(0, len(items), lpr):
        for j in range(lpr):
            idx = i + j
            if idx < len(items):
                draw_label(ws, cur_row, col_starts[j], items[idx], cfg, layout)
        cur_row += layout['rows_per_label']
    last_col = col_starts[-1] + 1
    ws.print_area = f'A1:{get_column_letter(last_col)}{cur_row}'
    return len(items)

# ── Public API ────────────────────────────────────────────────────────────────
READ_DTYPES = {'Upc': str, 'Size': str, 'ItemCode': str, 'PLU': str}

def generate_workbook(csv_files, cfg=None):
    """
    csv_files : list of (tab_name: str, file_obj)
    cfg       : dict from build_config() — uses DEFAULT_CONFIG if omitted
    Returns   : (openpyxl Workbook, summary list of (tab, n, error))
    """
    if cfg is None:
        cfg = DEFAULT_CONFIG
    layout  = get_layout(cfg)
    wb      = Workbook()
    wb.remove(wb.active)
    summary = []

    for tab_name, file_obj in csv_files:
        tab_name = tab_name[:31]
        try:
            df = pd.read_csv(file_obj, dtype=READ_DTYPES)
            ws = wb.create_sheet(title=tab_name)
            setup_sheet(ws, layout)
            n = populate_sheet(ws, df, cfg, layout)
            summary.append((tab_name, n, None))
        except Exception as e:
            summary.append((tab_name, 0, str(e)))

    return wb, summary
