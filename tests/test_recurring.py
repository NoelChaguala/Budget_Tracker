import pytest
from datetime import date, timedelta

from app import create_app
from app.models import db, User, Household, HouseholdMembership, Category, Transaction, RecurringTransaction
from app.main.utils import advance_month_preserve_end, sync_recurring


@pytest.fixture
def app_context():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def sample_user(app_context):
    user = User(username="user1", email="user1@example.com")
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def sample_category(sample_user):
    category = Category(name="Rent", user_id=sample_user.id)
    db.session.add(category)
    db.session.commit()
    return category


def test_advance_month_preserve_end_for_long_months():
    assert advance_month_preserve_end(date(2023, 1, 31)).day == 28
    assert advance_month_preserve_end(date(2023, 1, 31)).month == 2
    assert advance_month_preserve_end(date(2024, 1, 31)).day == 29
    assert advance_month_preserve_end(date(2023, 3, 31)).day == 30


def test_sync_recurring_creates_daily_and_monthly_instances(app_context, sample_user, sample_category):
    sample_user_id = sample_user.id
    start = date.today() - timedelta(days=3)
    recurring = RecurringTransaction(
        amount=10.0,
        description="Daily coffee",
        type="expense",
        user_id=sample_user_id,
        category_id=sample_category.category_id,
        frequency="daily",
        start_date=start,
        end_date=None,
        last_generated_date=None,
        is_active=True,
    )
    db.session.add(recurring)
    db.session.commit()

    created = sync_recurring(user_id=sample_user_id)
    assert len(created) >= 4
    db.session.refresh(recurring)
    assert recurring.last_generated_date == date.today()
    transactions = Transaction.query.filter_by(recurring_id=recurring.id).order_by(Transaction.date).all()
    assert len(transactions) == len(created)
    assert transactions[-1].date == date.today()


def test_sync_recurring_is_idempotent(app_context, sample_user, sample_category):
    recurring = RecurringTransaction(
        amount=25.0,
        description="Weekly allowance",
        type="income",
        user_id=sample_user.id,
        category_id=sample_category.category_id,
        frequency="weekly",
        start_date=date.today() - timedelta(days=14),
        last_generated_date=None,
        is_active=True,
    )
    db.session.add(recurring)
    db.session.commit()

    first = sync_recurring(user_id=sample_user.id)
    second = sync_recurring(user_id=sample_user.id)

    assert len(first) >= 2
    assert second == []
    assert Transaction.query.filter_by(recurring_id=recurring.id).count() == len(first)


def test_sync_recurring_scope_includes_household_rules(app_context, sample_user, sample_category):
    household = Household(name="Test Home", invite_code="INVITE")
    db.session.add(household)
    db.session.commit()

    membership = HouseholdMembership(user_id=sample_user.id, household_id=household.household_id, role="member")
    db.session.add(membership)
    db.session.commit()

    household_category = Category(name="Groceries", household_id=household.household_id)
    db.session.add(household_category)
    db.session.commit()

    personal_rule = RecurringTransaction(
        amount=5.0,
        description="Personal tea",
        type="expense",
        user_id=sample_user.id,
        category_id=sample_category.category_id,
        frequency="daily",
        start_date=date.today() - timedelta(days=1),
        is_active=True,
    )
    household_rule = RecurringTransaction(
        amount=15.0,
        description="Household coffee",
        type="expense",
        user_id=sample_user.id,
        household_id=household.household_id,
        category_id=household_category.category_id,
        frequency="weekly",
        start_date=date.today() - timedelta(days=7),
        is_active=True,
    )
    db.session.add_all([personal_rule, household_rule])
    db.session.commit()

    created = sync_recurring(user_id=sample_user.id)
    assert any(item["recurring_id"] == personal_rule.id for item in created)
    assert any(item["recurring_id"] == household_rule.id for item in created)


def test_monthly_rule_on_31st_rolls_to_month_end(app_context, sample_user, sample_category):
    recurring = RecurringTransaction(
        amount=100.0,
        description="Month end rent",
        type="expense",
        user_id=sample_user.id,
        category_id=sample_category.category_id,
        frequency="monthly",
        start_date=date(2023, 1, 31),
        end_date=date(2023, 3, 31),
        is_active=True,
    )
    db.session.add(recurring)
    db.session.commit()

    created = sync_recurring(user_id=sample_user.id)
    dates = [date.fromisoformat(item["date"]) for item in created]
    assert date(2023, 2, 28) in dates or date(2023, 2, 29) in dates
    assert date(2023, 3, 31) in dates
