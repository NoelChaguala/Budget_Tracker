from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
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
