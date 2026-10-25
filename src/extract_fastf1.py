"""T1.1.1 - Extracción y cacheo local de carreras con FastF1.

Por cada Gran Premio guarda en data/raw/fastf1/<año>/<ronda>_<gp>/:
  laps.parquet          vueltas: tiempo, stint, compuesto, TyreLife, boxes, TrackStatus...
  results.parquet       clasificación final, parrilla, estado (abandonos)
  weather.parquet       meteorología (1 registro/min)
  track_status.parquet  cambios de estado de pista (SC, VSC, bandera roja)
  race_control.parquet  mensajes de dirección de carrera

Uso:
  python src/extract_fastf1.py --seasons 2023            # una temporada
  python src/extract_fastf1.py --seasons 2023 --rounds 1 # una carrera (prueba)
  python src/extract_fastf1.py                           # todo el corpus
Es reanudable: salta las carreras ya descargadas.
"""
import argparse
import json
import logging
import re
import time

import fastf1
import pandas as pd

from config import CACHE_DIR, RAW_FASTF1, SEASONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extract_fastf1")
if hasattr(fastf1.Cache, "configure"):   # FastF1 >= 3.9
    fastf1.Cache.configure(cache_dir=str(CACHE_DIR))
else:
    fastf1.Cache.enable_cache(str(CACHE_DIR))
fastf1.set_log_level("WARNING")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def to_parquet(df: pd.DataFrame, path):
    """Convierte Timedelta a segundos (float) para que el Parquet sea portable."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_timedelta64_dtype(out[col]):
            out[col] = out[col].dt.total_seconds()
    out.to_parquet(path, index=False)


def extract_race(year: int, rnd: int, name: str) -> dict:
    folder = RAW_FASTF1 / str(year) / f"{rnd:02d}_{slug(name)}"
    if (folder / "laps.parquet").exists():
        return {"year": year, "round": rnd, "gp": name, "status": "skipped"}
    folder.mkdir(parents=True, exist_ok=True)

    session = fastf1.get_session(year, rnd, "R")
    session.load(laps=True, telemetry=False, weather=True, messages=True)

    laps = session.laps.copy()
    laps.insert(0, "Year", year)
    laps.insert(1, "Round", rnd)
    to_parquet(pd.DataFrame(laps), folder / "laps.parquet")
    to_parquet(pd.DataFrame(session.results), folder / "results.parquet")
    to_parquet(pd.DataFrame(session.weather_data), folder / "weather.parquet")
    to_parquet(pd.DataFrame(session.track_status), folder / "track_status.parquet")
    to_parquet(pd.DataFrame(session.race_control_messages), folder / "race_control.parquet")

    return {
        "year": year, "round": rnd, "gp": name, "status": "ok",
        "laps": len(laps), "drivers": laps["Driver"].nunique(),
        "pct_accurate": round(float(laps["IsAccurate"].mean()) * 100, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="*", default=SEASONS)
    parser.add_argument("--rounds", type=int, nargs="*", default=None)
    args = parser.parse_args()

    report = []
    for year in args.seasons:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        for _, ev in schedule.iterrows():
            rnd = int(ev["RoundNumber"])
            if args.rounds and rnd not in args.rounds:
                continue
            if ev["EventDate"] > pd.Timestamp.now():
                continue  # carrera aún no disputada
            for attempt in range(3):
                try:
                    info = extract_race(year, rnd, ev["EventName"])
                    log.info("%s %02d %s -> %s", year, rnd, ev["EventName"], info["status"])
                    report.append(info)
                    break
                except Exception as exc:  # red, datos ausentes, límites de la API
                    log.warning("Fallo %s %02d (intento %d): %s", year, rnd, attempt + 1, exc)
                    time.sleep(10 * (attempt + 1))
            else:
                report.append({"year": year, "round": rnd, "gp": ev["EventName"], "status": "error"})

    out = RAW_FASTF1 / "extraction_report.json"
    previous = json.loads(out.read_text()) if out.exists() else []
    out.write_text(json.dumps(previous + report, indent=2, ensure_ascii=False))
    ok = sum(r["status"] == "ok" for r in report)
    log.info("Terminado: %d carreras nuevas, informe en %s", ok, out)


if __name__ == "__main__":
    main()
