from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Simple login for now
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# Create a default user if none exists
def create_default_user():
    if not User.query.first():
        user = User(
            username='admin',
            email='admin@radioplan.lt',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(user)
        db.session.commit()