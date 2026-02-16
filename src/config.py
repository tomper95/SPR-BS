from pathlib import Path

# =========================
# Parámetros globales
# =========================
FECHA_CIERRE = "2026-02-16"   # fijo (simulado por ahora)
TC_ARS_USD = 1433.30

BASE_ANUAL = 360             # fijo (para TNA/TIR base 360)
PRECIO_CI_SOBRE_RESIDUAL = False

# =========================
# Paths del repo
# =========================
BASE_DIR = Path(__file__).resolve().parent          # .../src
REPO_ROOT = BASE_DIR.parent                         # .../ (raíz del repo)
DATA_DIR = REPO_ROOT / "data"

# Letras (LECAP/BONCAP)
MASTER_CSV_PATH = str(DATA_DIR / "instrumentos_master.csv")

# Precios (manuales)
PRECIOS_CI_JSON_PATH = str(DATA_DIR / "precios_ci.json")

# --- BONOS SOBERANOS (SPR_BS) ---
BONOS_MASTER_PATH = str(REPO_ROOT / "data" / "SPR_BS_master.xlsx")
BONOS_FLUJOS_PATH = str(DATA_DIR / "bonos_flujos.xlsx")