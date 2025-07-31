import os
import requests
from urllib.parse import urlparse, urlunparse
import urllib3

from flask import Flask, jsonify, request, render_template, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import (
    LoginManager, UserMixin, login_user,
    current_user, logout_user
)
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

APP_PORT   = 5000
AC_TIMEOUT = 10
DB_URI     = "sqlite:///leaderboard.db"
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SQLALCHEMY_DATABASE_URI=DB_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)

db         = SQLAlchemy(app)
CORS(app)
socketio   = SocketIO(app, cors_allowed_origins="*")

login_mgr  = LoginManager(app)
login_mgr.login_view = "login_route"

# ---- Modelos ----
car_category = db.Table(
    "car_category",
    db.Column("category_id", db.Integer,
              db.ForeignKey("categories.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("car_id", db.Integer,
              db.ForeignKey("cars.id", ondelete="CASCADE"),
              primary_key=True)
)

class Category(db.Model):
    __tablename__ = "categories"
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(60), unique=True, nullable=False)
    color = db.Column(db.String(7),  default="#cccccc")
    cars  = db.relationship(
        "Car", secondary=car_category,
        back_populates="categories", lazy="dynamic"
    )

class Car(db.Model):
    __tablename__ = "cars"
    id         = db.Column(db.Integer, primary_key=True)
    model_code = db.Column(db.String(120), unique=True, nullable=False)
    label      = db.Column(db.String(120))
    categories = db.relationship(
        "Category", secondary=car_category,
        back_populates="cars", lazy="dynamic"
    )

class User(db.Model, UserMixin):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    pw_hash  = db.Column(db.String(255), nullable=False)
    role     = db.Column(db.String(20), default="admin")

    def verify(self, pwd): return check_password_hash(self.pw_hash, pwd)

@login_mgr.user_loader
def load_user(uid): return User.query.get(int(uid))


def format_lap(ns):
    if isinstance(ns, (int, float)) and ns > 0:
        ms = int(ns) // 1_000_000
        m, s, ms = ms // 60000, (ms % 60000) // 1000, ms % 1000
        return f"{m}:{s:02d}.{ms:03d}"
    return "--"

def transform_url(u: str) -> str:
    if not u:
        return ""
    if "/api/live-timings/leaderboard.json" in u:
        return u.strip()
    p = urlparse(u)
    path = p.path.rstrip("/")
    if path.endswith("/live-timing"):
        path = path[:-13]
    new_path = f"{path}/api/live-timings/leaderboard.json"
    return urlunparse(
        ("http", p.netloc, new_path, p.params, p.query, p.fragment)
    ) if p.scheme in ["http", "https"] else u  # fuerza HTTP si es https

def car_category_of(model_code: str) -> str:
    car = Car.query.filter_by(model_code=model_code).first()
    if car and car.categories.count():
        return car.categories.first().name
    return model_code  # fallback: nombre completo del coche

# ======= BUGFIX: Mejor tiempo por coche/categoría y general correcto =======

@app.route("/api/leaderboard", methods=["POST"])
def api_leader():
    api_url = transform_url(request.json.get("url", ""))
    try:
        print(f"🔗 Conectando a {api_url}")
        r = requests.get(api_url, timeout=AC_TIMEOUT, verify=False)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ ERROR {e}")
        return jsonify({"error": f"Conexión fallida: {e}"}), 502

    data = r.json() or {}
    drivers = (data.get("ConnectedDrivers") or []) + (data.get("DisconnectedDrivers") or [])

    best_general = {}  # name → mejor lap_ns > 0
    categorias_data = {}  # categoria → { piloto: mejor lap formateado en ese coche/categoría }

    for driver in drivers:
        name = driver.get("CarInfo", {}).get("DriverName", "Desconocido")
        cars = driver.get("Cars", {})
        for model_code, car_info in cars.items():
            lap_ns = car_info.get("BestLap", 0)
            lap_formatted = format_lap(lap_ns)
            # General: SOLO laps válidos (>0)
            if lap_ns > 0:
                if name not in best_general or lap_ns < best_general[name]:
                    best_general[name] = lap_ns
            # Categoría: asignar mejor lap sólo de ese coche/categoría
            categoria = car_category_of(model_code)
            if categoria not in categorias_data:
                categorias_data[categoria] = {}
            prev_lap_str = categorias_data[categoria].get(name)
            # Comparar laps previos con el nuevo (solo válidos)
            if lap_ns > 0:
                if prev_lap_str and prev_lap_str != "--":
                    # Convertir tiempo previo a ns
                    parts = prev_lap_str.split(":")
                    if len(parts) == 2 and "." in parts[1]:
                        mm = int(parts[0])
                        ss, ms = map(int, parts[1].split("."))
                        prev_ns = (mm * 60 + ss) * 1000 + ms
                        prev_ns *= 1_000_000
                        if lap_ns < prev_ns:
                            categorias_data[categoria][name] = lap_formatted
                    else:
                        categorias_data[categoria][name] = lap_formatted
                else:
                    categorias_data[categoria][name] = lap_formatted
            elif not prev_lap_str:
                categorias_data[categoria][name] = "--"

    general = [
        {"name": n, "bestlap": format_lap(t)}
        for n, t in sorted(
            best_general.items(),
            key=lambda x: (format_lap(x[1]) == "--", format_lap(x[1]))
        )
    ]

    categorias_formatted = {}
    for categoria, pilotos in categorias_data.items():
        categorias_formatted[categoria] = [
            {"name": name, "bestlap": tiempo}
            for name, tiempo in sorted(
                pilotos.items(), key=lambda x: (x[1] == "--", x[1])
            )
        ]

    # Devuelve ambos para toggle general/categorías en frontend
    return jsonify({"general": general, "categorias": categorias_formatted})

# ---- Frontend ----
from flask import render_template
@app.route("/")
def index():
    # Asegúrate que existe templates/index.html
    return render_template("index.html")

# ---- Admin/Panel/Login ----
class SecureView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "admin"

admin = Admin(app, name="AC Leaderboard", template_mode="bootstrap4")
admin.add_view(SecureView(Category, db.session, category="Gestión"))
admin.add_view(SecureView(Car,      db.session, category="Gestión"))

@app.route("/login", methods=["GET", "POST"])
def login_route():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["u"]).first()
        if u and u.verify(request.form["p"]):
            login_user(u)
            return redirect(request.args.get("next") or "/admin")
        return "<h3>Login fallido</h3><a href='/login'>Volver</a>"
    return '''
    <form method="post" style="max-width:320px;margin:auto;padding-top:3rem">
        <h2>Iniciar sesión</h2><br>
        <label>Usuario:<input name="u" class="input"></label><br>
        <label>Contraseña:<input name="p" type="password" class="input"></label><br><br>
        <button class="button is-info">Entrar</button>
    </form>'''

@app.route("/logout")
def logout():
    logout_user(); return redirect("/")

@login_mgr.unauthorized_handler
def unauthorized(): return redirect("/login")

@db.event.listens_for(db.session, "after_commit")
def emit_changes(_): socketio.emit("cat_update")

def seed():
    if not User.query.first():
        db.session.add(User(username="admin",
                            pw_hash=generate_password_hash("admin")))
    default_cats = [("GT/Track-Day", "#3273dc"),
                    ("Hypercar",      "#ff3860"),
                    ("Rally",         "#23d160"),
                    ("Concept",       "#ffdd57")]
    for name, color in default_cats:
        c = Category.query.filter_by(name=name).first()
        if not c:
            db.session.add(Category(name=name, color=color))
        elif c.color != color:
            c.color = color
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all(); seed()
    print(f"🚀  http://localhost:{APP_PORT}   (admin/admin)")
    socketio.run(app, port=APP_PORT)
    