#!/bin/bash
trap "echo '🛑 APAGANDO TODO...'; sudo pkill -f python3; exit" SIGINT

IP=$(hostname -I | awk '{print $1}')

echo "⚡ Configurando WiFi..."
sudo iwconfig wlan0 power off

echo "🛑 LIMPIEZA INICIAL..."
sudo pkill -f python3
sleep 2

echo "🎥 Iniciando Cámara..."
python3 camara.py > /dev/null 2>&1 &
sleep 2

echo "🏎️ Iniciando Motores..."
python3 motor_fi.py > /dev/null 2>&1 &

echo "✅ SISTEMA INICIADO: http://$IP:8000"
echo "👨‍⚕️ ACTIVANDO MONITOR DE RESURRECCIÓN..."

# === BUCLE DE VIGILANCIA ===
while true; do
    sleep 3
    
    # Intentamos conectar al servidor de motores (timeout 1 segundo)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:8000/ping)

    if [ "$HTTP_CODE" == "200" ]; then
        # Todo bien, no hacemos nada
        :
    else
        echo "💀 DETECTADO FALLO (Código: $HTTP_CODE). Resucitando..."
        
        # 1. Matamos el proceso zombie
        sudo pkill -f motor_fi.py
        
        # 2. Esperamos un suspiro para liberar el puerto
        sleep 1
        
        # 3. Arrancamos de nuevo
        python3 motor_fi.py > /dev/null 2>&1 &
        
        echo "✨ Motores reiniciados."
    fi
done
