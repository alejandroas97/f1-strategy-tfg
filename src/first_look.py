"""Primer análisis exploratorio de una carrera extraída con FastF1.

Genera en outputs/:
  <año>_<ronda>_estrategias.png   stints por piloto coloreados por compuesto
  <año>_<ronda>_degradacion.png   tiempo por vuelta vs. vida del neumático
  <año>_<ronda>_resumen.txt       cifras básicas de calidad del dato

Uso:
  python src/first_look.py --year 2023 --round 1
"""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import OUTPUTS, RAW_FASTF1

COLORS = {"SOFT": "#DA291C", "MEDIUM": "#FFD12E", "HARD": "#CFCFCF",
          "INTERMEDIATE": "#43B02A", "WET": "#0067AD"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--round", type=int, required=True)
    a = p.parse_args()

    folder = next((RAW_FASTF1 / str(a.year)).glob(f"{a.round:02d}_*"), None)
    if folder is None:
        raise SystemExit("Carrera no extraída. Ejecuta antes extract_fastf1.py.")
    laps = pd.read_parquet(folder / "laps.parquet")
    tag = f"{a.year}_{a.round:02d}"

    # 1) Estrategias: un stint = una barra horizontal
    stints = (laps.groupby(["Driver", "Stint", "Compound"])["LapNumber"]
                  .agg(["min", "max"]).reset_index())
    order = laps.groupby("Driver")["Position"].last().sort_values().index
    fig, ax = plt.subplots(figsize=(10, 7))
    for i, drv in enumerate(order):
        for _, s in stints[stints["Driver"] == drv].iterrows():
            ax.barh(i, s["max"] - s["min"] + 1, left=s["min"], color=COLORS.get(s["Compound"], "grey"),
                    edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(order)), order)
    ax.invert_yaxis()
    ax.set_xlabel("Vuelta")
    ax.set_title(f"Estrategias de neumáticos – {folder.name.replace('_', ' ')} {a.year}")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
    ax.legend(handles, COLORS.keys(), loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=5, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(OUTPUTS / f"{tag}_estrategias.png", dpi=150)

    # 2) Degradación: solo vueltas fiables (sin SC/VSC, sin in/out laps)
    clean = laps[(laps["IsAccurate"]) & laps["Compound"].isin(["SOFT", "MEDIUM", "HARD"])]
    clean = clean[clean["LapTime"] < clean["LapTime"].median() * 1.07]
    fig, ax = plt.subplots(figsize=(9, 5))
    for comp, g in clean.groupby("Compound"):
        ax.scatter(g["TyreLife"], g["LapTime"], s=8, alpha=0.4, color=COLORS[comp], label=comp,
                   edgecolors="black", linewidths=0.2)
        trend = g.groupby("TyreLife")["LapTime"].median().rolling(3, min_periods=1).mean()
        ax.plot(trend.index, trend.values, color=COLORS[comp], linewidth=2.5)
    ax.set_xlabel("Vida del neumático (vueltas) — sin corregir por combustible")
    ax.set_ylabel("Tiempo por vuelta (s)")
    ax.set_title(f"Tiempo por vuelta frente a vida del neumático – {a.year} ronda {a.round}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUTS / f"{tag}_degradacion.png", dpi=150)

    # 3) Resumen de calidad del dato
    summary = [
        f"Carrera: {folder.name} {a.year}",
        f"Vueltas totales: {len(laps)}",
        f"Pilotos: {laps['Driver'].nunique()}",
        f"Vueltas fiables (IsAccurate): {laps['IsAccurate'].mean():.1%}",
        f"Vueltas sin tiempo: {laps['LapTime'].isna().mean():.1%}",
        f"Compuestos usados: {', '.join(sorted(laps['Compound'].dropna().unique()))}",
        f"Paradas en boxes: {int(laps['PitInTime'].notna().sum())}",
        f"Vueltas con SC/VSC: {int(laps['TrackStatus'].astype(str).str.contains('[4-7]').sum())}",
    ]
    (OUTPUTS / f"{tag}_resumen.txt").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    print(f"\nGráficos guardados en {OUTPUTS}")


if __name__ == "__main__":
    main()
