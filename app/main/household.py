import secrets

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from ..forms import HouseholdForm
from ..models import Household, HouseholdMembership, db


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

        membership = HouseholdMembership(
            user_id=current_user.id,
            household_id=household.household_id,
            role="owner",
        )
        db.session.add(membership)
        db.session.commit()
        flash(
            f"Household '{household.name}' created! Invite others with code: {household.invite_code}",
            "success",
        )
        return redirect(url_for("main.household_dashboard", household_id=household.household_id))

    return render_template("create_household.html", form=form)


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
                membership = HouseholdMembership(
                    user_id=current_user.id,
                    household_id=household.household_id,
                    role="member",
                )
                db.session.add(membership)
                db.session.commit()
                flash("Successfully joined household!", "success")
                return redirect(url_for("main.household_dashboard", household_id=household.household_id))
        else:
            flash("Invalid invite code.", "danger")

    return render_template("join_household.html")


@bp.route("/household/<int:household_id>/invite")
@login_required
def show_invite_code(household_id):
    household = Household.query.get_or_404(household_id)
    if not current_user.is_member_of(household):
        abort(404)

    return render_template("invite_code.html", household=household)
