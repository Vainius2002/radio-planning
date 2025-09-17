from flask import Flask
from flask_login import LoginManager
from config import Config
from app.models import db

login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    # Create tables
    with app.app_context():
        db.create_all()

        # Only initialize default data if database is empty
        from app.models import RadioGroup
        if RadioGroup.query.count() == 0:
            from app.utils import initialize_default_data
            initialize_default_data()

    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))