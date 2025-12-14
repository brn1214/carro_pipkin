import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, urllib.parse, io, threading, time
import sys

# === CONFIGURACIÓN HW ===
PINS = {'A_FWD': 27, 'A_REV': 4, 'B_FWD': 23, 'B_REV': 15, 'C_FWD': 6, 'C_REV': 5, 'D_FWD': 24, 'D_REV': 25}
GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
pwms = {}

for n, p in PINS.items():
    GPIO.setup(p, GPIO.OUT)
    pwms[n] = GPIO.PWM(p, 100)
    pwms[n].start(0)

# Carga segura del HTML
try:
    with open('index.html', 'rb') as f:
        PAGE_HTML = f.read()
except FileNotFoundError:
    print("ERROR FATAL: No se encuentra 'index.html' en la carpeta actual.")
    sys.exit(1)

# === WATCHDOG DE SEGURIDAD ===
last_cmd_time = time.time()

def watchdog_loop():
    while True:
        # Si no hay orden en 0.5s, apagar todo.
        if time.time() - last_cmd_time > 0.5:
            for p in pwms.values(): p.ChangeDutyCycle(0)
        time.sleep(0.1)

t = threading.Thread(target=watchdog_loop, daemon=True)
t.start()

# === CONTROL MOTORES ===
def set_motors(x, y):
    global last_cmd_time
    last_cmd_time = time.time() # Resetear timer del watchdog
    
    y = -y # Invertir Y web
    
    left = (y + x) * 100
    right = (y - x) * 100
    
    def drive(pins, val):
        duty = max(0, min(abs(val), 100))
        if duty < 10: duty = 0 # Zona muerta
        f, r = pwms[pins[0]], pwms[pins[1]]
        if val > 0: f.ChangeDutyCycle(duty); r.ChangeDutyCycle(0)
        elif val < 0: f.ChangeDutyCycle(0); r.ChangeDutyCycle(duty)
        else: f.ChangeDutyCycle(0); r.ChangeDutyCycle(0)

    drive(('A_FWD', 'A_REV'), left)
    drive(('C_FWD', 'C_REV'), left)
    drive(('B_FWD', 'B_REV'), right)
    drive(('D_FWD', 'D_REV'), right)

# === CÁMARA (Picamera2) ===
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    picam2 = Picamera2()
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
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
except Exception as e:
    print(f"Error camara: {e}")

# === SERVIDOR ===
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(PAGE_HTML)))
            self.end_headers()
            self.wfile.write(PAGE_HTML)

        elif self.path.startswith('/drive'):
            self.wfile.write(b'HTTP/1.0 200 OK\r\n\r\n')
            try:
                # Parseo robusto usando libreria estandar
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                if 'x' in params and 'y' in params:
                    x = float(params['x'][0])
                    y = float(params['y'][0])
                    set_motors(x, y)
            except: pass

        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        if output.condition.wait(timeout=1):
                            self.wfile.write(b'--FRAME\r\nContent-Type: image/jpeg\r\n\r\n' + output.frame + b'\r\n')
            except: pass
        
        else:
            # IMPORTANTE: Cerrar peticiones a /favicon.ico u otros para no colgar el navegador
            self.send_error(404)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    pass

try:
    server = ThreadedHTTPServer(('0.0.0.0', 8000), Handler)
    print("ONLINE: http://pipkin.local:8000")
    server.serve_forever()
except KeyboardInterrupt:
    picam2.stop()
    GPIO.cleanup()
