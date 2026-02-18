from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from .models import db, User, Household
from .forms import RegistrationForm, LoginForm, HouseholdForm

bp = Blueprint("main", __name__)

# Home / Dashboard
@bp.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

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

# User Login
@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("main.index"))
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
        household = Household(name=form.name.data, invite_code=form.invite_code.data)
        db.session.add(household)
        db.session.flush()  # INSERT household so household_id is set, without committing
        current_user.household_id = household.household_id
        db.session.commit()
        flash(f"Household '{household.name}' created!", "success")
        return redirect(url_for("main.index"))
    return render_template("create_household.html", form=form)


# Join Household
@bp.route("/join_household", methods=["GET", "POST"])
@login_required
def join_household():
    if request.method == "POST":
        code = request.form.get("invite_code")
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            current_user.household_id = household.household_id
            db.session.commit()
            flash("Successfully joined household!", "success")
            return redirect(url_for("main.index"))
        else:
            flash("Invalid invite code.", "danger")

    return render_template("join_household.html")
