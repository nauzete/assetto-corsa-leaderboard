@echo off
echo Actualizando pip...
python -m pip install --upgrade pip

echo Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

echo ¡Instalación completa!
pause