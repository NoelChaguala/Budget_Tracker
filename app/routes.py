from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User, Household, HouseholdMembership, Transaction, Budget, Category
from .forms import RegistrationForm, LoginForm, HouseholdForm
import secrets

bp = Blueprint("main", __name__)


# Home — redirect to Personal Dashboard
@bp.route("/")
@login_required
def index():
    return redirect(url_for("main.personal_dashboard"))


# Personal Dashboard
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
    return render_template(
        "personal.html",
        transactions=transactions,
        budgets=budgets,
        categories=categories,
    )


# Household Dashboard (by household id)
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
    return render_template(
        "household.html",
        household=household,
        transactions=transactions,
        budgets=budgets,
        categories=categories,
    )


# User Registration
@bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html", form=form)


# User Login — redirect to Personal Dashboard
@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("main.personal_dashboard"))
        flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)


# Logout
@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# Create Household
@bp.route("/create_household", methods=["GET", "POST"])
@login_required
def create_household():
    form = HouseholdForm()
    if form.validate_on_submit():
        raw_code = (form.invite_code.data or "").strip()
        invite_code = raw_code if raw_code else secrets.token_hex(4).upper()
        household = Household(name=form.name.data, invite_code=invite_code)
        db.session.add(household)
        db.session.flush()
        membership = HouseholdMembership(user_id=current_user.id, household_id=household.household_id, role="owner")
        db.session.add(membership)
        db.session.commit()
        flash(f"Household '{household.name}' created! Invite others with code: {household.invite_code}", "success")
        return redirect(url_for("main.household_dashboard", household_id=household.household_id))
    return render_template("create_household.html", form=form)


# Join Household
@bp.route("/join_household", methods=["GET", "POST"])
@login_required
def join_household():
    if request.method == "POST":
        code = (request.form.get("invite_code") or "").strip()
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            if current_user.is_member_of(household):
                flash("You are already a member of this household.", "info")
            else:
                membership = HouseholdMembership(user_id=current_user.id, household_id=household.household_id, role="member")
                db.session.add(membership)
                db.session.commit()
                flash("Successfully joined household!", "success")
                return redirect(url_for("main.household_dashboard", household_id=household.household_id))
        else:
            flash("Invalid invite code.", "danger")

    return render_template("join_household.html")


# Add Transaction
@bp.route("/transaction/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    # Allowed category names (from config) — used for rendering & validation
    allowed_categories = current_app.config.get("ALLOWED_CATEGORIES", [])

    if request.method == "POST":
        # Basic form values
        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("Invalid amount.", "danger")
            return redirect(url_for("main.add_transaction"))

        description = request.form.get("description") or ""
        t_type = request.form.get("type")
        raw_household_id = request.form.get("household_id")
        household_id = int(raw_household_id) if (raw_household_id and raw_household_id.strip()) else None

        # Category must be one of the allowed system categories
        selected_category = request.form.get("category")
        if not selected_category or selected_category not in allowed_categories:
            flash("Please select a valid category.", "danger")
            return redirect(url_for("main.add_transaction"))

        # Ensure Category row exists for the system category (global/system categories have null user/household)
        category = Category.query.filter_by(name=selected_category, user_id=None, household_id=None).first()
        if not category:
            category = Category(name=selected_category)
            db.session.add(category)
            db.session.flush()

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


# Edit Transaction
@bp.route("/transaction/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    
    # Permission Check
    # 1. Personal: User must own it (user_id matches and household_id is None)
    # 2. Household: User must be a member of that household
    is_personal_owner = transaction.user_id == current_user.id and transaction.household_id is None
    is_household_member = False
    
    if transaction.household_id:
        membership = HouseholdMembership.query.filter_by(
            user_id=current_user.id, 
            household_id=transaction.household_id
        ).first()
        is_household_member = membership is not None

    if not (is_personal_owner or is_household_member):
        flash("You do not have permission to edit this transaction.", "danger")
        return redirect(url_for("main.personal_dashboard"))

    # Get allowed categories for the form
    allowed_categories = current_app.config.get("ALLOWED_CATEGORIES", [])
    
    # Ensure system categories exist and get their IDs
    categories = []
    for name in allowed_categories:
        category = Category.query.filter_by(name=name, user_id=None, household_id=None).first()
        if not category:
            category = Category(name=name)
            db.session.add(category)
            db.session.flush()
        categories.append(category)

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount"))
        except (TypeError, ValueError):
            flash("Invalid amount.", "danger")
            return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)

        description = request.form.get("description") or ""
        t_type = request.form.get("type")
        date_str = request.form.get("date")
        
        # Validate date
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        except (ValueError, TypeError):
            flash("Invalid date format.", "danger")
            return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)

        # Update transaction
        transaction.amount = amount
        transaction.description = description
        transaction.type = t_type
        transaction.date = date_obj
        
        # Category handling - use the selected category
        category_id = request.form.get("category_id")
        if category_id:
            try:
                transaction.category_id = int(category_id)
            except (ValueError, TypeError):
                flash("Invalid category.", "danger")
                return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)

        db.session.commit()
        flash("Transaction updated successfully!", "success")
        
        # Redirect to appropriate dashboard
        if transaction.household_id:
            return redirect(url_for("main.household_dashboard", household_id=transaction.household_id))
        else:
            return redirect(url_for("main.personal_dashboard"))

    return render_template("edit_transaction.html", transaction=transaction, allowed_categories=categories)


# Delete Transaction
@bp.route("/transaction/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    
    # Permission Check (same logic as edit)
    is_personal_owner = transaction.user_id == current_user.id and transaction.household_id is None
    is_household_member = False
    
    if transaction.household_id:
        membership = HouseholdMembership.query.filter_by(
            user_id=current_user.id, 
            household_id=transaction.household_id
        ).first()
        is_household_member = membership is not None

    if not (is_personal_owner or is_household_member):
        flash("You do not have permission to delete this transaction.", "danger")
        return redirect(url_for("main.personal_dashboard"))

    db.session.delete(transaction)
    db.session.commit()
    flash("Transaction deleted.", "info")
    
    # Redirect back to the referring page or appropriate dashboard
    if request.referrer:
        return redirect(request.referrer)
    elif transaction.household_id:
        return redirect(url_for("main.household_dashboard", household_id=transaction.household_id))
    else:
        return redirect(url_for("main.personal_dashboard"))


# Show Invite Code (for household members)
@bp.route("/household/<int:household_id>/invite")
@login_required
def show_invite_code(household_id):
    household = Household.query.get_or_404(household_id)
    if not current_user.is_member_of(household):
        abort(404)
    
    return render_template("invite_code.html", household=household)


# Settings (placeholder)
@bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


# Profile (placeholder)
@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html")
