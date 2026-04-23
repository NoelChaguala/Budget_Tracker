from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    result = db.session.execute(db.text('PRAGMA table_info("transaction")'))
    print('Columns in transaction table:')
    columns = []
    for row in result.fetchall():
        print(f'  - {row[1]}')
        columns.append(row[1])
    
    print(f"\n'recurring_id' exists: {'recurring_id' in columns}")