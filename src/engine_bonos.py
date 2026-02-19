import pandas as pd
import numpy as np

from .config import FECHA_CIERRE, BASE_ANUAL, PRECIO_CI_SOBRE_RESIDUAL
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

def _read_bonos_flujos(flujos_path: str) -> pd.DataFrame:
    # Admite .csv o .xlsx
    if str(flujos_path).lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(flujos_path, engine='openpyxl')
    else:
        df = pd.read_csv(flujos_path, encoding='utf-8-sig')

    missing = [c for c in REQUIRED_FLUJOS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en flujos de bonos: {missing}")

    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    df["fecha_pago"] = pd.to_datetime(df["fecha_pago"], errors="coerce")
    df["moneda_flujo"] = df["moneda_flujo"].astype(str).str.strip().str.upper()

    for c in ["vr_pre_pago_por_vn100","interes_por_vn100","amortizacion_por_vn100"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["codigo","fecha_pago"])
    df = df.sort_values(["codigo","fecha_pago"]).reset_index(drop=True)
    return df

def _days_from_close(d: pd.Timestamp) -> float:
    """Días corridos desde FECHA_CIERRE hasta d."""
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

def macaulay_duration_base360(
    dates: list[pd.Timestamp],
    amounts: list[float],
    rate: float,
    price: float,
) -> float:
    """
    Duration de Macaulay (en años base 360), usando:
      PV_i = CF_i / (1+rate)^(t_i/BASE_ANUAL)
      D = sum(t_i_years * PV_i) / price
    dates[0] debe ser FECHA_CIERRE (t=0) y su amount suele ser -price (no se incluye en duration).
    """
    if not np.isfinite(rate) or rate <= -0.9999:
        return np.nan
    if not np.isfinite(price) or price <= 0:
        return np.nan
    if len(dates) != len(amounts) or len(dates) < 2:
        return np.nan

    fc = pd.to_datetime(FECHA_CIERRE)

    # solo flujos positivos futuros (ignoramos el -price de t=0)
    pv_sum = 0.0
    w_sum = 0.0

    for d, cf in zip(dates[1:], amounts[1:]):
        if cf is None:
            continue
        cf = float(cf)
        if not np.isfinite(cf) or cf <= 0:
            continue

        t_days = float((pd.to_datetime(d) - fc).days)
        if t_days <= 0:
            continue

        t_years = t_days / BASE_ANUAL
        disc = (1.0 + rate) ** (t_days / BASE_ANUAL)
        pv = cf / disc

        pv_sum += pv
        w_sum += t_years * pv

    if pv_sum <= 0:
        return np.nan

    # Usamos el precio de mercado como denominador (duration “de precio”)
    return w_sum / float(price)


def risk_score_balanced(mod_duration: float, tipo: str, moneda_cobro: str) -> float:
    """
    Score 0..1 (mayor = más riesgoso), balanceado:
    - 55% sensibilidad (mod duration)
    - 30% tipo instrumento
    - 15% moneda de cobro
    """
    # 1) Sensibilidad: normalizamos mod duration con umbrales simples (no especulativos)
    #    0..2 años => 0..0.35 | 2..6 => 0.35..0.75 | >6 => 0.75..1
    if not np.isfinite(mod_duration) or mod_duration < 0:
        sens = 0.50  # neutral si no se pudo calcular
    else:
        d = float(mod_duration)
        if d <= 2:
            sens = 0.35 * (d / 2.0)
        elif d <= 6:
            sens = 0.35 + (0.75 - 0.35) * ((d - 2.0) / 4.0)
        else:
            # asintótico hacia 1
            sens = 0.75 + 0.25 * (1.0 - np.exp(-(d - 6.0) / 6.0))
        sens = float(np.clip(sens, 0.0, 1.0))

    # 2) Tipo: estructura
    t = (tipo or "").strip().upper()
    if t in ["LECAP", "BONCAP"]:
        tipo_s = 0.25
    elif t == "SOBERANO":
        tipo_s = 0.60
    elif t == "ON":
        tipo_s = 0.75
    else:
        tipo_s = 0.60

    # 3) Moneda de cobro: ARS penaliza
    m = (moneda_cobro or "").strip().upper()
    if m == "ARS":
        mon_s = 0.80
    elif m == "USD":
        mon_s = 0.35
    else:
        mon_s = 0.55

    score = 0.55 * sens + 0.30 * tipo_s + 0.15 * mon_s
    return float(np.clip(score, 0.0, 1.0))

def _resolve_price_code(codigo: str, tipo: str, precios_ci: dict) -> str | None:
    """
    Devuelve el código a usar para buscar precio en precios_ci.
    Regla actual:
      - default: usa el mismo codigo
      - ON: si termina en 'D' y existe la variante 'O' en el JSON, usa la 'O'
    """
    c = str(codigo).strip().upper()
    t = str(tipo or "").strip().upper()

    if c in precios_ci:
        return c

    if t == "ON" and c.endswith("D"):
        alt = c[:-1] + "O"
        if alt in precios_ci:
            return alt

    return None


def _has_price(codigo: str, tipo: str, precios_ci: dict) -> bool:
    return _resolve_price_code(codigo, tipo, precios_ci) is not None

def run_engine_bonos(master_xlsx_path: str, flujos_path: str, precios_ci: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Bonos soberanos:
      - Precio CI manual desde JSON (por VN100)
      - Flujos desde CSV (por VN100)
      - Devuelve df_view (formateado) y df_curve (numérico para plot)
    """
    master = read_master_bonos(master_xlsx_path)
    flujos = _read_bonos_flujos(flujos_path)

    fc = pd.to_datetime(FECHA_CIERRE)

    # -------------------------------------------------
    # Excluir instrumentos vencidos (validación temporal)
    # -------------------------------------------------
    if "fecha_vto" in master.columns:
        master["fecha_vto"] = pd.to_datetime(master["fecha_vto"], errors="coerce")
        master = master[master["fecha_vto"] > fc].copy()

    # -------------------------------------------------
    # Filtrar bonos: solo los que tienen flujos futuros
    # y precio CI válido en el JSON
    # -------------------------------------------------
    # flujos futuros
    flujos_fut = flujos[flujos["fecha_pago"] >= fc].copy()
    codigos_con_flujos = set(flujos_fut["codigo"].dropna().astype(str).str.upper())

    # Precios válidos (normalizados)
    precios_ok = {}
    for k, v in (precios_ci or {}).items():
        kk = str(k).strip().upper()
        vv = pd.to_numeric(v, errors="coerce")
        if vv is not None and np.isfinite(vv) and float(vv) > 0:
            precios_ok[kk] = float(vv)

    # Tipos por código (desde master)
    master["codigo"] = master["codigo"].astype(str).str.strip().str.upper()
    master["tipo_instrumento"] = master.get("tipo_instrumento", "SOBERANO")
    master["tipo_instrumento"] = master["tipo_instrumento"].astype(str).str.strip().str.upper()

    tipo_by_code = dict(zip(master["codigo"], master["tipo_instrumento"]))

    # Códigos del master que tienen precio (directo o alias ON D->O) + flujos futuros
    codigos_con_precio_master = {
        code for code, t in tipo_by_code.items()
        if _has_price(code, t, precios_ok)
    }

    codigos_validos = codigos_con_flujos.intersection(codigos_con_precio_master)

    master = master[master["codigo"].isin(codigos_validos)].copy()

    # Aplicar filtro al master
    master = master[master["codigo"].astype(str).str.upper().isin(codigos_validos)].copy()

    # quedarnos solo con flujos >= cierre
    flujos_fut["flujo_total_por_vn100"] = (
        flujos_fut["interes_por_vn100"].fillna(0) + flujos_fut["amortizacion_por_vn100"].fillna(0)
    )

    rows = []
    for _, bono in master.iterrows():
        codigo = str(bono["codigo"]).upper().strip()
        tipo_instrumento = str(bono.get("tipo_instrumento", "SOBERANO")).strip().upper()
        # Tomamos flujos solo por codigo (la moneda real viene del flujo)
        g = flujos_fut[flujos_fut["codigo"] == codigo].sort_values("fecha_pago")
        if g.empty:
            moneda_flujo = ""
        else:
            moneda_flujo = str(g["moneda_flujo"].iloc[0]).upper().strip()

        # -------------------------
        # Valor residual (capital vivo)
        # -------------------------
        valor_residual = bono.get("valor_residual", np.nan)
        try:
            valor_residual = float(valor_residual)
        except Exception:
            valor_residual = np.nan

        # fallback seguro
        if not np.isfinite(valor_residual) or valor_residual <= 0:
            valor_residual = 100.0

        ratio_residual = valor_residual / 100.0

        price_code = _resolve_price_code(codigo, tipo_instrumento, precios_ok)
        precio_ci_raw = precios_ok.get(price_code) if price_code else np.nan
        try:
            precio_ci_raw = float(precio_ci_raw)
        except Exception:
            precio_ci_raw = np.nan

        # Precio equivalente por VN100 original:
        # - si el JSON viene sobre residual, lo convertimos
        # - si ya viene sobre VN100 original, lo dejamos igual
        if np.isfinite(precio_ci_raw):
            if PRECIO_CI_SOBRE_RESIDUAL:
                precio_ci = precio_ci_raw * ratio_residual
            else:
                precio_ci = precio_ci_raw
        else:
            precio_ci = np.nan

        if g.empty or not np.isfinite(precio_ci) or precio_ci <= 0:
            rows.append({
                "codigo": codigo,
                "tipo_instrumento": tipo_instrumento,
                "moneda": moneda_flujo,
                "precio_ci": precio_ci,
                "Dur_Mac": np.nan,
                "Dur_Mod": np.nan,
                "_risk_score": np.nan,

                # Interno para cálculo de monto (si después lo necesitás):
                "total_flujo_por_vn100": np.nan,

                # Salida clara al usuario:
                "fecha_final": pd.NaT,
                "Dias_al_vto": np.nan,
                "TNA_%": np.nan,
            })
            continue

        # Construir flujos para TIR (en moneda de cobro)
        fechas = [fc] + list(g["fecha_pago"])
        montos = [-precio_ci] + list(g["flujo_total_por_vn100"])

        tir = xirr_base360(fechas, montos)

        if np.isfinite(tir):
            tna_pct = tir * 100.0

            # Duration (Macaulay y Modified) base 360
            dur_mac = macaulay_duration_base360(fechas, montos, tir, precio_ci)
            dur_mod = dur_mac / (1.0 + tir) if np.isfinite(dur_mac) and (1.0 + tir) > 0 else np.nan
        else:
            tna_pct = np.nan
            dur_mac = np.nan
            dur_mod = np.nan

        total_flujo = float(g["flujo_total_por_vn100"].sum())
        fecha_final = g["fecha_pago"].max()
        dias_final = _days_from_close(fecha_final)

        rows.append({
            "codigo": codigo,
            "tipo_instrumento": tipo_instrumento,
            "moneda": moneda_flujo,
            "precio_ci": precio_ci,

            "Dur_Mac": dur_mac,
            "Dur_Mod": dur_mod,
            "_risk_score": risk_score_balanced(dur_mod, tipo_instrumento, moneda_flujo),

            # interno para cálculo de monto (si el usuario pone monto a invertir)
            "total_flujo_por_vn100": total_flujo,

            # salida clara al usuario
            "fecha_final": fecha_final,
            "Dias_al_vto": dias_final,
            "TNA_%": tna_pct,
        })

    out = pd.DataFrame(rows)
    out = out.sort_values(["Dias_al_vto","codigo"], na_position="last").reset_index(drop=True)

    # -----------------------------------
    # FICHA BONO: arrastrar metadata
    # -----------------------------------
    ficha_cols = [
    "codigo",
    "emisor", "sector", "legislacion", "rating", "tipo_tasa",
    "cupon_anual", "frecuencia", "fecha_emision", "fecha_vto",
    "garantia", "nota",
    ]
    ficha_cols = [c for c in ficha_cols if c in master.columns]

    if "codigo" in ficha_cols and not master.empty:
        ficha = master[ficha_cols].drop_duplicates(subset=["codigo"]).copy()
        out = out.merge(ficha, on="codigo", how="left")

    # Ahora sí construir vistas
    df_view, df_curve = build_view_df_bonos(out)

    return df_view, df_curve, flujos_fut