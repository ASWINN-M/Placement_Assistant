# Placement Assistant

Automates VIT-AP CDC placement mail handling:

1. Students join once (Neo ID, reg no, college email, degree, branch)
2. A worker reads CDC Gmail, extracts drive details with Groq
3. Filters by **shortlist Neo ID / reg no** and **eligible branch**
4. Creates Google Calendar events and invites registered students

Supabase stores student profiles. GitHub Actions can run the worker on a schedule so your PC does not need to stay on for mail → calendar.

> **Note:** GitHub Actions runs the **worker**, not a public always-on join website. The join form still needs a host (your PC, a VPS, etc.) when classmates register.

---

## Project layout

```text
Backend/
  join_app.py          # One-time join form + OTP API
  gmail_services.py    # CDC mail → calendar worker
  calendar_service.py  # Google Calendar helpers
  llm_extractor.py     # Groq structured extraction
  eligibility.py       # Branch / degree matching
  db.py                # SQLAlchemy + Supabase Postgres
  templates/join.html  # Join UI
requirements.txt
docker-compose.yml     # Optional local Postgres
.github/workflows/     # Scheduled worker
```

---

## What is secret (never commit)

These are gitignored:

- `Backend/.env`
- `Backend/credentials.json`
- `Backend/token.json`
- `Backend/calendar_token.json`
- `Backend/processed_messages.json`
- `Backend/attachments/`

---

## Local setup

### 1. Python deps

```powershell
cd C:\placement_automation
# with your venv active
uv pip install -r requirements.txt
```

### 2. Environment

Copy `.env.example` → `Backend/.env` and set:

```env
GROQ_API_KEY=...
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@aws-0-....pooler.supabase.com:6543/postgres
```

If the DB password contains `@`, encode it as `%40`.

### 3. Google OAuth (once on your PC)

Place Google Desktop OAuth client as `Backend/credentials.json`, then:

```powershell
cd Backend
python -c "from gmail_services import authenticate_gmail; authenticate_gmail()"
python -c "from calendar_service import authenticate_calendar; authenticate_calendar()"
```

This creates `token.json` (Gmail read+send) and `calendar_token.json`.

### 4. Join form

```powershell
cd Backend
uvicorn join_app:app --reload --port 8000
```

Open http://127.0.0.1:8000

### 5. Worker (manual)

```powershell
cd Backend
python gmail_services.py
```

---

## Filtering rules

| Email type | Who gets a calendar invite |
|---|---|
| Excel shortlist | Registered students whose **Neo ID or reg no** is on the sheet, and branch matches if criteria exist |
| IDs in email body | Same ID match + branch filter |
| Open registration / drive | Registered students whose **degree/branch** match eligibility in the mail |
| Congrats with no date | Skipped (nothing to schedule) |

---

## GitHub Actions worker (PC can be off)

Workflow: `.github/workflows/placement-worker.yml`

- Runs every **30 minutes**
- Also runnable manually (**Actions → Placement worker → Run workflow**)

### Required repository secrets

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq key |
| `DATABASE_URL` | Full Supabase URI (password with `@` → `%40`) |
| `GMAIL_CREDENTIALS_JSON` | Full contents of `credentials.json` |
| `GMAIL_TOKEN_JSON` | Full contents of `token.json` |
| `CALENDAR_TOKEN_JSON` | Full contents of `calendar_token.json` |

After the first push, add those secrets, then run the workflow once manually to verify.

### Limits

- Actions has monthly minutes on the free plan; 30‑minute cron is usually fine.
- OAuth tokens must stay valid (refresh token in `token.json` / `calendar_token.json`).
- Join form is **not** hosted by Actions.

---

## Optional Docker (local Postgres)

```powershell
docker compose up -d
```

Prefer Supabase for a cloud DB that survives PC sleep.

---

## License

Private student project — use only with accounts and data you are authorized to access.
