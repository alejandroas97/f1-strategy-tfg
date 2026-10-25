"""Configuración común del proyecto."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"            # caché interna de FastF1
DATA_DIR = ROOT / "data"              # datos extraídos (Parquet / CSV)
RAW_FASTF1 = DATA_DIR / "raw" / "fastf1"
RAW_OPENF1 = DATA_DIR / "raw" / "openf1"
OUTPUTS = ROOT / "outputs"            # gráficos y resúmenes

# Temporadas con datos de timing por vuelta en FastF1 (Live Timing oficial)
SEASONS = list(range(2018, 2026))

OPENF1_BASE = "https://api.openf1.org/v1"
# OpenF1 no tiene datos anteriores a 2023; 2026 queda fuera del alcance (nuevo reglamento)
OPENF1_SEASONS = [2023, 2024, 2025]
# Nivel gratuito de OpenF1: 3 peticiones/s y 30 peticiones/min
OPENF1_MIN_INTERVAL_S = 2.1

for d in (CACHE_DIR, RAW_FASTF1, RAW_OPENF1, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)
