from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_

from ..models import Budget, Category, HouseholdMembership, RecurringTransaction, Transaction, db


def get_budget_report(user_id=None, household_id=None, start_date=None, end_date=None):
    """Calculate budget report with spent amounts within a date range."""
    today = date.today()

    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    if start_date is None and end_date is None:
        start_date = today.replace(day=1)
        end_date = today.replace(day=monthrange(today.year, today.month)[1])
    elif start_date is None and end_date is not None:
        start_date = end_date.replace(day=1)
    elif end_date is None and start_date is not None:
        end_date = start_date.replace(day=monthrange(start_date.year, start_date.month)[1])

    if household_id:
        budgets = Budget.query.filter_by(household_id=household_id).all()
    else:
        budgets = Budget.query.filter_by(user_id=user_id, household_id=None).all()

    report = []
    for budget in budgets:
        spent_query = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.category_id == budget.category_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )

        if household_id:
            spent_query = spent_query.filter(Transaction.household_id == household_id)
        else:
            spent_query = spent_query.filter(
                Transaction.user_id == user_id,
                Transaction.household_id.is_(None),
            )

        spent = spent_query.scalar() or 0

        report.append(
            {
                "budget_id": budget.budget_id,
                "category": budget.category.name,
                "category_id": budget.category_id,
                "month": budget.month,
                "limit": budget.limit_amount,
                "spent": spent,
                "remaining": budget.limit_amount - spent,
                "percent": min((spent / budget.limit_amount) * 100, 100)
                if budget.limit_amount > 0
                else 0,
                "description": budget.description,
            }
        )

    return report


def user_can_manage_transaction(user_id, transaction):
    """Return True when a user can edit/delete a transaction."""
    is_personal_owner = transaction.user_id == user_id and transaction.household_id is None

    if is_personal_owner:
        return True

    if transaction.household_id:
        membership = HouseholdMembership.query.filter_by(
            user_id=user_id,
            household_id=transaction.household_id,
        ).first()
        return membership is not None

    return False


def get_or_create_system_categories(category_names):
    categories = []
    for name in category_names:
        category = Category.query.filter_by(
            name=name,
            user_id=None,
            household_id=None,
        ).first()
        if not category:
            category = Category(name=name)
            db.session.add(category)
            db.session.flush()
        categories.append(category)

    return categories


def advance_month_preserve_end(start_date, months=1):
    year = start_date.year + ((start_date.month - 1 + months) // 12)
    month = ((start_date.month - 1 + months) % 12) + 1
    last_day = monthrange(year, month)[1]
    day = min(start_date.day, last_day)
    return date(year, month, day)


def advance_year_preserve_leap(start_date, years=1):
    target_year = start_date.year + years
    try:
        return date(target_year, start_date.month, start_date.day)
    except ValueError:
        # Handle Feb 29 on non-leap years by moving to Feb 28
        if start_date.month == 2 and start_date.day == 29:
            return date(target_year, 2, 28)
        raise


def get_next_recurring_date(current_date, frequency):
    if frequency == "daily":
        return current_date + timedelta(days=1)
    if frequency == "weekly":
        return current_date + timedelta(days=7)
    if frequency == "monthly":
        return advance_month_preserve_end(current_date, 1)
    if frequency == "yearly":
        return advance_year_preserve_leap(current_date, 1)
    raise ValueError(f"Unsupported frequency: {frequency}")


def get_recurring_template_scope(user_id):
    household_ids = [m.household_id for m in HouseholdMembership.query.filter_by(user_id=user_id).all()]
    if household_ids:
        return RecurringTransaction.query.filter(
            RecurringTransaction.is_active.is_(True),
            or_(
                RecurringTransaction.user_id == user_id,
                RecurringTransaction.household_id.in_(household_ids),
            ),
        )
    return RecurringTransaction.query.filter_by(is_active=True, user_id=user_id)


def get_recurring_preview(recurring_entries, days=30, base_date=None):
    base_date = base_date or date.today()
    preview_end = base_date + timedelta(days=days)
    projected = []

    for recurring in recurring_entries:
        candidate = recurring.last_generated_date or recurring.start_date
        if recurring.last_generated_date is not None:
            candidate = get_next_recurring_date(candidate, recurring.frequency)

        while candidate <= preview_end:
            if recurring.end_date is not None and candidate > recurring.end_date:
                break
            if candidate >= base_date:
                projected.append(
                    {
                        "amount": recurring.amount,
                        "type": recurring.type,
                        "date": candidate.isoformat(),
                        "description": recurring.description,
                        "category_id": recurring.category_id,
                        "category_name": recurring.category.name if recurring.category else "Uncategorized",
                        "household_id": recurring.household_id,
                        "user_id": recurring.user_id,
                        "recurring_id": recurring.id,
                        "frequency": recurring.frequency,
                    }
                )
            candidate = get_next_recurring_date(candidate, recurring.frequency)

    projected.sort(key=lambda item: item["date"])
    return projected


def compute_next_occurrence(recurring, base_date=None):
    base_date = base_date or date.today()
    if recurring.last_generated_date is not None:
        candidate = get_next_recurring_date(recurring.last_generated_date, recurring.frequency)
    else:
        candidate = recurring.start_date

    while True:
        if recurring.end_date is not None and candidate > recurring.end_date:
            return None
        if candidate >= base_date:
            return candidate
        candidate = get_next_recurring_date(candidate, recurring.frequency)


def sync_recurring(user_id=None):
    today = date.today()
    if user_id is not None:
        query = get_recurring_template_scope(user_id)
    else:
        query = RecurringTransaction.query.filter_by(is_active=True)

    created = []
    for recurring in query.order_by(RecurringTransaction.id).all():
        if recurring.end_date is not None and recurring.start_date > today:
            continue

        current_run_date = recurring.last_generated_date or recurring.start_date
        if recurring.last_generated_date is not None:
            current_run_date = get_next_recurring_date(current_run_date, recurring.frequency)

        while current_run_date <= today:
            if recurring.end_date is not None and current_run_date > recurring.end_date:
                break

            exists = (
                Transaction.query.filter_by(
                    recurring_id=recurring.id,
                    date=current_run_date,
                ).first()
                is not None
            )
            if not exists:
                transaction = Transaction(
                    amount=recurring.amount,
                    description=recurring.description,
                    type=recurring.type,
                    date=current_run_date,
                    user_id=recurring.user_id,
                    household_id=recurring.household_id,
                    category_id=recurring.category_id,
                    recurring_id=recurring.id,
                )
                db.session.add(transaction)
                created.append(
                    {
                        "recurring_id": recurring.id,
                        "date": current_run_date.isoformat(),
                        "amount": recurring.amount,
                    }
                )
            recurring.last_generated_date = current_run_date
            db.session.flush()
            current_run_date = get_next_recurring_date(current_run_date, recurring.frequency)

    if created:
        db.session.commit()
    return created
