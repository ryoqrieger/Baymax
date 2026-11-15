-- ════════════════════════════════════════════════════════════════════
-- Baymax — database schema (complete, final)
--
-- ONE file builds everything. It first DROPS the ten Baymax tables, so
-- running it gives you a clean, empty database every time.
--   !! This deletes all Baymax data. Never run it on a live database. !!
--
-- Order:  1) schema.sql   2) dummy_data.sql  (demo data, optional)
-- Django's own tables (sessions, cache, ...) are NOT touched here; they
-- come from:  python manage.py migrate   and   python manage.py createcachetable
-- ════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS analytics_alerts        CASCADE;
DROP TABLE IF EXISTS event_rsvps             CASCADE;
DROP TABLE IF EXISTS events                  CASCADE;
DROP TABLE IF EXISTS appointments            CASCADE;
DROP TABLE IF EXISTS questionnaire_responses CASCADE;
DROP TABLE IF EXISTS semester_stats          CASCADE;
DROP TABLE IF EXISTS semester_schedule       CASCADE;
DROP TABLE IF EXISTS professionals           CASCADE;
DROP TABLE IF EXISTS students                CASCADE;
DROP TABLE IF EXISTS users                   CASCADE;


-- ── Users (all four roles) ──────────────────────────────────────────
CREATE TABLE users (
    id         SERIAL PRIMARY KEY,
    role       VARCHAR(20) NOT NULL
                   CHECK (role IN ('student','professional','authority','admin_it')),
    full_name  VARCHAR(120) NOT NULL,
    email      VARCHAR(254) UNIQUE NOT NULL,
    password   VARCHAR(256) NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,      -- Admin IT can deactivate an account
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Student details ─────────────────────────────────────────────────
CREATE TABLE students (
    id         SERIAL PRIMARY KEY,
    user_id    INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_id VARCHAR(30) NOT NULL,
    department VARCHAR(10) NOT NULL CHECK (department IN ('CSE','EEE','ENG','ECO','BBA')),
    semester   SMALLINT CHECK (semester IS NULL OR semester BETWEEN 1 AND 12)
               -- academic semester (1-12); optional, not asked at registration
);

-- ── Professional details (shown on the student Help page) ───────────
CREATE TABLE professionals (
    id             SERIAL PRIMARY KEY,
    user_id        INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialization VARCHAR(100) NOT NULL DEFAULT 'General Counseling'
);

-- ── Semester calendar and archived statistics ───────────────────────
CREATE TABLE semester_schedule (
    id                   SERIAL PRIMARY KEY,
    semester             VARCHAR(20) UNIQUE NOT NULL,    -- e.g. 'Fall 2026'
    start_date           DATE NOT NULL,
    end_date             DATE NOT NULL,
    is_current           BOOLEAN DEFAULT FALSE,
    stats_compiled       BOOLEAN DEFAULT FALSE,
    notification_pending BOOLEAN DEFAULT FALSE
);

CREATE TABLE semester_stats (
    id          SERIAL PRIMARY KEY,
    semester    VARCHAR(20) UNIQUE NOT NULL,
    total       INT DEFAULT 0,
    stable      INT DEFAULT 0,
    challenged  INT DEFAULT 0,
    critical    INT DEFAULT 0,
    at_risk_pct DECIMAL(5,2) DEFAULT 0,
    llm_summary TEXT,
    compiled_at TIMESTAMP DEFAULT NOW()
);

-- ── The 26-question questionnaire (PSS-10, GAD-7, PHQ-9) ────────────
CREATE TABLE questionnaire_responses (
    id              SERIAL PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    semester        VARCHAR(20) NOT NULL,
    pss1  SMALLINT, pss2  SMALLINT, pss3  SMALLINT, pss4  SMALLINT,
    pss5  SMALLINT, pss6  SMALLINT, pss7  SMALLINT, pss8  SMALLINT,
    pss9  SMALLINT, pss10 SMALLINT,
    gad1  SMALLINT, gad2  SMALLINT, gad3  SMALLINT, gad4  SMALLINT,
    gad5  SMALLINT, gad6  SMALLINT, gad7  SMALLINT,
    phq1  SMALLINT, phq2  SMALLINT, phq3  SMALLINT, phq4  SMALLINT,
    phq5  SMALLINT, phq6  SMALLINT, phq7  SMALLINT, phq8  SMALLINT,
    phq9  SMALLINT,
    final_status       VARCHAR(20) CHECK (final_status IN ('Stable','Challenged','Critical')),
    status_description TEXT,
    submitted_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (student_id, semester)
);

-- ── Appointment requests ────────────────────────────────────────────
CREATE TABLE appointments (
    id              SERIAL PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    professional_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) DEFAULT 'pending'
                        CHECK (status IN ('pending','accepted','declined','completed')),
    scheduled_at    TIMESTAMP,
    is_new          BOOLEAN NOT NULL DEFAULT TRUE,   -- TRUE until the professional opens it
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ── Events and RSVPs ────────────────────────────────────────────────
CREATE TABLE events (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    date        DATE NOT NULL,
    time        TIME NOT NULL,
    venue       VARCHAR(200) NOT NULL,
    description TEXT,
    rsvp_count  INT DEFAULT 0,
    created_by  INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE event_rsvps (
    id         SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id   INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    rsvped_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (student_id, event_id)
);

-- ── Authority alerts ────────────────────────────────────────────────
CREATE TABLE analytics_alerts (
    id         SERIAL PRIMARY KEY,
    alert_type VARCHAR(30) NOT NULL
                   CHECK (alert_type IN ('critical_surge','symptom_spike','department_at_risk')),
    message    TEXT NOT NULL,
    semester   VARCHAR(20),
    department VARCHAR(10),
    dismissed  BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Indexes for the queries the portals run most ────────────────────
CREATE INDEX idx_responses_semester     ON questionnaire_responses (semester);
CREATE INDEX idx_appointments_prof_stat ON appointments (professional_id, status);
CREATE INDEX idx_appointments_student   ON appointments (student_id);
CREATE INDEX idx_events_date            ON events (date);
CREATE INDEX idx_alerts_semester        ON analytics_alerts (semester);