from __future__ import annotations

from pathlib import Path
from datetime import datetime

# =========================
# Parámetros globales
# =========================
USE_SYSTEM_DATE = False  # True = usa fecha real del sistema (producción), False = usa fecha fija (simulación)

FECHA_CIERRE_FIJA = "2026-02-16"  # simulación / testing (YYYY-MM-DD)

FECHA_CIERRE = (
    datetime.now().strftime("%Y-%m-%d")
    if USE_SYSTEM_DATE
    else FECHA_CIERRE_FIJA
)

BASE_ANUAL = 360                 # fijo (para TNA/TIR base 360)
PRECIO_CI_SOBRE_RESIDUAL = False

# =========================
# Paths del repo
# =========================
BASE_DIR = Path(__file__).resolve().parent          # .../src
REPO_ROOT = BASE_DIR.parent                         # .../ (raíz del repo)
DATA_DIR = REPO_ROOT / "data"

MACRO_JSON_PATH = str(DATA_DIR / "macro.json")

# Fallback (si falta el macro.json)
DOLAR_OFICIAL: float = 1400.0
DOLAR_MEP: float = 1410.0
DOLAR_CCL: float = 1420.0

# Letras (LECAP/BONCAP)
MASTER_CSV_PATH = str(DATA_DIR / "instrumentos_master.csv")

# Precios (manuales)
PRECIOS_CI_JSON_PATH = str(DATA_DIR / "precios_ci.json")

# --- BONOS SOBERANOS (SPR_BS) ---
BONOS_MASTER_PATH = str(DATA_DIR / "SPR_BS_master.xlsx")  # sheet: master_bono

# Flujos (acepta .csv o .xlsx)
# Recomendado: usar .xlsx si estás manteniendo flujos en Excel
BONOS_FLUJOS_PATH = str(DATA_DIR / "bonos_flujos.xlsx")