from __future__ import annotations

import json
from pathlib import Path

import requests
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from src.config import (
    FECHA_CIERRE,
    BASE_ANUAL,
    BONOS_MASTER_PATH,
    BONOS_FLUJOS_PATH,
    PRECIOS_CI_JSON_PATH,
)

from src.engine_bonos import run_engine_bonos
from src.plotting import plot_curve
from src.checklist import run_checklist


def load_macro(macro_path: str) -> dict:
    p = Path(macro_path)
    if not p.exists():
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_dolares_realtime() -> dict:
    """
    DolarAPI: devuelve {"oficial": {"venta": x}, "mep": {"venta": y}, "ccl": {"venta": z}, "ts": "..."}
    """
    def get(url: str) -> dict:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json()

    ofi = get("https://dolarapi.com/v1/dolares/oficial")
    mep = get("https://dolarapi.com/v1/dolares/bolsa")
    ccl = get("https://dolarapi.com/v1/dolares/contadoconliqui")

    def pick(node: dict) -> dict:
        return {
            "compra": float(node["compra"]) if node.get("compra") is not None else None,
            "venta": float(node["venta"]) if node.get("venta") is not None else None,
        }

    return {
        "oficial": pick(ofi),
        "mep": pick(mep),
        "ccl": pick(ccl),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "dolarapi.com",
    }


# =========================
# Config UI
# =========================
st.set_page_config(layout="wide")
st.title("🕷️SPideR – Decidir mejor")

try:
    dolares = fetch_dolares_realtime()
    ofi = dolares["oficial"]
    mep = dolares["mep"]
    ccl = dolares["ccl"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dólar Oficial (venta)", f"{ofi['venta']:.2f}" if ofi["venta"] else "—")
    c2.metric("Dólar MEP (venta)",      f"{mep['venta']:.2f}" if mep["venta"] else "—")
    c3.metric("Dólar CCL (venta)",      f"{ccl['venta']:.2f}" if ccl["venta"] else "—")
    c4.caption(f"Actualizado: {dolares['ts']}")
except Exception:
    st.warning("Error al obtener cotizaciones en tiempo real.")

st.divider()

# =========================
# Sidebar filtros
# =========================
tipo_sel = st.sidebar.radio(
    "Tipo de instrumento:",
    options=["LECAP", "BONCAP", "SOBERANO", "ON"],
    index=2,
)

if tipo_sel in ["LECAP", "BONCAP"]:
    moneda_sel = "ARS"
    st.sidebar.caption("Moneda: ARS")
else:
    moneda_sel = st.sidebar.radio(
        "Moneda de cobro:",
        options=["USD", "ARS"],
        index=0,
    )

plazo_sel = st.sidebar.radio(
    "Plazo:",
    options=["TODOS", "CORTO", "MEDIANO", "LARGO"],
    index=0,
)

# =========================
# Cargar PRECIOS_CI (JSON)
# =========================
PRECIOS_CI_PATH = Path(PRECIOS_CI_JSON_PATH)

try:
    PRECIOS_CI = json.loads(PRECIOS_CI_PATH.read_text(encoding="utf-8"))
    if not isinstance(PRECIOS_CI, dict):
        st.error("precios_ci.json debe contener un objeto JSON (dict).")
        PRECIOS_CI = {}
except FileNotFoundError:
    st.error("No se encontró precios_ci.json")
    PRECIOS_CI = {}
except Exception as e:
    st.error(f"Error leyendo precios_ci.json: {e}")
    PRECIOS_CI = {}

st.sidebar.caption(f"Precios CI cargados desde JSON: {len(PRECIOS_CI)}")

# =========================
# Ejecutar motor BONOS
# =========================
df_view, df_curve, flujos_fut = run_engine_bonos(
    BONOS_MASTER_PATH,
    BONOS_FLUJOS_PATH,
    PRECIOS_CI,
)

# =========================
# Filtrar por moneda / tipo / plazo (TABLA)
# =========================
if df_view is None or df_view.empty:
    df_view = pd.DataFrame()

if "Moneda de Cobro" in df_view.columns:
    df_view = df_view[df_view["Moneda de Cobro"].astype(str).str.upper() == moneda_sel].copy()

if "Tipo" in df_view.columns:
    df_view = df_view[df_view["Tipo"].astype(str).str.upper() == tipo_sel].copy()

if plazo_sel != "TODOS" and "Plazo" in df_view.columns:
    df_view = df_view[df_view["Plazo"].astype(str).str.upper() == plazo_sel].copy()

# =========================
# Filtrar curva (MISMO criterio que la tabla)
# =========================
if df_curve is None:
    df_curve = pd.DataFrame()

if not df_curve.empty:
    if "Moneda de Cobro" in df_curve.columns:
        df_curve = df_curve[df_curve["Moneda de Cobro"].astype(str).str.upper() == moneda_sel].copy()

    if "Tipo" in df_curve.columns:
        df_curve = df_curve[df_curve["Tipo"].astype(str).str.upper() == tipo_sel].copy()

    if plazo_sel != "TODOS" and "Plazo" in df_curve.columns:
        df_curve = df_curve[df_curve["Plazo"].astype(str).str.upper() == plazo_sel].copy()

# =========================
# Tabs principales
# =========================
tab_mercado, tab_sim, tab_bono, tab_datos = st.tabs(
    ["📊 Mercado y Gráfico", "🧮 Simular inversión", "💵 INFORMACIÓN - Bonos y Flujos", "⚙️ Datos de programa"]
)

# ---------------------------------
# TAB 1 — MERCADO: curva + tabla
# ---------------------------------
with tab_mercado:
    st.subheader("Mercado")
    st.caption(
        "Visualizá el rendimiento anual estimado de cada bono según su plazo. "
        "La curva representa el comportamiento promedio del mercado."
    )

    st.markdown("### 📈 Curva de mercado")

    mostrar_labels = st.checkbox(
        "Mostrar nombres de bonos en la curva",
        value=True,
        help="Puede afectar la legibilidad si hay muchos bonos."
    )

    if df_curve is None or df_curve.empty:
        st.info("No hay datos para graficar con los filtros actuales.")
    else:
        x_mode = "years"
        if df_curve is not None and not df_curve.empty and "Dias al VTO" in df_curve.columns:
            max_days = float(pd.to_numeric(df_curve["Dias al VTO"], errors="coerce").dropna().max() or 0)
            max_years = max_days / 365.0
            if max_years <= 2.0:
                x_mode = "months"
        fig = plot_curve(df_curve, annotate=mostrar_labels, x_unit=x_mode)
        st.pyplot(fig, use_container_width=True)

    st.divider()
    st.markdown("### 📋 Bonos disponibles")

    cols_mostrar = [
        "Especie",
        "Moneda de Cobro",
        "Plazo",
        "Valor Actual",
        "Fecha de Vencimiento",
        "Tiempo al Vencimiento",
        "TNA %",
        "Riesgo",
    ]
    cols_mostrar_existentes = [c for c in cols_mostrar if c in df_view.columns]
    df_tab = df_view[cols_mostrar_existentes] if cols_mostrar_existentes else df_view

    rename_map = {
        "Especie": "Bono",
        "Moneda de Cobro": "Moneda de cobro",
        "Valor Actual": "Precio hoy (VN100)",
        "Fecha de Vencimiento": "Vencimiento",
        "Tiempo al Vencimiento": "Tiempo restante",
        "TNA %": "Rendimiento anual estimado",
    }
    df_display = df_tab.rename(columns=rename_map).copy()

    # --- mask de rendimiento negativo (para rojo + icono) ---
    if "Rendimiento anual estimado" in df_display.columns:
        rend_num = (
            df_display["Rendimiento anual estimado"]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        rend_num = pd.to_numeric(rend_num, errors="coerce")
        mask_neg = rend_num.lt(0).fillna(False)
    else:
        mask_neg = pd.Series(False, index=df_display.index)

    # Icono ⚠ junto al bono (solo display)
    if "Bono" in df_display.columns:
        df_display["Bono"] = np.where(
            mask_neg,
            "⚠ " + df_display["Bono"].astype(str),
            df_display["Bono"].astype(str)
        )

    # Formatos
    fmt = {}
    if "Precio hoy (VN100)" in df_display.columns:
        fmt["Precio hoy (VN100)"] = "{:,.2f}"
    if "Rendimiento anual estimado" in df_display.columns:
        fmt["Rendimiento anual estimado"] = "{:.2f}%"

    # Style: fila roja si rendimiento negativo
    def style_neg(row):
        if bool(mask_neg.loc[row.name]):
            return ["background-color: #5a0f0f; color: #ffffff"] * len(row)
        return [""] * len(row)

    # Mostrar sin columnas técnicas (no agregamos ninguna acá)
    styled = df_display.style.format(fmt).apply(style_neg, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=460,
    )

    st.caption("El rendimiento anual estimado supone que mantenés el bono hasta su vencimiento.")

# ---------------------------------
# TAB 2 — SIMULACIÓN: monto -> cuánto cobro
# ---------------------------------
with tab_sim:
    st.subheader("Simulación")
    st.caption("Simulá cuánto podrías cobrar si invertís hoy y mantenés el bono hasta el vencimiento.")

    monto_input = st.text_input(
        "Monto a invertir hoy",
        value="",
        help="Solo números. Se usa el 'Precio hoy (VN100)' como aproximación.",
    )

    monto_inicial: int | None = None
    if monto_input.strip() != "":
        if monto_input.isdigit():
            monto_inicial = int(monto_input)
            if monto_inicial <= 0:
                monto_inicial = None
                st.error("El monto debe ser mayor a 0.")
        else:
            st.error("El monto debe ser un número entero positivo.")

    if monto_inicial is None:
        st.info("Cargá un monto para ver la estimación.")
    else:
        required_cols = ["Especie", "Fecha de Vencimiento", "Valor Actual", "_total_flujo_por_vn100"]
        missing = [c for c in required_cols if c not in df_view.columns]

        if missing:
            st.error(f"Faltan columnas internas para calcular el monto: {missing}")
        else:
            df_monto = df_view[required_cols].copy()
            df_monto["Valor Actual"] = pd.to_numeric(df_monto["Valor Actual"], errors="coerce")
            df_monto["_total_flujo_por_vn100"] = pd.to_numeric(df_monto["_total_flujo_por_vn100"], errors="coerce")
            df_monto = df_monto.dropna(subset=["Valor Actual", "_total_flujo_por_vn100"])
            df_monto = df_monto[df_monto["Valor Actual"] > 0]

            if df_monto.empty:
                st.warning("No hay datos suficientes para estimar (precio o flujos inválidos).")
            else:
                df_monto["VN100_equivalentes"] = monto_inicial / df_monto["Valor Actual"]
                df_monto["Nominales"] = np.floor(df_monto["VN100_equivalentes"] * 100).astype(int)
                df_monto["VN100_equivalentes"] = df_monto["Nominales"] / 100.0
                df_monto["Monto a Cobrar (moneda de cobro)"] = df_monto["VN100_equivalentes"] * df_monto["_total_flujo_por_vn100"]

                out = df_monto[["Especie", "Fecha de Vencimiento", "Nominales", "Monto a Cobrar (moneda de cobro)"]].copy()
                out = out.rename(columns={"Especie": "Bono", "Fecha de Vencimiento": "Vencimiento"})
                out = out.sort_values("Vencimiento")

                # =========================
                # Alertas Simulación: pérdida implícita
                # + icono ⚠ + fila roja
                # =========================
                # Mapear flag desde df_view
                flag_map = {}
                if "_perdida_implicita" in df_view.columns:
                    flag_map = dict(zip(df_view["Especie"], df_view["_perdida_implicita"]))

                out["_perdida_implicita"] = out["Bono"].map(flag_map).fillna(False).astype(bool)

                # Agregar icono ⚠ solo visual
                out["Bono"] = np.where(
                    out["_perdida_implicita"],
                    "⚠ " + out["Bono"].astype(str),
                    out["Bono"].astype(str)
                )

                # Creamos DataFrame SOLO con columnas visibles
                out_visible = out[[
                   "Bono",
                   "Vencimiento",
                   "Nominales",
                   "Monto a Cobrar (moneda de cobro)"
                ]].copy()

                # Función de estilo (usa el flag del DF original)
                def style_sim(row):
                    if bool(out.loc[row.name, "_perdida_implicita"]):
                        return ["background-color: #5a0f0f; color: #ffffff"] * len(row)
                    return [""] * len(row)

                styled_sim = (
                    out_visible.style
                    .format({
                        "Nominales": "{:,.0f}",
                        "Monto a Cobrar (moneda de cobro)": "{:,.2f}",
                    })
                    .apply(style_sim, axis=1)
                )

                st.dataframe(
                    styled_sim,
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

                if out["_perdida_implicita"].any():
                    st.warning("⚠ Hay bonos que devuelven menos de lo que cuestan hoy (pérdida implícita). Miralos con cuidado.")

# ---------------------------------
# TAB 3 — BONO & FLUJOS: detalle + flujos
# ---------------------------------
with tab_bono:
    st.subheader("Bono & Flujos")
    st.caption("Detalle de pagos futuros estimados por cada VN100 del bono seleccionado.")

    if df_view.empty or "Especie" not in df_view.columns:
        st.info("No hay bonos para mostrar detalle con los filtros actuales.")
    else:
        especies = df_view["Especie"].astype(str).str.upper().tolist()
        especie_sel = st.selectbox("Elegí un bono:", options=especies)

        row = df_view[df_view["Especie"].astype(str).str.upper() == str(especie_sel).upper()]
        row = row.iloc[0] if not row.empty else None

        if row is not None:
            perdida = bool(row.get("_perdida_implicita", False))
            if perdida:
                st.error("⚠ Pérdida implícita: el total a cobrar (VN100) es menor que el precio hoy (VN100).")

        def _get(field: str) -> str:
            if row is None:
                return "—"
            val = row.get(field, None)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return "—"
            s = str(val).strip()
            return s if s else "—"

        st.markdown("### 🧾 Ficha del bono")

        a, b, c, d = st.columns(4)
        a.metric("Emisor", _get("emisor"))
        b.metric("Sector", _get("sector"))
        c.metric("Legislación", _get("legislacion"))
        d.metric("Rating", _get("rating"))

        e, f, g, h = st.columns(4)
        e.metric("Tipo de tasa", _get("tipo_tasa"))
        f.metric("Moneda de cobro", _get("Moneda de Cobro"))
        g.metric("Vencimiento", _get("Fecha de Vencimiento"))
        h.metric("Frecuencia", _get("frecuencia"))

        i, j, k, l = st.columns(4)
        cupon_raw = row.get("cupon_anual", None) if row is not None else None
        try:
            cupon_pct = float(str(cupon_raw).replace(",", ".")) * 100.0
            cupon_txt = f"{cupon_pct:.2f}%"
        except Exception:
            cupon_txt = "—"
        i.metric("Cupón anual", cupon_txt)

        nota = _get("nota")
        if nota != "—":
            st.caption(nota)

        st.divider()

        det = flujos_fut[flujos_fut["codigo"].astype(str).str.upper() == especie_sel].copy()
        det = det.sort_values("fecha_pago")

        if det.empty:
            st.info("Este bono no tiene flujos futuros desde la fecha de cierre.")
        else:
            det_view = det[[
                "fecha_pago",
                "interes_por_vn100",
                "amortizacion_por_vn100",
                "flujo_total_por_vn100",
                "moneda_flujo",
            ]].copy()

            det_view["fecha_pago"] = pd.to_datetime(det_view["fecha_pago"], errors="coerce").dt.date

            moneda = str(det_view["moneda_flujo"].iloc[0])
            total_vn100 = float(pd.to_numeric(det["flujo_total_por_vn100"], errors="coerce").fillna(0).sum())

            c1, c2 = st.columns(2)
            c1.metric("Moneda de cobro", moneda)
            c2.metric("Total estimado a cobrar (VN100)", f"{total_vn100:,.4f}")

            st.dataframe(
                det_view.rename(columns={
                    "fecha_pago": "Fecha",
                    "interes_por_vn100": "Interés (VN100)",
                    "amortizacion_por_vn100": "Amortización (VN100)",
                    "flujo_total_por_vn100": "Total (VN100)",
                    "moneda_flujo": "Moneda",
                }).style.format({
                    "Interés (VN100)": "{:,.4f}",
                    "Amortización (VN100)": "{:,.4f}",
                    "Total (VN100)": "{:,.4f}",
                }),
                use_container_width=True,
                hide_index=True,
                height=420,
            )

            st.caption("Tip: la simulación por monto se hace en la pestaña 🧮 Simulación.")

# ---------------------------------
# TAB 4 — DATOS: checklist / integridad
# ---------------------------------
with tab_datos:
    st.subheader("Datos & Calidad")

    errs, warns, summary, _artifacts = run_checklist(
        BONOS_MASTER_PATH,
        BONOS_FLUJOS_PATH,
        PRECIOS_CI,
        FECHA_CIERRE,
    )

    if summary is not None:
        st.caption(
            f"Master: {summary.codigos_master} | "
            f"Precios válidos: {summary.precios_validos} | "
            f"Códigos con flujos futuros: {summary.codigos_con_flujos_futuros} | "
            f"Usables por motor: {summary.codigos_usables_motor} | "
            f"Equivalencias: {summary.equivalencias_items}"
        )

    if errs:
        st.error("Errores críticos:")
        for e in errs:
            st.write(f"- {e}")
    else:
        st.success("Sin errores críticos.")

    if warns:
        st.warning("Warnings:")
        for w in warns:
            st.write(f"- {w}")
    else:
        st.info("Sin warnings relevantes.")
        st.info("Sin warnings relevantes.")