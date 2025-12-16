import io, socketserver, threading, time, sys, os
from http.server import BaseHTTPRequestHandler, HTTPServer # <--- ESTO FALTABA

# Limpiar procesos viejos
os.system("sudo pkill -f libcamera")

try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    
    print("🎥 CAMARA: Arrancando...")
    picam2 = Picamera2()
    
    # 1. Configuración Básica
    config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"}, buffer_count=2)
    picam2.configure(config)
    
    # 2. Iniciar
    picam2.start()

    # 3. LIMITAR A 15 FPS (Vital para que no se corte el WiFi)
    # 66666 microsegundos = 15 FPS
    #picam2.set_controls({"FrameDurationLimits": (66666, 66666)})

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
    print("✅ CAMARA: Lista a 15 FPS (Puerto 8001)")

except Exception as e:
    print(f"❌ ERROR CRITICO CAMARA: {e}")
    CAM_READY = False

class CameraHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return 
    def do_GET(self):
        if self.path == '/stream.mjpg':
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
        else:
            self.send_error(404)

class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

server = ThreadedHTTPServer(('0.0.0.0', 8001), CameraHandler)
server.serve_forever()
