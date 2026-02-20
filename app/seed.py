from app import create_app
from app.models import db, User, Household, Transaction
import random

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

    transactions = []

    # -------------------------
    # Alice Personal Transactions
    # -------------------------
    alice_personal = [
        ("Salary", 3000, "income"),
        ("Freelance Work", 800, "income"),
        ("Groceries", 220, "expense"),
        ("Gym Membership", 60, "expense"),
        ("Coffee", 45, "expense"),
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
