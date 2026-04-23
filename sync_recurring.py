from app import create_app
from app.main.utils import sync_recurring


def run_sync():
    app = create_app()
    with app.app_context():
        created = sync_recurring()
        if created:
            print(f"Created {len(created)} recurring transaction(s):")
            for item in created:
                print(f"- Recurring {item['recurring_id']} on {item['date']} (${item['amount']:.2f})")
        else:
            print("No recurring transactions needed generation.")


if __name__ == "__main__":
    run_sync()
