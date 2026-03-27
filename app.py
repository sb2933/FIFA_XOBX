from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "fifa_secret_key"

# Temporary user storage
users = {}
MAX_USERS = 20

# Tournament storage: { tournament_id: { password, host, players: [username, ...] } }
tournaments = {}


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


# ── Tournament: Create ─────────────────────────────────────────────────────────

@app.route("/create_tournament", methods=["GET", "POST"])
def create_tournament():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        tournament_id = request.form.get("tournament_id", "").strip()
        tournament_password = request.form.get("tournament_password", "")

        if not tournament_id or not tournament_password:
            flash("Tournament ID and password are required.", "error")
            return redirect(url_for("create_tournament"))

        if tournament_id in tournaments:
            flash("A tournament with that ID already exists.", "error")
            return redirect(url_for("create_tournament"))

        username = session["username"]
        tournaments[tournament_id] = {
            "password": tournament_password,
            "host": username,
            "players": [username]
        }

        session["tournament_id"] = tournament_id
        flash(f'Tournament "{tournament_id}" created!', "success")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    return render_template("create_tournament.html")


# ── Tournament: Join ───────────────────────────────────────────────────────────

@app.route("/join_tournament", methods=["GET", "POST"])
def join_tournament():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        tournament_id = request.form.get("tournament_id", "").strip()
        tournament_password = request.form.get("tournament_password", "")

        if not tournament_id or not tournament_password:
            flash("Tournament ID and password are required.", "error")
            return redirect(url_for("join_tournament"))

        if tournament_id not in tournaments:
            flash("Tournament not found.", "error")
            return redirect(url_for("join_tournament"))

        if tournaments[tournament_id]["password"] != tournament_password:
            flash("Incorrect tournament password.", "error")
            return redirect(url_for("join_tournament"))

        username = session["username"]
        if username not in tournaments[tournament_id]["players"]:
            tournaments[tournament_id]["players"].append(username)

        session["tournament_id"] = tournament_id
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    return render_template("join_tournament.html")


# ── Tournament: Lobby ──────────────────────────────────────────────────────────

@app.route("/tournament/<tournament_id>")
def tournament_lobby(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    if tournament_id not in tournaments:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    username = session["username"]
    tournament = tournaments[tournament_id]

    if username not in tournament["players"]:
        flash("You are not part of this tournament.", "error")
        return redirect(url_for("dashboard"))

    host_full_name = users.get(tournament["host"], {}).get("full_name", tournament["host"])

    players_info = []
    for p in tournament["players"]:
        players_info.append({
            "username": p,
            "full_name": users.get(p, {}).get("full_name", p),
            "is_host": p == tournament["host"]
        })

    return render_template(
        "tournament_lobby.html",
        tournament_id=tournament_id,
        host=tournament["host"],
        host_full_name=host_full_name,
        players=players_info,
        current_user=username
    )


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("tournament_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)