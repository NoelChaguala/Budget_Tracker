# Budget Tracker

A Flask-based personal finance web app supporting personal and household budgets, recurring transactions, category management, and monthly reporting.

---

## Features

### Accounts & Scope
- User registration and login via Flask-Login
- Personal finances scoped to the individual user
- Household finances — create or join a household, share budgets and transactions with members

### Categories
- System categories predefined in `config.py`
- Personal categories owned by a user
- Household categories shared across all household members
- Optional parent/child hierarchy with roll-up budget tracking (child spend counts toward parent budget)

### Transactions
- Record income and expenses with category assignment
- Assign transactions to personal or household scope
- Edit and delete transactions from the dashboard

### Budgets
- Monthly spending limits per category
- Personal or household scoped
- Progress tracking with visual indicators (safe / warning / danger)
- Edit budgets inline from the dashboard or from the budgets page

### Recurring Transactions
- Define repeating income/expense rules (daily, weekly, monthly, yearly)
- Automatic transaction generation via `sync_recurring.py`
- Pause, resume, or delete recurring rules
- 30-day preview of upcoming recurring transactions

### Dashboard & Reports
- Live spending summary with savings rate and health indicator
- Budget progress bars per category
- Recent transaction list
- Household scope toggle — switch between personal and household views

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Web framework | Flask + Jinja2 |
| Database | SQLite via Flask-SQLAlchemy |
| Auth | Flask-Login |
| Forms | Flask-WTF |
| Frontend | HTMX (partial page updates), vanilla JS |
| Tests | pytest |

---

## Quickstart

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python run.py
```

Open `http://127.0.0.1:5000` in your browser.

---

## Configuration

Core settings are in `app/__init__.py`:

| Setting | Default | Notes |
|---|---|---|
| `SECRET_KEY` | hardcoded default | **Replace before deploying** |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///...` | Change to Postgres/MySQL for production |

System categories are defined in `config.py` under `ALLOWED_CATEGORIES`.

---

## Database & Dev Scripts

These scripts are for local development only — do not run against production data.

| Script | What it does |
|---|---|
| `python recreate_db.py` | Drops and recreates all tables |
| `python seed.py` | Loads `seed_data.json`, drops and recreates tables |
| `python sync_recurring.py` | Generates any outstanding recurring transactions up to today |
| `python update_budget_schema.py` | One-off budget schema migration helper |
| `python update_recurring_schema.py` | One-off recurring schema migration helper |

---

## Tests

```bash
pytest
```

---

## Project Structure

```
Budget_Tracker/
├── app/
│   ├── __init__.py          # App factory, config
│   ├── models.py            # SQLAlchemy models
│   ├── main/                # Main blueprint (routes, utils)
│   ├── templates/           # Jinja2 templates
│   │   └── partials/        # HTMX partial templates
│   └── static/              # CSS, JS assets
├── instance/                # Runtime data (SQLite DB lives here)
├── tests/                   # pytest test suite
├── config.py                # System categories and app config constants
├── seed.py                  # Dev seed script
├── recreate_db.py           # Dev DB reset script
├── sync_recurring.py        # Recurring transaction generator
└── run.py                   # App entry point
```

---

## Additional Docs

- `BUDGET_IMPLEMENTATION_GUIDE.md` — design decisions and architecture notes
- `BUDGET_IMPLEMENTATION_SUMMARY.md` — implementation summary

---

## Deployment Notes

Before deploying to production:

1. Set a strong `SECRET_KEY` — never use the default.
2. Switch `SQLALCHEMY_DATABASE_URI` to a production database (Postgres recommended).
3. Run behind a WSGI server (Gunicorn or uWSGI) with a reverse proxy (Nginx).
4. Set `DEBUG = False`.