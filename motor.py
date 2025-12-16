import sys, traceback, time, os
import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading

# === CONFIGURACION ===
PINS = { 
    'A': {'FWD': 25, 'REV': 24}, 
    'B': {'FWD': 6,  'REV': 5},  
    'C': {'FWD': 4,  'REV': 27}, 
    'D': {'FWD': 15, 'REV': 23}  
}
MIN_VALS = { 'A': 6, 'B': 7, 'C': 7, 'D': 7 } 
KICK_VAL = 40; KICK_TIME = 0.05

try:
    GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
    pwms = {}; motor_states = {}
    for n, d in PINS.items():
        GPIO.setup(d['FWD'], GPIO.OUT); GPIO.setup(d['REV'], GPIO.OUT)
        pwms[f"{n}_FWD"] = GPIO.PWM(d['FWD'], 200); pwms[f"{n}_REV"] = GPIO.PWM(d['REV'], 200)
        pwms[f"{n}_FWD"].start(0); pwms[f"{n}_REV"].start(0)
        motor_states[n] = 0
except: traceback.print_exc(); sys.exit(1)

try:
    with open('index.html', 'rb') as f: PAGE_HTML = f.read()
except: PAGE_HTML = b"Error index"

last_interaction = time.time()

# === WATCHDOG (TOLERANCIA 2 SEGUNDOS) ===
def safety_monitor():
    while True:
        # AQUI ESTA EL CAMBIO: 2.0 en lugar de 1.0
        if time.time() - last_interaction > 2.0:
            active = False
            for s in motor_states.values():
                if s != 0: active = True
            if active:
                for p in pwms.values(): p.ChangeDutyCycle(0)
                for k in motor_states: motor_states[k] = 0
                print(f"⚠️ WATCHDOG: Frenado automatico (Inactivo > 2s)")
        time.sleep(0.1)

threading.Thread(target=safety_monitor, daemon=True).start()

# === LOGICA MOTORES ===
def set_motors(x, y, max_power):
    global last_interaction
    last_interaction = time.time()
    y = -y 
    limit = max_power / 100.0
    if abs(y) < 0.1: left, right = x * 0.8, -x * 0.8 
    else: 
        if x > 0: left, right = y, y * (1.0 - abs(x))
        else: left, right = y * (1.0 - abs(x)), y
    raw_l, raw_r = left * 100 * limit, right * 100 * limit

    def drive(name, val):
        target = 0; min_v = MIN_VALS[name]
        if abs(val) > 1: target = min_v + (abs(val) * (100 - min_v) / 100)
        duty = int(min(100, target))
        pf = pwms[f"{name}_FWD"]; pr = pwms[f"{name}_REV"]
        if val > 0: ff, fr = duty, 0; kf, kr = KICK_VAL, 0
        else: ff, fr = 0, duty; kf, kr = 0, KICK_VAL
        if duty > 0 and motor_states[name] == 0:
            pf.ChangeDutyCycle(kf); pr.ChangeDutyCycle(kr); time.sleep(KICK_TIME)
        pf.ChangeDutyCycle(ff); pr.ChangeDutyCycle(fr)
        motor_states[name] = 1 if duty > 0 else 0

    drive('A', raw_l); drive('C', raw_l); drive('B', raw_r); drive('D', raw_r)

# === SERVIDOR ===
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return 
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
            self.wfile.write(PAGE_HTML); return
        if self.path == '/ping':
            self.send_response(200); self.end_headers(); self.wfile.write(b'pong'); return
        if self.path.startswith('/drive'):
            self.wfile.write(b'HTTP/1.0 200 OK\r\n\r\n')
            try:
                q = self.path.split('?')[1].split('&')
                vx = float([k for k in q if k.startswith('x=')][0].split('=')[1])
                vy = float([k for k in q if k.startswith('y=')][0].split('=')[1])
                vs = int([k for k in q if k.startswith('s=')][0].split('=')[1])
                set_motors(vx, vy, vs)
            except: pass
            return

server = socketserver.ThreadingMixIn; server.daemon_threads = True
server = HTTPServer(('0.0.0.0', 8000), Handler)
print("✅ MOTORES V4 (Watchdog 2s). Puerto 8000")
server.serve_forever()
