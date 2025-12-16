import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading, time, sys, logging, io

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# === 1. ESTADO COMPARTIDO (MEMORIA GLOBAL) ===
# Esta variable es el "Registro" que conecta los dos hilos.
# Usamos un Lock para evitar que lean/escriban al mismo tiempo exacto.
shared_state = {
    'x': 0.0,
    'y': 0.0,
    'last_update': time.time(),
    'lock': threading.Lock()
}

# === CONFIGURACION FISICA ===
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

# === 2. HILO DEL MOTOR (CONSUMIDOR - SIMULA RTOS) ===
# Este bucle corre SIEMPRE a 20Hz, pase lo que pase en la red.
def motor_control_loop():
    print("⚙️ Hilo de Motores Iniciado (20Hz)")
    while True:
        cycle_start = time.time()
        
        # A. LEER EL ULTIMO COMANDO (Snapshot)
        with shared_state['lock']:
            x = shared_state['x']
            y = shared_state['y']
            last_time = shared_state['last_update']
        
        # B. WATCHDOG (Seguridad)
        # Si el dato es muy viejo (>1s), forzamos cero.
        if time.time() - last_time > 1.0:
            x, y = 0.0, 0.0

        # C. CALCULO DE MOTORES (Fisica)
        # Toda la logica matematica ocurre aqui, sin frenar al WiFi
        y = -y 
        limit = GLOBAL_LIMIT
        
        if abs(y) < 0.1: left, right = x * 0.7, -x * 0.7
        else: 
            if x > 0: left, right = y, y * (1.0 - abs(x))
            else: left, right = y * (1.0 - abs(x)), y
        
        raw_l, raw_r = left * 100 * limit, right * 100 * limit
        
        # D. APLICAR AL HARDWARE
        apply_pwm('A', raw_l); apply_pwm('C', raw_l)
        apply_pwm('B', raw_r); apply_pwm('D', raw_r)
        
        # E. MANTENER RITMO (Sleep preciso)
        # Queremos 20Hz (0.05s por ciclo)
        elapsed = time.time() - cycle_start
        sleep_time = 0.05 - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

def apply_pwm(group, val_in):
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

# Arrancamos el hilo "Musculo"
motor_thread = threading.Thread(target=motor_control_loop, daemon=True)
motor_thread.start()


# === 3. HILO DE RED (PRODUCTOR) ===
# Este solo recibe datos y actualiza la variable. 
# Responde en microsegundos porque NO hace calculos.
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return 
    
    def do_GET(self):
        global GLOBAL_LIMIT
        
        if self.path.startswith('/drive'):
            # RESPUESTA INSTANTANEA (FIRE AND FORGET)
            self.wfile.write(b'HTTP/1.0 200 OK\r\n\r\n')
            
            try:
                # Parsear rapido
                q = self.path.split('?')[1].split('&')
                vx = float([x for x in q if x.startswith('x=')][0].split('=')[1])
                vy = float([y for y in q if y.startswith('y=')][0].split('=')[1])
                
                # ACTUALIZAR ESTADO (CRITICO)
                with shared_state['lock']:
                    shared_state['x'] = vx
                    shared_state['y'] = vy
                    shared_state['last_update'] = time.time()
                    # ¡Listo! No movemos motores aqui. Solo guardamos el dato.
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
    # 320x240 para no saturar WiFi
    config = picam2.create_video_configuration(main={"size": (320, 240), "format": "RGB888"}, buffer_count=2)
    picam2.configure(config)
    picam2.start()
    
    class StreamingOutput(io.BufferedIOBase):
        def __init__(self):
            self.frame = None; self.condition = threading.Condition()
        def write(self, buf):
            with self.condition: self.frame = buf; self.condition.notify_all()
    output = StreamingOutput()
    picam2.start_recording(JpegEncoder(), FileOutput(output))
    CAM_READY = True
except: print("Error Camara")

server = LatencyFreeServer(('0.0.0.0', 8000), Handler)
print("ROVER CONCURRENTE (RTOS STYLE): http://pipkin.local:8000")
try: server.serve_forever()
except: GPIO.cleanup()