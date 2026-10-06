
import os, sqlite3, secrets, hashlib, hmac
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
DB = os.environ.get("DATABASE_PATH", "botswana_quick_deals.db")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

CATEGORIES = ["Cars","Phones","Fashion","Property","Food","Services","Other"]
LOCATIONS = ["Gaborone","Francistown","Palapye","Mahalapye","Maun","Kasane","Kanye","Mochudi","Other"]
PLANS = {"Basic": 0, "Featured": 10, "Top 7 Days": 25}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      phone TEXT NOT NULL, password TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS listings(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL, title TEXT NOT NULL,
      price REAL NOT NULL, category TEXT NOT NULL, location TEXT NOT NULL,
      phone TEXT NOT NULL, description TEXT, image TEXT,
      plan TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_payment',
      featured INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS payments(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      listing_id INTEGER NOT NULL, amount REAL NOT NULL,
      provider TEXT, reference TEXT, status TEXT NOT NULL DEFAULT 'pending',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(listing_id) REFERENCES listings(id)
    );
    """)
    con.commit(); con.close()

init_db()

def current_user():
    uid = session.get("uid")
    if not uid: return None
    con=db(); u=con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); con.close()
    return u

def login_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not current_user():
            flash("Please log in first.")
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrap

def admin_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrap

@app.context_processor
def globals():
    return {"current_user": current_user(), "categories": CATEGORIES, "locations": LOCATIONS, "plans": PLANS}

@app.route("/")
def home():
    q=request.args.get("q","").strip()
    cat=request.args.get("category","")
    loc=request.args.get("location","")
    con=db()
    sql="SELECT l.*, u.name seller FROM listings l JOIN users u ON u.id=l.user_id WHERE l.status='published'"
    args=[]
    if q:
        sql += " AND (lower(l.title) LIKE ? OR lower(l.description) LIKE ?)"
        args += [f"%{q.lower()}%", f"%{q.lower()}%"]
    if cat:
        sql += " AND l.category=?"; args.append(cat)
    if loc:
        sql += " AND l.location=?"; args.append(loc)
    sql += " ORDER BY l.featured DESC, l.created_at DESC"
    rows=con.execute(sql,args).fetchall(); con.close()
    return render_template("home.html", listings=rows, q=q, cat=cat, loc=loc)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower()
        phone=request.form["phone"].strip(); pw=request.form["password"]
        if len(pw)<6: flash("Password must be at least 6 characters."); return redirect(url_for("register"))
        con=db()
        try:
            cur=con.execute("INSERT INTO users(name,email,phone,password) VALUES(?,?,?,?)",
                            (name,email,phone,generate_password_hash(pw)))
            con.commit(); session["uid"]=cur.lastrowid
            flash("Account created. Welcome to Botswana Quick Deals!")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.")
        finally: con.close()
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].strip().lower(); pw=request.form["password"]
        con=db(); u=con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone(); con.close()
        if u and check_password_hash(u["password"],pw):
            session["uid"]=u["id"]; return redirect(url_for("dashboard"))
        flash("Wrong email or password.")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    con=db()
    rows=con.execute("SELECT * FROM listings WHERE user_id=? ORDER BY created_at DESC",(session["uid"],)).fetchall()
    con.close(); return render_template("dashboard.html", listings=rows)

@app.route("/sell", methods=["GET","POST"])
@login_required
def sell():
    if request.method=="POST":
        title=request.form["title"].strip(); price=float(request.form["price"])
        cat=request.form["category"]; loc=request.form["location"]; phone=request.form["phone"].strip()
        desc=request.form.get("description","").strip(); plan=request.form["plan"]
        if cat not in CATEGORIES or loc not in LOCATIONS or plan not in PLANS:
            flash("Invalid listing options."); return redirect(url_for("sell"))
        image=None
        f=request.files.get("image")
        if f and f.filename:
            ext=os.path.splitext(secure_filename(f.filename))[1].lower()
            if ext not in [".jpg",".jpeg",".png",".webp"]:
                flash("Image must be JPG, PNG or WEBP."); return redirect(url_for("sell"))
            image=secrets.token_hex(12)+ext; f.save(os.path.join(UPLOAD_DIR,image))
        con=db()
        cur=con.execute("""INSERT INTO listings(user_id,title,price,category,location,phone,description,image,plan,featured)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (session["uid"],title,price,cat,loc,phone,desc,image,plan,1 if plan!="Basic" else 0))
        lid=cur.lastrowid
        amount=PLANS[plan]
        con.execute("INSERT INTO payments(listing_id,amount,provider,status) VALUES(?,?,?,?)",
                    (lid,amount,os.environ.get("PAYMENT_PROVIDER","Not connected"),"pending" if amount else "paid"))
        if amount==0: con.execute("UPDATE listings SET status='published' WHERE id=?",(lid,))
        con.commit(); con.close()
        if amount:
            flash(f"Listing created. Payment of P{amount:.2f} is required before it becomes public.")
            return redirect(url_for("pay", listing_id=lid))
        flash("Listing published!")
        return redirect(url_for("dashboard"))
    return render_template("sell.html")

@app.route("/pay/<int:listing_id>", methods=["GET","POST"])
@login_required
def pay(listing_id):
    con=db()
    l=con.execute("SELECT l.*, p.id payment_id,p.amount,p.status payment_status FROM listings l JOIN payments p ON p.listing_id=l.id WHERE l.id=? AND l.user_id=?",(listing_id,session["uid"])).fetchone()
    con.close()
    if not l: return "Not found",404
    if request.method=="POST":
        ref=request.form["reference"].strip()
        con=db(); con.execute("UPDATE payments SET reference=?,provider=? WHERE id=?",(ref,os.environ.get("PAYMENT_PROVIDER","Manual"),l["payment_id"])); con.commit(); con.close()
        flash("Payment reference submitted. Your listing will publish after payment is verified.")
        return redirect(url_for("dashboard"))
    return render_template("pay.html", listing=l, checkout_url=os.environ.get("PAYMENT_CHECKOUT_URL",""))

@app.route("/webhook/payment", methods=["POST"])
def payment_webhook():
    secret=os.environ.get("PAYMENT_WEBHOOK_SECRET","")
    supplied=request.headers.get("X-Webhook-Secret","")
    if not secret or not hmac.compare_digest(secret,supplied): return jsonify({"ok":False}),401
    data=request.get_json(silent=True) or {}
    reference=str(data.get("reference","")); status=str(data.get("status","")).lower()
    listing_id=data.get("listing_id")
    if status not in ("paid","successful","success") or not listing_id: return jsonify({"ok":False,"error":"bad payload"}),400
    con=db()
    con.execute("UPDATE payments SET status='paid',reference=? WHERE listing_id=?",(reference,listing_id))
    con.execute("UPDATE listings SET status='published' WHERE id=?",(listing_id,))
    con.commit(); con.close()
    return jsonify({"ok":True})

@app.route("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOAD_DIR,name)

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        if request.form["email"]==os.environ.get("ADMIN_EMAIL","admin@botswanaquickdeals.com") and request.form["password"]==os.environ.get("ADMIN_PASSWORD","change-me"):
            session["admin"]=True; return redirect(url_for("admin"))
        flash("Wrong admin credentials.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin",None); return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def admin():
    con=db()
    listings=con.execute("""SELECT l.*,u.name seller,u.email FROM listings l JOIN users u ON u.id=l.user_id ORDER BY l.created_at DESC""").fetchall()
    payments=con.execute("""SELECT p.*,l.title,u.name seller FROM payments p JOIN listings l ON l.id=p.listing_id JOIN users u ON u.id=l.user_id ORDER BY p.created_at DESC""").fetchall()
    users=con.execute("SELECT id,name,email,phone,created_at FROM users ORDER BY created_at DESC").fetchall()
    con.close(); return render_template("admin.html",listings=listings,payments=payments,users=users)

@app.post("/admin/listing/<int:listing_id>/<action>")
@admin_required
def admin_listing(listing_id, action):
    con=db()
    if action=="publish": con.execute("UPDATE listings SET status='published' WHERE id=?",(listing_id,))
    elif action=="hide": con.execute("UPDATE listings SET status='hidden' WHERE id=?",(listing_id,))
    elif action=="delete": con.execute("DELETE FROM listings WHERE id=?",(listing_id,))
    con.commit(); con.close(); return redirect(url_for("admin"))

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
