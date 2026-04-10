from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from . import bp
from ..models import Budget, Category, HouseholdMembership, db


@bp.route("/budget/create", methods=["GET", "POST"])
@login_required
def create_budget():
    if request.method == "POST":
        category_id = request.form.get("category_id")
        limit = request.form.get("amount_limit")
        description = request.form.get("description", "").strip()
        scope = request.form.get("scope", "personal")
        month_str = request.form.get("month")

        try:
            limit = float(limit)
            if limit <= 0:
                raise ValueError()
        except Exception:
            flash("Please enter a valid budget limit greater than 0.", "danger")
            return redirect(url_for("main.create_budget"))

        try:
            category_id = int(category_id)
        except Exception:
            flash("Invalid category selected.", "danger")
            return redirect(url_for("main.create_budget"))

        category = Category.query.get(category_id)
        if not category:
            flash("Category does not exist.", "danger")
            return redirect(url_for("main.create_budget"))

        if category.parent_id is not None:
            flash("Budgets can only be created for top-level categories.", "warning")
            return redirect(url_for("main.create_budget"))

        try:
            month = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
        except Exception:
            flash("Invalid month format.", "danger")
            return redirect(url_for("main.create_budget"))

        household_id = None
        user_id = None

        if scope == "household":
            membership = HouseholdMembership.query.filter_by(user_id=current_user.id).first()
            if not membership:
                flash("You must belong to a household to create a household budget.", "danger")
                return redirect(url_for("main.create_budget"))
            household_id = membership.household_id
        else:
            user_id = current_user.id

        existing_budget = Budget.query.filter_by(
            category_id=category_id,
            month=month,
            user_id=user_id,
            household_id=household_id,
        ).first()

        if existing_budget:
            existing_budget.limit_amount = limit
            existing_budget.description = description
            db.session.commit()
            flash("Budget updated successfully!", "success")
        else:
            new_budget = Budget(
                category_id=category_id,
                limit_amount=limit,
                month=month,
                description=description,
                user_id=user_id,
                household_id=household_id,
            )
            db.session.add(new_budget)
            db.session.commit()
            flash("Budget created successfully!", "success")

        if scope == "household":
            return redirect(url_for("main.household_dashboard", household_id=household_id))
        return redirect(url_for("main.personal_dashboard"))

    categories = Category.query.filter(
        Category.parent_id.is_(None),
        or_(Category.is_system == True, Category.user_id == current_user.id),
    ).order_by(Category.name).all()

    membership = HouseholdMembership.query.filter_by(user_id=current_user.id).first()

    return render_template(
        "create_budget.html",
        categories=categories,
        has_household=(membership is not None),
        now=datetime.now(),
    )
