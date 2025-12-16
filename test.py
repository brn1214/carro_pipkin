import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver, threading, time, sys

# === CONFIGURACIÓN DE PINES ===
PINS = { 
    'A': {'FWD': 27, 'REV': 4},  
    'B': {'FWD': 23, 'REV': 15}, 
    'C': {'FWD': 6,  'REV': 5},  
    'D': {'FWD': 24, 'REV': 25}  
}

GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
pwms = {}
pwm_states = {} 

# Iniciamos PWM
for wheel, dirs in PINS.items():
    GPIO.setup(dirs['FWD'], GPIO.OUT)
    GPIO.setup(dirs['REV'], GPIO.OUT)
    
    pwms[f"{wheel}_FWD"] = GPIO.PWM(dirs['FWD'], 200)
    pwms[f"{wheel}_FWD"].start(0)
    pwm_states[f"{wheel}_FWD"] = 0
    
    pwms[f"{wheel}_REV"] = GPIO.PWM(dirs['REV'], 200)
    pwms[f"{wheel}_REV"].start(0)
    pwm_states[f"{wheel}_REV"] = 0

last_heartbeat = time.time()

# === WATCHDOG ===
def emergency_stop_monitor():
    while True:
        if time.time() - last_heartbeat > 1.5:
            any_active = False
            for val in pwm_states.values():
                if val > 0: any_active = True
            
            if any_active:
                print("⚠️ PERDIDA DE CONEXION: PARADA DE EMERGENCIA")
                for key in pwms:
                    pwms[key].ChangeDutyCycle(0)
                    pwm_states[key] = 0
        time.sleep(0.5)

t = threading.Thread(target=emergency_stop_monitor, daemon=True)
t.start()

# === INTERFAZ WEB CON BOTONES +/- ===
PAGE_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calibrador V3 Preciso</title>
    <style>
        body { background-color: #121212; color: #ffffff; font-family: monospace; padding: 5px; text-align: center; }
        
        #status-bar { 
            padding: 8px; margin-bottom: 15px; border-radius: 5px; font-weight: bold; font-size: 16px;
            transition: background 0.3s; text-transform: uppercase;
        }
        .ok { background: #2e7d32; color: #fff; }
        .lag { background: #f9a825; color: #000; }
        .bad { background: #c62828; color: #fff; }

        .motor-row { 
            background: #1e1e1e; margin: 8px auto; padding: 10px; 
            border-radius: 10px; max-width: 500px; display: flex; 
            align-items: center; justify-content: space-between; border: 1px solid #333;
        }
        .label { font-size: 24px; font-weight: bold; width: 30px; color: #00e5ff; }
        
        /* Estilo de los botones +/- */
        .btn-adj {
            width: 45px; height: 45px;
            background: #444; color: #fff;
            border: 1px solid #666; border-radius: 50%;
            font-size: 24px; font-weight: bold;
            cursor: pointer; touch-action: manipulation;
        }
        .btn-adj:active { background: #00e5ff; color: #000; }

        input[type=range] { flex-grow: 1; margin: 0 10px; height: 30px; }
        .val { font-size: 20px; width: 45px; text-align: right; color: #0f0; }
        
        button.stop { 
            background: #d32f2f; color: white; border: none; padding: 15px 30px; 
            font-size: 20px; border-radius: 8px; cursor: pointer; margin-top: 20px; width: 90%;
        }
    </style>
</head>
<body>
    <div id="status-bar" class="bad">CONECTANDO...</div>

    <div id="motors-container"></div>

    <button class="stop" onclick="stop()">PARADA TOTAL</button>

    <script>
        const motors = ['A', 'B', 'C', 'D'];
        const container = document.getElementById('motors-container');
        const stat = document.getElementById('status-bar');

        // Generar HTML dinamico
        motors.forEach(id => {
            container.innerHTML += `
            <div class="motor-row">
                <span class="label">${id}</span>
                <button class="btn-adj" onclick="adj('${id}', -1)">-</button>
                <input type="range" min="0" max="100" value="0" id="range${id}" oninput="setVal('${id}', this.value)">
                <button class="btn-adj" onclick="adj('${id}', 1)">+</button>
                <span id="v${id}" class="val">0</span>
            </div>`;
        });

        function adj(id, delta) {
            let range = document.getElementById('range' + id);
            let newVal = parseInt(range.value) + delta;
            if (newVal < 0) newVal = 0;
            if (newVal > 100) newVal = 100;
            range.value = newVal;
            setVal(id, newVal);
        }

        function setVal(id, val) {
            document.getElementById('v'+id).innerText = val;
            fetch(`/set?id=${id}&val=${val}`, {keepalive: true}).catch(()=>{});
        }

        function stop() {
            motors.forEach(id => {
                document.getElementById('range'+id).value = 0;
                document.getElementById('v'+id).innerText = "0";
            });
            fetch('/stop');
        }

        // Monitor de Red
        setInterval(async () => {
            const start = Date.now();
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 1000);
                const res = await fetch('/ping', { signal: controller.signal });
                clearTimeout(timeoutId);
                if (res.ok) {
                    const latency = Date.now() - start;
                    if(latency < 150) {
                        stat.className = 'ok'; stat.innerText = `OK (${latency}ms)`;
                    } else {
                        stat.className = 'lag'; stat.innerText = `LENTO (${latency}ms)`;
                    }
                }
            } catch (err) {
                stat.className = 'bad'; stat.innerText = "DESCONECTADO";
            }
        }, 1000);
    </script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return 
    
    def do_GET(self):
        global last_heartbeat
        
        if self.path == '/ping':
            last_heartbeat = time.time()
            self.send_response(200); self.end_headers(); self.wfile.write(b'pong')
            return

        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE_HTML.encode('utf-8'))
            return
            
        if self.path.startswith('/set'):
            last_heartbeat = time.time()
            self.send_response(200); self.end_headers()
            try:
                q = self.path.split('?')[1].split('&')
                mid = q[0].split('=')[1]
                val = int(q[1].split('=')[1])
                pwms[f"{mid}_FWD"].ChangeDutyCycle(val)
                pwms[f"{mid}_REV"].ChangeDutyCycle(0)
                pwm_states[f"{mid}_FWD"] = val
                pwm_states[f"{mid}_REV"] = 0
            except: pass
            return

        if self.path == '/stop':
            self.send_response(200); self.end_headers()
            for key in pwms:
                pwms[key].ChangeDutyCycle(0)
                pwm_states[key] = 0
            return

server = HTTPServer(('0.0.0.0', 8000), Handler)
print("CALIBRADOR V3 (CON BOTONES): http://pipkin.local:8000")

try: server.serve_forever()
except KeyboardInterrupt:
    for p in pwms.values(): p.stop()
    GPIO.cleanup()
