# Sistema de apoyo a la decisión para la estrategia de carrera en F1 (TFG)

TFG del Grado en Ciencia de Datos Aplicada (UOC) — Alejandro Alemán Sosa.

Sistema que modela la degradación de neumáticos y simula carreras mediante Monte Carlo
para comparar estrategias de paradas frente a un rival reactivo.

## Estado

| Fase | Estado |
| --- | --- |
| T1.1.1 Extracción y cacheo (OpenF1 2023-2025: 70 carreras) | Completada |
| T1.1.1 Extracción FastF1 2018-2022 (requiere F1 TV Access) | Pendiente de decisión |
| T1.1.2 Limpieza y carga en PostgreSQL | En curso: base de datos y esquema creados |
| T1.2 Modelo de tiempo por vuelta | Pendiente |

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Base de datos PostgreSQL (requiere Docker)
cp .env.example .env               # y cambia la contraseña
docker compose up -d               # crea el esquema de db/schema.sql la primera vez
```

## Uso

```bash
# 1. Corpus de OpenF1 2023-2025 (≈25 min por el límite de peticiones; reanudable)
python src/extract_openf1.py --seasons 2024 --rounds 1   # prueba con una carrera
python src/extract_openf1.py                             # corpus completo

# 2. FastF1 2018-2025 (desde el 15/10/2026 requiere una suscripción F1 TV Access)
python -m fastf1 auth f1tv --authenticate    # inicio de sesión con la cuenta de F1
python src/extract_fastf1.py --seasons 2024 --rounds 1
python src/extract_fastf1.py                 # corpus completo 2018-2025

# 3. Primer análisis exploratorio de una carrera de FastF1 -> outputs/
python src/first_look.py --year 2024 --round 1
```

## Estructura

```
src/
  config.py           rutas, temporadas y límites de las APIs
  extract_openf1.py   extracción de carreras de OpenF1 -> data/raw/openf1/<año>/<ronda>_<gp>/
  extract_fastf1.py   extracción de carreras con caché local -> data/raw/fastf1/
  explore_openf1.py   prueba rápida de la API de OpenF1 con una carrera
  first_look.py       EDA inicial: estrategias, degradación y calidad del dato
db/
  schema.sql          esquema relacional (schema f1): circuitos, carreras, pilotos,
                      vueltas, stints, paradas, dirección de carrera, neutralizaciones, meteo
docker-compose.yml    PostgreSQL 17 en el puerto 5433
data/                 (no versionado) datos extraídos
cache/                (no versionado) caché de FastF1
outputs/              (no versionado) gráficos
```

## Datos y licencias

- **OpenF1** (Open-F1 Project, 2024): fuente principal. Datos históricos desde 2023, licencia
  CC BY-NC-SA 4.0, uso no comercial; límite gratuito de 3 peticiones/s y 30 peticiones/min.
- **FastF1** (Oehrly, 2024): timing por vuelta desde 2018 a partir del Live Timing oficial.
  Desde el 15/10/2026 la F1 exige una suscripción F1 TV Access para descargar ese archivo
  (FastF1 >= 3.9 incluye el inicio de sesión).

El repositorio publica solo código y documentación. Los datos no se redistribuyen
(Directiva 96/9/CE sobre bases de datos y términos de cada proveedor).

## Licencia del código

MIT (ver [LICENSE](LICENSE)).
