"""
NY Price Label Generator — Web App
===================================
Run locally:   streamlit run app.py
Deploy free:   https://streamlit.io/cloud  (connect your GitHub repo)
"""

import streamlit as st
import pandas as pd
import io, os
from label_engine import generate_workbook

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NY Price Label Generator",
    page_icon="🏷️",
    layout="centered",
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🏷️ NY Price Label Generator")
st.markdown(
    "Upload one or more product CSV exports. "
    "Each file becomes its own tab of **2×1-inch NY-compliant labels** "
    "with embedded barcodes, ready to print."
)
st.divider()

# ── File uploader ─────────────────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "Drop your CSV export(s) here",
    type=["csv"],
    accept_multiple_files=True,
    help="Must have the same column format as your POS export. "
         "Each file gets its own tab in the output workbook.",
)

if not uploaded_files:
    st.info("👆  Upload at least one CSV file to get started.")
    st.stop()

# ── Preview each uploaded file ────────────────────────────────────────────────
st.subheader("Files ready to process")
file_data = []
all_valid = True

for f in uploaded_files:
    tab_name = os.path.splitext(f.name)[0]
    try:
        df = pd.read_csv(f, dtype={'Upc': str, 'Size': str, 'ItemCode': str, 'PLU': str})
        item_count = len(df)
        has_price  = 'Price' in df.columns
        has_desc   = 'Description' in df.columns
        has_upc    = 'Upc' in df.columns

        if not (has_price and has_desc and has_upc):
            st.error(
                f"**{f.name}** — missing required columns "
                f"({'Price ' if not has_price else ''}"
                f"{'Description ' if not has_desc else ''}"
                f"{'Upc' if not has_upc else ''}).strip()"
            )
            all_valid = False
        else:
            st.success(f"**{f.name}** — {item_count} items  ✓")
            f.seek(0)   # reset so we can re-read below
            file_data.append((tab_name, f))
    except Exception as e:
        st.error(f"**{f.name}** — could not be read: {e}")
        all_valid = False

st.divider()

# ── Generate button ───────────────────────────────────────────────────────────
if not all_valid:
    st.warning("Fix the errors above before generating.")
    st.stop()

if st.button("⚙️  Generate Labels", type="primary", use_container_width=True):
    with st.spinner("Generating labels and barcodes…"):
        wb, summary = generate_workbook(file_data)

        # Save workbook to an in-memory buffer
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

    # ── Results ───────────────────────────────────────────────────────────────
    st.success("Done!")
    total = sum(n for _, n, err in summary if err is None)

    for tab, n, err in summary:
        if err:
            st.error(f"**{tab}**: {err}")
        else:
            st.write(f"- **{tab}** — {n} labels")

    st.write(f"**Total: {total} labels across {len([s for s in summary if s[2] is None])} tab(s)**")

    # ── Download button ───────────────────────────────────────────────────────
    st.download_button(
        label="⬇️  Download Price_Labels.xlsx",
        data=buf,
        file_name="Price_Labels.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Labels are 2×1 inches, landscape, 4 across — sized for standard label stock. "
    "Each label includes the orange NY-compliant unit-price box, retail price, "
    "vendor item number, UPC, and an embedded Code128 barcode."
)
