import pandas as pd

# =========================================================
# FORMATTING – BONOS SOBERANOS (SPR_BS)
# =========================================================

BONOS_COLUMN_MAP = {
    "codigo": "Especie",
    "moneda": "Moneda",
    "precio_ci": "Valor Actual",
    "fecha_final": "Fecha de Vencimiento",
    "Dias_al_vto": "Dias al VTO",
    "TNA_%": "TNA %",
    # columna interna (NO mostrar en tabla principal)
    "total_flujo_por_vn100": "_total_flujo_por_vn100",
}

BONOS_ORDER_COLS = [
    "codigo",
    "moneda",
    "precio_ci",
    "fecha_final",
    "Dias_al_vto",
    "TNA_%",
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
    df = df_raw[BONOS_ORDER_COLS].copy()

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