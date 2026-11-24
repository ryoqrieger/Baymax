# Baymax

A mental-health check-in platform for universities, and honestly it slaps. Students take a 26-question wellbeing check once a semester, an SVM model tells them where they're at, an LLM explains it in actual human words, and the right people on campus get what they need to help. No sticky notes, no cursed spreadsheets, no "we'll circle back next term."

Named after the huggable healthcare robot, because mental-health tools should feel like a friend, not a form from the registrar. No cap.

Built with Django, raw psycopg2, Neon Postgres, scikit-learn, Groq, and Vercel.

---

## The vibe check (what it actually does)

Universities have a real problem: tons of students are struggling, almost none of them say it out loud, and the people who could help only find out when it's already a full-blown crisis. Baymax flips the script.

1. A student answers 26 questions, one at a time, in a chat-style flow. No walls of text.
2. A trained SVM reads the answers and lands on one of three statuses: **Stable**, **Challenged**, or **Critical**.
3. An LLM writes a short, kind explanation of what that status means, so the student isn't just staring at a scary label.
4. The system recommends a counselor who fits, and the student decides whether to book. Nothing is forced on them.
5. Campus leadership sees the big picture (anonymous, aggregated) and gets an alert when something is off, like a spike in critical cases in one department.
6. At the end of the term, IT closes the semester, the numbers get archived, and everyone starts fresh.

One platform, four kinds of people, each with their own front door.

---

## The four roles

Every role has its own login page and its own portal. Nobody wanders into a portal that isn't theirs, and the server checks it on every single request, not just at login. No sneaking in through the back door.

| Role | Login | What they get |
|---|---|---|
| Student | `/login/` | Take the assessment, see their status and AI explanation, request a counselor, browse and RSVP to wellbeing events, view their profile |
| Professional | `/professional/login/` | An appointment inbox with new-request badges, a detail page per student, accept / decline / release, and campus wellbeing stats |
| Authority | `/authority/login/` | Campus-wide dashboard, per-semester stats and trends, AI-written alerts they can dismiss, and full event management |
| Admin IT | `/admin/login/` | User management, creating staff accounts, deactivating people, monitoring appointments and events, and running the semester transition |

Only the student page has Google sign-in and self-registration. Staff accounts are created by an admin, and the new person sets their own password through a one-time emailed link.

---

## Student side

**The assessment.** 26 questions across three well-known clinical scales:

- PSS-10 for perceived stress (10 questions)
- GAD-7 for anxiety (7 questions)
- PHQ-9 for depression (9 questions)

One question per page, and you can't skip ahead. Answers sit in the session until question 26, then get written to the database in one shot. One assessment per student per semester, enforced by the database itself with a unique constraint, not just by hoping the UI behaves.

**The result.** The SVM predicts the status. On top of that the app computes plain-language levels for each scale (like "moderate stress", "mild anxiety") using the standard clinical score bands, and shows the top areas of concern. The LLM turns all that into a short description written for a student, not a clinician.

**Getting help.** The help page recommends a professional based on the student's result, then the student chooses to request an appointment. The recommendation is a suggestion. The student always makes the final call.

**Events.** Authorities post events (workshops, meetups, wellness sessions) and students RSVP. RSVP counts are tracked per event.

---

## Professional side

Professionals get an inbox, not a firehose.

- New requests show up with a badge until the professional actually opens them
- Accept a request and pick a time, decline it, or release the student when the relationship is done
- Accepting runs behind an advisory lock plus a 60-minute conflict check, so two requests can never land on the same hour (double-booking is not the vibe)
- A stats page shows the semester overview, with a picker to look back at past semesters
- Everything is paginated, and a messed-up `?page=` value just falls back safely instead of crashing

---

## Authority side

Authorities see the forest, never the trees. No names, no individual answers, just aggregates. Privacy is the whole point.

- **Semester overview:** how many students are Stable, Challenged, and Critical, the at-risk percentage, the most common symptoms, and a breakdown by department
- **Trends:** how this semester compares to the last
- **AI alerts:** generated automatically when authorities open the stats page. Three kinds:
  - **Critical surge:** critical share jumped more than 40 percent versus last semester
  - **Symptom spike:** the same top symptom showing up again as last semester's
  - **Department at risk:** a department with more than 60 percent of students at risk
- **Privacy guardrails on alerts:** campus-level alerts need at least 5 respondents, department-level ones need at least 3, so a tiny group can never be singled out
- **Alerts are deduped** per semester, type, and department, so refreshing the page doesn't spam anyone
- **Events:** create, edit, and delete wellbeing events that students then see

---

## Admin IT side

The admins keep the whole thing running. Low-key the most important role.

- Search, deactivate, and reactivate users. Deactivation is enforced on every request, so a locked-out account is kicked out of its live session immediately, not at the next login
- A last-admin guard so nobody can accidentally deactivate the final admin and lock everyone out
- Create professional, authority, and admin accounts. The new person gets an email with a signed, single-use link (valid 3 days) to set their own password. Admins never see or type anyone's password
- Resend a link if it expired
- Monitor all appointments and all events across campus
- **Semester transition:** the big red button, more on that below

---

## The AI layer

All the AI lives in one tidy corner of the codebase, on purpose. It's not allowed to be messy.

- **Model:** `openai/gpt-oss-20b` through Groq, called with the OpenAI-compatible SDK, low reasoning effort, temperature 0.50
- **One door:** every LLM call in the whole app goes through a single method, `chat_with_strategy()`. No view or agent talks to Groq directly
- **No identity leaks:** only the status, three level words, and a few symptom phrases are sent out. Never a name, email, or student ID
- **Never breaks the page:** if Groq is down, slow, rate-limited, or returns garbage, the client returns `None` and the strategy supplies its own built-in fallback text. The student still gets a result. After the first failure in a run, the rest skip the AI and use fallback text, and the triage agent backs off for 5 minutes before asking again
- **Prompts live in strategies,** not in views or agents. Want to change how the AI sounds? One file

The AI is a bonus layer on top of the SVM's decision, never a dependency for the core flow. If it ghosts us, the app still works.

---

## The semester transition

Semesters end, and then it's reset season. IT runs the transition, and the **ResetAgent** handles it like a very responsible accountant.

1. Validates the target semester and checks the admin isn't acting on a stale page
2. Compiles the stats for the closing semester
3. Asks the LLM for a short summary (fallback text if the AI is down or there's no data)
4. Runs a single database transaction under a row lock that:
   - saves the archived stats
   - marks stats as compiled
   - declines pending appointments
   - completes accepted ones
   - flips the current semester
5. **Deletes nothing.** Old responses and history stay put

It's forward-only (no going back), and it's all-or-nothing: either the whole thing happens or none of it does. No half-finished chaos.

---

## Architecture

### Stack

| Layer | Tech |
|---|---|
| Web framework | Django (templates, URL routing, sessions, cache) |
| Database | PostgreSQL on Neon, accessed with raw psycopg2 and `RealDictCursor`. No ORM models |
| ML | scikit-learn SVM and scaler, loaded with joblib |
| LLM | Groq via the OpenAI SDK |
| Google sign-in | django-allauth, used only for the Google handshake |
| Static files | WhiteNoise with a hashed manifest |
| Hosting | Vercel (Python runtime, single function) |
| Email | Gmail SMTP |

### How a request flows

```
Browser
  |
  v
Vercel Function (Django WSGI)
  |
  +-- middleware: security, WhiteNoise, sessions, CSRF, messages
  |
  +-- urls.py -> view (split by role)
        |
        +-- @login_required_role(...)   checks role + account is still active
        +-- @rate_limit(...)            login / OTP brute-force protection
        |
        +-- core/utils.py     shared helpers (pagination, stats, tokens)
        +-- core/db.py        connect_db() -> raw SQL, always parameterised
        +-- core/ml.py        SVM prediction (singleton)
        +-- core/agents/      TriageAgent, AnalyticsAgent, ResetAgent
        |       |
        |       +-- LLMClient.chat_with_strategy()  ->  Groq
        |
        +-- template (extends base.html)
```

### Project layout

```
Baymax/
  schema/
    schema.sql              drops and rebuilds all 10 tables
    dummy_data.sql          80 demo users and sample data
  app/
    config/                 settings, root URLs, WSGI entry
    core/
      components.py         every constant: questions, bands, limits, labels
      utils.py              shared helpers
      db.py                 connect_db(), get_current_semester()
      email_utils.py        every email the app sends
      ml.py                 SVM loader and predict()
      adapters.py           bridges Google sign-in into the custom session
      agents/
        llm_client.py       Singleton + Adapter to Groq
        strategies.py       one Strategy per kind of AI call + Factory
        triage_agent.py     result description + professional recommendation
        analytics_agent.py  alert detection and generation
        reset_agent.py      semester transition
      views/
        auth.py  student.py  professional.py  authority.py  admin.py
      management/commands/  create_admin, check_llm
      tests/                126 tests, including a rule-enforcing audit
    ml_artifacts/           trained svm.pkl and scaler.pkl
    static/                 CSS and JS
    templates/              one folder per role, plus partials and emails
```

### Database

Ten tables, regular Postgres, zero drama:

| Table | What it holds |
|---|---|
| `users` | Everyone: role, name, email, password hash, active flag |
| `students` | Student ID and department, linked to a user |
| `professionals` | Specialization, linked to a user |
| `questionnaire_responses` | The 26 answers, final status, AI description. Unique per student per semester |
| `appointments` | Student, professional, status (pending / accepted / declined / completed), time |
| `events` | Title, date, time, venue, RSVP count, who created it |
| `event_rsvps` | Which student RSVPed to which event. Unique pair |
| `semester_schedule` | The calendar, which semester is current, and whether stats are compiled |
| `semester_stats` | Archived per-semester totals and the AI summary |
| `analytics_alerts` | Generated alerts for authorities |

Sessions and the rate-limit cache also live in Postgres, so the whole thing runs on a single database. No Redis, no extra services, no stress.

### Design patterns, and where they show up

| Pattern | Where | Why |
|---|---|---|
| Singleton | `LLMClient`, the ML model loader | One HTTP client and one loaded model per process, created lazily so imports stay cheap |
| Adapter | `LLMClient` over Groq | Swap AI providers by editing one file |
| Strategy | `LLMStrategy` and its subclasses | Each AI task owns its prompt, token budget, cleanup, and fallback |
| Factory | `AlertStrategyFactory` | Builds the right alert strategy from an alert type name |
| Decorator | `login_required_role`, `rate_limit` | Access control and throttling without repeating code in every view |

### Security and safety

- **Auth is custom and session-based.** allauth only does the Google handshake, and an adapter converts it into the same session keys everything else uses
- **Role checks on every request,** plus an is-the-account-still-active check, so deactivation bites immediately
- **Parameterised SQL only.** Every query uses placeholders. There's an automated audit that fails the build if any view builds SQL from user input
- **Rate limiting** on logins and OTP attempts, stored in the database cache
- **Registration OTP:** 6-digit email code, hashed in the session, valid 10 minutes, 5 wrong tries max, resend every 5 minutes
- **Passwords** validated with Django's validators and stored as PBKDF2 hashes
- **Password-set links** are signed, expire in 3 days, and carry a fingerprint of the current password hash, so using one kills it
- **Production cookies** are Secure, and the proxy header is honored so HTTPS detection works behind Vercel
- **No secrets in code.** `settings.py` has zero hardcoded values and zero fallbacks. Everything comes from environment variables, and the app refuses to start if one is missing
- **Custom 403, 404, 500, and CSRF-failure pages** that match the rest of the site

### Rules the codebase enforces on itself

These aren't just "best practices" collecting dust in a doc. A test suite scans the source and fails if anyone breaks them:

- Zero inline styles and zero `<style>` blocks in templates
- Every template extends `base.html`
- No catch-all `views.py`, views are split by role
- No LLM call outside `chat_with_strategy()`
- No unparameterised SQL
- `core/db.py` stays tiny, email stays in `email_utils.py`, constants stay in `components.py`
- Every decorator uses `functools.wraps`

We proved the audit works by deliberately planting violations and watching the tests catch every single one. Trust, but verify.

---

## Design

The interface is calm, rounded, and soft-colored, because nobody wants a stressful UI on a wellbeing app. It's one design system in plain CSS files (variables, base, layout, components, forms, tables, dashboard, status, chatbot), no framework, no inline styling. It works on phones, respects reduced-motion settings, has screen-reader labels, and every page reuses the same building blocks so it all looks consistent.

---

## Testing

126 automated tests cover the ML wrapper, LLM client and strategies, all three agents, user management, events, shared utilities, and the hardening audit. The LLM is faked in tests, so they run fast and never need an API key or internet. Zero flaky vibes.

---

## Heads up

Real talk: Baymax is a student project and a screening and support tool, not a medical device. It doesn't diagnose anyone, and the AI text is there to explain and encourage, not to replace a real counselor. If someone is in danger, they need a human and emergency services, not a web app.