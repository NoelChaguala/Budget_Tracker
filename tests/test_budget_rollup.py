import pytest
from datetime import datetime, timedelta
from app.models import db, User, Household, Category, Transaction, Budget, HouseholdMembership
from app.rollup_utils import get_budget_status

@pytest.fixture
def test_client():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

@pytest.fixture
def setup_data(test_client):
    with test_client.application.app_context():
        # Create test user
        user = User(username='testuser', email='test@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.flush()  # <--- CRITICAL: This assigns an ID to 'user'

        # Create test household
        household = Household(name='Test Household', invite_code='TEST123')
        db.session.add(household)
        db.session.flush()  # <--- CRITICAL: This assigns an ID to 'household'

        # Create household membership
        membership = HouseholdMembership(user_id=user.id, household_id=household.household_id, role='member')
        db.session.add(membership)

        # Create categories
        food = Category(name='Food', user_id=user.id)
        db.session.add(food)
        db.session.flush()  # <--- CRITICAL: This assigns an ID to 'food'

        groceries = Category(name='Groceries', user_id=user.id, parent_id=food.category_id)
        dining = Category(name='Dining Out', user_id=user.id, parent_id=food.category_id)
        db.session.add_all([groceries, dining])
        db.session.flush()  # <--- CRITICAL: This assigns IDs to children

        # Create transactions
        today = datetime.now().date()
        transactions = [
            Transaction(amount=50.0, type='expense', date=today, user_id=user.id, category_id=groceries.category_id),
            Transaction(amount=30.0, type='expense', date=today, user_id=user.id, category_id=dining.category_id),
            Transaction(amount=20.0, type='expense', date=today, user_id=user.id, category_id=groceries.category_id),
        ]
        db.session.add_all(transactions)

        # Create budgets (Now food.category_id will NOT be None)
        food_budget = Budget(
            category_id=food.category_id,
            limit_amount=200.0,
            user_id=user.id,
            month=datetime.now().date().replace(day=1)
        )
        db.session.add(food_budget)

        db.session.commit()

        # Return the data for tests
        yield {
            'user': user,
            'household': household,
            'food': food,
            'groceries': groceries,
            'dining': dining,
            'transactions': transactions,
            'food_budget': food_budget
        }

def test_get_budget_status_with_rollup(setup_data, test_client):
    """Test roll-up budget calculation with parent and child categories"""
    with test_client.application.app_context():
        # Test food budget (parent category)
        status = get_budget_status(setup_data['food_budget'].budget_id)

        assert status is not None
        assert status['budget_limit'] == 200.0
        assert status['spent'] == 100.0  # 50 + 30 + 20
        assert status['remaining'] == 100.0
        assert status['percentage'] == 50.0

def test_get_budget_status_personal_scope(setup_data, test_client):
    """Test personal budget scope filtering"""
    with test_client.application.app_context():
        # Create household transaction for same category
        household_trans = Transaction(
            amount=25.0,
            type='expense',
            date=datetime.now().date(),
            user_id=setup_data['user'].id,
            household_id=setup_data['household'].household_id,
            category_id=setup_data['groceries'].category_id
        )
        db.session.add(household_trans)
        db.session.commit()

        # Test food budget should still only count personal transactions
        status = get_budget_status(setup_data['food_budget'].budget_id)

        assert status['spent'] == 100.0  # Still only 100 from personal transactions

def test_get_budget_status_household_scope(setup_data, test_client):
    """Test household budget scope filtering"""
    with test_client.application.app_context():
        # Create household transaction for this test case
        household_trans = Transaction(
            amount=25.0,
            type='expense',
            date=datetime.now().date(),
            user_id=setup_data['user'].id,
            household_id=setup_data['household'].household_id,
            category_id=setup_data['groceries'].category_id
        )
        db.session.add(household_trans)

        # Create household budget
        household_budget = Budget(
            category_id=setup_data['food'].category_id,
            limit_amount=300.0,
            user_id=setup_data['user'].id,
            household_id=setup_data['household'].household_id,
            month=datetime.now().date().replace(day=1)
        )
        db.session.add(household_budget)
        db.session.commit()

        # Test household budget should include household-scoped transactions
        status = get_budget_status(household_budget.budget_id)

        assert status['spent'] == 25.0
        assert status['remaining'] == 275.0
        assert status['percentage'] == pytest.approx((25/300 * 100), abs=0.01)

def test_get_budget_status_no_transactions(setup_data, test_client):
    """Test budget status when no transactions exist"""
    with test_client.application.app_context():
        # Create a category with no transactions tied to it
        utilities = Category(name='Utilities', user_id=setup_data['user'].id)
        db.session.add(utilities)
        db.session.flush()

        # Create budget with no transactions
        empty_budget = Budget(
            category_id=utilities.category_id,
            limit_amount=100.0,
            user_id=setup_data['user'].id,
            month=datetime.now().date().replace(day=1)
        )
        db.session.add(empty_budget)
        db.session.commit()

        status = get_budget_status(empty_budget.budget_id)

        assert status['spent'] == 0.0
        assert status['remaining'] == 100.0
        assert status['percentage'] == 0.0

def test_get_budget_status_zero_limit(setup_data, test_client):
    """Test budget status with zero limit amount"""
    with test_client.application.app_context():
        zero_budget = Budget(
            category_id=setup_data['food'].category_id,
            limit_amount=0.0,
            user_id=setup_data['user'].id,
            month=datetime.now().date().replace(day=1)
        )
        db.session.add(zero_budget)
        db.session.commit()

        status = get_budget_status(zero_budget.budget_id)

        assert status['spent'] == 100.0
        assert status['remaining'] == -100.0
        assert status['percentage'] == 0.0  # Should handle division by zero gracefully

def test_category_hierarchy_get_all_subcategory_ids(setup_data, test_client):
    """Test Category.get_all_subcategory_ids method"""
    with test_client.application.app_context():
        # Test food category (parent)
        food_ids = setup_data['food'].get_all_subcategory_ids()
        assert setup_data['food'].category_id in food_ids
        assert setup_data['groceries'].category_id in food_ids
        assert setup_data['dining'].category_id in food_ids
        assert len(food_ids) == 3

        # Test groceries category (child)
        groceries_ids = setup_data['groceries'].get_all_subcategory_ids()
        assert setup_data['groceries'].category_id in groceries_ids
        assert len(groceries_ids) == 1
