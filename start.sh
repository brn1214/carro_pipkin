#!/bin/bash

# 1. OBTENER IP AUTOMATICAMENTE
IP=$(hostname -I | awk '{print $1}')

echo "========================================"
echo "   🚀 INICIANDO PIPKIN ROVER V2.1"
echo "========================================"

# 2. LIMPIEZA
echo "🧹 Matando procesos viejos..."
sudo pkill -f python3

# 3. CAMARA (SILENCIO REAL DESDE BASH)
# La variable LIBCAMERA_LOG_LEVELS=none aqui SI funciona
echo "🎥 Iniciando Cámara..."
LIBCAMERA_LOG_LEVELS=none python3 camara.py &

# 4. MOTORES
echo "🏎️ Iniciando Motores..."
python3 motor.py &

# 5. MOSTRAR LA URL CORRECTA
echo ""
echo "✅ SISTEMA LISTO."
echo "⚠️  IMPORTANTE: No uses 'pipkin.local', es lento."
echo "👉  USA ESTE LINK EN TU CELULAR:"
echo ""
echo "    http://$IP:8000"
echo ""
echo "========================================"

# Mantener script vivo
wait
