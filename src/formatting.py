from __future__ import annotations

import pandas as pd

# =========================
# Column mapping (interno -> UI)
# =========================
BONOS_COLUMN_MAP = {
    "codigo": "Especie",
    "tipo_instrumento": "Tipo",
    "moneda": "Moneda de Cobro",
    "precio_ci": "Valor Actual",
    "fecha_final": "Fecha de Vencimiento",
    "Dias_al_vto": "_Dias_al_vto",              # interno (no mostrar)
    "Tiempo_al_vto": "Tiempo al Vencimiento",
    "plazo": "Plazo",
    "TNA_%": "TNA %",
    "total_flujo_por_vn100": "_total_flujo_por_vn100",  # interno para cálculos de monto
    "_risk_score": "_risk_score",   # interno
    "Riesgo": "Riesgo",             # display
    "Dur_Mod": "_Dur_Mod",          # interno (opcional)
    "_perdida_implicita": "_perdida_implicita",  # interno
    "Alerta": "Alerta",                          # display
}

BONOS_ORDER_COLS = [
    "codigo",
    "tipo_instrumento",
    "moneda",
    "precio_ci",
    "fecha_final",
    "Dias_al_vto",
    "Tiempo_al_vto",
    "plazo",
    "TNA_%",
    "total_flujo_por_vn100",
    "_risk_score",
    "Riesgo",
    "Dur_Mod",
    "_perdida_implicita",
    "Alerta",
]


def _fmt_tiempo_desde_dias(dias: float | int | None) -> str:
    if dias is None or pd.isna(dias):
        return ""
    try:
        dias_f = float(dias)
    except Exception:
        return ""
    if dias_f < 0:
        return ""

    meses_total = int(round(dias_f / 30.4375))  # 365.25/12
    anios = meses_total // 12
    meses = meses_total % 12

    if anios <= 0:
        return f"{meses} Meses" if meses != 1 else "1 Mes"
    if meses == 0:
        return f"{anios} Años" if anios != 1 else "1 Año"

    a_txt = "Año" if anios == 1 else "Años"
    m_txt = "Mes" if meses == 1 else "Meses"
    return f"{anios} {a_txt} y {meses} {m_txt}"


def _plazo_desde_dias(dias: float | int | None) -> str:
    if dias is None or pd.isna(dias):
        return ""
    try:
        anios = float(dias) / 365.0
    except Exception:
        return ""
    if anios <= 2:
        return "CORTO"
    if anios <= 7:
        return "MEDIANO"
    return "LARGO"


def build_view_df_bonos(out: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Toma el output del engine (interno) y construye:
    - df_view: tabla para UI (con columnas renombradas y algunas internas)
    - df_curve: tabla para curva (Especie, Dias al VTO, TNA %)
    """
    df = out.copy()

    # Normalizar tipos
    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    df["moneda"] = df["moneda"].astype(str).str.strip().str.upper()
    df["tipo_instrumento"] = df["tipo_instrumento"].astype(str).str.strip().str.upper()

    df["fecha_final"] = pd.to_datetime(df["fecha_final"], errors="coerce")

    for c in ["precio_ci", "total_flujo_por_vn100", "Dias_al_vto", "TNA_%"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # -----------------------------
    # ALERTA: Pérdida implícita
    # -----------------------------
    # Regla: si el total a cobrar (VN100) es menor que el precio hoy (VN100)
    ok = (
        df["precio_ci"].notna()
        & df["total_flujo_por_vn100"].notna()
        & (df["precio_ci"] > 0)
    )

    df["_perdida_implicita"] = False
    df.loc[ok, "_perdida_implicita"] = df.loc[ok, "total_flujo_por_vn100"] < df.loc[ok, "precio_ci"]

    df["Alerta"] = ""
    df.loc[df["_perdida_implicita"], "Alerta"] = "⚠ Pérdida implícita"

    for c in ["Dur_Mac", "Dur_Mod", "_risk_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    def _bucket_riesgo(score: float | None) -> str:
        if score is None or pd.isna(score):
            return ""
        s = float(score)
        if s < 0.45:
            return "BAJO"
        if s < 0.70:
            return "MEDIO"
        return "ALTO"

    df["Riesgo"] = df["_risk_score"].apply(_bucket_riesgo)
    # Ajuste UX: si hay pérdida implícita, el "riesgo de decisión" no puede ser BAJO
    df.loc[df["_perdida_implicita"] & (df["Riesgo"] == "BAJO"), "Riesgo"] = "MEDIO"

    # Tiempo al vencimiento + plazo
    df["Tiempo_al_vto"] = df["Dias_al_vto"].apply(_fmt_tiempo_desde_dias)
    df["plazo"] = df["Dias_al_vto"].apply(_plazo_desde_dias)

    # Orden columnas internas
    cols = [c for c in BONOS_ORDER_COLS if c in df.columns]
    df = df[cols].copy()

    # Renombrar (UI)
    df_view = df.rename(columns=BONOS_COLUMN_MAP)

    # Fecha de vencimiento solo fecha (sin hora) para UI
    if "Fecha de Vencimiento" in df_view.columns:
        df_view["Fecha de Vencimiento"] = pd.to_datetime(df_view["Fecha de Vencimiento"], errors="coerce").dt.date

    # Curva: años vs tna, pero dejamos días para que plot_curve convierta
    df_curve = pd.DataFrame({
        "Especie": df_view["Especie"],
        "Dias al VTO": df_view["_Dias_al_vto"],
        "TNA %": df_view["TNA %"],
    })

    # También preservamos "Tipo" y "Moneda de Cobro" en df_curve si existen (por si querés filtrar)
    if "Tipo" in df_view.columns:
        df_curve["Tipo"] = df_view["Tipo"]
    if "Moneda de Cobro" in df_view.columns:
        df_curve["Moneda de Cobro"] = df_view["Moneda de Cobro"]
    if "Plazo" in df_view.columns:
        df_curve["Plazo"] = df_view["Plazo"]

    return df_view, df_curve