import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "fifa_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "fifa_users.db")
MAX_USERS = 20


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    # Tournaments table — replaces the in-memory dict
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            tournament_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            host TEXT NOT NULL
        )
    """)

    # Tournament players join table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_players (
            tournament_id TEXT NOT NULL,
            username TEXT NOT NULL,
            PRIMARY KEY (tournament_id, username),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id),
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return user


def get_tournament(tournament_id):
    conn = get_db_connection()
    tournament = conn.execute(
        "SELECT * FROM tournaments WHERE tournament_id = ?", (tournament_id,)
    ).fetchone()
    conn.close()
    return tournament


def get_tournament_players(tournament_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT username FROM tournament_players WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()
    conn.close()
    return [r["username"] for r in rows]


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

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()["total"]

        if total_users >= MAX_USERS:
            conn.close()
            flash("Maximum number of players reached.", "error")
            return redirect(url_for("signup"))

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            flash("Username already exists.", "error")
            return redirect(url_for("signup"))

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("Email already registered.", "error")
            return redirect(url_for("signup"))

        cursor.execute("""
            INSERT INTO users (full_name, username, email, password)
            VALUES (?, ?, ?, ?)
        """, (full_name, username, email, password))

        conn.commit()
        conn.close()

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

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
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

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM users
            WHERE username = ? OR email = ?
        """, (username_or_email, username_or_email))
        user = cursor.fetchone()

        if not user:
            conn.close()
            flash("User not found.", "error")
            return redirect(url_for("forgot_password"))

        cursor.execute("""
            UPDATE users
            SET password = ?
            WHERE username = ? OR email = ?
        """, (new_password, username_or_email, username_or_email))

        conn.commit()
        conn.close()

        flash("Password reset successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    user = get_user_by_username(session["username"])

    if not user:
        session.pop("username", None)
        flash("User not found. Please log in again.", "error")
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=user)


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

        conn = get_db_connection()
        cursor = conn.cursor()

        existing = cursor.execute(
            "SELECT 1 FROM tournaments WHERE tournament_id = ?", (tournament_id,)
        ).fetchone()

        if existing:
            conn.close()
            flash("A tournament with that ID already exists.", "error")
            return redirect(url_for("create_tournament"))

        username = session["username"]

        cursor.execute(
            "INSERT INTO tournaments (tournament_id, password, host) VALUES (?, ?, ?)",
            (tournament_id, tournament_password, username)
        )
        cursor.execute(
            "INSERT INTO tournament_players (tournament_id, username) VALUES (?, ?)",
            (tournament_id, username)
        )

        conn.commit()
        conn.close()

        session["tournament_id"] = tournament_id
        flash(f'Tournament "{tournament_id}" created!', "success")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    return render_template("create_tournament.html")


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

        tournament = get_tournament(tournament_id)

        if not tournament:
            flash("Tournament not found.", "error")
            return redirect(url_for("join_tournament"))

        if tournament["password"] != tournament_password:
            flash("Incorrect tournament password.", "error")
            return redirect(url_for("join_tournament"))

        username = session["username"]
        conn = get_db_connection()
        cursor = conn.cursor()

        # INSERT OR IGNORE so joining twice is safe
        cursor.execute(
            "INSERT OR IGNORE INTO tournament_players (tournament_id, username) VALUES (?, ?)",
            (tournament_id, username)
        )
        conn.commit()
        conn.close()

        session["tournament_id"] = tournament_id
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    return render_template("join_tournament.html")


@app.route("/tournament/<tournament_id>")
def tournament_lobby(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    username = session["username"]
    players = get_tournament_players(tournament_id)

    if username not in players:
        flash("You are not part of this tournament.", "error")
        return redirect(url_for("dashboard"))

    host_user = get_user_by_username(tournament["host"])
    host_full_name = host_user["full_name"] if host_user else tournament["host"]

    players_info = []
    for p in players:
        player_user = get_user_by_username(p)
        players_info.append({
            "username": p,
            "full_name": player_user["full_name"] if player_user else p,
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
    init_db()
    app.run(debug=True)