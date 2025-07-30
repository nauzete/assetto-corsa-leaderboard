"""
server_dinamico.py

Backend Flask completo para Leaderboard de Assetto Corsa con:
• Descarga del leaderboard desde la URL que introduzcas
• Clasificación general y por categorías (panel /admin)
• Panel de administración protegido con login (admin / admin)
• Actualización en tiempo real vía Socket.IO
• Seed sin duplicados y base de datos SQLite
• Solución SSL: verificación desactivada para servidores con certificados inválidos
"""

import os
import requests
import urllib3
from urllib.parse import urlparse, urlunparse

from flask import Flask, jsonify, request, redirect, render_template
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

# 🔧 SOLUCIÓN SSL: Desactivar advertencias de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────── Configuración ───────────────────
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

# ──────────────────── Modelos ─────────────────────────
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

# ──────────────────── Helpers ─────────────────────────
def format_lap(ns):
    if isinstance(ns, (int, float)) and ns > 0:
        ms = int(ns) // 1_000_000
        m, s, ms = ms // 60000, (ms % 60000) // 1000, ms % 1000
        return f"{m}:{s:02d}.{ms:03d}"
    return "--"

def transform_url(u: str) -> str:
    """Convierte /live-timing → /api/live-timings/leaderboard.json"""
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
        (p.scheme, p.netloc, new_path, p.params, p.query, p.fragment)
    )

def best_by_pilot(drivers):
    res = {}
    for d in drivers:
        name = d.get("CarInfo", {}).get("DriverName", "Desconocido")
        for info in (d.get("Cars") or {}).values():
            lap = info.get("BestLap", 0)
            if 0 < lap < res.get(name, 1e18):
                res[name] = lap
    return res

def car_category_of(model_code: str) -> str:
    """Usa categoría asignada o, si no hay, el nombre completo del coche."""
    car = Car.query.filter_by(model_code=model_code).first()
    if car and car.categories.count():
        return car.categories.first().name
    return model_code  # fallback: nombre completo

# ───────────────────── API ────────────────────────────
@app.route("/api/leaderboard", methods=["POST"])
def api_leader():
    api_url = transform_url(request.json.get("url", ""))
    try:
        # 🔧 SOLUCIÓN SSL: Desactivar verificación SSL con verify=False
        print(f"🔗 Conectando a: {api_url}")
        r = requests.get(api_url, timeout=AC_TIMEOUT, verify=False)
        r.raise_for_status()
        print(f"✅ Conexión exitosa - Status: {r.status_code}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return jsonify({"error": f"Conexión fallida: {e}"}), 502

    data     = r.json() or {}
    drivers  = (data.get("ConnectedDrivers") or []) + \
               (data.get("DisconnectedDrivers") or [])
    bests    = best_by_pilot(drivers)

    grouped  = {}
    for d in drivers:
        name = d.get("CarInfo", {}).get("DriverName", "Desconocido")
        for model in (d.get("Cars") or {}):
            cat = car_category_of(model)
            grouped.setdefault(cat, {})[name] = format_lap(bests.get(name, 0))

    # salida: vista general + por categorías
    general = [{"name": n, "bestlap": l}
               for n, l in sorted(
                   {n: format_lap(t) for n, t in bests.items()}.items(),
                   key=lambda x: (x[1] == "--", x[1])
               )]
    categorias = {c: [{"name": n, "bestlap": l}
                      for n, l in sorted(p.items(),
                                         key=lambda x: (x[1] == "--", x[1]))]
                  for c, p in grouped.items()}

    print(f"📊 Procesados {len(general)} pilotos en {len(categorias)} categorías")
    return jsonify({"general": general, "categorias": categorias})

# ─────────────── Frontend ─────────────────
@app.route("/")
def index(): 
    return render_template("index.html")

# ──────────────── Admin y login ──────────────────────
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
        return """
        <div style="max-width:400px;margin:auto;padding-top:3rem;background:#fff;padding:2rem;border-radius:8px;">
            <h3 style="color:#ff3860;">❌ Login fallido</h3>
            <p style="color:#000;">Usuario o contraseña incorrectos.</p>
            <a href='/login' style="color:#3273dc;">← Volver a intentar</a>
        </div>"""
    
    return """
    <div style="max-width:400px;margin:auto;padding-top:3rem;background:#fff;padding:2rem;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
        <h2 style="color:#000;text-align:center;margin-bottom:1.5rem;">🏎️ Admin Panel</h2>
        <form method="post">
            <div style="margin-bottom:1rem;">
                <label style="color:#000;display:block;margin-bottom:0.5rem;font-weight:bold;">Usuario:</label>
                <input name="u" type="text" style="width:100%;padding:0.75rem;border:2px solid #dbdbdb;border-radius:4px;font-size:1rem;" autocomplete="username" required>
            </div>
            <div style="margin-bottom:1.5rem;">
                <label style="color:#000;display:block;margin-bottom:0.5rem;font-weight:bold;">Contraseña:</label>
                <input name="p" type="password" style="width:100%;padding:0.75rem;border:2px solid #dbdbdb;border-radius:4px;font-size:1rem;" autocomplete="current-password" required>
            </div>
            <button type="submit" style="width:100%;padding:0.75rem;background:#3273dc;color:#fff;border:none;border-radius:4px;font-size:1rem;cursor:pointer;font-weight:bold;">
                🔐 Iniciar Sesión
            </button>
        </form>
        <div style="text-align:center;margin-top:1.5rem;padding-top:1rem;border-top:1px solid #dbdbdb;">
            <small style="color:#666;">Usuario por defecto: <strong>admin</strong> / <strong>admin</strong></small><br>
            <a href="/" style="color:#3273dc;text-decoration:none;">← Volver al Leaderboard</a>
        </div>
    </div>
    <style>
        body { background: linear-gradient(135deg, #4a4a4a 0%, #00bfff 100%); min-height: 100vh; margin: 0; font-family: sans-serif; }
        button:hover { background: #2366d1 !important; }
        input:focus { border-color: #3273dc; outline: none; }
    </style>
    """

@app.route("/logout")
def logout():
    logout_user(); return redirect("/")

@login_mgr.unauthorized_handler
def unauthorized(): return redirect("/login")

# ───── Socket.IO: refresco en tiempo real ────────────
@db.event.listens_for(db.session, "after_commit")
def emit_changes(_): 
    socketio.emit("cat_update")
    print("🔄 Emitido evento cat_update via Socket.IO")

# ────────────── Datos iniciales (seed) ───────────────
def seed():
    print("🌱 Inicializando datos...")
    if not User.query.first():
        admin_user = User(username="admin", pw_hash=generate_password_hash("admin"))
        db.session.add(admin_user)
        print("👤 Usuario admin creado")
    
    default_cats = [
        ("GT/Track-Day", "#3273dc"),
        ("Hypercar",     "#ff3860"),
        ("Rally",        "#23d160"),
        ("Concept",      "#ffdd57"),
        ("Formula",      "#9b59b6"),
        ("Drift",        "#e67e22")
    ]
    
    for name, color in default_cats:
        c = Category.query.filter_by(name=name).first()
        if not c:
            db.session.add(Category(name=name, color=color))
            print(f"📂 Categoría '{name}' creada")
        elif c.color != color:
            c.color = color
            print(f"🎨 Color de '{name}' actualizado")
    
    db.session.commit()
    print("✅ Datos inicializados correctamente")

# ─────────────────── Ejecución ───────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed()
    
    print("=" * 60)
    print("🚀 ASSETTO CORSA LEADERBOARD - SERVIDOR ACTIVO")
    print("=" * 60)
    print(f"🌐 Frontend:    http://localhost:{APP_PORT}/")
    print(f"⚙️  Panel Admin: http://localhost:{APP_PORT}/admin")
    print(f"👤 Login:       admin / admin")
    print("🔧 SSL:         Verificación desactivada (verify=False)")
    print("=" * 60)
    
    socketio.run(app, port=APP_PORT, debug=False)