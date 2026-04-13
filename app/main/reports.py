import csv
import io
from collections import defaultdict
from datetime import date, datetime

from flask import Response, abort, jsonify, render_template, request, stream_with_context
from flask_login import current_user, login_required
from sqlalchemy import extract, func, or_

from . import bp
from ..models import Category, Household, HouseholdMembership, Transaction, db


def _parse_date_param(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        abort(400, description=f"Invalid {field_name}. Use YYYY-MM-DD.")


def _month_start(input_date):
    return input_date.replace(day=1)


def _subtract_months(month_date, months):
    year = month_date.year
    month = month_date.month
    for _ in range(months):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return date(year, month, 1)


def _iter_months(start_date, end_date):
    current = _month_start(start_date)
    end_month = _month_start(end_date)
    while current <= end_month:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _resolve_scope_filters(scope, household_id):
    if scope == "household":
        if not household_id:
            abort(400, description="household_id is required for household scope.")

        membership = HouseholdMembership.query.filter_by(
            user_id=current_user.id,
            household_id=household_id,
        ).first()
        if membership is None:
            abort(403)
        return [Transaction.household_id == household_id], "Household"

    if scope != "personal":
        abort(400, description="scope must be either personal or household.")

    return [
        Transaction.user_id == current_user.id,
        Transaction.household_id.is_(None),
    ], "Personal"


def _top_level_categories_for_scope(scope, household_id):
    if scope == "household":
        return (
            Category.query.filter(
                Category.parent_id.is_(None),
                or_(
                    Category.household_id == household_id,
                    (Category.user_id.is_(None) & Category.household_id.is_(None)),
                ),
            )
            .order_by(Category.name.asc())
            .all()
        )

    return (
        Category.query.filter(
            Category.parent_id.is_(None),
            or_(
                (Category.user_id == current_user.id) & Category.household_id.is_(None),
                (Category.user_id.is_(None) & Category.household_id.is_(None)),
            ),
        )
        .order_by(Category.name.asc())
        .all()
    )


@bp.route("/reports", methods=["GET"])
@login_required
def reports_page():
    scope = (request.args.get("scope") or "personal").strip().lower()
    if scope not in {"personal", "household"}:
        scope = "personal"

    start_date = _parse_date_param(request.args.get("start_date"), "start_date")
    end_date = _parse_date_param(request.args.get("end_date"), "end_date")

    today = date.today()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = _subtract_months(_month_start(end_date), 5)

    memberships = (
        db.session.query(HouseholdMembership, Household)
        .join(Household, Household.household_id == HouseholdMembership.household_id)
        .filter(HouseholdMembership.user_id == current_user.id)
        .order_by(Household.name.asc())
        .all()
    )

    households = [
        {"household_id": household.household_id, "name": household.name}
        for _, household in memberships
    ]

    household_id = request.args.get("household_id", type=int)
    if scope == "household":
        valid_household_ids = {household["household_id"] for household in households}
        if household_id not in valid_household_ids:
            household_id = households[0]["household_id"] if households else None
        if household_id is None:
            scope = "personal"

    return render_template(
        "reports.html",
        scope=scope,
        household_id=household_id,
        households=households,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


@bp.route("/api/reports/spending", methods=["GET"])
@login_required
def api_reports_spending():
    scope = (request.args.get("scope") or "personal").strip().lower()
    household_id = request.args.get("household_id", type=int)
    start_date = _parse_date_param(request.args.get("start_date"), "start_date")
    end_date = _parse_date_param(request.args.get("end_date"), "end_date")

    if start_date and end_date and start_date > end_date:
        abort(400, description="start_date cannot be after end_date.")

    today = date.today()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = _subtract_months(_month_start(end_date), 5)

    scope_filters, _ = _resolve_scope_filters(scope, household_id)

    category_totals = (
        db.session.query(
            Transaction.category_id,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.type == "expense",
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            *scope_filters,
        )
        .group_by(Transaction.category_id)
        .all()
    )

    totals_by_category_id = {
        category_id: float(total or 0)
        for category_id, total in category_totals
        if category_id is not None
    }

    by_category = []
    seen_category_ids = set()
    for parent in _top_level_categories_for_scope(scope, household_id):
        ids = parent.get_all_subcategory_ids()
        total = sum(totals_by_category_id.get(category_id, 0.0) for category_id in ids)
        seen_category_ids.update(ids)
        if total > 0:
            by_category.append(
                {
                    "category": parent.name,
                    "total": round(total, 2),
                }
            )

    uncategorized_total = 0.0
    for category_id, total in totals_by_category_id.items():
        if category_id not in seen_category_ids:
            uncategorized_total += total
    if uncategorized_total > 0:
        by_category.append({"category": "Other", "total": round(uncategorized_total, 2)})

    by_category.sort(key=lambda row: row["total"], reverse=True)

    month_totals_raw = (
        db.session.query(
            extract("year", Transaction.date).label("year_num"),
            extract("month", Transaction.date).label("month_num"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.type == "expense",
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            *scope_filters,
        )
        .group_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
        )
        .order_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
        )
        .all()
    )

    month_totals_lookup = defaultdict(float)
    for year_num, month_num, total in month_totals_raw:
        month_key = f"{int(year_num):04d}-{int(month_num):02d}"
        month_totals_lookup[month_key] = float(total or 0)

    by_month = []
    for month_start in _iter_months(start_date, end_date):
        month_key = month_start.strftime("%Y-%m")
        by_month.append({"month": month_key, "total": round(month_totals_lookup[month_key], 2)})

    total_spent = round(sum(item["total"] for item in by_month), 2)
    top_category = by_category[0]["category"] if by_category else ""

    return jsonify(
        {
            "summary": {
                "total_spent": total_spent,
                "top_category": top_category,
            },
            "by_category": by_category,
            "by_month": by_month,
        }
    )


@bp.route("/reports/export", methods=["GET"])
@login_required
def export_reports_csv():
    scope = (request.args.get("scope") or "personal").strip().lower()
    household_id = request.args.get("household_id", type=int)
    start_date = _parse_date_param(request.args.get("start_date"), "start_date")
    end_date = _parse_date_param(request.args.get("end_date"), "end_date")

    if start_date and end_date and start_date > end_date:
        abort(400, description="start_date cannot be after end_date.")

    scope_filters, scope_label = _resolve_scope_filters(scope, household_id)

    query = (
        db.session.query(
            Transaction.date,
            Transaction.amount,
            Category.name,
            Transaction.description,
            Transaction.household_id,
        )
        .outerjoin(Category, Category.category_id == Transaction.category_id)
        .filter(*scope_filters)
        .order_by(Transaction.date.desc(), Transaction.transaction_id.desc())
    )

    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    def generate_rows():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Amount", "Category", "Description", "Scope"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for row in query.yield_per(500):
            row_scope = "Household" if row.household_id else "Personal"
            writer.writerow(
                [
                    row.date.isoformat() if row.date else "",
                    f"{float(row.amount):.2f}",
                    row.name or "Uncategorized",
                    row.description or "",
                    row_scope if scope == "household" else scope_label,
                ]
            )
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"transactions_{date.today().isoformat()}.csv"
    return Response(
        stream_with_context(generate_rows()),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
