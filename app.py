"""
Label Generator for Markt POS  —  3-step wizard
  Step 1: Upload CSV exports
  Step 2: Configure label layout & fields
  Step 3: Preview with real data → Generate & Download
"""

import streamlit as st
import pandas as pd
import io, os
from label_engine import (
    generate_workbook, build_config, get_layout,
    SIZE_PRESETS, READ_DTYPES, render_label_html
)

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Label Generator for Markt POS",
    page_icon="🏷️",
    layout="wide",
)

# ── Session state defaults ────────────────────────────────────────────────────
defaults = dict(
    step=1,
    file_bytes=[],          # list of (tab_name, bytes)
    cfg=None,
    preset_name=list(SIZE_PRESETS.keys())[0],
    custom_w=2.0, custom_h=1.0,
    # field toggles
    show_unit_price=True, show_uom=True, show_date=True,
    show_special=True, show_multibuy=True, show_item_num=True,
    show_upc=True, show_size=True, show_pack=True,
    show_desc=True, show_barcode=True,
    show_snap=True, show_wic=True,
    orange_color='#FF8000',
)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def go(step): st.session_state.step = step

# ── Step indicator ────────────────────────────────────────────────────────────
STEPS = ['1  Upload', '2  Configure', '3  Preview & Print']
step  = st.session_state.step

cols = st.columns(len(STEPS))
for i, label in enumerate(STEPS):
    active = (i + 1 == step)
    with cols[i]:
        color  = '#FF8000' if active else '#ccc'
        weight = 'bold'    if active else 'normal'
        st.markdown(
            f'<div style="text-align:center;padding:8px;border-bottom:3px solid {color};'
            f'font-weight:{weight};font-size:15px">{label}</div>',
            unsafe_allow_html=True
        )
st.write('')

# ═════════════════════════════════════════════════════════════════════════════
#  STEP 1  —  Upload
# ═════════════════════════════════════════════════════════════════════════════
if step == 1:
    st.title('Label Generator for Markt POS')
    st.markdown(
        'Each file becomes its own tab in the final workbook. '
        'Files must be exports from your POS system in the standard column format.'
    )
    st.divider()

    uploaded = st.file_uploader(
        'Drop CSV files here', type=['csv'],
        accept_multiple_files=True,
        label_visibility='collapsed',
    )

    if uploaded:
        st.session_state.file_bytes = []
        all_ok = True
        REQUIRED = {'Price', 'Description', 'Upc'}

        for f in uploaded:
            raw = f.read()
            try:
                df = pd.read_csv(io.BytesIO(raw), dtype=READ_DTYPES)
                missing = REQUIRED - set(df.columns)
                if missing:
                    st.error(f'**{f.name}** — missing columns: {", ".join(missing)}')
                    all_ok = False
                else:
                    active_count = len(df[df.get('Active', pd.Series(['TRUE']*len(df))).astype(str).str.upper() != 'FALSE']) if 'Active' in df.columns else len(df)
                    specials = int(df['SpecialPrice'].notna().astype(int).sum()) if 'SpecialPrice' in df.columns else 0
                    snap_ct  = int((df['Foodstamp'].astype(str).str.upper() == 'TRUE').sum()) if 'Foodstamp' in df.columns else 0
                    info = f'**{f.name}** — {active_count} active items'
                    if specials: info += f' · {specials} with special price'
                    if snap_ct:  info += f' · {snap_ct} SNAP/EBT eligible'
                    st.success(info + '  ✓')
                    st.session_state.file_bytes.append(
                        (os.path.splitext(f.name)[0], raw)
                    )
            except Exception as e:
                st.error(f'**{f.name}** — {e}')
                all_ok = False

        st.write('')
        if all_ok and st.session_state.file_bytes:
            if st.button('Next: Configure Labels →', type='primary', use_container_width=True):
                go(2); st.rerun()
    else:
        st.info('👆  Upload at least one CSV to continue.')


# ═════════════════════════════════════════════════════════════════════════════
#  STEP 2  —  Configure
# ═════════════════════════════════════════════════════════════════════════════
elif step == 2:
    st.title('Configure your labels')
    st.divider()

    # ── Label size ─────────────────────────────────────────────────────────────
    st.subheader('📐  Label stock size')

    # Make size buttons tall and card-like
    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]
        div[data-testid="stButton"] > button {
        min-height: 80px;
        white-space: pre-wrap;
        line-height: 1.5;
        font-size: 13px;
    }
    </style>
    """, unsafe_allow_html=True)

    preset_names = list(SIZE_PRESETS.keys())
    size_cols = st.columns(len(preset_names))
    for i, name in enumerate(preset_names):
        dims = SIZE_PRESETS[name]
        with size_cols[i]:
            active = (st.session_state.preset_name == name)
            short  = name.split('—')[0].strip()
            if dims:
                btn_label = f'{short}\n{dims[0]}" × {dims[1]}"'
            else:
                btn_label = f'{short}\nEnter dimensions below'
            if st.button(btn_label, key=f'sz_{i}',
                         type='primary' if active else 'secondary',
                         use_container_width=True):
                st.session_state.preset_name = name
                st.rerun()

    if SIZE_PRESETS[st.session_state.preset_name] is None:
        cw, ch = st.columns(2)
        with cw: st.session_state.custom_w = st.number_input('Width (in)', 1.0, 6.0, st.session_state.custom_w, 0.25)
        with ch: st.session_state.custom_h = st.number_input('Height (in)', 0.5, 4.0, st.session_state.custom_h, 0.25)

    st.divider()

    # ── Fields ─────────────────────────────────────────────────────────────────
    st.subheader('📋  Fields to include')
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown('**🟠 Unit Price Box**')
        st.checkbox('Unit price',       key='show_unit_price')
        st.checkbox('Unit of measure',  key='show_uom',
                    help='e.g. PER POUND, PER OUNCE')
        st.checkbox('Date',             key='show_date')

    with c2:
        st.markdown('**💲 Price Area**')
        st.caption('Retail price is always shown.')
        st.checkbox('Special / sale price', key='show_special',
                    help='Items with an active SpecialPrice show in red. Regular price becomes "WAS $X.XX".')
        st.checkbox('Multi-buy price',      key='show_multibuy',
                    help='Shows "2 FOR $5.00" when GroupPrice and Quantity are set.')
        st.checkbox('Vendor item number',   key='show_item_num')
        st.checkbox('UPC number',           key='show_upc')
        st.checkbox('Size / weight',        key='show_size')
        st.checkbox('Pack count',           key='show_pack',
                    help='e.g. "24-pack" from the Pack field.')

    with c3:
        st.markdown('**📋 Bottom Bar**')
        st.checkbox('Item description', key='show_desc')
        st.checkbox('Barcode',          key='show_barcode')
        st.markdown('**🏷 Compliance Badges**')
        st.checkbox('SNAP / EBT badge', key='show_snap',
                    help='Green badge on items where Foodstamp = TRUE.')
        st.checkbox('WIC badge',        key='show_wic',
                    help='Blue badge on items where Wicable = 1.')

    st.divider()

    # ── Style ──────────────────────────────────────────────────────────────────
    st.subheader('🎨  Style')
    st.session_state.orange_color = st.color_picker(
        'Unit price box color', st.session_state.orange_color
    )

    st.divider()
    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button('← Back', use_container_width=True): go(1); st.rerun()
    with nav2:
        if st.button('Next: Preview →', type='primary', use_container_width=True):
            go(3); st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  STEP 3  —  Preview & Generate
# ═════════════════════════════════════════════════════════════════════════════
elif step == 3:
    st.title('Preview & Generate')

    # Build config from session state
    preset_dims = SIZE_PRESETS[st.session_state.preset_name]
    if preset_dims:
        lw, lh = preset_dims
    else:
        lw, lh = st.session_state.custom_w, st.session_state.custom_h

    cfg = build_config(
        label_width_in=lw, label_height_in=lh,
        show_unit_price=st.session_state.show_unit_price,
        show_uom=st.session_state.show_uom,
        show_date=st.session_state.show_date,
        show_special_price=st.session_state.show_special,
        show_multibuy=st.session_state.show_multibuy,
        show_item_number=st.session_state.show_item_num,
        show_upc=st.session_state.show_upc,
        show_size=st.session_state.show_size,
        show_pack=st.session_state.show_pack,
        show_description=st.session_state.show_desc,
        show_barcode=st.session_state.show_barcode,
        show_snap_badge=st.session_state.show_snap,
        show_wic_badge=st.session_state.show_wic,
        orange_hex=st.session_state.orange_color.lstrip('#'),
    )
    st.session_state.cfg = cfg

    # ── Real-data HTML preview ─────────────────────────────────────────────────
    st.subheader('Label preview — real data')
    st.caption('Showing up to 8 items from your first uploaded file. '
               'What you see here matches what will be in the Excel.')

    PREVIEW_COUNT = 8
    all_items = []
    if st.session_state.file_bytes:
        name0, raw0 = st.session_state.file_bytes[0]
        df0 = pd.read_csv(io.BytesIO(raw0), dtype=READ_DTYPES)
        if 'Active' in df0.columns:
            df0 = df0[df0['Active'].astype(str).str.strip().str.upper() != 'FALSE']
        all_items = df0.head(PREVIEW_COUNT).to_dict('records')

    if all_items:
        prev_cols = st.columns(4)
        for i, item in enumerate(all_items):
            with prev_cols[i % 4]:
                html = render_label_html(item, cfg)
                st.html(html)
                st.write('')
    else:
        st.warning('No items to preview — check your upload.')

    st.divider()

    # ── Summary stats ──────────────────────────────────────────────────────────
    total_items = sum(
        len(pd.read_csv(io.BytesIO(raw), dtype=READ_DTYPES))
        for _, raw in st.session_state.file_bytes
    )
    layout = get_layout(cfg)
    lpr    = layout['labels_per_row']
    files  = len(st.session_state.file_bytes)
    st.info(
        f'**{total_items} items** across **{files} tab(s)** · '
        f'**{lpr} labels across** per row · '
        f'**{lw}" × {lh}"** labels · '
        f'Inactive items will be filtered out automatically.'
    )

    st.divider()

    # ── Nav + Generate ─────────────────────────────────────────────────────────
    nav1, nav2 = st.columns([1, 2])
    with nav1:
        if st.button('← Back to Configure', use_container_width=True): go(2); st.rerun()
    with nav2:
        if st.button('⚙️  Generate Excel', type='primary', use_container_width=True):
            with st.spinner('Generating labels and barcodes…'):
                file_data = [(name, io.BytesIO(raw))
                             for name, raw in st.session_state.file_bytes]
                wb, summary = generate_workbook(file_data, cfg)
                buf = io.BytesIO(); wb.save(buf); buf.seek(0)

            total = sum(n for _, n, e in summary if e is None)
            st.success(f'Done — {total} labels ready')
            for tab, n, err in summary:
                if err: st.error(f'**{tab}**: {err}')
                else:   st.write(f'- **{tab}** — {n} labels')

            st.download_button(
                '⬇️  Download Price_Labels.xlsx',
                data=buf,
                file_name='Price_Labels.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
            )
