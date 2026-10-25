"""Prueba de la API de OpenF1 (fuente de contraste, datos desde 2023).

Descarga para una carrera: sesiones, stints, pit stops y dirección de carrera,
y los guarda en data/raw/openf1/<año>_<país>/ como CSV.

Uso:
  python src/explore_openf1.py --year 2024 --country Bahrain
"""
import argparse
import time

import pandas as pd
import requests

from config import OPENF1_BASE, OPENF1_MIN_INTERVAL_S, RAW_OPENF1

_last_call = 0.0


def get(endpoint: str, **params) -> pd.DataFrame:
    """GET con espera mínima entre llamadas para respetar el límite gratuito."""
    global _last_call
    wait = OPENF1_MIN_INTERVAL_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(f"{OPENF1_BASE}/{endpoint}", params=params, timeout=30)
    _last_call = time.time()
    r.raise_for_status()
    return pd.DataFrame(r.json())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--country", default="Bahrain")
    a = p.parse_args()

    sessions = get("sessions", year=a.year, country_name=a.country, session_name="Race")
    if sessions.empty:
        raise SystemExit("No se encontró la carrera; revisa año y país (en inglés).")
    key = int(sessions.iloc[0]["session_key"])
    print(f"Carrera encontrada: session_key={key}")

    folder = RAW_OPENF1 / f"{a.year}_{a.country.lower().replace(' ', '_')}"
    folder.mkdir(parents=True, exist_ok=True)
    for endpoint in ("stints", "pit", "race_control", "weather", "laps"):
        df = get(endpoint, session_key=key)
        df.to_csv(folder / f"{endpoint}.csv", index=False)
        print(f"  {endpoint:<13} {len(df):>6} filas  columnas: {', '.join(df.columns[:8])}...")


if __name__ == "__main__":
    main()
