import pandas as pd

REQUIRED_COLS = [
    "codigo","moneda","fecha_emision","fecha_vto",
    "cupon_anual","frecuencia","amortizacion_tipo",
    "valor_nominal","valor_residual"
]

def read_master_bonos(xlsx_path: str, sheet_name: str = "master_bono") -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en master_bono: {missing}")

    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    df["moneda"] = df["moneda"].astype(str).str.strip().str.upper()

    df["fecha_emision"] = pd.to_datetime(df["fecha_emision"], errors="coerce")
    df["fecha_vto"] = pd.to_datetime(df["fecha_vto"], errors="coerce")

    df["cupon_anual"] = pd.to_numeric(df["cupon_anual"], errors="coerce")
    df["frecuencia"] = pd.to_numeric(df["frecuencia"], errors="coerce")
    df["valor_nominal"] = pd.to_numeric(df["valor_nominal"], errors="coerce")
    df["valor_residual"] = pd.to_numeric(df["valor_residual"], errors="coerce")

    df = df.dropna(subset=["codigo","moneda","fecha_vto"])
    return df