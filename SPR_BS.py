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
)
from src.engine_bonos import run_engine_bonos
from src.plotting import plot_curve
from src.checklist import run_checklist

# =========================
# Config UI
# =========================
st.set_page_config(layout="wide")
st.title("SPR – Bonos Soberanos")

modo = "Fecha real" if USE_SYSTEM_DATE else "Simulación"
st.caption(f"{modo}: {FECHA_CIERRE} | Base anual: {BASE_ANUAL} (fija)")

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

with st.expander("✅ Checklist de Integridad (datos)", expanded=False):
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

# =========================
# Input monto (opcional)
# =========================
monto_input = st.sidebar.text_input(
    "Monto inicial a invertir",
    value="",
    help="Monto a invertir hoy al Valor Actual del bono (aprox). Solo números.",
)

monto_inicial: int | None = None
if monto_input.strip() != "":
    if monto_input.isdigit():
        monto_inicial = int(monto_input)
        if monto_inicial <= 0:
            monto_inicial = None
            st.sidebar.error("El monto debe ser mayor a 0")
    else:
        st.sidebar.error("El monto debe ser un número entero positivo")

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

# Copia para filtrar curva sin depender de cálculos de monto
df_view_for_curve = df_view.copy()

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
# Tabs (orden visual)
# =========================
tab_resumen, tab_flujo = st.tabs(["📋 Resumen", "💵 Flujo del bono"])

with tab_resumen:
    # Tabla principal
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

    # Tabla (formato)
    df_tab = df_view[cols_mostrar_existentes] if cols_mostrar_existentes else df_view

    fmt = {}
    if "Valor Actual" in df_tab.columns:
        fmt["Valor Actual"] = "{:,.2f}"
    if "TNA %" in df_tab.columns:
        fmt["TNA %"] = "{:.2f}%"

    st.dataframe(
        df_tab.style.format(fmt),
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    # Monto total estimado (opcional) -> expander para no ensuciar
    if monto_inicial is not None and monto_inicial > 0:
        with st.expander("Ver monto total estimado a cobrar por bono"):
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
                    st.warning("No hay datos suficientes para estimar el monto a cobrar (precio o flujos inválidos).")
                else:
                    df_monto["VN100_equivalentes"] = monto_inicial / df_monto["Valor Actual"]
                    df_monto["Nominales"] = np.floor(df_monto["VN100_equivalentes"] * 100).astype(int)
                    df_monto["VN100_equivalentes"] = df_monto["Nominales"] / 100.0
                    df_monto["Monto a Cobrar (moneda flujo)"] = df_monto["VN100_equivalentes"] * df_monto["_total_flujo_por_vn100"]

                    df_monto = df_monto[["Especie", "Fecha de Vencimiento", "Nominales", "Monto a Cobrar (moneda flujo)"]].sort_values(
                        "Fecha de Vencimiento"
                    )

                    st.dataframe(
                        df_monto.style.format({
                            "Nominales": "{:,.0f}",
                            "Monto a Cobrar (moneda flujo)": "{:,.2f}",
                        }),
                        use_container_width=True,
                        hide_index=True,
                        height=280,
                    )

    st.divider()

    if not df_curve.empty and "Dias al VTO" in df_curve.columns and "TNA %" in df_curve.columns:
        fig = plot_curve(
            df_curve,
            x_col="Dias al VTO",
            y_col="TNA %",
            title=f"Curva de Bonos ({moneda_sel}) – TNA % vs Años",
            x_unit="years",
            annotate=True,
            max_labels=40,
        )
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("Curva no disponible: faltan datos o columnas para graficar (se completa al cargar más bonos).")

with tab_flujo:
    st.subheader("Flujo de pagos del bono")

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
            c1.metric("Moneda", moneda)
            c2.metric("Total futuro por VN100", f"{total_vn100:,.4f}")

            st.dataframe(
                det_view.style.format({
                    "interes_por_vn100": "{:,.4f}",
                    "amortizacion_por_vn100": "{:,.4f}",
                    "flujo_total_por_vn100": "{:,.4f}",
                }),
                use_container_width=True,
                hide_index=True,
                height=420,
            )

            # Flujo estimado para monto -> expander
            if monto_inicial is not None and monto_inicial > 0:
                with st.expander("Ver flujo estimado para mi monto"):
                    fila = df_view[df_view["Especie"].astype(str).str.upper() == especie_sel].copy()
                    if not fila.empty and "Valor Actual" in fila.columns:
                        precio = pd.to_numeric(fila["Valor Actual"].iloc[0], errors="coerce")
                        if pd.notna(precio) and float(precio) > 0:
                            vn100_equiv = monto_inicial / float(precio)
                            nominales = int(np.floor(vn100_equiv * 100))  # VN enteros
                            vn100_equiv = nominales / 100.0

                            det_est = det.copy()
                            det_est["Interés (monto)"] = vn100_equiv * pd.to_numeric(det_est["interes_por_vn100"], errors="coerce").fillna(0)
                            det_est["Amortización (monto)"] = vn100_equiv * pd.to_numeric(det_est["amortizacion_por_vn100"], errors="coerce").fillna(0)
                            det_est["Total (monto)"] = vn100_equiv * pd.to_numeric(det_est["flujo_total_por_vn100"], errors="coerce").fillna(0)
                            det_est["fecha_pago"] = pd.to_datetime(det_est["fecha_pago"], errors="coerce").dt.date

                            st.caption(f"Nominales estimados: {nominales:,} | Moneda: {moneda}")

                            st.dataframe(
                                det_est[["fecha_pago", "Interés (monto)", "Amortización (monto)", "Total (monto)"]]
                                .style.format({
                                    "Interés (monto)": "{:,.2f}",
                                    "Amortización (monto)": "{:,.2f}",
                                    "Total (monto)": "{:,.2f}",
                                }),
                                use_container_width=True,
                                hide_index=True,
                                height=420,
                            )