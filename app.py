
import io, re, os
from pathlib import Path
import pandas as pd
import streamlit as st
import qrcode

st.set_page_config(page_title="Uzun Kod v7", page_icon="🧩", layout="wide")
st.title("🧩 Uzun Kod Oluşturma Programı — v7 / Statik")
st.caption("Format: 'MakineTipi' + seçilen 'ValueCode’lar' + sayısal alanlar (gerekirse önekle). Örn: **CMC SIE AT 2500 D1300**")

@st.cache_data
def read_schema(file)->dict:
    xls = pd.ExcelFile(file)
    return {
        "products": pd.read_excel(xls, "products"),
        "sections": pd.read_excel(xls, "sections"),
        "fields":   pd.read_excel(xls, "fields"),
        "options":  pd.read_excel(xls, "options"),
    }

DEFAULT_SCHEMA_PATH = "data/schema.xlsx"
schema = read_schema(DEFAULT_SCHEMA_PATH)

# ---- STATE ----
if "step" not in st.session_state: st.session_state["step"] = 1
if "s1" not in st.session_state: st.session_state["s1"] = None
if "s2" not in st.session_state: st.session_state["s2"] = None
if "product_row" not in st.session_state: st.session_state["product_row"] = None
if "form_values" not in st.session_state: st.session_state["form_values"] = {}

S1_ORDER = ["Rulo Besleme","Plaka Besleme","Tamamlayıcı Ürünler"]

def big_buttons(options, cols=3, key_prefix="bb"):
    cols_list = st.columns(cols)
    clicked = None
    for i, opt in enumerate(options):
        with cols_list[i % cols]:
            if st.button(opt, key=f"{key_prefix}_{opt}", use_container_width=True):
                clicked = opt
    return clicked

def sanitize(s:str)->str:
    return re.sub(r"[^A-Z0-9._-]", "", str(s).upper())

def pad_number(n, pad):
    if pd.isna(pad) or pad is None or pad == "":
        return str(int(n) if float(n).is_integer() else n)
    if isinstance(pad, (int, float)) or (isinstance(pad, str) and pad.isdigit()):
        return f"{int(n):0{int(pad)}d}"
    if isinstance(pad, str) and "." in pad:
        w, d = pad.split(".")
        s = f"{float(n):0{int(w)}.{int(d)}f}"
        return s.replace(".","")
    return str(n)

def build_linear_code(machine_type: str, values: dict, schema: dict, s1: str, s2: str) -> str:
    parts = []
    m = sanitize(machine_type) if machine_type else ""
    if m: parts.append(m)
    secs = schema["sections"].query("Kategori1 == @s1 and Kategori2 == @s2 and MakineTipi == @machine_type").sort_values("Order")
    fdf = schema["fields"]
    for _, sec in secs.iterrows():
        fields = fdf.query("SectionKey == @sec.SectionKey")
        for _, fld in fields.iterrows():
            k = fld["FieldKey"]
            typ = str(fld["Type"]).lower()
            val = values.get(k)
            if val in (None, "", [], 0):
                continue
            if typ == "select":
                parts.append(sanitize(val))  # ValueCode
            elif typ == "multiselect" and isinstance(val, list):
                parts.extend([sanitize(v) for v in val])
            elif typ == "number":
                num = pad_number(val, fld.get("Pad"))
                prefix = fld.get("EncodeKey")
                if isinstance(prefix, str) and prefix.strip() != "":
                    parts.append(f"{sanitize(prefix)}{num}")
                else:
                    parts.append(str(num))
            else:
                parts.append(sanitize(val))
    return " ".join([p for p in parts if p])

with st.sidebar:
    st.subheader("Şema")
    st.download_button("schema.xlsx indir", data=open(DEFAULT_SCHEMA_PATH, "rb").read(), file_name="schema.xlsx")

# Step 1
if st.session_state["step"] == 1:
    st.header("Aşama 1 — Ana Seçim")
    s1_candidates = [x for x in S1_ORDER if x in schema["products"]["Kategori1"].unique().tolist()]
    clicked = big_buttons(s1_candidates, cols=3, key_prefix="s1")
    if clicked:
        st.session_state["s1"] = clicked
        st.session_state["step"] = 2
        st.rerun()

# Step 2
elif st.session_state["step"] == 2:
    st.header("Aşama 2 — Alt Seçim")
    st.write(f"Ana grup: **{st.session_state['s1']}**")
    sub = schema["products"].query("Kategori1 == @st.session_state['s1']")["Kategori2"].dropna().unique().tolist()
    clicked = big_buttons(sub, cols=3, key_prefix="s2")
    col_back, _ = st.columns([1,1])
    with col_back:
        if st.button("⬅️ Geri (Aşama 1)"):
            st.session_state["step"] = 1
            st.rerun()
    if clicked:
        st.session_state["s2"] = clicked
        st.session_state["step"] = 3
        st.rerun()

# Step 3
else:
    st.header("Aşama 3 — Ürün ve Detay")
    s1, s2 = st.session_state["s1"], st.session_state["s2"]
    st.write(f"Seçimler: **{s1} → {s2}**")
    prods = schema["products"].query("Kategori1 == @s1 and Kategori2 == @s2")
    if prods.empty:
        st.warning("Bu seçim için 'products' sayfasında satır yok.")
    else:
        display = prods["UrunAdi"] + " (" + prods["UrunKodu"] + ") — " + prods["MakineTipi"]
        choice = st.selectbox("Ürün", options=display.tolist())
        if choice:
            idx = display.tolist().index(choice)
            row = prods.iloc[idx]
            st.session_state["product_row"] = row

    row = st.session_state["product_row"]
    if row is not None:
        mk = row["MakineTipi"]
        st.info(f"Seçilen makine: **{mk}** — Kod: **{row['UrunKodu']}**")
        secs = schema["sections"].query("Kategori1 == @s1 and Kategori2 == @s2 and MakineTipi == @mk").sort_values("Order")
        if secs.empty:
            st.warning("Bu makine için 'sections' sayfasında kayıt yok.")
        else:
            tabs = st.tabs(secs["SectionLabel"].tolist())
            fdf = schema["fields"]
            optdf = schema["options"]
            for i, (_, sec) in enumerate(secs.iterrows()):
                with tabs[i]:
                    fields = fdf.query("SectionKey == @sec.SectionKey")
                    if fields.empty:
                        st.write("Alan yok.")
                        continue
                    for _, fld in fields.iterrows():
                        k = fld["FieldKey"]; label = fld["FieldLabel"]; typ = str(fld["Type"]).lower(); req = bool(fld["Required"]); default = fld.get("Default")
                        if typ in ("select", "multiselect"):
                            opts = optdf.query("OptionsKey == @fld.OptionsKey").sort_values("Order")
                            opts_codes = opts["ValueCode"].astype(str).tolist()
                            opts_labels = (opts["ValueCode"].astype(str) + " — " + opts["ValueLabel"].astype(str)).tolist()
                            if typ == "select":
                                idx = 0
                                if default in opts_codes: idx = opts_codes.index(default)
                                sel = st.selectbox(label + (" *" if req else ""), options=opts_codes, format_func=lambda c: opts_labels[opts_codes.index(c)], index=idx, key=f"k_{k}")
                                st.session_state["form_values"][k] = sel
                            else:
                                default_vals = [default] if isinstance(default, str) and default in opts_codes else []
                                ms = st.multiselect(label + (" *" if req else ""), options=opts_codes, default=default_vals, format_func=lambda c: opts_labels[opts_codes.index(c)], key=f"k_{k}")
                                st.session_state["form_values"][k] = ms
                        elif typ == "number":
                            minv = fld.get("Min"); maxv = fld.get("Max"); step = fld.get("Step")
                            minv = float(minv) if pd.notna(minv) else 0.0
                            maxv = float(maxv) if pd.notna(maxv) else 1e9
                            step = float(step) if pd.notna(step) else 1.0
                            defv = float(default) if pd.notna(default) else minv
                            val = st.number_input(label + (" *" if req else ""), min_value=minv, max_value=maxv, value=defv, step=step, key=f"k_{k}")
                            st.session_state["form_values"][k] = val
                        else:
                            txt = st.text_input(label + (" *" if req else ""), value=str(default) if pd.notna(default) else "", key=f"k_{k}")
                            st.session_state["form_values"][k] = txt

            st.markdown("---")
            c1, c2 = st.columns([1,1])
            with c1:
                if st.button("🔐 Uzun Kodu Oluştur (Linear)"):
                    code = build_linear_code(mk, st.session_state["form_values"], schema, s1, s2)
                    st.session_state["long_code"] = code
            with c2:
                if "long_code" in st.session_state and st.session_state["long_code"]:
                    code = st.session_state["long_code"]
                    st.success("Uzun kod üretildi")
                    st.code(code, language="text")
                    img = qrcode.make(code)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    st.image(buf.getvalue(), caption="QR")
                    st.download_button("Kodu TXT indir", data=code.encode("utf-8"), file_name="uzun_kod.txt")
