import pandas as pd
import numpy as np

from .config import FECHA_CIERRE, BASE_ANUAL
from .io_bonos import read_master_bonos
from .formatting import build_view_df_bonos

REQUIRED_FLUJOS_COLS = [
    "codigo",
    "fecha_pago",
    "vr_pre_pago_por_vn100",
    "interes_por_vn100",
    "amortizacion_por_vn100",
    "moneda_flujo",
]

def _read_bonos_flujos(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    missing = [c for c in REQUIRED_FLUJOS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en bonos_flujos: {missing}")

    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    df["fecha_pago"] = pd.to_datetime(df["fecha_pago"], errors="coerce")
    df["moneda_flujo"] = df["moneda_flujo"].astype(str).str.strip().str.upper()

    for c in ["vr_pre_pago_por_vn100","interes_por_vn100","amortizacion_por_vn100"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["codigo","fecha_pago"])
    df = df.sort_values(["codigo","fecha_pago"]).reset_index(drop=True)
    return df

def _days_from_close(d: pd.Timestamp) -> float:
    fc = pd.to_datetime(FECHA_CIERRE)
    return float((pd.to_datetime(d) - fc).days)

def xirr_base360(dates: list[pd.Timestamp], amounts: list[float], guess: float = 0.5) -> float:
    """IRR con base 360 usando potencias (1+r)^(dias/BASE_ANUAL). Devuelve r (decimal)."""
    if len(dates) != len(amounts) or len(dates) < 2:
        return np.nan

    # convertir a días desde cierre
    fc = pd.to_datetime(FECHA_CIERRE)
    t = np.array([(pd.to_datetime(d) - fc).days for d in dates], dtype=float)
    c = np.array(amounts, dtype=float)

    # debe haber al menos un negativo y un positivo
    if not ((c < 0).any() and (c > 0).any()):
        return np.nan

    # Newton-Raphson con fallback
    r = float(guess)
    for _ in range(80):
        if r <= -0.9999:
            r = -0.9999

        # NPV y derivada
        denom = np.power(1.0 + r, t / BASE_ANUAL)
        npv = np.sum(c / denom)

        # derivada: d/dr [ c*(1+r)^(-t/BASE) ] = c * (-t/BASE) * (1+r)^(-t/BASE -1)
        der = np.sum(c * (-(t / BASE_ANUAL)) * np.power(1.0 + r, -(t / BASE_ANUAL) - 1.0))

        if np.isfinite(npv) and abs(npv) < 1e-10:
            return r
        if not np.isfinite(der) or der == 0:
            break

        step = npv / der
        r_new = r - step

        if abs(r_new - r) < 1e-10:
            return r_new

        r = r_new

    # fallback: búsqueda por bisección si hay cambio de signo en rango
    def f(rate: float) -> float:
        if rate <= -0.9999:
            return np.inf
        denom = np.power(1.0 + rate, t / BASE_ANUAL)
        return float(np.sum(c / denom))

    lo, hi = -0.9, 10.0
    f_lo, f_hi = f(lo), f(hi)
    if not (np.isfinite(f_lo) and np.isfinite(f_hi)) or f_lo * f_hi > 0:
        return np.nan

    for _ in range(120):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < 1e-10:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return mid

def run_engine_bonos(master_xlsx_path: str, flujos_csv_path: str, precios_ci: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Bonos soberanos:
      - Precio CI manual desde JSON (por VN100)
      - Flujos desde CSV (por VN100)
      - Devuelve df_view (formateado) y df_curve (numérico para plot)
    """
    master = read_master_bonos(master_xlsx_path)
    flujos = _read_bonos_flujos(flujos_csv_path)

    fc = pd.to_datetime(FECHA_CIERRE)

    # quedarnos solo con flujos >= cierre
    flujos_fut = flujos[flujos["fecha_pago"] >= fc].copy()
    flujos_fut["flujo_total_por_vn100"] = (
        flujos_fut["interes_por_vn100"].fillna(0) + flujos_fut["amortizacion_por_vn100"].fillna(0)
    )

    rows = []
    for _, bono in master.iterrows():
        codigo = str(bono["codigo"]).upper().strip()
        moneda = str(bono["moneda"]).upper().strip()

        precio_ci = precios_ci.get(codigo)
        try:
            precio_ci = float(precio_ci)
        except Exception:
            precio_ci = np.nan

        g = flujos_fut[flujos_fut["codigo"] == codigo].sort_values("fecha_pago")
        if g.empty or not np.isfinite(precio_ci) or precio_ci <= 0:
            rows.append({
                "codigo": codigo,
                "moneda": moneda,
                "precio_ci": precio_ci,

                # Interno para cálculo de monto (si después lo necesitás):
                "total_flujo_por_vn100": np.nan,

                # Salida clara al usuario:
                "fecha_final": pd.NaT,
                "Dias_al_vto": np.nan,
                "TNA_%": np.nan,
            })
            continue

        total_flujo = float(g["flujo_total_por_vn100"].sum())
        fecha_final = g["fecha_pago"].max()
        dias_final = _days_from_close(fecha_final)

        # TNA (aprox) anualizada simple a vencimiento:
        # TNA% ≈ ((TotalFlujos/Precio) - 1) * (360 / días) * 100
        if np.isfinite(dias_final) and dias_final > 0:
            tna_pct = ((total_flujo / precio_ci) - 1.0) * (BASE_ANUAL / dias_final) * 100.0
        else:
            tna_pct = np.nan

        rows.append({
            "codigo": codigo,
            "moneda": moneda,
            "precio_ci": precio_ci,

            # interno para cálculo de monto (si el usuario pone monto a invertir)
            "total_flujo_por_vn100": total_flujo,

            # salida clara al usuario
            "fecha_final": fecha_final,
            "Dias_al_vto": dias_final,
            "TNA_%": tna_pct,
        })

    out = pd.DataFrame(rows)
    out = out.sort_values(["Dias_al_vto","codigo"], na_position="last").reset_index(drop=True)
    
    df_view, df_curve = build_view_df_bonos(out)
    return df_view, df_curve