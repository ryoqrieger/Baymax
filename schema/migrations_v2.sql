-- ════════════════════════════════════════════════════════════════════
-- Baymax — schema additions (v2)
-- Run AFTER schema.sql. Structure only: safe to run more than once and
-- safe on a database that holds real data (no rows are deleted/changed
-- except the harmless back-fills noted below).
-- ════════════════════════════════════════════════════════════════════

-- 1. Deactivating a user (Admin IT, Sprint 6) needs a flag on users.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- 2. A student's academic semester (1–12), asked for at registration.
--    Not to be confused with semester_schedule.semester ("Fall 2026").
ALTER TABLE students
    ADD COLUMN IF NOT EXISTS semester SMALLINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'students_semester_range') THEN
        ALTER TABLE students
            ADD CONSTRAINT students_semester_range
            CHECK (semester IS NULL OR semester BETWEEN 1 AND 12);
    END IF;
END $$;

-- 3. Notification flag: TRUE while a professional has not yet seen a request.
--    The professional dashboard badge counts rows where is_new = TRUE;
--    opening the appointment sets it to FALSE (Sprint 4).
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS is_new BOOLEAN NOT NULL DEFAULT TRUE;

-- Back-fill: only still-pending requests can be "new".
UPDATE appointments SET is_new = FALSE WHERE status <> 'pending';

-- 4. Professional profile (shown on the student Help page).
CREATE TABLE IF NOT EXISTS professionals (
    id             SERIAL PRIMARY KEY,
    user_id        INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialization VARCHAR(100) NOT NULL DEFAULT 'General Counseling'
);

INSERT INTO professionals (user_id)
SELECT id FROM users WHERE role = 'professional'
ON CONFLICT (user_id) DO NOTHING;

-- 5. Indexes for the queries the portals run most.
CREATE INDEX IF NOT EXISTS idx_responses_semester     ON questionnaire_responses (semester);
CREATE INDEX IF NOT EXISTS idx_appointments_prof_stat ON appointments (professional_id, status);
CREATE INDEX IF NOT EXISTS idx_appointments_student   ON appointments (student_id);
CREATE INDEX IF NOT EXISTS idx_events_date            ON events (date);
CREATE INDEX IF NOT EXISTS idx_alerts_semester        ON analytics_alerts (semester);

-- Note: the rate-limit / OTP cache table is NOT created here. Django makes
-- it with:  python manage.py createcachetable