import pandas as pd

# =========================================================
# FORMATTING – BONOS SOBERANOS (SPR_BS)
# =========================================================

BONOS_COLUMN_MAP = {
    "codigo": "Especie",
    "tipo_instrumento": "Tipo",
    "moneda": "Moneda de Cobro",
    "precio_ci": "Valor Actual",
    "fecha_final": "Fecha de Vencimiento",
    "Tiempo_al_vto" : "Tiempo al Vencimiento",
    "TNA_%": "TNA %",
    "plazo": "Plazo",
    # columna interna (NO mostrar en tabla principal)
    "total_flujo_por_vn100": "_total_flujo_por_vn100",
}

BONOS_ORDER_COLS = [
    "codigo",
    "tipo_instrumento",
    "moneda",
    "precio_ci",
    "fecha_final",
    "Dias_al_vto",
    "Tiempo_al_vto",
    "TNA_%",
    "plazo",
    "total_flujo_por_vn100",
]


def build_view_df_bonos(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve:
    - df_view: DataFrame listo para UI (columnas claras, sin ruido)
    - df_curve: DataFrame mínimo para gráfico (Dias vs TNA)
    """

    # -----------------------------------------------------
    # Base
    # -----------------------------------------------------
    cols = [c for c in BONOS_ORDER_COLS if c in df_raw.columns]
    df = df_raw[cols].copy()

    # -----------------------------------------------------
    # Tipos
    # -----------------------------------------------------
    df["fecha_final"] = pd.to_datetime(df["fecha_final"], errors="coerce")

    for c in ["precio_ci", "total_flujo_por_vn100", "TNA_%"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["Dias_al_vto"] = (
        pd.to_numeric(df["Dias_al_vto"], errors="coerce")
        .round(0)
        .astype("Int64")
    )

    # -----------------------------------------------------
    # Tiempo hasta vencimiento
    # -----------------------------------------------------
    dias = pd.to_numeric(df["Dias_al_vto"], errors="coerce")

    # -----------------------------------------------------
    # Tiempo hasta vencimiento (sin decimales engañosos)
    # -----------------------------------------------------
    dias = pd.to_numeric(df["Dias_al_vto"], errors="coerce")

    # Para segmentación (exacto, sin redondear)
    df["Anios_al_vto"] = dias / 365.0

    # Para display (meses enteros)
    meses_total = (dias / 30.4375).round(0).astype("Int64")  # 365.25/12
    df["Meses_al_vto"] = meses_total

    anios = (meses_total // 12).astype("Int64")
    meses = (meses_total % 12).astype("Int64")

    def _fmt_tiempo(a, m):
        if pd.isna(a) or pd.isna(m):
            return ""
        a = int(a)
        m = int(m)
        if a <= 0:
            return f"{m} Meses"
        if m == 0:
            return f"{a} Años"
        # singular/plural simple
        a_txt = "Año" if a == 1 else "Años"
        m_txt = "Mes" if m == 1 else "Meses"
        return f"{a} {a_txt} y {m} {m_txt}"

    df["Tiempo_al_vto"] = [_fmt_tiempo(a, m) for a, m in zip(anios, meses)]

    # -----------------------------------------------------
    # Plazo (Corto / Mediano / Largo)
    # -----------------------------------------------------
    def _plazo(a):
        if pd.isna(a):
            return ""
        if a <= 2:
            return "CORTO"
        if a <= 7:
            return "MEDIANO"
        return "LARGO"

    df["plazo"] = df["Anios_al_vto"].apply(_plazo)

    # -----------------------------------------------------
    # Redondeos
    # -----------------------------------------------------
    df["precio_ci"] = df["precio_ci"].round(2)
    df["total_flujo_por_vn100"] = df["total_flujo_por_vn100"].round(4)
    df["TNA_%"] = df["TNA_%"].round(2)

    # -----------------------------------------------------
    # DataFrame para gráfico
    # -----------------------------------------------------
    df_curve = (
        df[["codigo", "Dias_al_vto", "TNA_%"]]
        .copy()
        .rename(
            columns={
                "codigo": "Especie",
                "Dias_al_vto": "Dias al VTO",
                "TNA_%": "TNA %",
            }
        )
    )

    # -----------------------------------------------------
    # DataFrame para vista
    # -----------------------------------------------------
    df_view = df.copy()
    df_view["fecha_final"] = df_view["fecha_final"].dt.date

    df_view = df_view.rename(columns=BONOS_COLUMN_MAP)
    df_view["TNA %"] = df_view["TNA %"].apply(
        lambda v: f"{v:.2f}%" if pd.notna(v) else ""
    )

    return df_view, df_curve