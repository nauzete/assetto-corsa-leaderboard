# 🏎️ Instalación de Dependencias - Assetto Corsa Leaderboard

Este documento explica cómo instalar automáticamente todas las dependencias necesarias para tu proyecto de leaderboard de Assetto Corsa usando los scripts proporcionados.

## 📦 Archivos de Instalación

Se incluyen **3 métodos** de instalación:

1. **`install-dependencies.sh`** - Script para Linux/macOS/WSL
2. **`install-dependencies.bat`** - Script para Windows
3. **`requirements.txt`** - Archivo estándar de Python (multiplataforma)

## 🚀 Instalación Rápida

### **Opción A: Windows**
```batch
# Doble clic en el archivo o ejecutar en CMD/PowerShell:
install-dependencies.bat
```

### **Opción B: Linux/macOS/WSL**
```bash
# Dar permisos de ejecución y ejecutar:
chmod +x install-dependencies.sh
./install-dependencies.sh
```

### **Opción C: Método Estándar Python (Recomendado)**
```bash
# Multiplataforma - funciona en Windows, Linux y macOS:
pip install -r requirements.txt
```

## 🛠️ Instalación con Entorno Virtual (Recomendado)

Para evitar conflictos entre proyectos, usa un entorno virtual:

### **Windows:**
```batch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### **Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

## 📋 Dependencias Incluidas

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| **Flask** | 2.3.3 | Framework web principal |
| **Flask-SQLAlchemy** | 3.0.5 | Base de datos ORM |
| **Flask-Admin** | 1.6.1 | Panel de administración |
| **Flask-SocketIO** | 5.3.6 | WebSockets para tiempo real |
| **Flask-CORS** | 4.0.0 | Manejo de CORS |
| **Flask-Login** | 0.6.3 | Sistema de autenticación |
| **Requests** | 2.31.0 | Cliente HTTP para API de Assetto Corsa |
| **Eventlet** | 0.33.3 | Servidor async para SocketIO |
| **Werkzeug** | 2.3.7 | WSGI toolkit para Flask |
| **urllib3** | 2.0.7 | Utilidades HTTP (SSL bypass) |

## ✅ Verificación de Instalación

Después de ejecutar cualquier script, verifica que todo funcione:

```bash
# Ejecutar la aplicación
python server_dinamico.py
```

Deberías ver:
```
🚀 ASSETTO CORSA LEADERBOARD - SERVIDOR ACTIVO
🌐 Frontend:    http://localhost:5000/
⚙️  Panel Admin: http://localhost:5000/admin
```

## 🔧 Solución de Problemas

### **Error: "Python no encontrado"**
- **Windows:** Instala Python desde https://www.python.org/downloads/
- **Linux:** `sudo apt install python3 python3-pip`
- **macOS:** `brew install python3`

### **Error: "pip no encontrado"**
```bash
# Linux/macOS
sudo apt install python3-pip  # Ubuntu/Debian
brew install python3          # macOS

# Windows - reinstalar Python con pip incluido
```

### **Error: "Permission denied"**
- **Linux/macOS:** Ejecuta `chmod +x install-dependencies.sh`
- **Windows:** Ejecuta CMD como Administrador

### **Error durante la instalación**
```bash
# Actualizar pip primero
python -m pip install --upgrade pip

# Instalar sin cache
pip install --no-cache-dir -r requirements.txt

# Instalar con usuario (sin permisos admin)
pip install --user -r requirements.txt
```

## 🎯 Estructura del Proyecto

Después de la instalación, tu proyecto debería tener esta estructura:

```
assetto-corsa-leaderboard/
├── server_dinamico.py          # Backend Flask
├── requirements.txt            # Dependencias
├── install-dependencies.sh     # Script Linux/macOS
├── install-dependencies.bat    # Script Windows
├── templates/
│   └── index.html             # Frontend HTML
├── static/
│   ├── style.css              # Estilos CSS
│   └── script.js              # JavaScript
└── leaderboard.db             # Base de datos (se crea automáticamente)
```

## 🏁 ¡Listo para Usar!

Una vez instaladas las dependencias:

1. **Ejecuta:** `python server_dinamico.py`
2. **Abre:** http://localhost:5000/ (Frontend)
3. **Admin:** http://localhost:5000/admin (admin/admin)
4. **Disfruta** de tu leaderboard profesional de Assetto Corsa

---
**💡 Tip:** Guarda estos archivos junto a tu proyecto para futuras instalaciones o cuando compartas el código con otros usuarios.