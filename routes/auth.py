
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)

from flask_login import (
    login_user, logout_user,
    login_required, current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from models import db, User


auth = Blueprint("auth", __name__)


# ==========================================
# REGISTRATION
# ==========================================

@auth.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter(
            (User.username == username) |
            (User.email == email)
        ).first()

        if existing_user:
            flash("Username or email already exists.")
            return redirect(url_for("auth.register"))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in.")

        return redirect(url_for("auth.login"))

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@auth.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(
            user.password_hash, password
        ):

            login_user(user, remember=True)

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# ==========================================
# LOGOUT
# ==========================================

@auth.route("/logout")
@login_required
def logout():

    logout_user()

    flash("You have been logged out.")

    return redirect(url_for("auth.login"))
