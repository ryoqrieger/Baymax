-- ════════════════════════════════════════════════════════════════════
-- Baymax — DEMO DATA refresh   (development / demo databases ONLY)
-- Run AFTER schema.sql, migrations_v2.sql and dummy_data.sql.
-- Never run this on a database holding real student data.
--
-- dummy_data.sql was written for Spring 2026 with events in Mar–May 2026,
-- so today every event is in the past and the current semester is wrong.
-- This script:
--   • archives Spring 2026 (stats row built from the real seeded answers)
--   • makes Fall 2026 the current semester
--   • moves every event into the near future
--   • fills the new demo columns (student semester, specialisations)
-- ════════════════════════════════════════════════════════════════════

-- 1. Archive Spring 2026 so history and the Symptom-Spike alert have data.
INSERT INTO semester_stats (semester, total, stable, challenged, critical, at_risk_pct, llm_summary)
SELECT 'Spring 2026',
       COUNT(*),
       COUNT(*) FILTER (WHERE final_status = 'Stable'),
       COUNT(*) FILTER (WHERE final_status = 'Challenged'),
       COUNT(*) FILTER (WHERE final_status = 'Critical'),
       ROUND(100.0 * COUNT(*) FILTER (WHERE final_status <> 'Stable') / NULLIF(COUNT(*), 0), 2),
       NULL
FROM questionnaire_responses
WHERE semester = 'Spring 2026'
ON CONFLICT (semester) DO NOTHING;

-- 2. Current semester = Fall 2026 (Sep 1 – Dec 31, 2026).
UPDATE semester_schedule SET stats_compiled = TRUE WHERE semester = 'Spring 2026';
UPDATE semester_schedule SET is_current = (semester = 'Fall 2026');

-- 3. Events: spread over the next ~7 weeks, then 95 RSVPs stay valid.
UPDATE events
SET date = CURRENT_DATE + (2 + (id * 7) % 45);

UPDATE events e
SET rsvp_count = (SELECT COUNT(*) FROM event_rsvps r WHERE r.event_id = e.id);

-- 4. Student academic semester (1–8) where still empty.
UPDATE students SET semester = 1 + (id % 8) WHERE semester IS NULL;

-- 5. Professional profiles (re-created after dummy_data.sql truncates users).
INSERT INTO professionals (user_id)
SELECT id FROM users WHERE role = 'professional'
ON CONFLICT (user_id) DO NOTHING;

UPDATE professionals p
SET specialization = (ARRAY[
        'Clinical Psychology', 'Counseling Psychology', 'Anxiety & Stress',
        'Depression & Mood', 'Academic Counseling', 'Psychiatry',
        'Cognitive Behavioural Therapy', 'Student Wellbeing',
        'Trauma & Resilience', 'General Counseling'
    ])[1 + (p.id % 10)];