#!/bin/bash

echo "Actualizando pip..."
python3 -m pip install --upgrade pip

echo "Instalando dependencias desde requirements.txt..."
pip3 install -r requirements.txt

echo "¡Instalación completa!"