from flask import Flask
from flask_login import LoginManager
from .models import db

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key'  # change this in production
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///budget_app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "main.login"
    login_manager.init_app(app)

    from .models import User
    import config as project_config
    app.config.from_object(project_config)


    from .models import Category

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Import routes
    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    # Create database tables
    with app.app_context():
        db.create_all()

        # Ensure system-defined categories exist (global/system categories have no user_id/household_id)
        allowed = getattr(project_config, "ALLOWED_CATEGORIES", [])
        for name in allowed:
            existing = Category.query.filter_by(name=name, user_id=None, household_id=None).first()
            if not existing:
                db.session.add(Category(name=name, is_system=True))
        db.session.commit()

    return app
