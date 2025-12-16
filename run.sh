#!/bin/bash
echo "🧹 Matando procesos viejos..."
sudo pkill -f python3

echo "🧽 Limpiando memoria RAM..."
sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

echo "🚀 Iniciando Rover..."
python3 rover.py
