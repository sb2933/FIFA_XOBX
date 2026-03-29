import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = "fifa_secret_key"

DATABASE_URL = os.environ.get("DATABASE_URL")  # Railway sets this automatically
MAX_USERS = 20


def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            tournament_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            host TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_players (
            tournament_id TEXT NOT NULL,
            username TEXT NOT NULL,
            PRIMARY KEY (tournament_id, username),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id),
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'waiting'
    """)

    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS tournament_type TEXT
    """)

    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS winner TEXT
    """)

    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS bye_player TEXT
    """)

    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS finalist_player TEXT
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,
            tournament_id TEXT NOT NULL,
            round_name TEXT,
            home_player TEXT NOT NULL,
            away_player TEXT NOT NULL,
            home_goals INTEGER DEFAULT 0,
            away_goals INTEGER DEFAULT 0,
            winner TEXT,
            match_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            sequence_order INTEGER,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS league_standings (
            id SERIAL PRIMARY KEY,
            tournament_id TEXT NOT NULL,
            username TEXT NOT NULL,
            played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            goals_for INTEGER DEFAULT 0,
            goals_against INTEGER DEFAULT 0,
            goal_difference INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            UNIQUE (tournament_id, username),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id),
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_points (
            id SERIAL PRIMARY KEY,
            tournament_id TEXT NOT NULL,
            username TEXT NOT NULL,
            points_balance INTEGER DEFAULT 0,
            UNIQUE (tournament_id, username),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id),
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            match_id INTEGER NOT NULL,
            tournament_id TEXT NOT NULL,
            bet_type TEXT NOT NULL,
            prediction_value TEXT NOT NULL,
            points_wagered INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            payout_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (username) REFERENCES users(username),
            FOREIGN KEY (match_id) REFERENCES matches(id),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id)
        )
    """)

    conn.commit()
    conn.close()


def fetchone_as_dict(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


def fetchall_as_dicts(cursor):
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = fetchone_as_dict(cursor)
    conn.close()
    return user


def get_tournament(tournament_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tournaments WHERE tournament_id = %s", (tournament_id,))
    tournament = fetchone_as_dict(cursor)
    conn.close()
    return tournament


def get_tournament_players(tournament_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username FROM tournament_players WHERE tournament_id = %s", (tournament_id,)
    )
    rows = fetchall_as_dicts(cursor)
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

        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        if total_users >= MAX_USERS:
            conn.close()
            flash("Maximum number of players reached.", "error")
            return redirect(url_for("signup"))

        cursor.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            conn.close()
            flash("Username already exists.", "error")
            return redirect(url_for("signup"))

        cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            flash("Email already registered.", "error")
            return redirect(url_for("signup"))

        cursor.execute("""
            INSERT INTO users (full_name, username, email, password)
            VALUES (%s, %s, %s, %s)
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
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password)
        )
        user = fetchone_as_dict(cursor)
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
            SELECT * FROM users WHERE username = %s OR email = %s
        """, (username_or_email, username_or_email))
        user = fetchone_as_dict(cursor)

        if not user:
            conn.close()
            flash("User not found.", "error")
            return redirect(url_for("forgot_password"))

        cursor.execute("""
            UPDATE users SET password = %s WHERE username = %s OR email = %s
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

        cursor.execute("SELECT 1 FROM tournaments WHERE tournament_id = %s", (tournament_id,))
        if cursor.fetchone():
            conn.close()
            flash("A tournament with that ID already exists.", "error")
            return redirect(url_for("create_tournament"))

        username = session["username"]

        cursor.execute(
            "INSERT INTO tournaments (tournament_id, password, host) VALUES (%s, %s, %s)",
            (tournament_id, tournament_password, username)
        )
        cursor.execute(
            "INSERT INTO tournament_players (tournament_id, username) VALUES (%s, %s)",
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
        
        if tournament["status"] != "waiting":
           flash("Tournament already started. Joining is closed.", "error")
           return redirect(url_for("join_tournament"))

        if tournament["password"] != tournament_password:
            flash("Incorrect tournament password.", "error")
            return redirect(url_for("join_tournament"))

        username = session["username"]
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO tournament_players (tournament_id, username)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (tournament_id, username))

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
        current_user=username,
        tournament_status=tournament.get("status", "waiting"),
        tournament_type=tournament.get("tournament_type"),
    )

@app.route("/kick/<tournament_id>/<username>", methods=["POST"])
def kick_player(tournament_id, username):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can kick players.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    if tournament.get("status") != "waiting":
        flash("Cannot kick players after tournament has started.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    if username == session["username"]:
        flash("Host cannot remove themselves.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM tournament_players
        WHERE tournament_id = %s AND username = %s
    """, (tournament_id, username))

    conn.commit()
    conn.close()

    flash(f"{username} was removed from the tournament.", "success")
    return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

@app.route("/start/<tournament_id>", methods=["POST"])
def start_tournament(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can start the tournament.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM tournament_players
        WHERE tournament_id = %s
    """, (tournament_id,))
    player_count = cursor.fetchone()[0]

    if player_count < 2:
        conn.close()
        flash("At least 2 players are required to start the tournament.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    cursor.execute("""
        UPDATE tournaments
        SET status = 'started'
        WHERE tournament_id = %s
    """, (tournament_id,))

    conn.commit()
    conn.close()

    flash("Tournament started. Choose tournament type.", "success")
    return redirect(url_for("choose_type", tournament_id=tournament_id))
@app.route("/choose/<tournament_id>", methods=["GET", "POST"])
def choose_type(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can choose the tournament type.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        tournament_type = request.form.get("tournament_type")

        if tournament_type not in ["knockout", "league"]:
            flash("Invalid tournament type selected.", "error")
            return redirect(url_for("choose_type", tournament_id=tournament_id))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tournaments
            SET tournament_type = %s
            WHERE tournament_id = %s
        """, (tournament_type, tournament_id))

        conn.commit()
        conn.close()

        if tournament_type == "knockout":
            return redirect(url_for("generate_knockout", tournament_id=tournament_id))
        else:
            return redirect(url_for("generate_league", tournament_id=tournament_id))

    return render_template("choose_type.html", tournament_id=tournament_id)

@app.route("/generate_league/<tournament_id>")
def generate_league(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can generate league fixtures.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username
        FROM tournament_players
        WHERE tournament_id = %s
        ORDER BY username
    """, (tournament_id,))
    players = [row[0] for row in cursor.fetchall()]

    if len(players) < 2:
        conn.close()
        flash("At least 2 players are required for a league.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    cursor.execute("""
        SELECT 1 FROM matches
        WHERE tournament_id = %s AND match_type = 'league'
        LIMIT 1
    """, (tournament_id,))
    existing_match = cursor.fetchone()

    if existing_match:
        conn.close()
        return redirect(url_for("view_league", tournament_id=tournament_id))

    for player in players:
        cursor.execute("""
            INSERT INTO league_standings (tournament_id, username)
            VALUES (%s, %s)
            ON CONFLICT (tournament_id, username) DO NOTHING
        """, (tournament_id, player))

    # Round-robin scheduling using circle method
    player_list = players[:]

    bye = None
    if len(player_list) % 2 == 1:
        bye = "BYE"
        player_list.append(bye)

    n = len(player_list)
    rounds = n - 1
    half = n // 2
    first_half_matches = []

    rotating = player_list[:]

    for round_num in range(rounds):
        round_matches = []

        for i in range(half):
            home = rotating[i]
            away = rotating[n - 1 - i]

            if home != bye and away != bye:
                round_matches.append((home, away))

        first_half_matches.append(round_matches)

        # rotate players except first one
        rotating = [rotating[0]] + [rotating[-1]] + rotating[1:-1]

    sequence = 1

    # First half
    for round_index, round_matches in enumerate(first_half_matches, start=1):
        for home, away in round_matches:
            cursor.execute("""
                INSERT INTO matches (
                    tournament_id, round_name, home_player, away_player,
                    match_type, status, sequence_order
                )
                VALUES (%s, %s, %s, %s, 'league', 'pending', %s)
            """, (
                tournament_id,
                f"Round {round_index}",
                home,
                away,
                sequence
            ))
            sequence += 1

    # Second half (reverse fixtures)
    for round_index, round_matches in enumerate(first_half_matches, start=1):
        for home, away in round_matches:
            cursor.execute("""
                INSERT INTO matches (
                    tournament_id, round_name, home_player, away_player,
                    match_type, status, sequence_order
                )
                VALUES (%s, %s, %s, %s, 'league', 'pending', %s)
            """, (
                tournament_id,
                f"Round {round_index + rounds}",
                away,
                home,
                sequence
            ))
            sequence += 1

    conn.commit()
    conn.close()

    flash("League fixtures generated successfully.", "success")
    return redirect(url_for("view_league", tournament_id=tournament_id))


@app.route("/league/<tournament_id>")
def view_league(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)

    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check user is part of tournament
    cursor.execute("""
        SELECT 1 FROM tournament_players
        WHERE tournament_id = %s AND username = %s
    """, (tournament_id, session["username"]))
    member = cursor.fetchone()

    if not member:
        conn.close()
        flash("You are not part of this tournament.", "error")
        return redirect(url_for("dashboard"))

    # Standings
    cursor.execute("""
        SELECT *
        FROM league_standings
        WHERE tournament_id = %s
        ORDER BY points DESC, goal_difference DESC, goals_for DESC, username ASC
    """, (tournament_id,))
    standings = fetchall_as_dicts(cursor)

    # Fixtures
    cursor.execute("""
        SELECT *
        FROM matches
        WHERE tournament_id = %s AND match_type = 'league'
        ORDER BY sequence_order ASC
    """, (tournament_id,))
    matches = fetchall_as_dicts(cursor)

    conn.close()

    return render_template(
        "league_table.html",
        tournament_id=tournament_id,
        tournament=tournament,
        standings=standings,
        matches=matches,
        current_user=session["username"]
    )
    
@app.route("/submit_league_score/<int:match_id>", methods=["POST"])
def submit_league_score(match_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch the match
    cursor.execute("SELECT * FROM matches WHERE id = %s AND match_type = 'league'", (match_id,))
    match = fetchone_as_dict(cursor)

    if not match:
        conn.close()
        flash("Match not found.", "error")
        return redirect(url_for("dashboard"))

    tournament = get_tournament(match["tournament_id"])

    if not tournament or tournament["host"] != session["username"]:
        conn.close()
        flash("Only the host can submit scores.", "error")
        return redirect(url_for("view_league", tournament_id=match["tournament_id"]))

    try:
        home_goals = int(request.form.get("home_goals", 0))
        away_goals = int(request.form.get("away_goals", 0))
    except ValueError:
        conn.close()
        flash("Invalid score values.", "error")
        return redirect(url_for("view_league", tournament_id=match["tournament_id"]))

    # Determine result
    if home_goals > away_goals:
        winner = match["home_player"]
    elif away_goals > home_goals:
        winner = match["away_player"]
    else:
        winner = "draw"

    was_completed = match["status"] == "completed"

    # If match was already completed, reverse the old standings first
    if was_completed:
        old_home = match["home_goals"]
        old_away = match["away_goals"]

        if old_home > old_away:
            old_winner, old_loser = match["home_player"], match["away_player"]
            cursor.execute("""
                UPDATE league_standings
                SET played = played - 1, wins = wins - 1,
                    goals_for = goals_for - %s, goals_against = goals_against - %s,
                    goal_difference = goal_difference - %s, points = points - 3
                WHERE tournament_id = %s AND username = %s
            """, (old_home, old_away, old_home - old_away, match["tournament_id"], old_winner))
            cursor.execute("""
                UPDATE league_standings
                SET played = played - 1, losses = losses - 1,
                    goals_for = goals_for - %s, goals_against = goals_against - %s,
                    goal_difference = goal_difference - %s
                WHERE tournament_id = %s AND username = %s
            """, (old_away, old_home, old_away - old_home, match["tournament_id"], old_loser))
        elif old_away > old_home:
            old_winner, old_loser = match["away_player"], match["home_player"]
            cursor.execute("""
                UPDATE league_standings
                SET played = played - 1, wins = wins - 1,
                    goals_for = goals_for - %s, goals_against = goals_against - %s,
                    goal_difference = goal_difference - %s, points = points - 3
                WHERE tournament_id = %s AND username = %s
            """, (old_away, old_home, old_away - old_home, match["tournament_id"], old_winner))
            cursor.execute("""
                UPDATE league_standings
                SET played = played - 1, losses = losses - 1,
                    goals_for = goals_for - %s, goals_against = goals_against - %s,
                    goal_difference = goal_difference - %s
                WHERE tournament_id = %s AND username = %s
            """, (old_home, old_away, old_home - old_away, match["tournament_id"], old_loser))
        else:
            # old draw
            for player, gf, ga in [
                (match["home_player"], old_home, old_away),
                (match["away_player"], old_away, old_home),
            ]:
                cursor.execute("""
                    UPDATE league_standings
                    SET played = played - 1, draws = draws - 1,
                        goals_for = goals_for - %s, goals_against = goals_against - %s,
                        goal_difference = goal_difference - %s, points = points - 1
                    WHERE tournament_id = %s AND username = %s
                """, (gf, ga, gf - ga, match["tournament_id"], player))

    # Apply new result to standings
    if winner == "draw":
        for player, gf, ga in [
            (match["home_player"], home_goals, away_goals),
            (match["away_player"], away_goals, home_goals),
        ]:
            cursor.execute("""
                UPDATE league_standings
                SET played = played + 1, draws = draws + 1,
                    goals_for = goals_for + %s, goals_against = goals_against + %s,
                    goal_difference = goal_difference + %s, points = points + 1
                WHERE tournament_id = %s AND username = %s
            """, (gf, ga, gf - ga, match["tournament_id"], player))
    else:
        loser = match["away_player"] if winner == match["home_player"] else match["home_player"]
        w_gf, w_ga = (home_goals, away_goals) if winner == match["home_player"] else (away_goals, home_goals)
        l_gf, l_ga = w_ga, w_gf

        cursor.execute("""
            UPDATE league_standings
            SET played = played + 1, wins = wins + 1,
                goals_for = goals_for + %s, goals_against = goals_against + %s,
                goal_difference = goal_difference + %s, points = points + 3
            WHERE tournament_id = %s AND username = %s
        """, (w_gf, w_ga, w_gf - w_ga, match["tournament_id"], winner))
        cursor.execute("""
            UPDATE league_standings
            SET played = played + 1, losses = losses + 1,
                goals_for = goals_for + %s, goals_against = goals_against + %s,
                goal_difference = goal_difference + %s
            WHERE tournament_id = %s AND username = %s
        """, (l_gf, l_ga, l_gf - l_ga, match["tournament_id"], loser))

    # Update match record
    cursor.execute("""
        UPDATE matches
        SET home_goals = %s, away_goals = %s, winner = %s, status = 'completed'
        WHERE id = %s
    """, (home_goals, away_goals, winner, match_id))

    # Settle all pending bets for this match (only first time it's completed)
    if not was_completed:
        _process_bets_for_match(cursor, match_id, home_goals, away_goals, winner, match["tournament_id"])

    conn.commit()
    conn.close()

    flash("Score saved successfully.", "success")
    return redirect(url_for("view_league", tournament_id=match["tournament_id"]))


@app.route("/api/lobby_state/<tournament_id>")
def api_lobby_state(tournament_id):
    from flask import jsonify
    if "username" not in session:
        return jsonify({"error": "not logged in"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM tournament_players WHERE tournament_id = %s ORDER BY username", (tournament_id,))
    players = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT status, tournament_type FROM tournaments WHERE tournament_id = %s", (tournament_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({"players": players, "player_count": len(players), "status": row[0], "tournament_type": row[1]})


@app.route("/generate_knockout/<tournament_id>")
def generate_knockout(tournament_id):
    import random
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)
    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can generate the knockout bracket.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM matches WHERE tournament_id = %s AND match_type = 'knockout' LIMIT 1",
        (tournament_id,)
    )
    if cursor.fetchone():
        conn.close()
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    cursor.execute(
        "SELECT username FROM tournament_players WHERE tournament_id = %s",
        (tournament_id,)
    )
    players = [row[0] for row in cursor.fetchall()]

    if len(players) < 2:
        conn.close()
        flash("At least 2 players are required.", "error")
        return redirect(url_for("dashboard"))

    random.shuffle(players)

    if len(players) % 2 == 1:
        bye_player = players.pop()
        cursor.execute(
            "UPDATE tournaments SET bye_player = %s WHERE tournament_id = %s",
            (bye_player, tournament_id)
        )

    for i in range(0, len(players), 2):
        cursor.execute("""
            INSERT INTO matches (tournament_id, round_name, home_player, away_player, match_type, status, sequence_order)
            VALUES (%s, 'Round 1', %s, %s, 'knockout', 'pending', %s)
        """, (tournament_id, players[i], players[i + 1], i // 2 + 1))

    conn.commit()
    conn.close()

    flash("Knockout bracket generated!", "success")
    return redirect(url_for("view_knockout", tournament_id=tournament_id))


@app.route("/knockout/<tournament_id>")
def view_knockout(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)
    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1 FROM tournament_players
        WHERE tournament_id = %s AND username = %s
    """, (tournament_id, session["username"]))
    if not cursor.fetchone():
        conn.close()
        flash("You are not part of this tournament.", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT * FROM matches
        WHERE tournament_id = %s AND match_type = 'knockout'
        ORDER BY sequence_order ASC
    """, (tournament_id,))
    matches = fetchall_as_dicts(cursor)
    conn.close()

    from collections import OrderedDict
    rounds = OrderedDict()
    for m in matches:
        rn = m["round_name"]
        if rn not in rounds:
            rounds[rn] = []
        rounds[rn].append(m)

    # Only show bye notice while Round 1 still has pending matches
    r1_pending = any(
        m["status"] == "pending" and m["round_name"] == "Round 1"
        for m in matches
    )
    bye_player = tournament.get("bye_player") if r1_pending else None

    return render_template(
        "knockout.html",
        tournament_id=tournament_id,
        tournament=tournament,
        rounds=rounds,
        bye_player=bye_player,
        current_user=session["username"]
    )


@app.route("/submit_knockout_score/<int:match_id>", methods=["POST"])
def submit_knockout_score(match_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM matches WHERE id = %s AND match_type = 'knockout'", (match_id,))
    match = fetchone_as_dict(cursor)

    if not match:
        conn.close()
        flash("Match not found.", "error")
        return redirect(url_for("dashboard"))

    tournament_id = match["tournament_id"]
    tournament = get_tournament(tournament_id)

    if not tournament or tournament["host"] != session["username"]:
        conn.close()
        flash("Only the host can submit scores.", "error")
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    if match["status"] == "completed":
        conn.close()
        flash("This match is already completed.", "error")
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    try:
        home_goals = int(request.form.get("home_goals", 0))
        away_goals = int(request.form.get("away_goals", 0))
    except ValueError:
        conn.close()
        flash("Invalid score.", "error")
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    if home_goals < 0 or away_goals < 0:
        conn.close()
        flash("Scores cannot be negative.", "error")
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    if home_goals == away_goals:
        conn.close()
        flash("Knockout matches cannot end in a draw.", "error")
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    winner = match["home_player"] if home_goals > away_goals else match["away_player"]

    cursor.execute("""
        UPDATE matches
        SET home_goals = %s, away_goals = %s, winner = %s, status = 'completed'
        WHERE id = %s
    """, (home_goals, away_goals, winner, match_id))

    current_round = match["round_name"]

    # Check if all other matches in this round are already completed
    cursor.execute("""
        SELECT COUNT(*) FROM matches
        WHERE tournament_id = %s AND match_type = 'knockout'
        AND round_name = %s AND status != 'completed' AND id != %s
    """, (tournament_id, current_round, match_id))
    remaining = cursor.fetchone()[0]

    if remaining == 0:
        _advance_knockout_bracket(cursor, tournament_id, current_round, tournament)

    conn.commit()
    conn.close()

    flash("Score saved.", "success")
    return redirect(url_for("view_knockout", tournament_id=tournament_id))


def _advance_knockout_bracket(cursor, tournament_id, completed_round, tournament):
    cursor.execute("""
        SELECT home_player, away_player, winner, home_goals, away_goals
        FROM matches
        WHERE tournament_id = %s AND match_type = 'knockout' AND round_name = %s
        ORDER BY sequence_order ASC
    """, (tournament_id, completed_round))
    round_matches = cursor.fetchall()

    bye_player = tournament.get("bye_player")

    cursor.execute(
        "SELECT COALESCE(MAX(sequence_order), 0) FROM matches WHERE tournament_id = %s AND match_type = 'knockout'",
        (tournament_id,)
    )
    max_seq = cursor.fetchone()[0]

    if completed_round == "Round 1":
        num_matches = len(round_matches)
        winners = [m[2] for m in round_matches]

        if not bye_player:
            # Even-player bracket — no bye
            if num_matches == 1:
                # 2 players: this match was the Final
                cursor.execute(
                    "UPDATE tournaments SET status = 'finished', winner = %s WHERE tournament_id = %s",
                    (winners[0], tournament_id)
                )
            else:
                # 4+ players: pair winners into Final / next round
                cursor.execute("""
                    INSERT INTO matches (tournament_id, round_name, home_player, away_player, match_type, status, sequence_order)
                    VALUES (%s, 'Final', %s, %s, 'knockout', 'pending', %s)
                """, (tournament_id, winners[0], winners[1], max_seq + 1))
        else:
            # Odd-player bracket — has bye
            if num_matches == 1:
                # 3-player: R1 winner goes to Final, R1 loser plays bye in Round 2
                r1_match = round_matches[0]
                home, away, r1_winner = r1_match[0], r1_match[1], r1_match[2]
                r1_loser = away if r1_winner == home else home
                cursor.execute(
                    "UPDATE tournaments SET finalist_player = %s WHERE tournament_id = %s",
                    (r1_winner, tournament_id)
                )
                cursor.execute("""
                    INSERT INTO matches (tournament_id, round_name, home_player, away_player, match_type, status, sequence_order)
                    VALUES (%s, 'Round 2', %s, %s, 'knockout', 'pending', %s)
                """, (tournament_id, r1_loser, bye_player, max_seq + 1))

            elif num_matches == 2:
                # 5-player: sort R1 winners by goals scored desc
                # high scorer → seeded to Final; low scorer plays bye in Round 2
                winners_with_goals = []
                for home, away, w, hg, ag in round_matches:
                    goals = hg if w == home else ag
                    winners_with_goals.append((w, goals))
                winners_with_goals.sort(key=lambda x: x[1], reverse=True)
                high_scorer = winners_with_goals[0][0]
                low_scorer = winners_with_goals[1][0]

                cursor.execute(
                    "UPDATE tournaments SET finalist_player = %s WHERE tournament_id = %s",
                    (high_scorer, tournament_id)
                )
                cursor.execute("""
                    INSERT INTO matches (tournament_id, round_name, home_player, away_player, match_type, status, sequence_order)
                    VALUES (%s, 'Round 2', %s, %s, 'knockout', 'pending', %s)
                """, (tournament_id, low_scorer, bye_player, max_seq + 1))

    elif completed_round == "Round 2":
        # Round 2 winner faces the stored finalist in the Final
        r2_winner = round_matches[0][2]
        cursor.execute(
            "SELECT finalist_player FROM tournaments WHERE tournament_id = %s",
            (tournament_id,)
        )
        finalist = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO matches (tournament_id, round_name, home_player, away_player, match_type, status, sequence_order)
            VALUES (%s, 'Final', %s, %s, 'knockout', 'pending', %s)
        """, (tournament_id, finalist, r2_winner, max_seq + 1))

    elif completed_round == "Final":
        final_winner = round_matches[0][2]
        cursor.execute(
            "UPDATE tournaments SET status = 'finished', winner = %s WHERE tournament_id = %s",
            (final_winner, tournament_id)
        )


# ─── BETTING / POINTS SYSTEM ─────────────────────────────────────────────────

def _process_bets_for_match(cursor, match_id, home_goals, away_goals, winner, tournament_id):
    """Settle all pending bets for a just-completed match."""
    total_goals = home_goals + away_goals
    actual_score = f"{home_goals}-{away_goals}"

    cursor.execute("SELECT * FROM bets WHERE match_id = %s AND status = 'pending'", (match_id,))
    cols = [desc[0] for desc in cursor.description]
    bets = [dict(zip(cols, row)) for row in cursor.fetchall()]

    for bet in bets:
        won = False
        payout = 0

        if bet["bet_type"] == "winner":
            if bet["prediction_value"] == winner:
                won = True
                payout = bet["points_wagered"] * 2

        elif bet["bet_type"] == "exact_score":
            if bet["prediction_value"] == actual_score:
                won = True
                payout = bet["points_wagered"] * 4

        elif bet["bet_type"] == "total_goals":
            pred = bet["prediction_value"]
            try:
                direction, threshold_str = pred.split("_", 1)
                threshold = int(threshold_str)
                if direction == "over" and total_goals > threshold:
                    won = True
                elif direction == "under" and total_goals < threshold:
                    won = True
            except (ValueError, AttributeError):
                pass
            if won:
                payout = int(bet["points_wagered"] * 2.5)

        cursor.execute(
            "UPDATE bets SET status = %s, payout_points = %s WHERE id = %s",
            ("won" if won else "lost", payout, bet["id"])
        )
        if won:
            cursor.execute("""
                UPDATE player_points SET points_balance = points_balance + %s
                WHERE tournament_id = %s AND username = %s
            """, (payout, tournament_id, bet["username"]))


@app.route("/assign_points/<tournament_id>", methods=["GET", "POST"])
def assign_points(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)
    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can assign points.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        target_username = request.form.get("username", "").strip()
        try:
            points_amount = int(request.form.get("points_amount", 0))
        except ValueError:
            flash("Invalid points amount.", "error")
            return redirect(url_for("assign_points", tournament_id=tournament_id))

        if points_amount < 20 or points_amount > 100:
            flash("Starting points must be between 20 and 100.", "error")
            return redirect(url_for("assign_points", tournament_id=tournament_id))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM tournament_players WHERE tournament_id = %s AND username = %s",
            (tournament_id, target_username)
        )
        if not cursor.fetchone():
            conn.close()
            flash("Player not found in this tournament.", "error")
            return redirect(url_for("assign_points", tournament_id=tournament_id))

        cursor.execute("""
            INSERT INTO player_points (tournament_id, username, points_balance)
            VALUES (%s, %s, %s)
            ON CONFLICT (tournament_id, username) DO UPDATE SET points_balance = EXCLUDED.points_balance
        """, (tournament_id, target_username, points_amount))

        conn.commit()
        conn.close()
        flash(f"Assigned {points_amount} points to {target_username}.", "success")
        return redirect(url_for("assign_points", tournament_id=tournament_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tp.username, COALESCE(pp.points_balance, NULL) AS points_balance
        FROM tournament_players tp
        LEFT JOIN player_points pp
            ON tp.tournament_id = pp.tournament_id AND tp.username = pp.username
        WHERE tp.tournament_id = %s
        ORDER BY tp.username
    """, (tournament_id,))
    players = fetchall_as_dicts(cursor)
    conn.close()

    return render_template(
        "assign_points.html",
        tournament_id=tournament_id,
        tournament=tournament,
        players=players,
        current_user=session["username"]
    )


@app.route("/place_bet/<int:match_id>", methods=["GET", "POST"])
def place_bet(match_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM matches WHERE id = %s", (match_id,))
    match = fetchone_as_dict(cursor)

    if not match:
        conn.close()
        flash("Match not found.", "error")
        return redirect(url_for("dashboard"))

    tournament_id = match["tournament_id"]

    cursor.execute(
        "SELECT 1 FROM tournament_players WHERE tournament_id = %s AND username = %s",
        (tournament_id, session["username"])
    )
    if not cursor.fetchone():
        conn.close()
        flash("You are not in this tournament.", "error")
        return redirect(url_for("dashboard"))

    if match["status"] == "completed":
        conn.close()
        flash("Cannot bet on a completed match.", "error")
        return redirect(url_for("view_league", tournament_id=tournament_id))

    if request.method == "POST":
        bet_type = request.form.get("bet_type", "").strip()

        if bet_type not in ("winner", "exact_score", "total_goals"):
            conn.close()
            flash("Invalid bet type.", "error")
            return redirect(url_for("place_bet", match_id=match_id))

        try:
            points_wagered = int(request.form.get("points_wagered", 0))
        except ValueError:
            conn.close()
            flash("Invalid points amount.", "error")
            return redirect(url_for("place_bet", match_id=match_id))

        if points_wagered <= 0:
            conn.close()
            flash("Wagered points must be positive.", "error")
            return redirect(url_for("place_bet", match_id=match_id))

        # Build prediction_value from type-specific fields
        if bet_type == "winner":
            prediction_value = request.form.get("winner_prediction", "").strip()
            if prediction_value not in (match["home_player"], match["away_player"]):
                conn.close()
                flash("Invalid winner prediction.", "error")
                return redirect(url_for("place_bet", match_id=match_id))

        elif bet_type == "exact_score":
            exact_home = request.form.get("exact_home", "").strip()
            exact_away = request.form.get("exact_away", "").strip()
            if not exact_home.isdigit() or not exact_away.isdigit():
                conn.close()
                flash("Invalid score prediction.", "error")
                return redirect(url_for("place_bet", match_id=match_id))
            prediction_value = f"{exact_home}-{exact_away}"

        else:  # total_goals
            direction = request.form.get("goals_direction", "").strip()
            goals_num = request.form.get("goals_number", "").strip()
            if direction not in ("over", "under") or not goals_num.isdigit():
                conn.close()
                flash("Invalid total goals prediction.", "error")
                return redirect(url_for("place_bet", match_id=match_id))
            prediction_value = f"{direction}_{goals_num}"

        # Check sufficient balance
        cursor.execute(
            "SELECT points_balance FROM player_points WHERE tournament_id = %s AND username = %s",
            (tournament_id, session["username"])
        )
        balance_row = cursor.fetchone()
        if not balance_row or balance_row[0] < points_wagered:
            conn.close()
            flash("Insufficient points balance.", "error")
            return redirect(url_for("place_bet", match_id=match_id))

        # Prevent duplicate bet on same match + type
        cursor.execute(
            "SELECT 1 FROM bets WHERE username = %s AND match_id = %s AND bet_type = %s AND status = 'pending'",
            (session["username"], match_id, bet_type)
        )
        if cursor.fetchone():
            conn.close()
            flash(f"You already have a pending {bet_type.replace('_', ' ')} bet on this match.", "error")
            return redirect(url_for("place_bet", match_id=match_id))

        # Deduct points and record bet in one transaction
        cursor.execute(
            "UPDATE player_points SET points_balance = points_balance - %s WHERE tournament_id = %s AND username = %s",
            (points_wagered, tournament_id, session["username"])
        )
        cursor.execute("""
            INSERT INTO bets (username, match_id, tournament_id, bet_type, prediction_value, points_wagered, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
        """, (session["username"], match_id, tournament_id, bet_type, prediction_value, points_wagered))

        conn.commit()
        conn.close()
        flash("Bet placed successfully!", "success")
        return redirect(url_for("place_bet", match_id=match_id))

    # GET — load balance and existing bets for this match
    tournament = get_tournament(tournament_id)

    cursor.execute(
        "SELECT points_balance FROM player_points WHERE tournament_id = %s AND username = %s",
        (tournament_id, session["username"])
    )
    balance_row = cursor.fetchone()
    user_balance = balance_row[0] if balance_row else None

    cursor.execute(
        "SELECT * FROM bets WHERE username = %s AND match_id = %s ORDER BY created_at DESC",
        (session["username"], match_id)
    )
    user_bets = fetchall_as_dicts(cursor)
    conn.close()

    return render_template(
        "place_bet.html",
        match=match,
        tournament=tournament,
        tournament_id=tournament_id,
        user_balance=user_balance,
        user_bets=user_bets,
        current_user=session["username"]
    )


@app.route("/points_leaderboard/<tournament_id>")
def points_leaderboard(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)
    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM tournament_players WHERE tournament_id = %s AND username = %s",
        (tournament_id, session["username"])
    )
    if not cursor.fetchone():
        conn.close()
        flash("You are not in this tournament.", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT
            tp.username,
            COALESCE(pp.points_balance, 0)                                    AS points_balance,
            COUNT(b.id) FILTER (WHERE b.status = 'won')                       AS bets_won,
            COUNT(b.id) FILTER (WHERE b.status = 'lost')                      AS bets_lost,
            COUNT(b.id) FILTER (WHERE b.status = 'pending')                   AS bets_pending,
            COALESCE(SUM(b.payout_points) FILTER (WHERE b.status = 'won'), 0) AS total_won_points
        FROM tournament_players tp
        LEFT JOIN player_points pp
            ON tp.tournament_id = pp.tournament_id AND tp.username = pp.username
        LEFT JOIN bets b
            ON tp.username = b.username AND b.tournament_id = tp.tournament_id
        WHERE tp.tournament_id = %s
        GROUP BY tp.username, pp.points_balance
        ORDER BY points_balance DESC, total_won_points DESC
    """, (tournament_id,))
    leaderboard = fetchall_as_dicts(cursor)
    conn.close()

    return render_template(
        "leaderboard.html",
        tournament_id=tournament_id,
        tournament=tournament,
        leaderboard=leaderboard,
        current_user=session["username"]
    )


# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/match_state/<tournament_id>")
def api_match_state(tournament_id):
    from flask import jsonify
    import hashlib
    if "username" not in session:
        return jsonify({"error": "not logged in"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status, home_goals, away_goals, winner FROM matches WHERE tournament_id = %s ORDER BY id ASC", (tournament_id,))
    rows = cursor.fetchall()
    cursor.execute("SELECT status, winner, bye_player FROM tournaments WHERE tournament_id = %s", (tournament_id,))
    t_row = cursor.fetchone()
    conn.close()
    fingerprint = hashlib.md5(str(rows).encode() + str(t_row).encode()).hexdigest()
    return jsonify({"fingerprint": fingerprint, "tournament_status": t_row[0] if t_row else None})


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("tournament_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))