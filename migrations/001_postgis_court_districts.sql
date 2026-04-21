-- Миграция: схема court_districts для PostGIS
-- Запуск: psql -U postgres -d courts -f 001_postgis_court_districts.sql

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS court_districts (
    id SERIAL PRIMARY KEY,
    court_name VARCHAR(255),
    court_code VARCHAR(50),
    district_type VARCHAR(20) CHECK (district_type IN ('world', 'district', 'regional')),
    boundary GEOMETRY(Polygon, 4326),
    valid_from DATE,
    valid_to DATE,
    exceptions JSONB,
    address TEXT,
    phone TEXT,
    region TEXT,
    section_num INTEGER
);

CREATE INDEX IF NOT EXISTS idx_court_districts_boundary ON court_districts USING GIST(boundary);
CREATE INDEX IF NOT EXISTS idx_court_districts_region ON court_districts(region);
CREATE INDEX IF NOT EXISTS idx_court_districts_type ON court_districts(district_type);

-- Таблица кэша геокодирования (опционально)
CREATE TABLE IF NOT EXISTS geocode_cache (
    id SERIAL PRIMARY KEY,
    address_hash VARCHAR(64) UNIQUE NOT NULL,
    address_original TEXT,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_geocode_cache_hash ON geocode_cache(address_hash);
