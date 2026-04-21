-- Система верификации границ судебных участков
-- verification_results, verification_history

CREATE TABLE IF NOT EXISTS verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    court_id VARCHAR(36) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    verification_date TIMESTAMPTZ DEFAULT NOW(),
    result JSONB,
    status VARCHAR(20) DEFAULT 'completed',
    duration_ms DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_results_court ON verification_results(court_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_date ON verification_results(verification_date);

CREATE TABLE IF NOT EXISTS verification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id VARCHAR(36) NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    change_description TEXT,
    change_date TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_history_result ON verification_history(result_id);
