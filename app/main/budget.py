from datetime import date, datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from . import bp
from .utils import get_budget_report
from ..models import Budget, Category, Household, HouseholdMembership, db


@bp.route("/budgets")
@login_required
def view_budgets():
    user_id = current_user.id
    today = date.today()

    personal_report = get_budget_report(user_id=user_id)

    household_reports = []
    for household in current_user.households:
        report = get_budget_report(household_id=household.household_id)
        if report:
            household_reports.append(
                {
                    "household": household,
                    "report": report,
                }
            )

    return render_template(
        "budgets.html",
        personal_report=personal_report,
        household_reports=household_reports,
        today=today,
    )


@bp.route("/budgets/add", methods=["GET", "POST"])
@login_required
def add_budget():
    user_id = current_user.id
    today = date.today()
    default_month = today.strftime("%Y-%m")

    personal_categories = Category.query.filter(
        (Category.user_id == user_id) | (Category.is_system == True)
    ).order_by(Category.name).all()

    household_categories = {}
    for h in current_user.households:
        household_categories[h.household_id] = (
            Category.query.filter(
                (Category.household_id == h.household_id) | (Category.is_system == True)
            )
            .order_by(Category.name)
            .all()
        )

    if request.method == "POST":
        scope = request.form.get("scope")
        category_id = request.form.get("category_id")
        limit_amount = request.form.get("limit_amount")
        month_str = request.form.get("month")
        description = request.form.get("description", "").strip()

        errors = []
        month_date = None

        if not category_id:
            errors.append("Please select a category.")
        else:
            try:
                category_id_int = int(category_id)
            except ValueError:
                errors.append("Invalid category.")
                category_id_int = None

        if not limit_amount:
            errors.append("Please enter a limit amount.")
        else:
            try:
                limit_amount = float(limit_amount)
                if limit_amount <= 0:
                    errors.append("Limit must be greater than zero.")
            except ValueError:
                errors.append("Invalid limit amount.")

        if not month_str:
            errors.append("Please select a month.")
        else:
            try:
                month_date = datetime.strptime(month_str + "-01", "%Y-%m-%d").date()
            except ValueError:
                errors.append("Invalid month.")

        household_id = None
        if scope == "personal":
            pass
        elif scope:
            try:
                household_id = int(scope)
            except ValueError:
                errors.append("Invalid scope.")
                household_id = None
        else:
            errors.append("Please select a scope.")

        if not errors and category_id_int is not None:
            if scope == "personal":
                allowed = {c.category_id for c in personal_categories}
                if category_id_int not in allowed:
                    errors.append("That category is not available for personal budgets.")
            elif household_id is not None:
                household = Household.query.get(household_id)
                if not household or not current_user.is_member_of(household):
                    errors.append("You cannot create a budget for that household.")
                else:
                    allowed = {c.category_id for c in household_categories.get(household_id, [])}
                    if category_id_int not in allowed:
                        errors.append("That category is not available for this household.")

        if errors:
            return render_template(
                "add_budget.html",
                errors=errors,
                personal_categories=personal_categories,
                household_categories=household_categories,
                households=current_user.households,
                default_month=month_str or default_month,
            )

        if scope == "personal":
            budget = Budget(
                user_id=user_id,
                household_id=None,
                category_id=category_id_int,
                limit_amount=limit_amount,
                month=month_date,
                description=description or None,
            )
        else:
            budget = Budget(
                user_id=None,
                household_id=household_id,
                category_id=category_id_int,
                limit_amount=limit_amount,
                month=month_date,
                description=description or None,
            )

        db.session.add(budget)
        db.session.commit()
        return redirect(url_for("main.view_budgets"))

    return render_template(
        "add_budget.html",
        errors=[],
        personal_categories=personal_categories,
        household_categories=household_categories,
        households=current_user.households,
        default_month=default_month,
    )


@bp.route("/budgets/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)

    if budget.is_personal():
        if budget.user_id != current_user.id:
            abort(403)
    else:
        household = Household.query.get(budget.household_id)
        if not household or not current_user.is_member_of(household):
            abort(403)

    db.session.delete(budget)
    db.session.commit()
    return redirect(url_for("main.view_budgets"))


@bp.route("/budget/edit/<int:budget_id>", methods=["GET", "POST"])
@login_required
def edit_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)

    if budget.user_id:
        if budget.user_id != current_user.id:
            abort(403)
    elif budget.household_id:
        if not current_user.is_member_of(budget.household):
            abort(403)
    else:
        abort(403)

    if request.method == "POST":
        limit = request.form.get("amount_limit")
        description = request.form.get("description", "").strip()
        month_str = request.form.get("month")

        try:
            limit = float(limit)
            if limit <= 0:
                raise ValueError()
        except Exception:
            flash("Please enter a valid budget limit greater than 0.", "danger")
            return redirect(url_for("main.edit_budget", budget_id=budget_id))

        try:
            month = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
        except Exception:
            flash("Invalid month format.", "danger")
            return redirect(url_for("main.edit_budget", budget_id=budget_id))

        budget.limit_amount = limit
        budget.description = description
        budget.month = month
        db.session.commit()
        flash("Budget updated successfully!", "success")

        if budget.household_id:
            return redirect(url_for("main.household_dashboard", household_id=budget.household_id))
        return redirect(url_for("main.personal_dashboard"))

    categories = Category.query.filter(
        Category.parent_id.is_(None),
        or_(Category.is_system == True, Category.user_id == current_user.id),
    ).order_by(Category.name).all()

    membership = HouseholdMembership.query.filter_by(user_id=current_user.id).first()

    return render_template(
        "edit_budget.html",
        budget=budget,
        categories=categories,
        has_household=(membership is not None),
    )
