import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- LISTA DE TODOS LOS PINES GPIO DISPONIBLES (BCM) ---
# Quitamos los reservados del sistema, dejamos los de uso general
TEST_PINS = [4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 14, 15]

# --- CONFIGURACIÓN ---
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(TEST_PINS, GPIO.OUT)
GPIO.output(TEST_PINS, GPIO.LOW)

# --- HTML DEL PANEL ---
def get_html():
    buttons_html = ""
    for pin in sorted(TEST_PINS):
        buttons_html += f"""
        <div class="box">
            <h3>GPIO {pin}</h3>
            <button class="btn" 
                onmousedown="trigger({pin}, 1)" 
                onmouseup="trigger({pin}, 0)" 
                ontouchstart="trigger({pin}, 1)" 
                ontouchend="trigger({pin}, 0)">PROBAR</button>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: monospace; background: #111; color: #0f0; text-align: center; }}
            .container {{ display: flex; flex-wrap: wrap; justify-content: center; }}
            .box {{ border: 1px solid #333; margin: 5px; padding: 10px; width: 100px; border-radius: 5px; }}
            .btn {{ width: 100%; height: 50px; background: #333; color: white; border: none; font-weight: bold; cursor: pointer; }}
            .btn:active {{ background: #f00; }}
            h1 {{ border-bottom: 1px solid #0f0; padding-bottom: 10px; }}
        </style>
        <script>
            function trigger(pin, state) {{
                fetch('/set/' + pin + '/' + state).catch(e => console.log(e));
            }}
        </script>
    </head>
    <body>
        <h1>PANEL DE TESTEO GPIO</h1>
        <p>Manten presionado para activar (3.3v)</p>
        <div class="container">
            {buttons_html}
        </div>
    </body>
    </html>
    """

# --- SERVIDOR ---
class TestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return # Silenciar logs
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(get_html().encode('utf-8'))
            return
            
        if self.path.startswith('/set/'):
            # Ejemplo ruta: /set/17/1
            parts = self.path.split('/')
            pin = int(parts[2])
            state = int(parts[3])
            
            if pin in TEST_PINS:
                GPIO.output(pin, state)
                print(f"GPIO {pin} -> {'ENCENDIDO' if state else 'APAGADO'}")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

# --- ARRANQUE ---
server = HTTPServer(('0.0.0.0', 8000), TestHandler)
print("PANEL LISTO EN: http://pipkin.local:8000")
print("Presiona Ctrl+C para salir")

try:
    server.serve_forever()
except KeyboardInterrupt:
    GPIO.cleanup()
    print("\nLimpieza completada.")
