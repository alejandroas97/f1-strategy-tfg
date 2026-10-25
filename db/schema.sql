-- T1.1.2 - Esquema relacional del corpus (PostgreSQL 17)
--
-- Los Parquet de data/raw/ son la copia fiel de las APIs; estas tablas son la capa limpia
-- sobre la que trabajan el modelo de degradación (OE1.2), las distribuciones de Safety Car
-- (OE1.3) y la simulación. Unidades: tiempos en segundos, velocidades en km/h,
-- temperaturas en ºC. Claves naturales de OpenF1 (session_key, driver_number) para poder
-- trazar cada fila hasta su origen.
--
-- Se ejecuta automáticamente al crear el contenedor (docker-entrypoint-initdb.d).

CREATE SCHEMA IF NOT EXISTS f1;
SET search_path TO f1;

-- ---------------------------------------------------------------- Dimensiones

CREATE TABLE circuits (
    circuit_key     integer PRIMARY KEY,           -- OpenF1
    short_name      text    NOT NULL,              -- "Sakhir", "Monaco"...
    location        text,
    country_code    char(3),
    country_name    text,
    circuit_type    text CHECK (circuit_type IN ('Permanent', 'Temporary - Street', 'Temporary - Road'))
);

CREATE TABLE races (
    session_key     integer PRIMARY KEY,           -- OpenF1: sesión de carrera
    meeting_key     integer  NOT NULL,             -- OpenF1: fin de semana del GP
    year            smallint NOT NULL,
    round           smallint NOT NULL,
    gp_name         text     NOT NULL,             -- "Bahrain Grand Prix"
    circuit_key     integer  NOT NULL REFERENCES circuits,
    date_start      timestamptz NOT NULL,
    date_end        timestamptz,
    total_laps      smallint,                      -- vueltas del ganador
    split           text CHECK (split IN ('calibration', 'test')),  -- 2023-2024 / 2025
    UNIQUE (year, round)
);

-- Piloto y equipo por carrera: el dorsal y el equipo pueden cambiar entre temporadas
CREATE TABLE race_drivers (
    session_key     integer  REFERENCES races ON DELETE CASCADE,
    driver_number   smallint,
    acronym         char(3)  NOT NULL,             -- "VER": identificador estable entre años
    full_name       text     NOT NULL,
    team_name       text     NOT NULL,
    team_colour     char(6),
    PRIMARY KEY (session_key, driver_number)
);

-- ---------------------------------------------------------------- Hechos

CREATE TABLE results (
    session_key     integer,
    driver_number   smallint,
    position        smallint,                      -- NULL si no se clasifica
    laps_completed  smallint,
    points          real,
    status          text NOT NULL CHECK (status IN ('Finished', 'DNF', 'DNS', 'DSQ')),
    race_time_s     double precision,              -- solo para el ganador y los que acaban en la vuelta del líder
    gap_to_leader   text,                          -- "+12.345" o "+1 LAP"
    PRIMARY KEY (session_key, driver_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES race_drivers ON DELETE CASCADE
);

CREATE TABLE stints (
    session_key        integer,
    driver_number      smallint,
    stint_number       smallint,
    compound           text NOT NULL CHECK (compound IN ('SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN')),
    lap_start          smallint,
    lap_end            smallint,
    tyre_age_at_start  smallint NOT NULL,          -- vueltas previas del juego (usado en clasificación)
    PRIMARY KEY (session_key, driver_number, stint_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES race_drivers ON DELETE CASCADE,
    CHECK (lap_end >= lap_start)
);

CREATE TABLE laps (
    session_key       integer,
    driver_number     smallint,
    lap_number        smallint,
    date_start        timestamptz,
    lap_time_s        double precision,
    sector1_s         double precision,
    sector2_s         double precision,
    sector3_s         double precision,
    i1_speed          real,                        -- trampas de velocidad intermedias
    i2_speed          real,
    st_speed          real,                        -- speed trap
    is_pit_out_lap    boolean NOT NULL,
    -- Columnas derivadas en la limpieza (T1.1.2)
    is_pit_in_lap     boolean,                     -- de la tabla pit_stops
    stint_number      smallint,                    -- cruzando con stints
    compound          text,
    tyre_age          smallint,                    -- tyre_age_at_start + vueltas en el stint
    track_status      text CHECK (track_status IN ('GREEN', 'YELLOW', 'VSC', 'SC', 'RED')),
    is_clean          boolean,                     -- apta para el modelo de degradación (ver v_model_laps)
    PRIMARY KEY (session_key, driver_number, lap_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES race_drivers ON DELETE CASCADE
);

CREATE TABLE pit_stops (
    session_key       integer,
    driver_number     smallint,
    lap_number        smallint,
    date              timestamptz NOT NULL,
    lane_duration_s   double precision,            -- entrada a salida del pit lane
    stop_duration_s   double precision,            -- coche parado (solo desde mediados de 2024)
    PRIMARY KEY (session_key, driver_number, lap_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES race_drivers ON DELETE CASCADE
);

CREATE TABLE race_control (
    id              bigserial PRIMARY KEY,
    session_key     integer NOT NULL REFERENCES races ON DELETE CASCADE,
    date            timestamptz NOT NULL,
    lap_number      smallint,
    category        text NOT NULL,                 -- Flag, SafetyCar, Drs, CarEvent, Other...
    flag            text,
    scope           text,                          -- Track, Sector, Driver
    sector          smallint,
    driver_number   smallint,
    message         text NOT NULL
);

-- Periodos de neutralización derivados de race_control: base de OE1.3
CREATE TABLE neutralizations (
    session_key     integer  REFERENCES races ON DELETE CASCADE,
    seq             smallint,                      -- 1, 2... dentro de la carrera
    type            text     NOT NULL CHECK (type IN ('SC', 'VSC', 'RED')),
    lap_start       smallint NOT NULL,
    lap_end         smallint NOT NULL,
    date_start      timestamptz NOT NULL,
    date_end        timestamptz,
    PRIMARY KEY (session_key, seq),
    CHECK (lap_end >= lap_start)
);

CREATE TABLE weather (
    session_key        integer REFERENCES races ON DELETE CASCADE,
    date               timestamptz,
    air_temp_c         real,
    track_temp_c       real,
    humidity_pct       real,
    pressure_hpa       real,
    rainfall           boolean,
    wind_speed_ms      real,
    wind_direction_deg smallint,
    PRIMARY KEY (session_key, date)
);

CREATE INDEX ON laps (session_key, compound, tyre_age);
CREATE INDEX ON race_control (session_key, category);

-- ---------------------------------------------------------------- Vistas

-- Vueltas aptas para ajustar la degradación: neumáticos de seco, bandera verde,
-- sin entrar ni salir de boxes y sin la primera vuelta (salida)
CREATE VIEW v_model_laps AS
SELECT r.year, r.round, r.split, r.circuit_key, d.acronym, d.team_name, l.*
FROM laps l
JOIN races r USING (session_key)
JOIN race_drivers d USING (session_key, driver_number)
WHERE l.is_clean;

-- Número de Safety Car y VSC por carrera: insumo de las distribuciones por circuito
CREATE VIEW v_neutralizations_per_race AS
SELECT r.session_key, r.year, r.circuit_key,
       count(n.*) FILTER (WHERE n.type = 'SC')  AS n_sc,
       count(n.*) FILTER (WHERE n.type = 'VSC') AS n_vsc,
       count(n.*) FILTER (WHERE n.type = 'RED') AS n_red
FROM races r
LEFT JOIN neutralizations n USING (session_key)
GROUP BY r.session_key, r.year, r.circuit_key;
