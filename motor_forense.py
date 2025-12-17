import sys, traceback, time, os
import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading

print(">>> INICIANDO ANALISIS FORENSE (MODO TEXTO)...")

# === CONFIGURACION ===
PINS = { 
    'A': {'FWD': 25, 'REV': 24}, 
    'B': {'FWD': 6,  'REV': 5},  
    'C': {'FWD': 4,  'REV': 27}, 
    'D': {'FWD': 15, 'REV': 23}  
}
MIN_VALS = { 'A': 6, 'B': 7, 'C': 7, 'D': 7 } 

# Variables de Estado
target_x, target_y, target_s = 0.0, 0.0, 40
current_x, current_y = 0.0, 0.0
FACTOR_INERCIA = 0.02

# === SETUP GPIO ===
try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    pwms = {}
    for n, d in PINS.items():
        GPIO.setup(d['FWD'], GPIO.OUT)
        GPIO.setup(d['REV'], GPIO.OUT)
        pwms[f"{n}_FWD"] = GPIO.PWM(d['FWD'], 200)
        pwms[f"{n}_REV"] = GPIO.PWM(d['REV'], 200)
        pwms[f"{n}_FWD"].start(0)
        pwms[f"{n}_REV"].start(0)
    print("[OK] GPIO INICIALIZADO")
except:
    print("[ERROR] GPIO AL INICIO")
    traceback.print_exc()
    sys.exit(1)

try:
    with open('index.html', 'rb') as f: PAGE_HTML = f.read()
except: PAGE_HTML = b"Error index"

last_interaction = time.time()

# === FUNCION MOTORES ===
def apply_motors_forensic(x, y, max_power):
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
        
        pf = pwms[f"{name}_FWD"]
        pr = pwms[f"{name}_REV"]
        
        if val > 0: ff, fr = duty, 0
        else: ff, fr = 0, duty
        
        try:
            pf.ChangeDutyCycle(ff)
            pr.ChangeDutyCycle(fr)
        except Exception as e:
            print(f"[ERROR CRITICO] ESCRIBIENDO A MOTOR {name}: {e}")

    drive('A', raw_l); drive('C', raw_l); drive('B', raw_r); drive('D', raw_r)

# === HILO DE FISICA ===
def physics_loop():
    global current_x, current_y
    print("[INFO] Hilo de Fisica Iniciado")
    while True:
        try:
            diff_x = target_x - current_x
            if abs(diff_x) < FACTOR_INERCIA: current_x = target_x
            else: current_x += FACTOR_INERCIA if diff_x > 0 else -FACTOR_INERCIA

            diff_y = target_y - current_y
            if abs(diff_y) < FACTOR_INERCIA: current_y = target_y
            else: current_y += FACTOR_INERCIA if diff_y > 0 else -FACTOR_INERCIA

            apply_motors_forensic(current_x, current_y, target_s)
            time.sleep(0.05)
        except Exception as e:
            print(f"[ERROR] EN HILO FISICA: {e}")

threading.Thread(target=physics_loop, daemon=True).start()

# === WATCHDOG ===
def safety_monitor():
    global target_x, target_y
    while True:
        if time.time() - last_interaction > 2.0:
            if target_x != 0 or target_y != 0:
                print("[WATCHDOG] FRENANDO POR INACTIVIDAD")
                target_x, target_y = 0.0, 0.0
        time.sleep(0.1)

threading.Thread(target=safety_monitor, daemon=True).start()

# === SERVIDOR ===
class ForensicHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return

    def do_GET(self):
        global target_x, target_y, target_s, last_interaction
        
        if self.path == '/ping':
            self.send_response(200); self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers(); self.wfile.write(b'pong'); return

        if self.path.startswith('/drive'):
            # AQUI ESTA EL LOG DESCOMENTADO PARA VER SI LLEGAN LAS ORDENES
            print(f" [CMD] {self.path}") 
            
            self.wfile.write(b'HTTP/1.0 200 OK\r\nAccess-Control-Allow-Origin: *\r\n\r\n')
            try:
                last_interaction = time.time()
                q = self.path.split('?')[1].split('&')
                target_x = float([k for k in q if k.startswith('x=')][0].split('=')[1])
                target_y = float([k for k in q if k.startswith('y=')][0].split('=')[1])
                target_s = int([k for k in q if k.startswith('s=')][0].split('=')[1])
            except Exception as e:
                print(f"[ERROR] PARSEANDO COMANDO: {e}")
            return
            
        if self.path == '/' or self.path == '/index.html':
            print("[INFO] SIRVIENDO INDEX.HTML")
            self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers()
            self.wfile.write(PAGE_HTML); return

server = socketserver.ThreadingMixIn; server.daemon_threads = True
server = HTTPServer(('0.0.0.0', 8000), ForensicHandler)
print("[OK] SERVIDOR FORENSE LISTO EN PUERTO 8000")
server.serve_forever()
