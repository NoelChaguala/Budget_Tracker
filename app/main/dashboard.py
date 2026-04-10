from flask import abort, redirect, render_template, url_for
from flask_login import current_user, login_required

from . import bp
from .utils import get_budget_report
from ..models import Budget, Category, Household, Transaction


@bp.route("/")
@login_required
def index():
    return redirect(url_for("main.personal_dashboard"))


@bp.route("/personal")
@login_required
def personal_dashboard():
    transactions = (
        Transaction.query.filter_by(user_id=current_user.id, household_id=None)
        .order_by(Transaction.date.desc())
        .limit(20)
        .all()
    )
    budgets = (
        Budget.query.filter_by(user_id=current_user.id, household_id=None)
        .order_by(Budget.month.desc())
        .limit(10)
        .all()
    )
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    budget_report = get_budget_report(user_id=current_user.id, household_id=None)

    return render_template(
        "personal.html",
        transactions=transactions,
        budgets=budgets,
        categories=categories,
        budget_report=budget_report,
    )


@bp.route("/household/<int:household_id>")
@login_required
def household_dashboard(household_id):
    household = Household.query.get(household_id)
    if not household or not current_user.is_member_of(household):
        abort(404)

    transactions = (
        Transaction.query.filter_by(household_id=household.household_id)
        .order_by(Transaction.date.desc())
        .limit(20)
        .all()
    )
    budgets = (
        Budget.query.filter_by(household_id=household.household_id)
        .order_by(Budget.month.desc())
        .limit(10)
        .all()
    )
    categories = Category.query.filter_by(household_id=household.household_id).order_by(Category.name).all()
    budget_report = get_budget_report(household_id=household.household_id)

    return render_template(
        "household.html",
        household=household,
        transactions=transactions,
        budgets=budgets,
        categories=categories,
        budget_report=budget_report,
    )


@bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html")
