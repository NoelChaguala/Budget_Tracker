import json
from datetime import datetime
from app import create_app, db
from app.models import User, Household, HouseholdMembership, Category, Transaction, Budget
from werkzeug.security import generate_password_hash

def seed_database(json_file='seed_data.json'):
    app = create_app()
    with app.app_context():
        # Clear existing data to avoid conflicts
        db.drop_all()
        db.create_all()

        with open(json_file) as f:
            data = json.load(f)

        # 1. Create Users
        user_map = {}
        for u_data in data['users']:
            user = User(
                username=u_data['username'],
                email=u_data['email']
            )
            user.set_password(u_data['password'])
            db.session.add(user)
            user_map[u_data['username']] = user
        
        db.session.flush()

        # 2. Create Households and Memberships
        household_map = {}
        for h_data in data['households']:
            household = Household(name=h_data['name'], invite_code=h_data['name'].upper()[:4])
            db.session.add(household)
            db.session.flush()
            household_map[h_data['name']] = household

            for member in h_data['members']:
                membership = HouseholdMembership(
                    user_id=user_map[member['username']].id,
                    household_id=household.household_id,
                    role=member['role']
                )
                db.session.add(membership)

        # 3. Create Categories
        category_map = {}
        # First pass: Create categories without parents
        for c_data in data['categories']:
            user_id = user_map[c_data['user']].id if 'user' in c_data else None
            household_id = household_map[c_data['household']].household_id if 'household' in c_data else None
            is_system = c_data.get('type') == 'system'

            category = Category(
                name=c_data['name'],
                user_id=user_id,
                household_id=household_id,
                is_system=is_system
            )
            db.session.add(category)
            db.session.flush()
            category_map[c_data['name']] = category

        # Second pass: Link parents
        for c_data in data['categories']:
            if 'parent' in c_data:
                child = category_map[c_data['name']]
                parent = category_map[c_data['parent']]
                child.parent_id = parent.category_id

        # 4. Create Transactions
        for t_data in data['transactions']:
            household_id = household_map[t_data['household']].household_id if 'household' in t_data else None
            
            transaction = Transaction(
                amount=t_data['amount'],
                type=t_data['type'],
                date=datetime.strptime(t_data['date'], '%Y-%m-%d').date(),
                description=t_data.get('description', ''),
                category_id=category_map[t_data['category']].category_id,
                user_id=user_map[t_data['user']].id,
                household_id=household_id
            )
            db.session.add(transaction)

        # 5. Create Budgets
        for b_data in data['budgets']:
            household_id = household_map[b_data['household']].household_id if 'household' in b_data else None
            user_id = user_map[b_data['user']].id if 'user' in b_data else None

            budget = Budget(
                description=b_data.get('description', ''),
                month=datetime.strptime(b_data['month'], '%Y-%m-%d').date(),
                limit_amount=b_data['limit_amount'],
                category_id=category_map[b_data['category']].category_id,
                user_id=user_id,
                household_id=household_id
            )
            db.session.add(budget)

        db.session.commit()
        print("Database seeded successfully.")

if __name__ == '__main__':
    seed_database()