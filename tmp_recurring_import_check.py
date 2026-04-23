from app import create_app
from app.models import db
from app.main.utils import advance_month_preserve_end
from datetime import date

app = create_app()
with app.app_context():
    db.create_all()
    print('ok')
    print('month end', advance_month_preserve_end(date(2023, 1, 31)))
