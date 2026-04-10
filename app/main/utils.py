from datetime import datetime

from sqlalchemy import func

from ..models import Budget, Category, HouseholdMembership, Transaction, db


def get_budget_report(user_id=None, household_id=None):
    """Calculate budget report with spent amounts for current month."""
    now = datetime.now()

    if household_id:
        budgets = Budget.query.filter_by(household_id=household_id).all()
    else:
        budgets = Budget.query.filter_by(user_id=user_id, household_id=None).all()

    report = []
    for budget in budgets:
        spent_query = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.category_id == budget.category_id,
            func.extract("month", Transaction.date) == now.month,
            func.extract("year", Transaction.date) == now.year,
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
