# Budget Implementation Guide

## Overview

Budgets in Budget Tracker are monthly spending limits scoped to either a personal user or a household. Budget progress is calculated dynamically at request time by summing transactions against the budget's category and scope — there is no cached or stored "spent" value.

---

## Data Model

```python
class Budget(db.Model):
    budget_id     = db.Column(db.Integer, primary_key=True)
    month         = db.Column(db.Date, nullable=False)        # Always stored as first day of month
    limit_amount  = db.Column(db.Float, nullable=False)
    description   = db.Column(db.String(255), nullable=True)
    category_id   = db.Column(db.ForeignKey("category.category_id"), nullable=False)
    user_id       = db.Column(db.ForeignKey("user.id"), nullable=True)
    household_id  = db.Column(db.ForeignKey("household.household_id"), nullable=True)
```

### Scope rules

Exactly one of `user_id` or `household_id` must be set per budget row. `budget.is_personal()` returns `True` when `household_id` is `None`.

| Scope | `user_id` | `household_id` |
|---|---|---|
| Personal | set | NULL |
| Household | NULL | set |

---

## Core Utility — `get_budget_report()`

Located in `app/main/utils.py`. Called by dashboard and budget page routes.

```python
get_budget_report(user_id=None, household_id=None, start_date=None, end_date=None)
```

Returns a list of dicts, one per budget:

```python
{
    "budget_id":   int,
    "category":    str,       # category name
    "category_id": int,
    "month":       date,
    "limit":       float,
    "spent":       float,     # sum of matching expense transactions
    "remaining":   float,     # limit - spent (negative = over budget)
    "percent":     float,     # capped at 100
    "description": str | None,
}
```

If no date range is supplied, it defaults to the current calendar month.

Spent amounts are calculated by summing `Transaction.amount` where:
- `Transaction.category_id == budget.category_id`
- `Transaction.date` falls within the date range
- Scope matches (personal: `household_id IS NULL`, household: `household_id = X`)

> **Note:** Roll-up budgeting (child category spend counting toward a parent budget) is handled separately via `get_budget_status()` in `utils.py`, which uses `Category.get_all_subcategory_ids()`.

---

## Routes

All budget routes live in `app/main/routes.py` (or your main blueprint file).

### `GET /budgets`
Renders `budgets.html` with:
- `personal_report` — result of `get_budget_report(user_id=...)`
- `household_reports` — list of `{ household, report }` dicts, one per household the user belongs to

### `GET /budgets/add` + `POST /budgets/add`
Renders `add_budget.html`. On POST:
1. Validates scope, category, limit, and month
2. Verifies the user owns or is a member of the target household
3. Verifies the category belongs to the correct scope
4. Creates and commits a `Budget` record
5. Redirects to `/budgets`

### `GET /budget/edit/<id>` + `POST /budget/edit/<id>`
Renders `edit_budget.html`. Editable fields: `limit_amount`, `month`, `description`. Category is fixed after creation.

On POST, redirects to the URL in the `next` form field if present, otherwise to `/budgets`. This allows the dashboard modal to redirect back to the dashboard after saving.

### `POST /budgets/<id>/delete`
Verifies ownership/membership, deletes the budget, redirects to `/budgets`.

---

## Templates

| Template | Purpose |
|---|---|
| `budgets.html` | Budget hub — lists personal and household budgets with progress bars, edit and delete actions |
| `add_budget.html` | Full-page form to create a new budget |
| `edit_budget.html` | Full-page form to edit limit, month, and description |
| `partials/dashboard_content.html` | Includes budget progress rows on the dashboard and the budget edit modal |

### Dashboard integration

The dashboard budget section renders progress bars for the active scope (personal or household). Each row includes an **Edit** button that opens a modal (`#budget-modal`) pre-populated via `data-*` attributes:

```html
<button type="button"
  data-open-budget-modal
  data-category="{{ item.category }}"
  data-month="{{ item.month.strftime('%Y-%m') }}"
  data-limit="{{ item.limit }}"
  data-description="{{ item.description or '' }}"
  data-action="{{ url_for('main.edit_budget', budget_id=item.budget_id) }}">
  Edit
</button>
```

The modal posts directly to the `edit_budget` route with a hidden `next` field set to `window.location.pathname`, so the user is returned to the dashboard after saving rather than the budgets page.

---

## Category Scoping

Categories are scoped the same way budgets are:

| Category type | `user_id` | `household_id` | `is_system` |
|---|---|---|---|
| System | NULL | NULL | True |
| Personal | set | NULL | False |
| Household | NULL | set | False |

When building the category dropdown for budget creation, the route queries:
- For personal budgets: `user_id == current_user.id OR is_system == True`
- For household budgets: `household_id == X OR is_system == True`

This prevents a user from assigning a household category to a personal budget and vice versa.

---

## Progress Bar States

| Class | Threshold | Meaning |
|---|---|---|
| `safe` | < 75% spent | On track |
| `warning` | 75–99% spent | Approaching limit |
| `danger` | ≥ 100% spent | Over budget |

Applied to `.progress-fill` in the template. The CSS animates the fill width via the `--target` CSS variable.

---

## Adding a New Budget Programmatically

```python
from datetime import date
from app.models import Budget, db

budget = Budget(
    user_id=user.id,          # or None for household
    household_id=None,         # or household_id for household
    category_id=category.category_id,
    limit_amount=500.00,
    month=date(2025, 1, 1),   # always first day of month
    description="Grocery allowance",
)
db.session.add(budget)
db.session.commit()
```

---

## Troubleshooting

**Budget progress not updating after a transaction**
- Confirm the transaction has a `category_id` set.
- Confirm the transaction `date` falls within the budget's month.
- Confirm the transaction `type` is `"expense"` — income transactions are not subtracted from budgets.
- Confirm the transaction scope matches the budget scope (personal vs. household).

**Category not appearing in the add budget dropdown**
- Personal budgets: category must have `user_id == current_user.id` or `is_system == True`.
- Household budgets: category must have `household_id` matching the target household or `is_system == True`.
- If a category was just created inline, confirm the `create_category_inline` endpoint saved it with the correct scope.

**`/budget/edit/<id>` redirecting to the wrong page**
- The route reads a `next` field from the POST body. Ensure the form or modal includes `<input type="hidden" name="next" value="...">`. If absent, it falls back to `/budgets`.