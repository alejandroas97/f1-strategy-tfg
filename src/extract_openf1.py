"""T1.1.1 - Extracción y cacheo local de carreras con OpenF1 (datos desde 2023).

Por cada Gran Premio guarda en data/raw/openf1/<año>/<ronda>_<gp>/:
  session.parquet         carrera y circuito: fechas, ronda, nombre del GP, tipo de circuito
  drivers.parquet        número, acrónimo, nombre y equipo de cada piloto
  laps.parquet            vueltas: duración total y por sector, velocidades, vuelta de salida de boxes
  stints.parquet          stints: compuesto, vuelta inicial y final, edad del neumático al montarlo
  pit.parquet             paradas: vuelta y duración en el pit lane
  race_control.parquet    dirección de carrera: banderas, SC, VSC, bandera roja
  weather.parquet         meteorología (1 registro/min)
  session_result.parquet  clasificación final, vueltas completadas, DNF/DNS/DSQ

Uso:
  python src/extract_openf1.py --seasons 2024 --rounds 1   # una carrera (prueba)
  python src/extract_openf1.py                             # 2023-2025 completo
Es reanudable: salta las carreras ya descargadas.
"""
import argparse
import json
import logging
import re
import time
import unicodedata

import pandas as pd
import requests

from config import OPENF1_BASE, OPENF1_MIN_INTERVAL_S, OPENF1_SEASONS, RAW_OPENF1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extract_openf1")

ENDPOINTS = ("drivers", "laps", "stints", "pit", "race_control", "weather", "session_result")
_last_call = 0.0


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()  # São -> Sao
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def to_parquet(df: pd.DataFrame, path):
    """Columnas con tipos mezclados (p. ej. gap_to_leader = 12.3 o '+1 LAP') se guardan como texto."""
    out = df.copy()
    for col in out.columns[out.dtypes == object]:
        if out[col].map(type).nunique() > 1:
            out[col] = out[col].map(lambda v: None if v is None else str(v))
    out.to_parquet(path, index=False)


def get(endpoint: str, **params) -> pd.DataFrame:
    """GET respetando el límite gratuito; 404 = sin datos; reintenta si se excede el límite."""
    global _last_call
    for attempt in range(5):
        wait = OPENF1_MIN_INTERVAL_S - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(f"{OPENF1_BASE}/{endpoint}", params=params, timeout=60)
        _last_call = time.time()
        if r.status_code == 404:
            return pd.DataFrame()
        if r.status_code == 429 or r.status_code >= 500:
            log.warning("%s -> HTTP %d, reintento en %d s", endpoint, r.status_code, 20 * (attempt + 1))
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return pd.DataFrame(r.json())
    raise RuntimeError(f"{endpoint}: demasiados reintentos")


def race_calendar(year: int) -> pd.DataFrame:
    """Carreras (domingo) del año con su número de ronda y nombre del GP."""
    races = get("sessions", year=year, session_name="Race", session_type="Race")
    meetings = get("meetings", year=year)[["meeting_key", "meeting_name", "meeting_official_name",
                                           "circuit_type"]]
    races = races.merge(meetings, on="meeting_key", how="left")
    races["date_start"] = pd.to_datetime(races["date_start"], utc=True)
    return races[races["date_start"] < pd.Timestamp.now(tz="UTC")].sort_values("date_start")


def extract_race(year: int, rnd: int, name: str, race: pd.Series) -> dict:
    folder = RAW_OPENF1 / str(year) / f"{rnd:02d}_{slug(name)}"
    session_key = int(race["session_key"])
    info = {"year": year, "round": rnd, "gp": name, "session_key": session_key}
    # session.parquet: datos de la carrera y del circuito (sale del calendario, sin peticiones extra)
    session = race.to_frame().T.assign(round=rnd)
    if (folder / "laps.parquet").exists():
        if not (folder / "session.parquet").exists():
            to_parquet(session, folder / "session.parquet")
        return info | {"status": "skipped"}

    tables = {ep: get(ep, session_key=session_key) for ep in ENDPOINTS}
    if tables["laps"].empty:
        return info | {"status": "no_data"}

    folder.mkdir(parents=True, exist_ok=True)
    tables["session"] = session
    # laps.parquet se escribe el último: su existencia marca la carrera como completa
    for ep in sorted(tables, key=lambda ep: ep == "laps"):
        to_parquet(tables[ep], folder / f"{ep}.parquet")

    laps = tables["laps"]
    return info | {
        "status": "ok",
        "laps": len(laps),
        "drivers": int(laps["driver_number"].nunique()),
        "pct_with_time": round(float(laps["lap_duration"].notna().mean()) * 100, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="*", default=OPENF1_SEASONS)
    parser.add_argument("--rounds", type=int, nargs="*", default=None)
    args = parser.parse_args()

    report = []
    for year in args.seasons:
        rnd = 0
        for _, race in race_calendar(year).iterrows():
            # Las carreras canceladas (p. ej. Emilia-Romaña 2023) figuran en el calendario
            # sin datos y no cuentan como ronda
            rnd += 1
            name = race["meeting_name"] if pd.notna(race["meeting_name"]) else race["country_name"]
            if args.rounds and rnd not in args.rounds:
                continue
            try:
                info = extract_race(year, rnd, name, race)
            except Exception as exc:  # red o límites de la API: se reintenta en la próxima ejecución
                log.warning("Fallo %s %02d %s: %s", year, rnd, name, exc)
                info = {"year": year, "round": rnd, "gp": name, "status": "error"}
            log.info("%s %02d %s -> %s", year, rnd, name, info["status"])
            if info["status"] == "no_data":
                rnd -= 1
            report.append(info)

    out = RAW_OPENF1 / "extraction_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(r["status"] in ("ok", "skipped") for r in report)
    log.info("Terminado: %d/%d carreras disponibles, informe en %s", ok, len(report), out)


if __name__ == "__main__":
    main()
