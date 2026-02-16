import json
import pandas as pd
import streamlit as st
import numpy as np

from pathlib import Path
from src.config import FECHA_CIERRE, BASE_ANUAL, BONOS_MASTER_PATH, BONOS_FLUJOS_PATH, USE_SYSTEM_DATE, PRECIOS_CI_JSON_PATH
from src.engine_bonos import run_engine_bonos
from src.plotting import plot_curve

# =========================
# Config UI
# =========================
st.set_page_config(layout="wide")
st.title("SPR – Bonos Soberanos")
modo = "Fecha real" if USE_SYSTEM_DATE else "Simulación"
st.caption(f"{modo}: {FECHA_CIERRE} | Base anual: {BASE_ANUAL} (fija)")

tipo_sel = st.sidebar.radio(
    "Tipo de instrumento:",
    options=["SOBERANO", "ON"],
    index=0,
)

# =========================
# Selector moneda (USD / ARS)
# Moneda = moneda de cobro (moneda_flujo)
# =========================
moneda_sel = st.sidebar.radio(
    "Mostrar bonos en:",
    options=["USD", "ARS"],
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
    st.error("No se encontró data/precios_ci.json")
    PRECIOS_CI = {}
except Exception as e:
    st.error(f"Error leyendo data/precios_ci.json: {e}")
    PRECIOS_CI = {}

st.sidebar.caption(f"Precios CI cargados desde JSON: {len(PRECIOS_CI)}")


# =========================
# Input monto (opcional)
# =========================
monto_input = st.sidebar.text_input(
    "Monto inicial a invertir",
    value="",
    help="Monto a invertir hoy al Valor Actual del bono (aprox). Solo números."
)

monto_inicial = None
if monto_input.strip() != "":
    if monto_input.isdigit():
        monto_inicial = int(monto_input)
    else:
        st.sidebar.error("El monto debe ser un número entero positivo")


# =========================
# Ejecutar motor BONOS (PRE-DÓLAR)
# =========================
df_view, df_curve = run_engine_bonos(
    BONOS_MASTER_PATH,
    BONOS_FLUJOS_PATH,
    PRECIOS_CI
)

# =========================
# Filtrar por moneda de cobro (tabla + curva)
# =========================
# Nota: en formatting.py la columna se llama "Moneda de Cobro"
if "Moneda de Cobro" in df_view.columns:
    df_view = df_view[df_view["Moneda de Cobro"].astype(str).str.upper() == moneda_sel].copy()
if "Tipo" in df_view.columns:
    df_view = df_view[df_view["Tipo"].astype(str).str.upper() == tipo_sel].copy()

# df_curve no trae moneda, filtramos por especies presentes en la tabla
if df_curve is not None and not df_curve.empty and "Especie" in df_view.columns:
    especies_ok = set(df_view["Especie"].astype(str).str.upper())
    if "Especie" in df_curve.columns:
        df_curve = df_curve[df_curve["Especie"].astype(str).str.upper().isin(especies_ok)].copy()


# =========================
# Tabla principal (limpia)
# =========================
# Si no existe "Años al VTO" (normal), lo calculamos acá a partir de "Dias al VTO"
if "Dias al VTO" in df_view.columns and "Años al VTO" not in df_view.columns:
    dias = pd.to_numeric(df_view["Dias al VTO"], errors="coerce")
    df_view["Años al VTO"] = (dias / 365.0).round(2)

cols_mostrar = [
    "Especie",
    "Moneda de Cobro",
    "Valor Actual",
    "Fecha de Vencimiento",
    "Años al VTO",
    "TNA %",
]

cols_mostrar_existentes = [c for c in cols_mostrar if c in df_view.columns]
st.dataframe(df_view[cols_mostrar_existentes], use_container_width=True)


# =========================
# Monto total estimado a cobrar (si hay input)
# =========================
if monto_inicial is not None and monto_inicial > 0:
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
            # Aproximación: monto invertido / precio -> VN100 equivalentes (precio está por VN=100)
            df_monto["VN100_equivalentes"] = monto_inicial / df_monto["Valor Actual"]

            # NOMINALES (VN) comprados (entero, sin fracciones)
            df_monto["Nominales"] = np.floor(df_monto["VN100_equivalentes"] * 100).astype(int)

            # Recalcular VN100 equivalentes desde nominales (consistente con el floor)
            df_monto["VN100_equivalentes"] = df_monto["Nominales"] / 100.0

            df_monto["Monto a Cobrar (moneda flujo)"] = df_monto["VN100_equivalentes"] * df_monto["_total_flujo_por_vn100"]

            df_monto = df_monto[["Especie", "Fecha de Vencimiento", "Nominales", "Monto a Cobrar (moneda flujo)"]].sort_values(
                "Fecha de Vencimiento"
            )

            st.subheader("Monto total estimado a cobrar por bono")
            st.dataframe(
                df_monto.style.format({
                    "Nominales": "{:,.0f}",
                    "Monto a Cobrar (moneda flujo)": "{:,.2f}"
                }),
                use_container_width=False,
                height=260,
            )


# =========================
# Gráfico (TNA % vs Años)
# =========================
if df_curve is not None and not df_curve.empty and "Dias al VTO" in df_curve.columns and "TNA %" in df_curve.columns:
    fig = plot_curve(
        df_curve,
        x_col="Dias al VTO",
        y_col="TNA %",
        title=f"Curva de Bonos ({moneda_sel}) – TNA % vs Años",
        x_unit="years"
    )
    st.pyplot(fig, use_container_width=True)
else:
    st.info("Curva no disponible: faltan datos o columnas para graficar (se completa al cargar más bonos).")