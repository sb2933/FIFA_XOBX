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
        current_user=username
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

    cursor.execute(
    "UPDATE tournaments SET status = 'started' WHERE tournament_id = %s",
    (tournament_id,)
)

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

@app.route("/generate_knockout/<tournament_id>")
def generate_knockout(tournament_id):
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    tournament = get_tournament(tournament_id)
    if not tournament:
        flash("Tournament not found.", "error")
        return redirect(url_for("dashboard"))

    if tournament["host"] != session["username"]:
        flash("Only the host can generate knockout fixtures.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure bye_player column exists
    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS bye_player TEXT
    """)
    cursor.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS winner TEXT
    """)

    cursor.execute("""
        SELECT username FROM tournament_players
        WHERE tournament_id = %s ORDER BY RANDOM()
    """, (tournament_id,))
    players = [row[0] for row in cursor.fetchall()]

    if len(players) < 2:
        conn.close()
        flash("At least 2 players are required for a knockout.", "error")
        return redirect(url_for("tournament_lobby", tournament_id=tournament_id))

    # Prevent duplicate generation
    cursor.execute("""
        SELECT 1 FROM matches WHERE tournament_id = %s AND match_type = 'knockout' LIMIT 1
    """, (tournament_id,))
    if cursor.fetchone():
        conn.close()
        return redirect(url_for("view_knockout", tournament_id=tournament_id))

    # If odd number of players, last player gets a bye
    bye_player = None
    active_players = players
    if len(players) % 2 == 1:
        bye_player = players[-1]
        active_players = players[:-1]
        cursor.execute("""
            UPDATE tournaments SET bye_player = %s WHERE tournament_id = %s
        """, (bye_player, tournament_id))

    sequence = 1
    for i in range(0, len(active_players), 2):
        cursor.execute("""
            INSERT INTO matches (
                tournament_id, round_name, home_player, away_player,
                match_type, status, sequence_order
            ) VALUES (%s, 'Round 1', %s, %s, 'knockout', 'pending', %s)
        """, (tournament_id, active_players[i], active_players[i + 1], sequence))
        sequence += 1

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
        SELECT 1 FROM tournament_players WHERE tournament_id = %s AND username = %s
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
    all_matches = fetchall_as_dicts(cursor)
    conn.close()

    # Group matches by round
    from collections import OrderedDict
    rounds = OrderedDict()
    for m in all_matches:
        rname = m["round_name"]
        if rname not in rounds:
            rounds[rname] = []
        rounds[rname].append(m)

    bye_player = tournament.get("bye_player")

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

    home_goals = request.form.get("home_goals", "").strip()
    away_goals = request.form.get("away_goals", "").strip()

    if home_goals == "" or away_goals == "":
        flash("Both score fields are required.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    try:
        home_goals = int(home_goals)
        away_goals = int(away_goals)
    except ValueError:
        flash("Scores must be numbers.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    if home_goals < 0 or away_goals < 0:
        flash("Scores cannot be negative.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    if home_goals == away_goals:
        flash("Knockout matches cannot end in a draw. Enter a decisive score.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM matches WHERE id = %s AND match_type = 'knockout'
    """, (match_id,))
    match = fetchone_as_dict(cursor)

    if not match:
        conn.close()
        flash("Match not found.", "error")
        return redirect(url_for("dashboard"))

    tid = match["tournament_id"]
    tournament = get_tournament(tid)

    if not tournament or tournament["host"] != session["username"]:
        conn.close()
        flash("Only the host can enter scores.", "error")
        return redirect(url_for("view_knockout", tournament_id=tid))

    winner = match["home_player"] if home_goals > away_goals else match["away_player"]
    loser  = match["away_player"] if home_goals > away_goals else match["home_player"]
    winner_goals = home_goals if home_goals > away_goals else away_goals

    cursor.execute("""
        UPDATE matches
        SET home_goals = %s, away_goals = %s, winner = %s, status = 'completed'
        WHERE id = %s
    """, (home_goals, away_goals, winner, match_id))

    # Fetch all matches in this round (after update applied in-memory)
    cursor.execute("""
        SELECT * FROM matches
        WHERE tournament_id = %s AND match_type = 'knockout' AND round_name = %s
    """, (tid, match["round_name"]))
    round_matches = fetchall_as_dicts(cursor)

    # Consider current match as completed
    all_done = all(
        m["status"] == "completed" or m["id"] == match_id
        for m in round_matches
    )

    if all_done:
        # Collect winners with their goals scored (for bye seeding)
        winners_data = []
        for m in round_matches:
            if m["id"] == match_id:
                winners_data.append({"player": winner, "goals": winner_goals})
            else:
                w = m["winner"]
                g = m["home_goals"] if m["winner"] == m["home_player"] else m["away_goals"]
                winners_data.append({"player": w, "goals": g})

        bye_player = tournament.get("bye_player")

        # Determine next round name
        current_round_num = int(match["round_name"].replace("Round ", ""))
        next_round = f"Round {current_round_num + 1}"

        cursor.execute("""
            SELECT COALESCE(MAX(sequence_order), 0) FROM matches WHERE tournament_id = %s
        """, (tid,))
        seq = (cursor.fetchone()[0] or 0) + 1

        if bye_player:
            # Sort winners by goals scored ascending — lowest scorer plays the bye player
            winners_data_sorted = sorted(winners_data, key=lambda x: x["goals"])
            bye_opponent = winners_data_sorted[0]["player"]   # lowest scorer faces bye player
            remaining = [w["player"] for w in winners_data_sorted[1:]]  # rest go to final

            # Bye player vs lowest scorer
            cursor.execute("""
                INSERT INTO matches (
                    tournament_id, round_name, home_player, away_player,
                    match_type, status, sequence_order
                ) VALUES (%s, %s, %s, %s, 'knockout', 'pending', %s)
            """, (tid, next_round, bye_player, bye_opponent, seq))
            seq += 1

            # Clear bye now — next round is even
            cursor.execute("""
                UPDATE tournaments SET bye_player = NULL WHERE tournament_id = %s
            """, (tid,))

            # Pair remaining winners together
            for i in range(0, len(remaining) - 1, 2):
                cursor.execute("""
                    INSERT INTO matches (
                        tournament_id, round_name, home_player, away_player,
                        match_type, status, sequence_order
                    ) VALUES (%s, %s, %s, %s, 'knockout', 'pending', %s)
                """, (tid, next_round, remaining[i], remaining[i + 1], seq))
                seq += 1

        else:
            all_winners = [w["player"] for w in winners_data]

            if len(all_winners) == 1:
                # Tournament over — crown the champion
                cursor.execute("""
                    UPDATE tournaments SET status = 'finished', winner = %s
                    WHERE tournament_id = %s
                """, (all_winners[0], tid))
            else:
                # Standard pairing — pair winners in order
                for i in range(0, len(all_winners) - 1, 2):
                    cursor.execute("""
                        INSERT INTO matches (
                            tournament_id, round_name, home_player, away_player,
                            match_type, status, sequence_order
                        ) VALUES (%s, %s, %s, %s, 'knockout', 'pending', %s)
                    """, (tid, next_round, all_winners[i], all_winners[i + 1], seq))
                    seq += 1

                # If still odd after pairing (shouldn't happen often but safe)
                if len(all_winners) % 2 == 1:
                    new_bye = all_winners[-1]
                    cursor.execute("""
                        UPDATE tournaments SET bye_player = %s WHERE tournament_id = %s
                    """, (new_bye, tid))

    conn.commit()
    conn.close()

    flash("Knockout result saved.", "success")
    return redirect(url_for("view_knockout", tournament_id=tid))


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

    # Prevent duplicate generation
    cursor.execute("""
        SELECT 1 FROM matches
        WHERE tournament_id = %s AND match_type = 'league'
        LIMIT 1
    """, (tournament_id,))
    existing_match = cursor.fetchone()

    if existing_match:
        conn.close()
        return redirect(url_for("view_league", tournament_id=tournament_id))

    # Create standings rows
    for player in players:
        cursor.execute("""
            INSERT INTO league_standings (tournament_id, username)
            VALUES (%s, %s)
            ON CONFLICT (tournament_id, username) DO NOTHING
        """, (tournament_id, player))

    # Double round-robin: every pair plays twice
    sequence = 1
    for i in range(len(players)):
        for j in range(len(players)):
            if i != j:
                cursor.execute("""
                    INSERT INTO matches (
                        tournament_id, round_name, home_player, away_player,
                        match_type, status, sequence_order
                    )
                    VALUES (%s, %s, %s, %s, 'league', 'pending', %s)
                """, (
                    tournament_id,
                    "League Stage",
                    players[i],
                    players[j],
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

    home_goals = request.form.get("home_goals", "").strip()
    away_goals = request.form.get("away_goals", "").strip()

    if home_goals == "" or away_goals == "":
        flash("Both score fields are required.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    try:
        home_goals = int(home_goals)
        away_goals = int(away_goals)
    except ValueError:
        flash("Scores must be numbers.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    if home_goals < 0 or away_goals < 0:
        flash("Scores cannot be negative.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM matches
        WHERE id = %s AND match_type = 'league'
    """, (match_id,))
    match = fetchone_as_dict(cursor)

    if not match:
        conn.close()
        flash("Match not found.", "error")
        return redirect(url_for("dashboard"))

    tournament = get_tournament(match["tournament_id"])

    if not tournament or tournament["host"] != session["username"]:
        conn.close()
        flash("Only the host can enter scores.", "error")
        return redirect(url_for("view_league", tournament_id=match["tournament_id"]))

    # Update match result
    cursor.execute("""
        UPDATE matches
        SET home_goals = %s,
            away_goals = %s,
            status = 'completed'
        WHERE id = %s
    """, (home_goals, away_goals, match_id))

    # Recalculate standings from scratch for this tournament
    cursor.execute("""
        UPDATE league_standings
        SET played = 0,
            wins = 0,
            draws = 0,
            losses = 0,
            goals_for = 0,
            goals_against = 0,
            goal_difference = 0,
            points = 0
        WHERE tournament_id = %s
    """, (match["tournament_id"],))

    cursor.execute("""
        SELECT *
        FROM matches
        WHERE tournament_id = %s
          AND match_type = 'league'
          AND status = 'completed'
    """, (match["tournament_id"],))
    completed_matches = fetchall_as_dicts(cursor)

    for m in completed_matches:
        home = m["home_player"]
        away = m["away_player"]
        hg = m["home_goals"]
        ag = m["away_goals"]

        # Played / goals
        cursor.execute("""
            UPDATE league_standings
            SET played = played + 1,
                goals_for = goals_for + %s,
                goals_against = goals_against + %s
            WHERE tournament_id = %s AND username = %s
        """, (hg, ag, match["tournament_id"], home))

        cursor.execute("""
            UPDATE league_standings
            SET played = played + 1,
                goals_for = goals_for + %s,
                goals_against = goals_against + %s
            WHERE tournament_id = %s AND username = %s
        """, (ag, hg, match["tournament_id"], away))

        # Result
        if hg > ag:
            cursor.execute("""
                UPDATE league_standings
                SET wins = wins + 1,
                    points = points + 3
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], home))

            cursor.execute("""
                UPDATE league_standings
                SET losses = losses + 1
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], away))

        elif ag > hg:
            cursor.execute("""
                UPDATE league_standings
                SET wins = wins + 1,
                    points = points + 3
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], away))

            cursor.execute("""
                UPDATE league_standings
                SET losses = losses + 1
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], home))

        else:
            cursor.execute("""
                UPDATE league_standings
                SET draws = draws + 1,
                    points = points + 1
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], home))

            cursor.execute("""
                UPDATE league_standings
                SET draws = draws + 1,
                    points = points + 1
                WHERE tournament_id = %s AND username = %s
            """, (match["tournament_id"], away))

    # Recompute goal difference
    cursor.execute("""
        UPDATE league_standings
        SET goal_difference = goals_for - goals_against
        WHERE tournament_id = %s
    """, (match["tournament_id"],))

    conn.commit()
    conn.close()

    flash("Match result saved and standings updated.", "success")
    return redirect(url_for("view_league", tournament_id=match["tournament_id"]))
    
@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("tournament_id", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))