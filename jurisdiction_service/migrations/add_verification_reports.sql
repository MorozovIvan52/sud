-- Таблица отчётов о верификации подсудности (краудсорсинг)
-- docs/jurisdiction_verification_sources.md
CREATE TABLE IF NOT EXISTS verification_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    reported_court VARCHAR(500) NOT NULL,
    suggested_court VARCHAR(500),
    comment TEXT,
    user_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_reports_status ON verification_reports(status);
CREATE INDEX IF NOT EXISTS idx_verification_reports_created ON verification_reports(created_at);
