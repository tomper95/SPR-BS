from __future__ import annotations

"""
Checklist de integridad de datos (SPR_BS).

Objetivo:
- Detectar errores que rompen el motor o dejan el universo vacío.
- Detectar inconsistencias comunes (master vs precios vs flujos vs equivalencias).

No depende de Streamlit: devuelve (errors, warnings, summary, artifacts).
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ChecklistSummary:
    codigos_master: int
    precios_validos: int
    codigos_con_flujos_futuros: int
    codigos_usables_motor: int
    equivalencias_items: int


def _u(x: Any) -> str:
    return str(x).strip().upper() if x is not None else ""


def _coerce_positive_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:
        return None
    if not np.isfinite(v) or v <= 0:
        return None
    return v


def _read_master(master_xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(master_xlsx_path, sheet_name="master_bono", engine="openpyxl")
    if "codigo" not in df.columns:
        raise ValueError("master_bono no tiene columna 'codigo'.")
    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    return df


def _read_flujos(flujos_path: str) -> pd.DataFrame:
    if str(flujos_path).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(flujos_path, engine="openpyxl")
    else:
        df = pd.read_csv(flujos_path, encoding="utf-8-sig")

    required_cols = [
        "codigo",
        "fecha_pago",
        "interes_por_vn100",
        "amortizacion_por_vn100",
        "moneda_flujo",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en flujos: {missing}")

    df["codigo"] = df["codigo"].astype(str).str.strip().str.upper()
    df["fecha_pago"] = pd.to_datetime(df["fecha_pago"], errors="coerce")
    return df


def _read_equivalencias_long(master_xlsx_path: str) -> pd.DataFrame | None:
    """
    Lee la sheet 'equivalencias' en formato ancho (ARS/MEP/CCL) y la normaliza.

    Devuelve columnas: codigo, grupo, canal.
    - grupo: valor de la columna ARS (base)
    - canal: ARS / MEP / CCL
    """
    try:
        eq = pd.read_excel(master_xlsx_path, sheet_name="equivalencias", engine="openpyxl")
    except Exception:
        return None

    cols = {c.strip().upper(): c for c in eq.columns}
    expected = ["ARS", "MEP", "CCL"]
    if any(c not in cols for c in expected):
        return pd.DataFrame(columns=["codigo", "grupo", "canal"])

    rows: list[dict[str, str]] = []
    for _, r in eq.iterrows():
        grupo = _u(r[cols["ARS"]])
        if not grupo or grupo == "NAN":
            continue
        for canal in expected:
            val = _u(r[cols[canal]])
            if val and val != "NAN":
                rows.append({"codigo": val, "grupo": grupo, "canal": canal})

    return pd.DataFrame(rows, columns=["codigo", "grupo", "canal"])


def run_checklist(
    master_xlsx_path: str,
    flujos_path: str,
    precios_ci: dict,
    fecha_cierre: str,
) -> tuple[list[str], list[str], ChecklistSummary | None, dict[str, Any]]:
    """
    Devuelve:
    - errors: errores críticos
    - warnings: advertencias
    - summary: conteos clave (o None si no se pudo construir)
    - artifacts: dataframes útiles para debug (master_full, flujos_fut, eq_long)
    """
    errors: list[str] = []
    warnings: list[str] = []
    artifacts: dict[str, Any] = {}

    # ---------- Master ----------
    try:
        master_full = _read_master(master_xlsx_path)
    except Exception as e:
        errors.append(f"No pude leer master_bono desde {master_xlsx_path}: {e}")
        return errors, warnings, None, artifacts

    artifacts["master_full"] = master_full
    codigos_master = set(master_full["codigo"].dropna())

    # Columnas recomendadas (no rompen si faltan)
    for col in ["moneda", "fecha_vto", "tipo_instrumento"]:
        if col not in master_full.columns:
            warnings.append(f"master_bono no tiene columna '{col}' (recomendado).")

    # Duplicados
    dup = master_full["codigo"].duplicated(keep=False)
    if dup.any():
        dups = master_full.loc[dup, "codigo"].value_counts().head(20).to_dict()
        warnings.append(f"Códigos duplicados en master_bono (top 20): {dups}")

    # ---------- Precios ----------
    if not isinstance(precios_ci, dict):
        errors.append("precios_ci.json no es un dict (objeto JSON).")
        precios_ci = {}

    precios_ok: dict[str, float] = {}
    precios_bad: list[str] = []
    for k, v in precios_ci.items():
        kk = _u(k)
        vv = _coerce_positive_float(v)
        if vv is None:
            precios_bad.append(kk)
        else:
            precios_ok[kk] = vv

    if len(precios_ok) == 0:
        errors.append("No hay precios válidos (>0) en precios_ci.json.")
    if precios_bad:
        warnings.append(f"Precios inválidos/no numéricos en JSON (muestra 20): {precios_bad[:20]}")

    codigos_precio = set(precios_ok.keys())

    # ---------- Flujos ----------
    try:
        flujos = _read_flujos(flujos_path)
    except Exception as e:
        errors.append(f"No pude leer flujos desde {flujos_path}: {e}")
        return errors, warnings, None, artifacts

    fc = pd.to_datetime(fecha_cierre)
    flujos_fut = flujos[flujos["fecha_pago"] >= fc].copy()
    artifacts["flujos_fut"] = flujos_fut
    codigos_flujo_fut = set(flujos_fut["codigo"].dropna())

    if len(codigos_flujo_fut) == 0:
        errors.append("No hay flujos futuros (>= FECHA_CIERRE). Revisá FECHA_CIERRE o bonos_flujos.xlsx.")

    # ---------- Cruces ----------
    sin_precio = sorted(list(codigos_master - codigos_precio))
    if sin_precio:
        warnings.append(f"Códigos en master sin precio en JSON (muestra 30): {sin_precio[:30]}")

    sin_flujo = sorted(list(codigos_master - codigos_flujo_fut))
    if sin_flujo:
        warnings.append(f"Códigos en master sin flujo futuro (muestra 30): {sin_flujo[:30]}")

    # ---------- Alertas específicas: ON ----------
    if "tipo_instrumento" in master_full.columns:
        m_on = master_full.copy()
        m_on["tipo_instrumento"] = m_on["tipo_instrumento"].astype(str).str.strip().str.upper()
        codigos_on = set(m_on.loc[m_on["tipo_instrumento"] == "ON", "codigo"].dropna())
    
        if codigos_on:
            on_sin_flujo = sorted(list(codigos_on - codigos_flujo_fut))
            if on_sin_flujo:
                warnings.append(
                    f"[ON] En master sin match exacto en flujos futuros (muestra 30): {on_sin_flujo[:30]}"
                )

                on_sin_precio = sorted(list(codigos_on - codigos_precio))
                if on_sin_precio:
                    warnings.append(
                        f"[ON] En master sin precio exacto en precios_ci.json (muestra 30): {on_sin_precio[:30]}"
                    )
        else:
            # ya existe un warning arriba si falta tipo_instrumento, pero lo dejamos explícito
            warnings.append("[ON] No puedo validar ON: falta columna 'tipo_instrumento' en master_bono.")

    precio_sin_master = sorted(list(codigos_precio - codigos_master))
    if precio_sin_master:
        warnings.append(f"Precios en JSON sin master (muestra 30): {precio_sin_master[:30]}")

    flujo_sin_master = sorted(list(codigos_flujo_fut - codigos_master))
    if flujo_sin_master:
        warnings.append(f"Flujos futuros sin master (muestra 30): {flujo_sin_master[:30]}")

    codigos_usable = codigos_master & codigos_precio & codigos_flujo_fut
    if len(codigos_usable) == 0:
        errors.append("No hay ningún código que cumpla master + precio + flujo futuro. Motor quedará vacío.")

    # ---------- Equivalencias ----------
    eq_long = _read_equivalencias_long(master_xlsx_path)
    artifacts["eq_long"] = eq_long

    eq_items = 0
    if eq_long is None:
        warnings.append("No se encontró sheet 'equivalencias' (ok por ahora). Si la creaste, verificá el nombre exacto.")
    else:
        eq_items = int(len(eq_long))

        if not eq_long.empty:
            eq_codes = set(eq_long["codigo"].dropna())
            faltan_en_master = sorted(list(eq_codes - codigos_master))
            if faltan_en_master:
                warnings.append(f"Equivalencias con códigos que NO están en master (muestra 30): {faltan_en_master[:30]}")

            conflict = (
                eq_long.groupby("codigo")["grupo"].nunique().loc[lambda s: s > 1].index.tolist()
            )
            if conflict:
                warnings.append(f"Códigos asignados a más de un grupo (muestra 30): {conflict[:30]}")

            # Validación moneda_precio vs canal (si existe columna)
            if "moneda_precio" in master_full.columns:
                mp = master_full[["codigo", "moneda_precio"]].copy()
                mp["codigo"] = mp["codigo"].astype(str).str.strip().str.upper()
                mp["moneda_precio"] = mp["moneda_precio"].astype(str).str.strip().str.upper()
                eq_mp = eq_long.merge(mp, on="codigo", how="left")

                bad_ars = eq_mp[(eq_mp["canal"] == "ARS") & (~eq_mp["moneda_precio"].fillna("").str.contains("ARS"))]
                bad_usd = eq_mp[(eq_mp["canal"].isin(["MEP", "CCL"])) & (~eq_mp["moneda_precio"].fillna("").str.contains("USD"))]

                if not bad_ars.empty:
                    warnings.append("Canal ARS pero moneda_precio no contiene 'ARS' (muestra 15): " + str(bad_ars["codigo"].head(15).tolist()))
                if not bad_usd.empty:
                    warnings.append("Canal MEP/CCL pero moneda_precio no contiene 'USD' (muestra 15): " + str(bad_usd["codigo"].head(15).tolist()))

    summary = ChecklistSummary(
        codigos_master=len(codigos_master),
        precios_validos=len(codigos_precio),
        codigos_con_flujos_futuros=len(codigos_flujo_fut),
        codigos_usables_motor=len(codigos_usable),
        equivalencias_items=eq_items,
    )

    return errors, warnings, summary, artifacts