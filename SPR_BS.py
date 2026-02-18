from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.config import (
    FECHA_CIERRE,
    BASE_ANUAL,
    BONOS_MASTER_PATH,
    BONOS_FLUJOS_PATH,
    USE_SYSTEM_DATE,
    PRECIOS_CI_JSON_PATH,
    MACRO_JSON_PATH,
    DOLAR_OFICIAL,
    DOLAR_MEP,
    DOLAR_CCL
)

from src.engine_bonos import run_engine_bonos
from src.plotting import plot_curve
from src.checklist import run_checklist

@st.cache_data(ttl=60)
def load_macro(macro_path: str) -> dict:
    p = Path(macro_path)
    if not p.exists():
        return {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

# =========================
# Config UI
# =========================
st.set_page_config(layout="wide")
st.title("SPR – Sistema de Precios Real")

modo = "Fecha real" if USE_SYSTEM_DATE else "Simulación"
st.caption(
    f"📅 Fecha de referencia: {FECHA_CIERRE} | "
    f"Modo: {modo} | "
    f"Base anual: {BASE_ANUAL}"
)

c1, c2, c3 = st.columns(3)
macro = load_macro(MACRO_JSON_PATH)

oficial = float(macro.get("dolar_oficial", DOLAR_OFICIAL) or DOLAR_OFICIAL)
mep = float(macro.get("dolar_mep", DOLAR_MEP) or DOLAR_MEP)
ccl = float(macro.get("dolar_ccl", DOLAR_CCL) or DOLAR_CCL)

as_of = str(macro.get("as_of", "")).strip()
source = str(macro.get("source", "")).strip()

c1, c2, c3 = st.columns(3)
c1.metric("💵 Dólar oficial", f"{oficial:,.2f}")
c2.metric("💵 Dólar MEP", f"{mep:,.2f}")
c3.metric("💵 Dólar CCL", f"{ccl:,.2f}")

if as_of or source:
    st.caption(" | ".join([s for s in [f"Actualizado: {as_of}" if as_of else "", f"Fuente: {source}" if source else ""] if s]))

st.divider()

# =========================
# Sidebar filtros
# =========================
# --- Tipo de instrumento ---
tipo_sel = st.sidebar.radio(
    "Tipo de instrumento:",
    options=["LECAP", "BONCAP", "SOBERANO", "ON"],
    index=2,  # por ejemplo arrancar en SOBERANO
)

# --- Moneda (condicional) ---
if tipo_sel in ["LECAP", "BONCAP"]:
    moneda_sel = "ARS"          # forzado
    st.sidebar.caption("Moneda: ARS (fija para LECAP/BONCAP)")
else:
    moneda_sel = st.sidebar.radio(
        "Mostrar bonos en:",
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
    # Moneda
    if "Moneda de Cobro" in df_curve.columns:
        df_curve = df_curve[df_curve["Moneda de Cobro"].astype(str).str.upper() == moneda_sel].copy()

    # Tipo
    if "Tipo" in df_curve.columns:
        df_curve = df_curve[df_curve["Tipo"].astype(str).str.upper() == tipo_sel].copy()

    # Plazo
    if plazo_sel != "TODOS" and "Plazo" in df_curve.columns:
        df_curve = df_curve[df_curve["Plazo"].astype(str).str.upper() == plazo_sel].copy()

    # Importante: si por filtros no queda nada, NO mostramos el universo (evita puntos raros)

# =========================
# Tabs principales (Producto comercial)
# =========================
tab_mercado, tab_sim, tab_bono, tab_datos = st.tabs(
    ["📊 Mercado", "🧮 Simulación", "💵 Bono & Flujos", "⚙️ Datos"]
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

    # Curva arriba (visual principal)
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
        fig = plot_curve(df_curve, annotate=mostrar_labels, x_unit=x_mode)  # x_mode = "months" o "years"
        st.pyplot(fig, use_container_width=True)

    st.divider()

    st.markdown("### 📋 Bonos disponibles")

    # Tabla (soporte)
    cols_mostrar = [
        "Especie",
        "Moneda de Cobro",
        "Plazo",
        "Valor Actual",
        "Fecha de Vencimiento",
        "Tiempo al Vencimiento",
        "TNA %",
    ]
    cols_mostrar_existentes = [c for c in cols_mostrar if c in df_view.columns]
    df_tab = df_view[cols_mostrar_existentes] if cols_mostrar_existentes else df_view

    # Renombres comerciales (solo display)
    rename_map = {
        "Especie": "Bono",
        "Moneda de Cobro": "Moneda de cobro",
        "Valor Actual": "Precio hoy (VN100)",
        "Fecha de Vencimiento": "Vencimiento",
        "Tiempo al Vencimiento": "Tiempo restante",
        "TNA %": "Rendimiento anual estimado",
    }
    df_display = df_tab.rename(columns=rename_map).copy()

    # Formatos
    fmt = {}
    if "Precio hoy (VN100)" in df_display.columns:
        fmt["Precio hoy (VN100)"] = "{:,.2f}"
    if "Rendimiento anual estimado" in df_display.columns:
        fmt["Rendimiento anual estimado"] = "{:.2f}%"

    st.dataframe(
        df_display.style.format(fmt),
        use_container_width=True,
        hide_index=True,
        height=460,
    )

    st.caption(
    "El rendimiento anual estimado supone que mantenés el bono hasta su vencimiento."
    )

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

                st.dataframe(
                    out.style.format({
                        "Nominales": "{:,.0f}",
                        "Monto a Cobrar (moneda de cobro)": "{:,.2f}",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

# ---------------------------------
# TAB 3 — BONO & FLUJOS: detalle + flujos (y opcional estimación por monto)
# ---------------------------------
with tab_bono:
    st.subheader("Bono & Flujos")
    st.caption(
    "Detalle de pagos futuros estimados por cada VN100 del bono seleccionado."
    )

    if df_view.empty or "Especie" not in df_view.columns:
        st.info("No hay bonos para mostrar detalle con los filtros actuales.")
    else:
        especies = df_view["Especie"].astype(str).str.upper().tolist()
        especie_sel = st.selectbox("Elegí un bono:", options=especies)

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