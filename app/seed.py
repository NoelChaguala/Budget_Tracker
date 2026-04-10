from app import create_app
from app.models import db, User, Household, Transaction, Category
import config as project_config
import random
from datetime import datetime, timedelta

app = create_app()
with app.app_context():

    # Reset database (DEV ONLY)
    db.drop_all()
    db.create_all()

    # -------------------------
    # Create Users
    # -------------------------
    alice = User(username="alice", email="alice@test.com")
    alice.set_password("alice")

    bob = User(username="bob", email="bob@test.com")
    bob.set_password("bob")

    db.session.add_all([alice, bob])
    db.session.commit()

    # -------------------------
    # Create Household
    # -------------------------
    house = Household(name="Smith Family", invite_code="ABC123")
    house.members.append(alice)
    house.members.append(bob)

    db.session.add(house)
    db.session.commit()

    # Ensure system categories exist in seed too
    for name in getattr(project_config, "ALLOWED_CATEGORIES", []):
        if not Category.query.filter_by(name=name, user_id=None, household_id=None).first():
            db.session.add(Category(name=name))
    db.session.commit()

    # -------------------------
    # Create User-Specific Categories with Hierarchy
    # -------------------------
    
    # 1. Create a Parent Category: Food & Dining (User-specific)
    food_parent = Category(name='Food & Dining', user_id=alice.id, is_system=False)
    db.session.add(food_parent)
    db.session.flush()  # Get the ID so children can use it

    # 2. Create Child Categories under Food & Dining
    child_categories = [
        Category(name='Groceries', user_id=alice.id, parent_id=food_parent.category_id, is_system=False),
        Category(name='Coffee Shops', user_id=alice.id, parent_id=food_parent.category_id, is_system=False),
        Category(name='Fine Dining', user_id=alice.id, parent_id=food_parent.category_id, is_system=False),
    ]
    db.session.add_all(child_categories)
    db.session.flush()

    # 3. Create another Parent Category: Transportation
    transport_parent = Category(name='Transportation', user_id=alice.id, is_system=False)
    db.session.add(transport_parent)
    db.session.flush()

    # 4. Create Child Categories under Transportation
    transport_children = [
        Category(name='Gas', user_id=alice.id, parent_id=transport_parent.category_id, is_system=False),
        Category(name='Public Transit', user_id=alice.id, parent_id=transport_parent.category_id, is_system=False),
        Category(name='Ride Share', user_id=alice.id, parent_id=transport_parent.category_id, is_system=False),
    ]
    db.session.add_all(transport_children)
    db.session.flush()

    # Store child category IDs for transactions
    groceries_cat = child_categories[0]
    coffee_cat = child_categories[1]
    fine_dining_cat = child_categories[2]
    gas_cat = transport_children[0]
    transit_cat = transport_children[1]
    rideshare_cat = transport_children[2]

    transactions = []
    now = datetime.now()

    # -------------------------
    # Alice Personal Transactions
    # -------------------------
    alice_personal = [
        ("Salary", 3000, "income"),
        ("Freelance Work", 800, "income"),
        ("Gym Membership", 60, "expense"),
        ("Online Shopping", 150, "expense"),
        ("Car Insurance", 400, "expense"),
        ("Tax Refund", 500, "income"),
    ]

    for desc, amount, t_type in alice_personal:
        transactions.append(Transaction(
            amount=amount,
            description=desc,
            type=t_type,
            user_id=alice.id
        ))

    # -------------------------
    # Alice Food & Dining Transactions (using child categories)
    # This demonstrates the roll-up feature!
    # -------------------------
    food_transactions = [
        # Groceries
        ("Weekly grocery run", 85.50, groceries_cat.category_id),
        ("Farmers market produce", 42.30, groceries_cat.category_id),
        ("Costco bulk shopping", 156.75, groceries_cat.category_id),
        
        # Coffee Shops
        ("Morning latte", 5.50, coffee_cat.category_id),
        ("Coffee with friends", 12.00, coffee_cat.category_id),
        ("Iced coffee and pastry", 8.75, coffee_cat.category_id),
        ("Starbucks", 6.25, coffee_cat.category_id),
        ("Local cafe", 4.50, coffee_cat.category_id),
        
        # Fine Dining
        ("Anniversary dinner", 125.00, fine_dining_cat.category_id),
        ("Birthday celebration", 95.00, fine_dining_cat.category_id),
    ]

    for desc, amount, cat_id in food_transactions:
        transactions.append(Transaction(
            amount=amount,
            description=desc,
            type="expense",
            user_id=alice.id,
            category_id=cat_id,
            date=now - timedelta(days=random.randint(1, 28))
        ))

    # -------------------------
    # Alice Transportation Transactions (using child categories)
    # -------------------------
    transport_transactions = [
        # Gas
        ("Gas station fill-up", 45.00, gas_cat.category_id),
        ("Gas for road trip", 62.50, gas_cat.category_id),
        ("Quick gas stop", 35.00, gas_cat.category_id),
        
        # Public Transit
        ("Monthly metro pass", 75.00, transit_cat.category_id),
        ("Bus fare", 2.75, transit_cat.category_id),
        
        # Ride Share
        ("Uber to airport", 35.00, rideshare_cat.category_id),
        ("Lyft home", 18.50, rideshare_cat.category_id),
        ("Uber to downtown", 22.00, rideshare_cat.category_id),
    ]

    for desc, amount, cat_id in transport_transactions:
        transactions.append(Transaction(
            amount=amount,
            description=desc,
            type="expense",
            user_id=alice.id,
            category_id=cat_id,
            date=now - timedelta(days=random.randint(1, 28))
        ))

    # -------------------------
    # Bob Personal Transactions
    # -------------------------
    bob_personal = [
        ("Salary", 2500, "income"),
        ("Bonus", 1000, "income"),
        ("Groceries", 180, "expense"),
        ("Fuel", 120, "expense"),
        ("Dining Out", 90, "expense"),
        ("New Phone", 900, "expense"),
        ("Streaming Subscription", 20, "expense"),
    ]

    for desc, amount, t_type in bob_personal:
        transactions.append(Transaction(
            amount=amount,
            description=desc,
            type=t_type,
            user_id=bob.id
        ))

    # -------------------------
    # Household Transactions
    # -------------------------
    household_transactions = [
        ("Rent", 1200),
        ("Utilities", 300),
        ("Internet", 80),
        ("Water Bill", 70),
        ("Electricity", 150),
        ("Furniture", 600),
        ("Home Repairs", 350),
        ("Shared Groceries", 400),
    ]

    for desc, amount in household_transactions:
        transactions.append(Transaction(
            amount=amount,
            description=desc,
            type="expense",
            user_id=random.choice([alice.id, bob.id]),
            household_id=house.household_id
        ))

    # Save all transactions
    db.session.add_all(transactions)
    db.session.commit()

    print("Database seeded successfully with extended mock data!")
