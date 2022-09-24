import os
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)


# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///akcijas.db")

#uri = os.getenv("DATABASE_URL")
#if uri.startswith("postgres://"):
#    uri = uri.replace("postgres://", "postgresql://")
#db = SQL(uri)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    # for grand total counting
    g_tt = 0
    # get data from db
    portfolio = db.execute("""
    SELECT id, symbol, name, count
    FROM symbols
    INNER JOIN shares
    ON symbols.id = shares.symbol_id
    WHERE user_id=?
    AND count > 0
    """, user_id)

    # get price for each symbol, shares and price sum for each symbol(sh_tt), user cash bilance, grand total = cash + sh_tt(g_tt)
    for row in portfolio:
        shares = int(row["count"])
        symbol = row["symbol"]
        # get latest price with api
        price = lookup(symbol)["price"]
        # add price dict with symbol price
        row["price"] = price
        # shares price summ total
        row["sh_tt"] = (price * shares)
        # count grand total
        g_tt += row["sh_tt"]

    # get acount bilance
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    # add user cash to total balance
    g_tt += cash[0]["cash"]
    return render_template("index.html", data=portfolio, cash=cash, gtt=g_tt)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # "POST" method
    if request.method == "POST":
        # curent symbol user buyng. convert to uppercase.
        symb = (request.form.get("symbol")).upper()
        # get share count
        share_count = request.form.get("shares")
        # check for nondigit input
        if not share_count.isdigit():
            return apology("shares input isnt digit")
        # convert string value to int
        share_count = int(share_count)
        # Contact API in helpers.py
        api = lookup(symb)
        # validate symbol input
        if not api:
            return apology("missing symbol")
        # validate shares input in form
        if not share_count or not share_count > 0:
            return apology("incorrrect share value")
        # check acount bilance and stock curent price, before alow to buy shares
        bilance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        # cash sum needed for all shares user is buying
        sum = api["price"] * share_count
        # cancel purchase if insuficient funds
        if bilance[0]["cash"] < sum:
            return apology("insufficient funds")
        # change bilance in database
        newBilance = bilance[0]["cash"] - sum
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newBilance, session["user_id"])
        # check symbols table: add curent symbol if not found
        rows = db.execute("SELECT * FROM symbols WHERE symbol = ?", symb)
        if len(rows) != 1:
            db.execute("INSERT INTO symbols (symbol, name) VALUES (?, ?)", symb, api["name"])
        # get symbol_id
        s_id = (db.execute("SELECT id FROM symbols WHERE symbol = ?", symb))[0]["id"]
        # add curent purchase data to history
        db.execute("""
        INSERT INTO history (
        symbol_id,
        shares,
        price,
        transacted,
        user_id)
        VALUES (
        ?,
        ?,
        ?,
        (SELECT DATETIME('now')),
        ?)
        """, s_id, share_count, api["price"], session["user_id"])

        ## update user_shares table in db ##
        # check if user buying curent symbol shares first time
        if not db.execute("SELECT symbol_id FROM shares WHERE user_id = ? AND symbol_id = ?", session["user_id"], s_id):
            db.execute("""
            INSERT INTO shares (
            user_id,
            symbol_id,
            count)
            VALUES (
            ?,
            ?,
            ?)
            """, session["user_id"], s_id, share_count)
        # update share count
        else:
            db.execute("""
            UPDATE shares
            SET count = count + ?
            WHERE user_id = ?
            AND symbol_id = ?
            """, share_count, session["user_id"], s_id)
        # show flash mesage
        flash('Purchased')
        return redirect("/")

    # "GET" method
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # SYMBOL SHARES PRICE TRANSACTED
    # query db for user history data
    data = db.execute("""
    SELECT
        user_id, symbol, shares, price, transacted
    FROM
        history
    INNER JOIN
        symbols
    ON
        symbols.id = history.symbol_id
    WHERE
        user_id = ?
    """, session["user_id"])
    return render_template("history.html", data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # show flash mesage
        flash('Welcome!')
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # "POST" method
    if request.method == "POST":
        data = lookup(request.form.get("symbol"))

        # return if incorrect symbol
        if not data:
            return apology('incorrect symbol', 400)
        # show flash mesage
        flash('Quoted!')
        return render_template("quoted.html", data=data)

    # "GET method"
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # "POST" method
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)
        # Ensure password was submitted correctly
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password provided incorrectly", 400)
        # Ensure username is available
        if db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username")):
            return apology("username unavailable", 400)
        # Generate hash code from given password
        hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        # Add user to database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), hash)
        # show flash mesage
        flash('Registered!')
        return redirect("/login")

    # "GET" method
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    data = db.execute("""
    SELECT id, symbol, name, count
        FROM symbols
        INNER JOIN shares
        ON symbols.id = shares.symbol_id
        WHERE user_id=?
        AND count > 0
        """, user_id)

    # POST method
    if request.method == "POST":
        # validate shares input in form
        if not request.form.get("shares") or not int(request.form.get("shares")) > 0:
            return apology("incorrrect share value")
        # users selected symbol
        symbol = (request.form.get("symbol"))
        # get symblol data
        for row in data:
            if symbol in row["symbol"]:
                s_dict = row
        # validate users symbol input
        if not s_dict:
            return apology("incorrect symbol")

        # amount of shares, user is selling
        shares_sell = int(request.form.get("shares"))
        shares_hold = s_dict["count"]
        # check share amount user is selling
        if shares_sell <= 0 or shares_sell > shares_hold:
            return apology("incorect share amount")
        # Contact API in helpers.py
        api = lookup(symbol)
        # validate symbol input
        if not api:
            return apology("incorrect symbol")
        # cash amount to add users balance for selling shares
        cash_return = api["price"] * shares_sell

        # update users_shares db table
        db.execute("""
        UPDATE shares
        SET count = count - ?
        WHERE user_id = ?
        AND symbol_id = (SELECT id FROM symbols WHERE symbol = ?)
        """, shares_sell, session["user_id"], symbol)

        # update users bilance in db
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", cash_return, session["user_id"])

        # add curent sell data to history table
        db.execute("""
        INSERT INTO history (symbol_id, shares, price, transacted, user_id)
        VALUES (
            (SELECT id FROM symbols WHERE symbol = ?),
            (-1 * ?),
            ?,
            (SELECT DATETIME('now')),
            ?
            )""", symbol, shares_sell, api["price"], session["user_id"])
        # show flash mesage
        flash('Sold!')
        return redirect("/")

    # GET method
    else:
        # count shares for each symbol
        symb_shares = dict()
        for row in data:
            symb_shares[row["symbol"]] = row["count"]
        # give to template, symbols with shares more than 0
        return render_template("sell.html", symb_shares=symb_shares)


@app.route("/cash", methods=["GET", "POST"])
def cash():
    """Add cash to acount"""
    # "POST" method
    if request.method == "POST":

        cash = int(request.form.get("cash"))
        # check user input
        if not cash or cash <= 0:
            return apology("incorrect cash amount")
        # Add cash to user acount
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", cash, session["user_id"])
        flash('Cash added!')
        return redirect("/")

    # "GET" method
    return render_template("addcash.html")
