from datetime import datetime

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .utils import get_or_create_system_categories, user_can_manage_transaction
from ..models import Category, Transaction, db


@bp.route("/transaction/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    allowed_category_names = current_app.config.get("ALLOWED_CATEGORIES", [])
    allowed_categories = get_or_create_system_categories(allowed_category_names)

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("Invalid amount.", "danger")
            return redirect(url_for("main.add_transaction"))

        description = request.form.get("description") or ""
        t_type = request.form.get("type")
        raw_household_id = request.form.get("household_id")
        household_id = int(raw_household_id) if (raw_household_id and raw_household_id.strip()) else None

        selected_category_id = request.form.get("category")
        if not selected_category_id:
            flash("Please select a category.", "danger")
            return redirect(url_for("main.add_transaction"))

        category = Category.query.get(int(selected_category_id))
        if not category:
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

        flash("Transaction added successfully!", "success")
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
