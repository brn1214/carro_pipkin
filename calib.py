import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading, time, sys

# === CONFIGURACION RAPIDA ===
PINS = { 
    'A_FWD': 27, 'A_REV': 4, 
    'B_FWD': 23, 'B_REV': 15, 
    'C_FWD': 6,  'C_REV': 5, 
    'D_FWD': 24, 'D_REV': 25 
}

GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
pwms = {}

for name, pin in PINS.items():
    GPIO.setup(pin, GPIO.OUT)
    pwms[name] = GPIO.PWM(pin, 100)
    pwms[name].start(0)

# HTML INTEGRADO (SLIDER GIGANTE)
PAGE_HTML = b"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
    <style>
        body { background: #111; color: #fff; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        h1 { font-size: 80px; margin: 0; color: #00e5ff; }
        input[type=range] { width: 90%; margin: 40px 0; -webkit-appearance: none; height: 30px; background: #333; border-radius: 15px; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 50px; height: 50px; background: #00e5ff; border-radius: 50%; cursor: pointer; }
        button { padding: 20px 40px; font-size: 24px; background: #d32f2f; color: white; border: none; border-radius: 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div style="margin-bottom:20px; font-size:20px;">POTENCIA (%):</div>
    <h1 id="val">0</h1>
    <input type="range" min="0" max="100" value="0" id="slider" oninput="update(this.value)" onchange="update(this.value)">
    <button onclick="stop()">STOP (0%)</button>

    <script>
        function update(val) {
            document.getElementById('val').innerText = val;
            fetch('/set?val=' + val);
        }
        function stop() {
            document.getElementById('slider').value = 0;
            update(0);
        }
    </script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE_HTML)
        elif self.path.startswith('/set'):
            self.send_response(200); self.end_headers()
            try:
                # Extraer valor /set?val=XX
                val = int(self.path.split('=')[1])
                print(f"Probando potencia: {val}%")
                
                # Mover TODOS los motores hacia adelante
                for name in ['A_FWD', 'B_FWD', 'C_FWD', 'D_FWD']:
                    pwms[name].ChangeDutyCycle(val)
                # Asegurar que reversa este en 0
                for name in ['A_REV', 'B_REV', 'C_REV', 'D_REV']:
                    pwms[name].ChangeDutyCycle(0)
            except: pass

print("CALIBRADOR LISTO: http://pipkin.local:8000")
server = HTTPServer(('0.0.0.0', 8000), Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    GPIO.cleanup()
