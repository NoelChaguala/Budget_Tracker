import json
from datetime import datetime

from flask import current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .dashboard import _build_dashboard_context
from .utils import get_or_create_system_categories, user_can_manage_transaction
from ..models import Category, Household, Transaction, db


def _render_dashboard_for_hx(scope, household_id, message=None, level="danger"):
    scoped_household = None
    if scope == "household" and household_id:
        scoped_household = Household.query.get(household_id)
        if not scoped_household or not current_user.is_member_of(scoped_household):
            scoped_household = None
    context = _build_dashboard_context(household=scoped_household)
    html = render_template("partials/dashboard_content.html", **context)
    response = make_response(html)
    if message:
        response.headers["HX-Trigger"] = json.dumps(
            {"dashboard:transaction-added": {"message": message, "level": level}}
        )
    return response


@bp.route("/transaction/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    allowed_category_names = current_app.config.get("ALLOWED_CATEGORIES", [])
    allowed_categories = get_or_create_system_categories(allowed_category_names)

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            active_scope = request.form.get("active_scope", "personal")
            active_household_id = request.form.get("active_household_id", type=int)
            if request.headers.get("HX-Request") == "true":
                return _render_dashboard_for_hx(
                    active_scope,
                    active_household_id,
                    message="Invalid amount. Please try again.",
                )
            flash("Invalid amount.", "danger")
            return redirect(url_for("main.add_transaction"))

        description = request.form.get("description") or ""
        t_type = request.form.get("type")
        raw_household_id = request.form.get("household_id")
        household_id = int(raw_household_id) if (raw_household_id and raw_household_id.strip()) else None
        active_scope = request.form.get("active_scope", "personal")
        active_household_id = request.form.get("active_household_id", type=int)

        if household_id:
            target_household = Household.query.get(household_id)
            if not target_household or not current_user.is_member_of(target_household):
                if request.headers.get("HX-Request") == "true":
                    return _render_dashboard_for_hx(
                        active_scope,
                        active_household_id,
                        message="You cannot add transactions to that household.",
                    )
                flash("You cannot add transactions to that household.", "danger")
                return redirect(url_for("main.personal_dashboard"))

        selected_category_id = request.form.get("category")
        if not selected_category_id:
            if request.headers.get("HX-Request") == "true":
                return _render_dashboard_for_hx(
                    active_scope,
                    active_household_id,
                    message="Pick a category first.",
                )
            flash("Please select a category.", "danger")
            return redirect(url_for("main.add_transaction"))

        category = Category.query.get(int(selected_category_id))
        if not category:
            if request.headers.get("HX-Request") == "true":
                return _render_dashboard_for_hx(
                    active_scope,
                    active_household_id,
                    message="Invalid category selected.",
                )
            flash("Invalid category.", "danger")
            return redirect(url_for("main.add_transaction"))

        transaction = Transaction(
            amount=amount,
            description=description,
            type=t_type,
            user_id=current_user.id,
            household_id=household_id,
            category_id=category.category_id,
        )
        db.session.add(transaction)
        db.session.commit()

        toast_message = f"{'+' if t_type == 'income' else '-'}${amount:.2f} added"
        if category:
            toast_message += f" to {category.name}"

        if request.headers.get("HX-Request") == "true":
            response = _render_dashboard_for_hx(active_scope, active_household_id)
            response.headers["HX-Trigger"] = json.dumps(
                {"dashboard:transaction-added": {"message": toast_message, "level": "success"}}
            )
            return response

        flash("Transaction added successfully!", "success")
        if active_scope == "household" and active_household_id:
            return redirect(url_for("main.household_dashboard", household_id=active_household_id))
        return redirect(url_for("main.personal_dashboard"))

    return render_template("add_transaction.html", allowed_categories=allowed_categories)


@bp.route("/transaction/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if not user_can_manage_transaction(current_user.id, transaction):
        flash("You do not have permission to edit this transaction.", "danger")
        return redirect(url_for("main.personal_dashboard"))

    allowed_category_names = current_app.config.get("ALLOWED_CATEGORIES", [])
    categories = get_or_create_system_categories(allowed_category_names)

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("Invalid amount.", "danger")
            return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)

        description = request.form.get("description") or ""
        t_type = request.form.get("type")
        date_str = request.form.get("date")

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        except (ValueError, TypeError):
            flash("Invalid date format.", "danger")
            return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)

        transaction.amount = amount
        transaction.description = description
        transaction.type = t_type
        transaction.date = date_obj

        category_id = request.form.get("category_id")
        if category_id:
            try:
                transaction.category_id = int(category_id)
            except (ValueError, TypeError):
                flash("Invalid category.", "danger")
                return render_template(
                    "edit_transaction.html",
                    transaction=transaction,
                    allowed_categories=categories,
                )

        db.session.commit()
        flash("Transaction updated successfully!", "success")

        if transaction.household_id:
            return redirect(url_for("main.household_dashboard", household_id=transaction.household_id))
        return redirect(url_for("main.personal_dashboard"))

    return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)


@bp.route("/transaction/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if not user_can_manage_transaction(current_user.id, transaction):
        flash("You do not have permission to delete this transaction.", "danger")
        return redirect(url_for("main.personal_dashboard"))

    db.session.delete(transaction)
    db.session.commit()
    flash("Transaction deleted.", "info")

    if request.referrer:
        return redirect(request.referrer)
    if transaction.household_id:
        return redirect(url_for("main.household_dashboard", household_id=transaction.household_id))
    return redirect(url_for("main.personal_dashboard"))
