from app import create_app
from app.models import db, Category, Budget
from sqlalchemy import text

def update_budget_schema():
    """Update database schema to support category hierarchy and roll-up functionality"""
    app = create_app()
    with app.app_context():
# Add parent_id column to Category table
        db.session.execute(text("""
            ALTER TABLE category
            ADD COLUMN parent_id INTEGER REFERENCES category(category_id)
        """))

        # Add is_system column to Category table
        db.session.execute(text("""
            ALTER TABLE category
            ADD COLUMN is_system BOOLEAN DEFAULT FALSE
        """))

        # Add validation constraint to Budget table
        db.session.execute(text("""
            ALTER TABLE budget
            ADD CONSTRAINT valid_budget_scope
            CHECK (
                (user_id IS NOT NULL AND household_id IS NULL) OR
                (user_id IS NOT NULL AND household_id IS NOT NULL)
            )
        """))

        # Set parent_id to NULL for existing categories (no hierarchy)
        db.session.execute("UPDATE category SET parent_id = NULL")

        # Commit changes
        db.session.commit()
        print("Database schema updated successfully!")

if __name__ == "__main__":
    update_budget_schema()