#!/bin/bash

echo "🔧 INICIANDO PROTOCOLO DE ALTO RENDIMIENTO..."

# 1. WIFI: APAGAR AHORRO DE ENERGÍA (Vital para el lag)
# Esto evita que la antena se duerma cada vez que hay un silencio de 100ms
if sudo iwconfig wlan0 power off; then
    echo "✅ WiFi Power Management: OFF (Modo Baja Latencia)"
else
    echo "⚠️ No se pudo configurar el WiFi (¿Tal vez ya estaba listo?)"
fi

# 2. CPU: FORZAR MODO 'PERFORMANCE'
# Evita que el procesador baje de velocidad. Siempre al máximo.
echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
echo "✅ CPU: Modo Performance Activo (Todos los núcleos a tope)"

# 3. RAM: LIMPIEZA DE CACHÉ
# Libera RAM ocupada por archivos basura del sistema
sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
echo "✅ RAM: Caché liberada"

echo "🚀 RASPBERRY LISTA PARA LA CARRERA."
