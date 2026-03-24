"""
NY Price Label Generator — Web App
Run locally : streamlit run app.py
Deploy free : https://streamlit.io/cloud
"""

import streamlit as st
import pandas as pd
import io, os
from label_engine import generate_workbook, build_config, SIZE_PRESETS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NY Price Label Generator",
    page_icon="🏷️",
    layout="wide",
)

# ═════════════════════════════════════════════════════════════════════════════
#  SIDEBAR  — Label Configuration
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("⚙️ Label Configuration")

    # ── 1. Label Stock Size ───────────────────────────────────────────────────
    st.subheader("📐 Label Stock Size")

    preset_name = st.selectbox(
        "Size preset",
        options=list(SIZE_PRESETS.keys()),
        index=0,
        help="Choose a standard label stock size, or pick Custom to enter your own dimensions."
    )

    preset_dims = SIZE_PRESETS[preset_name]
    if preset_dims is None:   # Custom
        col_w, col_h = st.columns(2)
        with col_w:
            label_w = st.number_input("Width (inches)",  min_value=1.0, max_value=6.0,
                                       value=2.0, step=0.25)
        with col_h:
            label_h = st.number_input("Height (inches)", min_value=0.5, max_value=4.0,
                                       value=1.0, step=0.25)
    else:
        label_w, label_h = preset_dims
        st.caption(f"**{label_w}\" wide × {label_h}\" tall**")

    st.divider()

    # ── 2. Fields — Orange Box ────────────────────────────────────────────────
    st.subheader("🟠 Orange Box Fields")
    show_unit_price = st.checkbox("Unit price",           value=True)
    show_uom        = st.checkbox("Unit of measure",      value=True,
                                   help="e.g. PER POUND, PER OUNCE, EACH")
    show_date       = st.checkbox("Date",                 value=True)

    st.divider()

    # ── 3. Fields — Price Area ────────────────────────────────────────────────
    st.subheader("💲 Price Area Fields")
    st.caption("Retail price is always shown.")
    show_special    = st.checkbox("Special / sale price",
                                   value=False,
                                   help="When active, items with a valid SpecialPrice and "
                                        "within their Start–End date window will show the "
                                        "sale price in red. The regular price appears as "
                                        "'WAS $X.XX' below it.")
    show_item_num   = st.checkbox("Vendor item number",   value=True)
    show_upc        = st.checkbox("UPC number",           value=True)
    show_size       = st.checkbox("Size / weight",        value=True)

    st.divider()

    # ── 4. Fields — Bottom Bar ────────────────────────────────────────────────
    st.subheader("📋 Bottom Bar Fields")
    show_desc       = st.checkbox("Item description",     value=True)
    show_barcode    = st.checkbox("Barcode image",        value=True)

    st.divider()

    # ── 5. Styling ────────────────────────────────────────────────────────────
    st.subheader("🎨 Style")
    orange_color = st.color_picker("Unit price box color", value="#FF8000")
    orange_hex   = orange_color.lstrip('#')

    # ── Live label preview ────────────────────────────────────────────────────
    st.divider()
    st.subheader("👁 Label Preview")

    # Rough HTML mock of the label layout
    unit_row  = "UNIT PRICE<br><b>$X.XX</b><br>PER POUND" if show_unit_price else ""
    if show_uom and show_unit_price:
        pass   # already included above
    elif show_unit_price:
        unit_row = "UNIT PRICE<br><b>$X.XX</b>"
    date_row  = f"<small>{pd.Timestamp.now().strftime('%m/%d/%y')}</small>" if show_date else ""
    price_lbl = "SPECIAL PRICE" if show_special else "RETAIL PRICE"
    price_row = f"<span style='color:#CC0000;font-size:1.4em;font-weight:bold'>$X.XX</span>" \
                if show_special else "<span style='font-size:1.4em;font-weight:bold'>$X.XX</span>"
    was_row   = f"<small>WAS $X.XX</small>" if show_special else ""
    item_row  = "<small>Item #: 12345</small>" if show_item_num else ""
    upc_row   = "<small>0-12345-67890-1</small>" if show_upc else ""
    desc_row  = "<b>ITEM DESCRIPTION</b>" if show_desc else ""
    bc_row    = "▌▌▌▌▌▌▌▌▌▌▌▌" if show_barcode else ""

    preview_html = f"""
    <div style="font-family:Arial;font-size:11px;border:2px solid #333;
                display:flex;flex-direction:column;width:100%;max-width:280px;">
      <div style="display:flex;min-height:56px;">
        <div style="background:{orange_color};color:white;width:40%;
                    display:flex;flex-direction:column;align-items:center;
                    justify-content:center;text-align:center;padding:4px;
                    font-size:10px;border-right:1px solid #999;">
          {unit_row}
        </div>
        <div style="width:60%;display:flex;flex-direction:column;
                    align-items:center;justify-content:center;padding:4px;
                    text-align:center;">
          <span style="font-size:9px">{price_lbl}</span>
          {price_row}
          {was_row}
          {item_row}
        </div>
      </div>
      <div style="display:flex;border-top:1px solid #ccc;font-size:9px;
                  padding:2px 4px;">
        <div style="width:40%;text-align:center;">{date_row}</div>
        <div style="width:60%;text-align:center;">{upc_row}</div>
      </div>
      <div style="display:flex;border-top:1px solid #333;padding:2px 4px;
                  align-items:center;justify-content:space-between;">
        <div style="font-size:9px;">{desc_row}</div>
        <div style="font-size:9px;letter-spacing:-1px;">{bc_row}</div>
      </div>
    </div>
    """
    st.html(preview_html)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN AREA  — Upload & Generate
# ═════════════════════════════════════════════════════════════════════════════
st.title("🏷️ NY Price Label Generator")
st.markdown(
    "Upload one or more CSV exports — each becomes its own tab of "
    "**NY-compliant 2×1 price labels** with embedded barcodes. "
    "Use the sidebar to configure the label layout."
)
st.divider()

uploaded_files = st.file_uploader(
    "Drop your CSV export(s) here",
    type=["csv"],
    accept_multiple_files=True,
    help="Each file becomes a separate tab in the output workbook.",
)

if not uploaded_files:
    st.info("👆  Upload at least one CSV file, then hit **Generate Labels**.")
    st.stop()

# ── Validate uploads ──────────────────────────────────────────────────────────
st.subheader("Files ready to process")
file_data  = []
all_valid  = True
REQUIRED   = {'Price', 'Description', 'Upc'}

for f in uploaded_files:
    tab_name = os.path.splitext(f.name)[0]
    try:
        df = pd.read_csv(f, dtype={'Upc': str, 'Size': str,
                                    'ItemCode': str, 'PLU': str})
        missing = REQUIRED - set(df.columns)
        if missing:
            st.error(f"**{f.name}** — missing columns: {', '.join(missing)}")
            all_valid = False
        else:
            # Count specials for info
            special_count = 0
            if 'SpecialPrice' in df.columns:
                special_count = df['SpecialPrice'].notna().sum()
            info = f"**{f.name}** — {len(df)} items"
            if special_count:
                info += f"  ·  {special_count} with special price"
            st.success(info + "  ✓")
            f.seek(0)
            file_data.append((tab_name, f))
    except Exception as e:
        st.error(f"**{f.name}** — could not be read: {e}")
        all_valid = False

st.divider()

if not all_valid:
    st.warning("Fix the errors above before generating.")
    st.stop()

# ── Build config from sidebar ─────────────────────────────────────────────────
cfg = build_config(
    label_width_in   = label_w,
    label_height_in  = label_h,
    show_unit_price  = show_unit_price,
    show_uom         = show_uom,
    show_date        = show_date,
    show_special_price = show_special,
    show_item_number = show_item_num,
    show_upc         = show_upc,
    show_size        = show_size,
    show_description = show_desc,
    show_barcode     = show_barcode,
    orange_hex       = orange_hex,
)

# ── Generate ──────────────────────────────────────────────────────────────────
if st.button("⚙️  Generate Labels", type="primary", use_container_width=True):
    with st.spinner("Generating labels and barcodes…"):
        wb, summary = generate_workbook(file_data, cfg)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

    total = sum(n for _, n, err in summary if err is None)
    st.success(f"Done — {total} labels across {len([s for s in summary if s[2] is None])} tab(s)")

    for tab, n, err in summary:
        if err:
            st.error(f"**{tab}**: {err}")
        else:
            st.write(f"- **{tab}** — {n} labels")

    st.download_button(
        label    = "⬇️  Download Price_Labels.xlsx",
        data     = buf,
        file_name= "Price_Labels.xlsx",
        mime     = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Labels print landscape on Letter paper. "
    "Each label includes the NY-compliant unit-price box, retail price, "
    "UPC, and an embedded Code128 barcode. "
    "Special prices are highlighted in red when active within their date window."
)
