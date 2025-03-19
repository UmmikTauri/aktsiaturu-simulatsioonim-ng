from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from tinydb import TinyDB, Query
import yfinance as yf
import datetime
from flask_bcrypt import Bcrypt

# Initialize databases
DB_FILE = "stocks.json"
db = TinyDB(DB_FILE)
users_db = TinyDB("users.json")
portfolio_db = TinyDB("portfolio.json")

tickers = ["AAPL", "GOOGL", "TSLA", "AMZN"]  # Sample tickers

# Function to fetch stock data
def fetch_stock_data(tickers, days=30):
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)
    db.truncate()

    for ticker in tickers:
        stock = yf.Ticker(ticker)
        history = stock.history(start=start_date, end=end_date)

        if not history.empty:
            latest = history.iloc[-1]
            previous = history.iloc[-2] if len(history) > 1 else latest
            change_percent = ((latest["Close"] - previous["Close"]) / previous["Close"]) * 100

            db.insert({
                "ticker": ticker,
                "date": str(latest.name.date()),
                "open": latest["Open"],
                "close": latest["Close"],
                "high": latest["High"],
                "low": latest["Low"],
                "change_percent": round(change_percent, 2)
            })

fetch_stock_data(tickers)

# Initialize Flask app and Bcrypt for password hashing
app = Flask(__name__)
app.secret_key = "supersecretkey"  # Secure this in a real application
bcrypt = Bcrypt(app)

# Set transaction fee percentage
TRANSACTION_FEE = 0.01  # 1%

# Challenge duration: 1 week in seconds
CHALLENGE_DURATION = 60 * 60 * 24 * 7  # 1 week

# Route for main page
@app.route("/")
def index():
    stocks = db.all()
    balance = 0

    if "username" in session:
        User = Query()
        user = users_db.get(User.username == session["username"])
        balance = user["balance"]

    return render_template("index.html", stocks=stocks, balance=balance)

# Route for challenge page
@app.route("/challenge", methods=["GET", "POST"])
def challenge():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    # If challenge_start_time doesn't exist, set it to the current time when the user starts the challenge
    current_time = int(datetime.datetime.now().timestamp())

    if "challenge_start_time" not in user:
        user["challenge_start_time"] = current_time
        users_db.update(user, User.username == session["username"])
        flash("Challenge started! You have 7 days to earn as much as possible.", "success")

    challenge_start_time = user["challenge_start_time"]
    challenge_money = user.get("challenge_money", 0)

    # Challenge duration: 7 days
    if current_time - challenge_start_time > CHALLENGE_DURATION:
        # If the challenge has expired, reset progress
        user["challenge_money"] = 0
        user["challenge_start_time"] = current_time  # Reset start time to now
        user["portfolio"] = {}  # Optionally reset portfolio (comment if not required)
        users_db.update(user, User.username == session["username"])
        flash("The challenge has expired! Start again.", "warning")
        return redirect(url_for("challenge"))  # Redirect back to the challenge page

    return render_template("challenge.html", challenge_money=challenge_money)

# Route for PVP competition
@app.route("/pvp", methods=["GET", "POST"])
def pvp():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    if request.method == "POST":
        opponent_username = request.form["opponent_username"]
        opponent = users_db.get(User.username == opponent_username)

        if opponent:
            user_portfolio_value = sum([stock_data["close"] * quantity for ticker, quantity in user["portfolio"].items()])
            opponent_portfolio_value = sum([stock_data["close"] * quantity for ticker, quantity in opponent["portfolio"].items()])

            if user_portfolio_value > opponent_portfolio_value:
                flash("Sa võitsid mõõduvõtmise!", "success")
            elif user_portfolio_value < opponent_portfolio_value:
                flash("Sa kaotasid mõõduvõtmise!", "error")
            else:
                flash("Mõõduvõtmine lõppes viigiga!", "info")
        else:
            flash("Vastast ei leitud!", "error")

    return render_template("pvp.html")

# Route for competition (leaderboard)
@app.route("/competition")
def competition():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    # Jälgime parimaid sooritusi kasumite järgi
    users = users_db.all()
    top_performers = sorted(users, key=lambda u: u["balance"], reverse=True)[:3]

    return render_template("competition.html", top_performers=top_performers)

# Route for tournament leaderboard
@app.route("/tournament")
def tournament():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    # Jälgime turniiri seisu ja edetabelit
    tournament_leaderboard = sorted(users_db.all(), key=lambda u: u["balance"], reverse=True)

    return render_template("tournament.html", leaderboard=tournament_leaderboard)

# Route for stock detail page
@app.route("/stock/<ticker>")
def stock_detail(ticker):
    stock_data = db.get(Query().ticker == ticker)
    return render_template("stock_detail.html", stock=stock_data)

# Route for portfolio page
@app.route("/portfolio")
def portfolio():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    # Check if portfolio exists, if not create an empty one
    if "portfolio" not in user:
        user["portfolio"] = {}  # Create empty portfolio if not exists

    # Update the database if portfolio is empty or missing
    users_db.update({"portfolio": user["portfolio"]}, User.username == session["username"])

    return render_template("portfolio.html", balance=user["balance"], portfolio=user["portfolio"])


@app.route("/restart", methods=["POST"])
def restart():
    if "username" not in session:
        return redirect(url_for("login"))

    User = Query()
    user = users_db.get(User.username == session["username"])

    # Lähtesta saldo ja portfell
    user["balance"] = 10000  # Taastame algse saldo
    user["portfolio"] = {}   # Kustutame kõik varud
    user["challenge_money"] = 0  # Lähtestame väljakutse edusammud
    user["challenge_start_time"] = None  # Lähtestame ajad
    users_db.update(user, User.username == session["username"])

    flash("Mäng on lähtestatud. Saldo on taastatud ja tehingud kustutatud.", "success")
    return redirect(url_for("index"))
# Route for buying stocks
@app.route("/buy/<ticker>", methods=["POST"])
def buy_stock(ticker):
    if "username" not in session:
        return redirect(url_for("login"))

    quantity = request.form.get("quantity")

    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash("Vale kogus!", "error")
        return redirect(url_for("index"))

    quantity = int(quantity)
    User = Query()
    user = users_db.get(User.username == session["username"])
    stock_data = db.get(Query().ticker == ticker)

    if not stock_data:
        flash("Aktsiat ei leitud!", "error")
        return redirect(url_for("index"))

    stock_price = stock_data["close"]
    total_price = stock_price * quantity
    transaction_fee = total_price * TRANSACTION_FEE
    total_price_with_fee = total_price + transaction_fee

    if user["balance"] >= total_price_with_fee:
        user["balance"] -= total_price_with_fee
        if ticker in user["portfolio"]:
            user["portfolio"][ticker] += quantity
        else:
            user["portfolio"][ticker] = quantity

        users_db.update({"balance": user["balance"], "portfolio": user["portfolio"]}, User.username == session["username"])
        flash(f"Õnnestus osta {quantity} aktsiat {ticker}!", "success")
    else:
        flash("Ei piisa rahast!", "error")

    return redirect(url_for("index"))

# Route for selling stocks
@app.route("/sell/<ticker>", methods=["POST"])
def sell_stock(ticker):
    if "username" not in session:
        return redirect(url_for("login"))

    quantity = request.form.get("quantity")

    if not quantity or not quantity.isdigit() or int(quantity) <= 0:
        flash("Vale kogus!", "error")
        return redirect(url_for("index"))

    quantity = int(quantity)
    User = Query()
    user = users_db.get(User.username == session["username"])
    stock_data = db.get(Query().ticker == ticker)

    if not stock_data:
        flash("Aktsiat ei leitud!", "error")
        return redirect(url_for("index"))

    stock_price = stock_data["close"]
    transaction_fee = stock_price * quantity * TRANSACTION_FEE
    total_price_with_fee = stock_price * quantity - transaction_fee

    if ticker in user["portfolio"] and user["portfolio"][ticker] >= quantity:
        user["balance"] += total_price_with_fee
        user["portfolio"][ticker] -= quantity

        if user["portfolio"][ticker] == 0:
            del user["portfolio"][ticker]  # Remove stock if all shares are sold

        users_db.update({"balance": user["balance"], "portfolio": user["portfolio"]}, User.username == session["username"])
        flash(f"Õnnestus müüa {quantity} aktsiat {ticker}!", "success")
    else:
        flash("Pole piisavalt aktsiaid müümiseks!", "error")

    return redirect(url_for("index"))

# Register route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = bcrypt.generate_password_hash(request.form["password"]).decode('utf-8')
        User = Query()

        if users_db.search(User.username == username):
            flash("Kasutaja eksisteerib!", "error")
            return redirect(url_for("register"))

        users_db.insert({"username": username, "password": password, "balance": 10000, "portfolio": {}})
        flash("Konto edukalt loodud! Palun logige sisse.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        User = Query()
        user = users_db.get(User.username == username)

        if user and bcrypt.check_password_hash(user["password"], password):
            session["username"] = username
            flash("Sisse logitud edukalt!", "success")
            return redirect(url_for("index"))
        else:
            flash("Vale kasutajanimi või parool!", "error")

    return render_template("login.html")

# Logout route
@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logitud välja edukalt!", "success")
    return redirect(url_for("index"))

# Route to fetch real-time stock data for the frontend
@app.route("/get_stock_data")
def get_stock_data():
    stock_data = []
    for ticker in tickers:
        stock = yf.Ticker(ticker)
        latest_data = stock.history(period="1d").iloc[-1]
        stock_data.append({
            "ticker": ticker,
            "price": latest_data["Close"],
            "change_percent": round(((latest_data["Close"] - latest_data["Open"]) / latest_data["Open"]) * 100, 2)
        })
    return jsonify({"stocks": stock_data})

# Route for learning page
@app.route("/learning")
def learning():
    # Õppepeatükid
    lessons = [
        {"title": "Aktsiate ostmine ja müümine", "content": "Saab kaubelda nii käsitsi nr sisestades, kui ka hotkey-sid kasutades. Pärast ostu on võimalik oma avatud ostupositsiooni vaadata portfoolio nupule vajutades. Seal samas on ka kajastatud lõpetatud tehingud."},
        {"title": "Hotkeyd", "content": "Ostmiseks klahv(1)=10, klahv(2)=100, klahv(3)=1000. Müümiseks klahv(4)=-10, klahv(5)=-100, klahv(6)=-1000."},
        {"title": "Tehnilise analüüsi huvilistele: Tradingview tutvustus", "content": "......"},
        {"title": "Miks on kindla investeerimisstrateegia omamine vajalik", "content": "......."},
        {"title": "YahooFinance tutvustus", "content": "......"}
    ]

    return render_template("learning.html", lessons=lessons)


# Start the app
if __name__ == "__main__":
    app.run(debug=True)
