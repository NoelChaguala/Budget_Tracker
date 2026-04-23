from datetime import date, timedelta

from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import bp
from .utils import get_budget_report
from ..models import Budget, Category, Household, HouseholdMembership, Transaction, db


@bp.route("/")
@login_required
def index():
    return redirect(url_for("main.personal_dashboard"))


def _build_dashboard_context(household=None):
    is_household = household is not None
    household_id = household.household_id if household else None

    allowed_category_names = current_app.config.get("ALLOWED_CATEGORIES", [])
    system_categories = []
    if allowed_category_names:
        system_categories = (
            Category.query.filter(
                Category.user_id.is_(None),
                Category.household_id.is_(None),
                Category.name.in_(allowed_category_names),
            )
            .order_by(Category.name)
            .all()
        )

    if is_household:
        transactions = (
            Transaction.query.filter_by(household_id=household_id).order_by(Transaction.date.desc()).limit(12).all()
        )
        budgets = Budget.query.filter_by(household_id=household_id).order_by(Budget.month.desc()).limit(10).all()
        categories = Category.query.filter_by(household_id=household_id).order_by(Category.name).all()
        transaction_categories = sorted(
            {c.category_id: c for c in [*system_categories, *categories]}.values(),
            key=lambda cat: cat.name.lower(),
        )
        budget_report = get_budget_report(household_id=household_id)
        member_count = HouseholdMembership.query.filter_by(household_id=household_id).count()
    else:
        transactions = (
            Transaction.query.filter_by(user_id=current_user.id, household_id=None)
            .order_by(Transaction.date.desc())
            .limit(12)
            .all()
        )
        budgets = (
            Budget.query.filter_by(user_id=current_user.id, household_id=None).order_by(Budget.month.desc()).limit(10).all()
        )
        categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
        transaction_categories = sorted(
            {c.category_id: c for c in [*system_categories, *categories]}.values(),
            key=lambda cat: cat.name.lower(),
        )
        budget_report = get_budget_report(user_id=current_user.id, household_id=None)
        member_count = 1

    today = date.today()
    start_of_month = today.replace(day=1)

    income_query = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.type == "income",
        Transaction.date >= start_of_month,
        Transaction.date <= today,
    )
    expense_query = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.type == "expense",
        Transaction.date >= start_of_month,
        Transaction.date <= today,
    )

    if is_household:
        income_query = income_query.filter(Transaction.household_id == household_id)
        expense_query = expense_query.filter(Transaction.household_id == household_id)
    else:
        income_query = income_query.filter(
            Transaction.user_id == current_user.id,
            Transaction.household_id.is_(None),
        )
        expense_query = expense_query.filter(
            Transaction.user_id == current_user.id,
            Transaction.household_id.is_(None),
        )

    month_income = float(income_query.scalar() or 0)
    month_expenses = float(expense_query.scalar() or 0)

    available_to_spend = month_income - month_expenses
    savings_rate = ((available_to_spend / month_income) * 100) if month_income > 0 else 0

    overspends = [b for b in budget_report if b["remaining"] < 0]
    largest_overspend = min(overspends, key=lambda b: b["remaining"]) if overspends else None

    health_state = "good"
    if available_to_spend < 0 or largest_overspend:
        health_state = "bad"
    elif savings_rate < 10:
        health_state = "warning"

    # Show the top budgets by highest usage to reduce cognitive load.
    budget_items = sorted(budget_report, key=lambda row: row["percent"], reverse=True)[:6]

    next_month = today.replace(day=28) + timedelta(days=4)
    month_last_day = (next_month - timedelta(days=next_month.day)).day
    days_remaining = max(month_last_day - today.day, 0)

    last_used_category_id = transactions[0].category_id if transactions and transactions[0].category_id else None

    return {
        "date": date,
        "today": today,
        "is_household": is_household,
        "household": household,
        "household_id": household_id,
        "member_count": member_count,
        "transactions": transactions,
        "budgets": budgets,
        "categories": categories,
        "transaction_categories": transaction_categories,
        "budget_items": budget_items,
        "days_remaining": days_remaining,
        "month_income": month_income,
        "month_expenses": month_expenses,
        "available_to_spend": available_to_spend,
        "savings_rate": savings_rate,
        "largest_overspend": largest_overspend,
        "health_state": health_state,
        "last_used_category_id": last_used_category_id,
    }


@bp.route("/personal")
@login_required
def personal_dashboard():
    context = _build_dashboard_context()
    return render_template("personal.html", **context)


@bp.route("/household/<int:household_id>")
@login_required
def household_dashboard(household_id):
    household = Household.query.get(household_id)
    if not household or not current_user.is_member_of(household):
        abort(404)

    context = _build_dashboard_context(household=household)
    return render_template("household.html", **context)


@bp.route("/dashboard/content")
@login_required
def dashboard_content():
    household_id = request.args.get("household_id", type=int)
    household = None
    if household_id:
        household = Household.query.get(household_id)
        if not household or not current_user.is_member_of(household):
            abort(404)

    context = _build_dashboard_context(household=household)
    return render_template("partials/dashboard_content.html", **context)


@bp.route("/settings")
@login_required
def settings():
    personal_categories = (
        Category.query.filter((Category.user_id == current_user.id) | (Category.is_system == True))
        .order_by(Category.name)
        .all()
    )

    household_categories = {}
    for h in current_user.households:
        household_categories[h.household_id] = (
            Category.query.filter(
                (Category.household_id == h.household_id) | (Category.is_system == True)
            )
            .order_by(Category.name)
            .all()
        )

    return render_template(
        "settings.html",
        personal_categories=personal_categories,
        household_categories=household_categories,
    )


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html")
