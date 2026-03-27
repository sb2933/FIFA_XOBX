from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "fifa_secret_key"

# Temporary user storage
# Later you can replace this with a database
users = {}

MAX_USERS = 20


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not full_name or not username or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        if len(users) >= MAX_USERS:
            flash("Maximum number of players reached.", "error")
            return redirect(url_for("signup"))

        if username in users:
            flash("Username already exists.", "error")
            return redirect(url_for("signup"))

        for user_data in users.values():
            if user_data["email"] == email:
                flash("Email already registered.", "error")
                return redirect(url_for("signup"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        users[username] = {
            "full_name": full_name,
            "email": email,
            "password": password
        }

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter all required fields.", "error")
            return redirect(url_for("login"))

        if username in users and users[username]["password"] == password:
            session["username"] = username
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username_or_email = request.form.get("username_or_email", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_new_password = request.form.get("confirm_new_password", "")

        if not username_or_email or not new_password or not confirm_new_password:
            flash("All fields are required.", "error")
            return redirect(url_for("forgot_password"))

        if new_password != confirm_new_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("forgot_password"))

        found_user = None

        for username, user_data in users.items():
            if username == username_or_email or user_data["email"] == username_or_email:
                found_user = username
                break

        if not found_user:
            flash("User not found.", "error")
            return redirect(url_for("forgot_password"))

        users[found_user]["password"] = new_password
        flash("Password reset successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    username = session["username"]
    user = users.get(username)
    return render_template("dashboard.html", user=user, username=username)


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)