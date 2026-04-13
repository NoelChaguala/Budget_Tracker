from calendar import monthrange
from datetime import date, datetime

from sqlalchemy import func

from ..models import Budget, Category, HouseholdMembership, Transaction, db


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
