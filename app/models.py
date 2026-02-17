from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

db = SQLAlchemy()

# -------------------
# Household Model
# -------------------
class Household(db.Model):
    __tablename__ = "household"
    household_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    invite_code = db.Column(db.String(50), unique=True, nullable=True)

    # Relationships
    users = db.relationship("User", backref="household", lazy=True)
    categories = db.relationship("Category", backref="household", lazy=True)
    transactions = db.relationship("Transaction", backref="household", lazy=True)
    budgets = db.relationship("Budget", backref="household", lazy=True)

    def __repr__(self):
        return f"<Household {self.name}>"

# -------------------
# User Model
# -------------------
class User(db.Model, UserMixin):
    __tablename__ = "user"
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    household_id = db.Column(db.Integer, db.ForeignKey("household.household_id"), nullable=False)

    # Relationships
    personal_transactions = db.relationship("Transaction", backref="user", lazy=True)
    personal_budgets = db.relationship("Budget", backref="user", lazy=True)

    # Password methods
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

# -------------------
# Category Model
# -------------------
class Category(db.Model):
    __tablename__ = "category"
    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    household_id = db.Column(db.Integer, db.ForeignKey("household.household_id"), nullable=False)

    transactions = db.relationship("Transaction", backref="category", lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"

# -------------------
# Transaction Model
# -------------------
class Transaction(db.Model):
    __tablename__ = "transaction"
    transaction_id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # "income" or "expense"
    date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(200), nullable=True)

    household_id = db.Column(db.Integer, db.ForeignKey("household.household_id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=True)  # NULL = shared transaction
    category_id = db.Column(db.Integer, db.ForeignKey("category.category_id"), nullable=True)

    def is_personal(self):
        return self.user_id is not None

    def __repr__(self):
        scope = "Personal" if self.is_personal() else "Shared"
        return f"<Transaction {self.amount} ({scope})>"

# -------------------
# Budget Model
# -------------------
class Budget(db.Model):
    __tablename__ = "budget"
    budget_id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Date, nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)

    household_id = db.Column(db.Integer, db.ForeignKey("household.household_id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.user_id"), nullable=True)  # NULL = household budget

    def is_personal(self):
        return self.user_id is not None

    def __repr__(self):
        scope = "Personal" if self.is_personal() else "Household"
        return f"<Budget {scope} {self.limit_amount} for {self.month}>"
