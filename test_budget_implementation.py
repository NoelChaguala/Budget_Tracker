#!/usr/bin/env python3
"""
Test script to verify the budget tracking implementation.
This script tests the core functionality without running the full Flask app.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date
from app import create_app, db
from app.models import User, Household, HouseholdMembership, Category, Transaction, Budget

def test_budget_implementation():
    """Test the budget tracking functionality."""
    print("Testing Budget Implementation...")
    
    # Create app and test client
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Create test user
        user = User(username='testuser', email='test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        
        # Create test category
        category = Category(name='Food', user_id=user.id)
        db.session.add(category)
        db.session.commit()
        
        # Create test budget
        budget = Budget(
            category_id=category.category_id,
            limit_amount=500.0,
            user_id=user.id,
            month=datetime.now().replace(day=1)
        )
        db.session.add(budget)
        db.session.commit()
        
        # Create test transactions
        transaction1 = Transaction(
            amount=100.0,
            type='expense',
            date=date.today(),
            description='Groceries',
            user_id=user.id,
            category_id=category.category_id
        )
        transaction2 = Transaction(
            amount=50.0,
            type='expense',
            date=date.today(),
            description='Dining out',
            user_id=user.id,
            category_id=category.category_id
        )
        db.session.add_all([transaction1, transaction2])
        db.session.commit()
        
        # Test the budget report function
        from app.main.utils import get_budget_report
        
        report = get_budget_report(user_id=user.id, household_id=None)
        
        print(f"Budget Report: {report}")
        
        if report:
            budget_data = report[0]
            expected_spent = 150.0  # 100 + 50
            expected_remaining = 350.0  # 500 - 150
            expected_percent = 30.0  # (150 / 500) * 100
            
            print(f"Expected spent: {expected_spent}, Actual: {budget_data['spent']}")
            print(f"Expected remaining: {expected_remaining}, Actual: {budget_data['remaining']}")
            print(f"Expected percent: {expected_percent}, Actual: {budget_data['percent']}")
            
            # Verify calculations
            assert budget_data['spent'] == expected_spent, f"Spent mismatch: {budget_data['spent']} != {expected_spent}"
            assert budget_data['remaining'] == expected_remaining, f"Remaining mismatch: {budget_data['remaining']} != {expected_remaining}"
            assert budget_data['percent'] == expected_percent, f"Percent mismatch: {budget_data['percent']} != {expected_percent}"
            
            print("✅ Budget calculations are correct!")
            print("✅ All tests passed!")
            return True
        else:
            print("❌ No budget report generated")
            return False

if __name__ == '__main__':
    try:
        success = test_budget_implementation()
        if success:
            print("\n🎉 Budget implementation test completed successfully!")
        else:
            print("\n❌ Budget implementation test failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
