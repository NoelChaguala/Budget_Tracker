import json
from datetime import datetime, date

from flask import current_app, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from . import bp
from .dashboard import _build_dashboard_context
from .utils import (
    compute_next_occurrence,
    get_or_create_system_categories,
    get_recurring_preview,
    get_recurring_template_scope,
    sync_recurring,
    user_can_manage_transaction,
)
from ..models import Category, Household, RecurringTransaction, Transaction, db


def _category_allowed_for_transaction(category, household_id):
    if category is None:
        return False
    if category.is_system and category.user_id is None and category.household_id is None:
        return True
    if household_id is None:
        return category.user_id == current_user.id and category.household_id is None
    return category.household_id == household_id


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


@bp.before_app_request
def ensure_recurring_synced():
    if not current_user.is_authenticated:
        return
    if request.endpoint in [
        "main.personal_dashboard",
        "main.household_dashboard",
        "main.dashboard_content",
        "main.recurring_page",
    ]:
        try:
            sync_recurring(current_user.id)
        except Exception:
            db.session.rollback()


@bp.route("/transaction/add", methods=["GET", "POST"])
@login_required
def add_transaction():
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
        if not category or not _category_allowed_for_transaction(category, household_id):
            if request.headers.get("HX-Request") == "true":
                return _render_dashboard_for_hx(
                    active_scope,
                    active_household_id,
                    message="Invalid category selected.",
                )
            flash("Invalid category.", "danger")
            return redirect(url_for("main.add_transaction"))

        date_str = request.form.get("date")
        try:
            transaction_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        except (TypeError, ValueError):
            if request.headers.get("HX-Request") == "true":
                return _render_dashboard_for_hx(
                    active_scope,
                    active_household_id,
                    message="Invalid date format.",
                )
            flash("Invalid date format.", "danger")
            return redirect(url_for("main.add_transaction"))

        make_recurring = request.form.get("make_recurring") == "on"
        recurring = None
        if make_recurring:
            frequency = request.form.get("frequency")
            if frequency not in {"daily", "weekly", "monthly", "yearly"}:
                if request.headers.get("HX-Request") == "true":
                    return _render_dashboard_for_hx(
                        active_scope,
                        active_household_id,
                        message="Please choose a valid recurring frequency.",
                    )
                flash("Invalid recurring frequency.", "danger")
                return redirect(url_for("main.add_transaction"))

            start_date_str = request.form.get("start_date")
            end_date_str = request.form.get("end_date")
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else transaction_date
            except (TypeError, ValueError):
                start_date = transaction_date
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None
            except (TypeError, ValueError):
                end_date = None

            if end_date is not None and end_date < start_date:
                if request.headers.get("HX-Request") == "true":
                    return _render_dashboard_for_hx(
                        active_scope,
                        active_household_id,
                        message="End date cannot be before start date.",
                    )
                flash("End date cannot be before start date.", "danger")
                return redirect(url_for("main.add_transaction"))

            recurring = RecurringTransaction(
                amount=amount,
                description=description,
                type=t_type,
                user_id=current_user.id,
                household_id=household_id,
                category_id=category.category_id,
                frequency=frequency,
                start_date=start_date,
                end_date=end_date,
                last_generated_date=None,
            )
            db.session.add(recurring)
            db.session.flush()

        transaction = Transaction(
            amount=amount,
            description=description,
            type=t_type,
            date=transaction_date,
            user_id=current_user.id,
            household_id=household_id,
            category_id=category.category_id,
            recurring_id=recurring.id if recurring else None,
        )
        db.session.add(transaction)

        if recurring:
            if transaction_date < recurring.start_date:
                db.session.rollback()
                if request.headers.get("HX-Request") == "true":
                    return _render_dashboard_for_hx(
                        active_scope,
                        active_household_id,
                        message="Transaction date cannot come before recurring start date.",
                    )
                flash("Transaction date cannot come before recurring start date.", "danger")
                return redirect(url_for("main.add_transaction"))
            if transaction_date <= date.today():
                recurring.last_generated_date = transaction_date

        db.session.commit()

        toast_message = f"{'+' if t_type == 'income' else '-'}${amount:.2f} added"
        if category:
            toast_message += f" to {category.name}"
        if recurring:
            toast_message += " as recurring"

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
        "add_transaction.html",
        personal_categories=personal_categories,
        household_categories=household_categories,
        date=date,
    )


@bp.route("/recurring", methods=["GET", "POST"])
@login_required
def recurring_page():
    household_ids = [m.household_id for m in current_user.memberships]
    if household_ids:
        rules = (
            RecurringTransaction.query.filter(
                or_(
                    RecurringTransaction.user_id == current_user.id,
                    RecurringTransaction.household_id.in_(household_ids),
                )
            )
            .order_by(RecurringTransaction.is_active.desc(), RecurringTransaction.start_date)
            .all()
        )
    else:
        rules = (
            RecurringTransaction.query.filter_by(user_id=current_user.id)
            .order_by(RecurringTransaction.is_active.desc(), RecurringTransaction.start_date)
            .all()
        )

    preview = get_recurring_preview([rule for rule in rules if rule.is_active], days=30)
    next_occurrences = {rule.id: compute_next_occurrence(rule) for rule in rules}

    transaction_categories = Category.query.filter(
        or_(
            Category.user_id == current_user.id,
            Category.is_system == True
        )
    ).order_by(Category.name).all()

    if request.method == "POST":
        data = request.form if request.form else request.get_json(force=True, silent=True) or {}
        amount = float(data.get("amount", 0)) if data.get("amount") else 0
        category_id = data.get("category_id")
        if not category_id:
            return jsonify({"error": "Category required."}), 400
        category = Category.query.get(int(category_id))
        if not category:
            return jsonify({"error": "Invalid category."}), 400

        frequency = data.get("frequency")
        if frequency not in {"daily", "weekly", "monthly", "yearly"}:
            return jsonify({"error": "Invalid frequency."}), 400

        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid start date."}), 400
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid end date."}), 400
        if end_date and end_date < start_date:
            return jsonify({"error": "End date must follow start date."}), 400

        recurring = RecurringTransaction(
            amount=amount,
            description=data.get("description", ""),
            type=data.get("type", "expense"),
            user_id=current_user.id,
            household_id=int(data["household_id"]) if data.get("household_id") else None,
            category_id=int(category_id),
            frequency=frequency,
            start_date=start_date,
            end_date=end_date,
            last_generated_date=None,
        )
        db.session.add(recurring)
        db.session.commit()

        return jsonify({"recurring_id": recurring.id, "status": "created"}), 201

    return render_template("recurring.html", 
        recurring_rules=rules, 
        preview=preview, 
        next_occurrences=next_occurrences,
        transaction_categories=transaction_categories,
        date=date,
        today=date.today()
    )


@bp.route("/recurring/<int:recurring_id>/toggle", methods=["POST"])
@login_required
def toggle_recurring(recurring_id):
    household_ids = [m.household_id for m in current_user.memberships]
    if household_ids:
        query = RecurringTransaction.query.filter(
            RecurringTransaction.id == recurring_id,
            or_(
                RecurringTransaction.user_id == current_user.id,
                RecurringTransaction.household_id.in_(household_ids),
            ),
        )
    else:
        query = RecurringTransaction.query.filter_by(id=recurring_id, user_id=current_user.id)

    recurring = query.first_or_404()
    recurring.is_active = not recurring.is_active
    db.session.commit()
    return redirect(request.referrer or url_for('main.recurring_page'))


@bp.route("/recurring/<int:recurring_id>", methods=["DELETE", "POST"])
@login_required
def delete_recurring(recurring_id):
    delete_future = request.args.get("delete_future", "false").lower() == "true"
    household_ids = [m.household_id for m in current_user.memberships]
    if household_ids:
        query = RecurringTransaction.query.filter(
            RecurringTransaction.id == recurring_id,
            or_(
                RecurringTransaction.user_id == current_user.id,
                RecurringTransaction.household_id.in_(household_ids),
            ),
        )
    else:
        query = RecurringTransaction.query.filter_by(id=recurring_id, user_id=current_user.id)
    recurring = query.first_or_404()

    if delete_future:
        Transaction.query.filter(
            Transaction.recurring_id == recurring.id,
            Transaction.date >= date.today(),
        ).delete()

    db.session.delete(recurring)
    db.session.commit()
    return redirect(request.referrer or url_for('main.recurring_page'))


@bp.route("/api/recurring/preview")
@login_required
def recurring_preview():
    days = request.args.get("days", type=int, default=30)
    household_ids = [m.household_id for m in current_user.memberships]
    if household_ids:
        query = RecurringTransaction.query.filter(
            RecurringTransaction.is_active.is_(True),
            or_(
                RecurringTransaction.user_id == current_user.id,
                RecurringTransaction.household_id.in_(household_ids),
            ),
        )
    else:
        query = RecurringTransaction.query.filter_by(is_active=True, user_id=current_user.id)

    preview = get_recurring_preview(query.all(), days=days)
    return jsonify({"preview": preview})


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
