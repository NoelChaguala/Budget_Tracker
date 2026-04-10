from calendar import monthrange
from datetime import date
from sqlalchemy import and_, func
from .models import Budget, Transaction, Category

def get_budget_status(budget_id):
    """
    Calculate budget status including roll-up of child categories.

    Args:
        budget_id: ID of the budget to calculate status for

    Returns:
        Dictionary with budget status including roll-up calculations
    """
    # Get the budget and its category
    budget = Budget.query.get(budget_id)
    if not budget:
        return None

    # Get the category and all its subcategory IDs (including itself)
    category = Category.query.get(budget.category_id)
    if not category:
        return None

    # Get all category IDs for roll-up (parent + all children)
    category_ids = category.get_all_subcategory_ids()

    # Calculate current month boundaries
    today = date.today()
    first_day = date(today.year, today.month, 1)
    last_day = date(today.year, today.month, monthrange(today.year, today.month)[1])

    # Build query to sum transactions for the budget scope
    query = Transaction.query.with_entities(
        func.sum(Transaction.amount).label('total_spent')
    ).filter(
        Transaction.category_id.in_(category_ids),
        Transaction.date >= first_day,
        Transaction.date <= last_day
    )

    # Add scope filtering
    if budget.is_personal():
        query = query.filter(Transaction.household_id.is_(None))
    else:
        query = query.filter(Transaction.household_id == budget.household_id)

    # Execute query
    result = query.first()
    spent = result.total_spent if result and result.total_spent else 0.0

    # Calculate remaining and percentage
    remaining = budget.limit_amount - spent
    percentage = round((spent / budget.limit_amount * 100), 2) if budget.limit_amount > 0 else 0.0

    return {
        "budget_limit": budget.limit_amount,
        "spent": spent,
        "remaining": remaining,
        "percentage": percentage
    }