#!/bin/bash

echo "🛑 INICIANDO PROTOCOLO DE APAGADO SEGURO..."

# 1. INTENTO DE CIERRE SUAVE
# Enviamos SIGINT (equivalente a Ctrl+C). 
# Esto permite que tu script de Python detecte el cierre y ejecute GPIO.cleanup()
# para apagar los motores y liberar la cámara correctamente.
echo "1. Deteniendo Rover y Cámara..."
sudo pkill -SIGINT -f "python3 rover.py"

# Esperamos 3 segundos para darle tiempo a la cámara de cerrarse
sleep 3

# 2. CIERRE FORZADO (POR SI ACASO)
# Si algo se quedó colgado, lo matamos a la fuerza para que no impida el apagado.
sudo pkill -f python3
sudo pkill -f libcamera

# 3. PROTECCIÓN DE TARJETA SD (CRÍTICO)
# 'sync' fuerza a la Raspberry a escribir cualquier dato pendiente en la RAM hacia la SD.
# Si no haces esto y apagas, se corrompe la memoria.
echo "2. Sincronizando datos a la SD..."
sync
sync

# 4. LIMPIEZA DE CACHÉ
# Borramos la basura de la RAM (opcional, pero pedido por ti).
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

# 5. APAGADO DEFINITIVO
echo "😴 Buenas noches, Pipkin. Apagando..."
sleep 1
sudo poweroff
