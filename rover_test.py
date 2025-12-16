import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading, time, sys, logging, io, os

# Configuración básica
logging.basicConfig(level=logging.ERROR) # Solo errores graves
START_VALS = { 'A': 8, 'B': 11, 'C': 16, 'D': 6 }
REF = 16.0 
MOTOR_TRIMS = {
    'A': START_VALS['A'] / REF, 'B': START_VALS['B'] / REF,
    'C': 1.0, 'D': START_VALS['D'] / REF
}
GLOBAL_LIMIT = 0.3 
PINS = { 'A_FWD': 27, 'A_REV': 4, 'B_FWD': 23, 'B_REV': 15, 'C_FWD': 6, 'C_REV': 5, 'D_FWD': 24, 'D_REV': 25 }

GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
pwms = {}
for name, pin in PINS.items():
    GPIO.setup(pin, GPIO.OUT)
    pwms[name] = GPIO.PWM(pin, 200)
    pwms[name].start(0)

current_duty_cache = { name: -1 for name in PINS.keys() }

try:
    with open('index.html', 'rb') as f: PAGE_HTML = f.read()
except: sys.exit("Falta index.html")

# === VARIABLES DE DIAGNÓSTICO ===
last_packet_time = time.perf_counter() # Usamos perf_counter para precision de microsegundos

# === WATCHDOG ===
last_interaction = time.time()
def safety_monitor():
    while True:
        if time.time() - last_interaction > 1.5:
            if any(v > 0 for v in current_duty_cache.values()):
                for n, p in pwms.items():
                    p.ChangeDutyCycle(0)
                    current_duty_cache[n] = 0
        time.sleep(0.1)
threading.Thread(target=safety_monitor, daemon=True).start()

# === MOTORES ===
def set_motors(x, y):
    global last_interaction, last_packet_time
    
    # 1. MEDIR TIEMPO DE RED (NET)
    now = time.perf_counter()
    net_diff = now - last_packet_time
    
    # Ignoramos pausas largas voluntarias (usuario dejo de mover)
    if net_diff < 0.5:
        # Analisis de anomalia
        if net_diff > 0.11: # Umbral de tolerancia (0.11s = 110ms)
            print(f"⚠️ LAG DE RED DETECTADO: {net_diff*1000:.1f}ms (Esperado: ~75ms)")
        elif net_diff < 0.02: 
            # Si llegan muy rapido, es 'jitter' (se amontonaron y llegaron juntos)
            pass 
            
    last_packet_time = now
    last_interaction = time.time()
    
    # 2. MEDIR TIEMPO DE PROCESAMIENTO (CPU)
    cpu_start = time.perf_counter()
    
    # --- LOGICA MATEMATICA ---
    y = -y 
    limit = GLOBAL_LIMIT
    if abs(y) < 0.1: 
        left, right = x * 0.7, -x * 0.7
    else: 
        if x > 0: left, right = y, y * (1.0 - abs(x))
        else: left, right = y * (1.0 - abs(x)), y
    
    raw_l, raw_r = left * 100 * limit, right * 100 * limit
    
    def apply(group, val_in):
        val = val_in * MOTOR_TRIMS[group]
        target = 0
        if abs(val) > 0.5:
            minimum = START_VALS[group]
            target = minimum if abs(val) < minimum else abs(val)
            target = min(100, target)
        duty = int(target)
        fwd, rev = (duty, 0) if val_in > 0 else (0, duty)
        if current_duty_cache[f'{group}_FWD'] != fwd:
            pwms[f'{group}_FWD'].ChangeDutyCycle(fwd)
            current_duty_cache[f'{group}_FWD'] = fwd
        if current_duty_cache[f'{group}_REV'] != rev:
            pwms[f'{group}_REV'].ChangeDutyCycle(rev)
            current_duty_cache[f'{group}_REV'] = rev

    apply('A', raw_l); apply('C', raw_l)
    apply('B', raw_r); apply('D', raw_r)
    
    # Fin medicion CPU
    cpu_end = time.perf_counter()
    cpu_duration = cpu_end - cpu_start
    
    # Si el calculo tomo mas de 10ms (0.01s), la Pi esta sufriendo
    if cpu_duration > 0.015:
         print(f"🔥 LAG DE CPU DETECTADO: {cpu_duration*1000:.1f}ms procesando comando.")


# === SERVIDOR ===
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return 
    
    def do_GET(self):
        global GLOBAL_LIMIT
        if self.path.startswith('/drive'):
            self.wfile.write(b'HTTP/1.0 200 OK\r\n\r\n')
            try:
                q = self.path.split('?')[1].split('&')
                vx = float([x for x in q if x.startswith('x=')][0].split('=')[1])
                vy = float([y for y in q if y.startswith('y=')][0].split('=')[1])
                set_motors(vx, vy)
            except: pass
            return

        if self.path.startswith('/speed_limit'):
            self.wfile.write(b'HTTP/1.0 200 OK\r\n\r\n')
            try: GLOBAL_LIMIT = max(0.0, min(1.0, float(self.path.split('=')[1])))
            except: pass
            return

        if self.path == '/' or self.path == '/index.html':
            self.send_response(200); self.end_headers(); self.wfile.write(PAGE_HTML); return
            
        if self.path.startswith('/stream.mjpg'):
            if not CAM_READY: return self.send_error(503)
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        if output.condition.wait(timeout=2):
                            self.wfile.write(b'--FRAME\r\nContent-Type: image/jpeg\r\n\r\n' + output.frame + b'\r\n')
                        else: break
            except: pass
            return
        self.send_error(404)

class LatencyFreeServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# === CAMARA ===
CAM_READY = False
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"}, buffer_count=2)
    picam2.configure(config)
    picam2.start()
    
    class StreamingOutput(io.BufferedIOBase):
        def __init__(self):
            self.frame = None
            self.condition = threading.Condition()
        def write(self, buf):
            with self.condition:
                self.frame = buf
                self.condition.notify_all()
    output = StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))
    CAM_READY = True
except: print("Error Camara")

server = LatencyFreeServer(('0.0.0.0', 8000), Handler)
print("--- BUSCANDO MICRO-LAG (MUEVE EL JOYSTICK) ---")
try: server.serve_forever()
except: GPIO.cleanup()
