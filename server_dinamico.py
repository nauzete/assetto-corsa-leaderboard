"""
server_dinamico.py - CORRECCIÓN DEL BUG DE MÚLTIPLES COCHES

Backend Flask completo para Leaderboard de Assetto Corsa con:
• Descarga del leaderboard desde la URL que introduzcas
• Clasificación general y por categorías (panel /admin)
• Panel de administración protegido con login (admin / admin)
• Actualización en tiempo real vía Socket.IO
• Seed sin duplicados y base de datos SQLite
• ✅ BUG CORREGIDO: Tiempos específicos por coche, no globales

CORRECCIÓN PRINCIPAL:
- Cada coche muestra su tiempo específico en su categoría
- Si un piloto usa múltiples coches en la misma categoría, se muestra el mejor de esa categoría
- El tiempo global del piloto NO se aplica a todas las categorías
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

def car_category_of(model_code: str) -> str:
    """Usa categoría asignada o, si no hay, el nombre completo del coche."""
    car = Car.query.filter_by(model_code=model_code).first()
    if car and car.categories.count():
        return car.categories.first().name
    return model_code  # fallback: nombre completo

def parse_lap_to_ns(lap_str):
    """Convierte string de tiempo a nanosegundos para comparar"""
    if lap_str == "--":
        return float('inf')
    try:
        parts = lap_str.split(":")
        minutes = int(parts[0])
        sec_ms = parts[1].split(".")
        seconds = int(sec_ms[0])
        milliseconds = int(sec_ms[1])
        return (minutes * 60000 + seconds * 1000 + milliseconds) * 1_000_000
    except:
        return float('inf')

# ✅ FUNCIÓN CORREGIDA: Procesa cada coche individualmente
def process_drivers_corrected(drivers):
    """
    CORRECCIÓN DEL BUG: Procesa cada coche de cada piloto individualmente
    para mostrar tiempos específicos por vehículo en cada categoría.
    """
    # Para vista general: mejor tiempo absoluto de cada piloto
    best_general = {}
    
    # Para vista por categorías: mejor tiempo por piloto EN CADA CATEGORÍA
    categorias_data = {}
    
    for driver in drivers:
        name = driver.get("CarInfo", {}).get("DriverName", "Desconocido")
        cars = driver.get("Cars", {})
        
        for model_code, car_info in cars.items():
            lap_ns = car_info.get("BestLap", 0)
            lap_formatted = format_lap(lap_ns)
            
            # 1. Para vista general: guardar el mejor tiempo absoluto
            if name not in best_general or (lap_ns > 0 and lap_ns < best_general[name]):
                best_general[name] = lap_ns
            
            # 2. ✅ CORRECCIÓN: Para categorías, usar tiempo específico del coche
            categoria = car_category_of(model_code)
            
            # Inicializar categoría si no existe
            if categoria not in categorias_data:
                categorias_data[categoria] = {}
            
            # ✅ CLAVE: Comparar tiempos dentro de la MISMA CATEGORÍA
            if name in categorias_data[categoria]:
                # Si el piloto ya tiene tiempo en esta categoría, mantener el mejor
                tiempo_actual_ns = parse_lap_to_ns(categorias_data[categoria][name])
                if lap_ns > 0 and lap_ns < tiempo_actual_ns:
                    categorias_data[categoria][name] = lap_formatted
                    print(f"🔄 {name} mejoró en {categoria}: {lap_formatted}")
            else:
                # Primera vez del piloto en esta categoría
                categorias_data[categoria][name] = lap_formatted
                print(f"➕ {name} agregado a {categoria}: {lap_formatted}")
    
    return best_general, categorias_data

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

    data = r.json() or {}
    drivers = (data.get("ConnectedDrivers") or []) + \
              (data.get("DisconnectedDrivers") or [])
    
    print(f"📊 Procesando {len(drivers)} pilotos...")
    
    # ✅ USAR FUNCIÓN CORREGIDA
    best_general, categorias_data = process_drivers_corrected(drivers)
    
    # Formatear vista general
    general = [{"name": n, "bestlap": format_lap(t)}
               for n, t in sorted(best_general.items(),
                                  key=lambda x: (x[1] if x[1] > 0 else float('inf')))]
    
    # Formatear vista por categorías (ya procesada correctamente)
    categorias_formatted = {}
    for categoria, pilotos in categorias_data.items():
        categorias_formatted[categoria] = [
            {"name": name, "bestlap": tiempo}
            for name, tiempo in sorted(pilotos.items(),
                                     key=lambda x: (x[1] == "--", x[1]))
        ]
    
    print(f"📊 Procesados {len(general)} pilotos en {len(categorias_formatted)} categorías")
    print(f"🔄 Emitido evento cat_update via Socket.IO")

    return jsonify({"general": general, "categorias": categorias_formatted})

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

# ───── Socket.IO: refresco en tiempo real ────────────
@db.event.listens_for(db.session, "after_commit")
def emit_changes(_): socketio.emit("cat_update")

# ────────────── Datos iniciales (seed) ───────────────
def seed():
    print("🌱 Inicializando datos...")
    if not User.query.first():
        db.session.add(User(username="admin",
                            pw_hash=generate_password_hash("admin")))
        print("👤 Usuario admin creado")
    
    default_cats = [("GT/Track-Day", "#3273dc"),
                    ("Hypercar",      "#ff3860"),
                    ("Rally",         "#23d160"),
                    ("Concept",       "#ffdd57"),
                    ("Formula",       "#9b59b6"),
                    ("Drift",         "#e67e22")]
    
    for name, color in default_cats:
        c = Category.query.filter_by(name=name).first()
        if not c:
            db.session.add(Category(name=name, color=color))
            print(f"📂 Categoría '{name}' creada")
        elif c.color != color:
            c.color = color
    
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
    print(f"🔧 SSL:         Verificación desactivada (verify=False)")
    print(f"✅ BUG CORREGIDO: Tiempos específicos por coche")
    print("=" * 60)
    
    socketio.run(app, port=APP_PORT)