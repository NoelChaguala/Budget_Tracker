from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .models import Category, HouseholdMembership, db

bp_categories = Blueprint("categories", __name__)


def _user_owns_household(household_id):
    return (
        HouseholdMembership.query.filter_by(
            user_id=current_user.id,
            household_id=household_id,
        ).first()
        is not None
    )


@bp_categories.route("/categories/create", methods=["POST"])
@login_required
def create_category():
    name = request.form.get("name", "").strip()
    scope = request.form.get("scope", "personal")
    next_url = request.form.get("next", url_for("main.settings"))

    if not name:
        return redirect(next_url)

    if scope == "personal":
        existing = Category.query.filter_by(
            name=name,
            user_id=current_user.id,
            household_id=None,
        ).first()
        if not existing:
            db.session.add(Category(name=name, user_id=current_user.id))
            db.session.commit()
    else:
        household_id = int(scope)
        if not _user_owns_household(household_id):
            abort(403)
        existing = Category.query.filter_by(
            name=name,
            household_id=household_id,
        ).first()
        if not existing:
            db.session.add(Category(name=name, household_id=household_id))
            db.session.commit()

    return redirect(next_url)


@bp_categories.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    cat = Category.query.get_or_404(category_id)
    next_url = request.form.get("next", url_for("main.settings"))

    if cat.is_system:
        abort(403)

    if cat.user_id and cat.user_id != current_user.id:
        abort(403)

    if cat.household_id and not _user_owns_household(cat.household_id):
        abort(403)

    db.session.delete(cat)
    db.session.commit()
    return redirect(next_url)


@bp_categories.route("/categories/inline", methods=["POST"])
@login_required
def create_category_inline():
    """Called via fetch() from forms. Returns JSON with the new category."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    scope = data.get("scope", "personal")

    if not name:
        return jsonify({"error": "Name is required"}), 400

    if scope == "personal":
        existing = Category.query.filter_by(
            name=name,
            user_id=current_user.id,
            household_id=None,
        ).first()
        if existing:
            return jsonify({"id": existing.category_id, "name": existing.name})
        cat = Category(name=name, user_id=current_user.id)
    else:
        household_id = int(scope)
        if not _user_owns_household(household_id):
            return jsonify({"error": "Forbidden"}), 403
        existing = Category.query.filter_by(
            name=name,
            household_id=household_id,
        ).first()
        if existing:
            return jsonify({"id": existing.category_id, "name": existing.name})
        cat = Category(name=name, household_id=household_id)

    db.session.add(cat)
    db.session.commit()
    return jsonify({"id": cat.category_id, "name": cat.name})
