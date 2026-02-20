"""Recreate the database with the current models. Run with: python recreate_db.py
Stop the Flask app first so the DB is not in use."""
from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database recreated successfully. Personal + optional household structure in place.")
