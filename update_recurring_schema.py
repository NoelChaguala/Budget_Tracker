from app import create_app
from app.models import db
from sqlalchemy import text


def update_recurring_schema():
    app = create_app()
    with app.app_context():
        # Ensure the recurring_transaction table exists for new schema support.
        db.create_all()

        engine_name = db.engine.name
        if engine_name == "sqlite":
            result = db.session.execute(text('PRAGMA table_info("transaction")'))
            columns = [row[1] for row in result.fetchall()]
            if "recurring_id" not in columns:
                db.session.execute(text('ALTER TABLE "transaction" ADD COLUMN recurring_id INTEGER'))
                db.session.commit()
                print("Added recurring_id column to transaction table.")
            else:
                print("Transaction table already has recurring_id column.")
        else:
            try:
                db.session.execute(text("ALTER TABLE transaction ADD COLUMN recurring_id INTEGER REFERENCES recurring_transaction(id)"))
                db.session.commit()
                print("Added recurring_id column to transaction table.")
            except Exception as exc:
                db.session.rollback()
                print("Skipping recurring_id creation; it may already exist or require manual migration.")
                print(exc)

        print("Recurring schema update complete.")


if __name__ == "__main__":
    update_recurring_schema()
