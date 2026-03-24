"""
Label Generator for Markt POS  —  2-step wizard
  Step 1: Upload CSV exports
  Step 2: Configure (left) + Live preview (right) → Generate & Download
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
    generated_xlsx=None,    # bytes of last generated workbook
    preset_name=list(SIZE_PRESETS.keys())[0],
    custom_w=2.0, custom_h=1.0,
    # field toggles — all core features on by default
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
STEPS = ['1  Upload', '2  Configure & Preview']
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
        st.session_state.generated_xlsx = None
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
                    active_count = (
                        len(df[df['Active'].astype(str).str.upper() != 'FALSE'])
                        if 'Active' in df.columns else len(df)
                    )
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
#  STEP 2  —  Configure (left) + Live Preview (right)
# ═════════════════════════════════════════════════════════════════════════════
elif step == 2:

    left, right = st.columns([1, 1.9], gap='large')

    # ── LEFT: configuration panel ─────────────────────────────────────────────
    with left:
        st.subheader('⚙️  Configure')

        # Size
        st.markdown('**📐 Label stock size**')
        preset_names = list(SIZE_PRESETS.keys())
        st.radio(
            'Size preset',
            options=preset_names,
            key='preset_name',
            label_visibility='collapsed',
        )
        if SIZE_PRESETS[st.session_state.preset_name] is None:
            cw, ch = st.columns(2)
            with cw: st.number_input('Width (in)',  1.0, 6.0, st.session_state.custom_w, 0.25, key='custom_w')
            with ch: st.number_input('Height (in)', 0.5, 4.0, st.session_state.custom_h, 0.25, key='custom_h')

        st.divider()

        # Fields
        st.markdown('**📋 Fields to include**')

        st.markdown('<p style="font-size:12px;color:#888;margin-bottom:4px">🟠 Unit price box</p>', unsafe_allow_html=True)
        fa, fb = st.columns(2)
        with fa: st.checkbox('Unit price',      key='show_unit_price')
        with fb: st.checkbox('Unit of measure', key='show_uom')
        st.checkbox('Date', key='show_date')

        st.markdown('<p style="font-size:12px;color:#888;margin:8px 0 4px">💲 Price area</p>', unsafe_allow_html=True)
        fc, fd = st.columns(2)
        with fc: st.checkbox('Special / sale',  key='show_special',  help='Items with an active SpecialPrice show in red.')
        with fd: st.checkbox('Multi-buy',       key='show_multibuy', help='e.g. "2 FOR $5.00"')
        fe, ff = st.columns(2)
        with fe: st.checkbox('Item number',     key='show_item_num')
        with ff: st.checkbox('UPC',             key='show_upc')
        fg, fh = st.columns(2)
        with fg: st.checkbox('Size / weight',   key='show_size')
        with fh: st.checkbox('Pack count',      key='show_pack', help='e.g. "24-pack"')

        st.markdown('<p style="font-size:12px;color:#888;margin:8px 0 4px">📋 Bottom bar</p>', unsafe_allow_html=True)
        fi, fj = st.columns(2)
        with fi: st.checkbox('Description',     key='show_desc')
        with fj: st.checkbox('Barcode',         key='show_barcode')

        st.markdown('<p style="font-size:12px;color:#888;margin:8px 0 4px">🏷 Badges</p>', unsafe_allow_html=True)
        fk, fl = st.columns(2)
        with fk: st.checkbox('SNAP / EBT', key='show_snap', help='Foodstamp = TRUE')
        with fl: st.checkbox('WIC',        key='show_wic',  help='Wicable = 1')

        st.divider()

        # Style
        st.markdown('**🎨 Style**')
        st.color_picker('Unit price box color', key='orange_color')

        st.divider()
        if st.button('← Back to Upload', use_container_width=True):
            go(1); st.rerun()

    # ── RIGHT: live preview + generate ───────────────────────────────────────
    with right:
        # Build cfg fresh on every render from session state
        preset_dims = SIZE_PRESETS[st.session_state.preset_name]
        if preset_dims:
            lw, lh = preset_dims
        else:
            lw, lh = st.session_state.custom_w, st.session_state.custom_h

        cfg = build_config(
            label_width_in    = lw,
            label_height_in   = lh,
            show_unit_price   = st.session_state.show_unit_price,
            show_uom          = st.session_state.show_uom,
            show_date         = st.session_state.show_date,
            show_special_price= st.session_state.show_special,
            show_multibuy     = st.session_state.show_multibuy,
            show_item_number  = st.session_state.show_item_num,
            show_upc          = st.session_state.show_upc,
            show_size         = st.session_state.show_size,
            show_pack         = st.session_state.show_pack,
            show_description  = st.session_state.show_desc,
            show_barcode      = st.session_state.show_barcode,
            show_snap_badge   = st.session_state.show_snap,
            show_wic_badge    = st.session_state.show_wic,
            orange_hex        = st.session_state.orange_color.lstrip('#'),
        )

        st.subheader('Live preview')
        st.caption(f'Showing up to 4 items from your first file · {lw}" × {lh}" labels · updates as you configure')

        PREVIEW_COUNT = 4
        all_items = []
        if st.session_state.file_bytes:
            _, raw0 = st.session_state.file_bytes[0]
            df0 = pd.read_csv(io.BytesIO(raw0), dtype=READ_DTYPES)
            if 'Active' in df0.columns:
                df0 = df0[df0['Active'].astype(str).str.strip().str.upper() != 'FALSE']
            all_items = df0.head(PREVIEW_COUNT).to_dict('records')

        if all_items:
            prev_cols = st.columns(2)
            for i, item in enumerate(all_items):
                with prev_cols[i % 2]:
                    st.html(render_label_html(item, cfg))
        else:
            st.warning('No items to preview — check your upload.')

        st.divider()

        # Summary + generate
        layout = get_layout(cfg)
        total_items = sum(
            len(pd.read_csv(io.BytesIO(raw), dtype=READ_DTYPES))
            for _, raw in st.session_state.file_bytes
        )
        st.caption(
            f'**{total_items} total items** across **{len(st.session_state.file_bytes)} tab(s)** · '
            f'**{layout["labels_per_row"]} labels per row** · inactive items filtered automatically'
        )

        if st.button('⚙️  Generate Excel', type='primary', use_container_width=True):
            with st.spinner('Generating labels and barcodes…'):
                file_data = [(name, io.BytesIO(raw)) for name, raw in st.session_state.file_bytes]
                wb, summary = generate_workbook(file_data, cfg)
                buf = io.BytesIO(); wb.save(buf); buf.seek(0)
                st.session_state.generated_xlsx = buf.getvalue()

            total = sum(n for _, n, e in summary if e is None)
            st.success(f'Done — {total} labels generated')
            for tab, n, err in summary:
                if err: st.error(f'**{tab}**: {err}')
                else:   st.write(f'- **{tab}** — {n} labels')

        if st.session_state.generated_xlsx:
            st.download_button(
                '⬇️  Download Price_Labels.xlsx',
                data=st.session_state.generated_xlsx,
                file_name='Price_Labels.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
            )
