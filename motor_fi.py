import sys, traceback, time, subprocess
import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading

print(">>> 🏎️ MOTORES LISTOS (MODO SILENCIOSO)")

# === CONFIGURACION PINES ===
PINS = { 
    'A': {'FWD': 25, 'REV': 24}, 
    'B': {'FWD': 6,  'REV': 5},  
    'C': {'FWD': 4,  'REV': 27}, 
    'D': {'FWD': 15, 'REV': 23}  
}
FREQ = 50  # 50Hz para mejor torque

# Variables de Estado
target_x, target_y, target_s = 0.0, 0.0, 40
current_x, current_y = 0.0, 0.0
FACTOR_INERCIA = 0.095

# === SETUP GPIO ===
try:
    GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
    pwms = {}
    for n, d in PINS.items():
        GPIO.setup(d['FWD'], GPIO.OUT); GPIO.setup(d['REV'], GPIO.OUT)
        pwms[f"{n}_FWD"] = GPIO.PWM(d['FWD'], FREQ)
        pwms[f"{n}_REV"] = GPIO.PWM(d['REV'], FREQ)
        pwms[f"{n}_FWD"].start(0); pwms[f"{n}_REV"].start(0)
except:
    traceback.print_exc(); sys.exit(1)

try:
    with open('index.html', 'rb') as f: PAGE_HTML = f.read()
except: PAGE_HTML = b"Error index"

last_interaction = time.time()

# === FUNCION MOTORES ===
def apply_motors(x, y, max_power):
    y = -y 
    limit = max_power / 100.0
    if abs(y) < 0.1: left, right = x * 0.8, -x * 0.8 
    else: 
        if x > 0: left, right = y, y * (1.0 - abs(x))
        else: left, right = y * (1.0 - abs(x)), y
    raw_l, raw_r = left * 100 * limit, right * 100 * limit

    def drive(name, val):
        target = 0; min_v = 7
        if abs(val) > 1: target = min_v + (abs(val) * (100 - min_v) / 100)
        duty = int(min(100, target))
        pf = pwms[f"{name}_FWD"]; pr = pwms[f"{name}_REV"]
        if val > 0: ff, fr = duty, 0
        else: ff, fr = 0, duty
        try: pf.ChangeDutyCycle(ff); pr.ChangeDutyCycle(fr)
        except: pass

    drive('A', raw_l); drive('C', raw_l); drive('B', raw_r); drive('D', raw_r)

# === HILO DE FISICA (Sin Prints) ===
def physics_loop():
    global current_x, current_y
    while True:
        diff_x = target_x - current_x
        if abs(diff_x) < FACTOR_INERCIA: current_x = target_x
        else: current_x += FACTOR_INERCIA if diff_x > 0 else -FACTOR_INERCIA
        
        diff_y = target_y - current_y
        if abs(diff_y) < FACTOR_INERCIA: current_y = target_y
        else: current_y += FACTOR_INERCIA if diff_y > 0 else -FACTOR_INERCIA

        apply_motors(current_x, current_y, target_s)
        time.sleep(0.05)

threading.Thread(target=physics_loop, daemon=True).start()

# === WATCHDOG (FRENO RAPIDO 0.4s) ===
def safety_monitor():
    global target_x, target_y
    while True:
        # Si pasan 0.4s sin señal, frenamos (para evitar lag fantasma)
        if time.time() - last_interaction > 0.4:
            if target_x != 0 or target_y != 0:
                target_x, target_y = 0.0, 0.0
        time.sleep(0.1)

threading.Thread(target=safety_monitor, daemon=True).start()

# === SERVIDOR ===
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return # Silencia logs HTTP
    
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-store, no-cache')

    def do_GET(self):
        global target_x, target_y, target_s, last_interaction
        if self.path == '/ping':
            self.send_response(200); self.send_cors_headers(); self.end_headers()
            self.wfile.write(b'pong'); return
        
        if self.path.startswith('/drive'):
            self.send_response(200); self.send_cors_headers(); self.end_headers()
            try:
                last_interaction = time.time()
                q = self.path.split('?')[1].split('&')
                target_x = float([k for k in q if k.startswith('x=')][0].split('=')[1])
                target_y = float([k for k in q if k.startswith('y=')][0].split('=')[1])
                target_s = int([k for k in q if k.startswith('s=')][0].split('=')[1])
            except: pass
            return
            
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
            self.wfile.write(PAGE_HTML); return

server = socketserver.ThreadingMixIn; server.daemon_threads = True
server = HTTPServer(('0.0.0.0', 8000), Handler)
print("✅ SERVIDOR LISTO EN PUERTO 8000")
server.serve_forever()
