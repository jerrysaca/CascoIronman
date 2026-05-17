import gpiod
import pyaudio
import wave
import assemblyai as aai
import http.client
import json
import os
import sys
import threading
from contextlib import contextmanager
from time import sleep

# ==========================================
# 0. CONTROL DE VARIABLES DE ESTADO LOCAL
# ==========================================
estado_actual_casco = None  # Evita que el servo se mueva si el estado no ha cambiado

# ==========================================
# 1. CONFIGURACIÓN DE HARDWARE (gpiod NATIVO)
# ==========================================
SERVO_LINEA = 73  # Pin Físico 13 (PC9)
LED_LINEA = 70    # Pin Físico 11 (PC6)

chip = gpiod.Chip('gpiochip0')

linea_led = chip.get_line(LED_LINEA)
linea_led.request(consumer="Jarvis_LED", type=gpiod.LINE_REQ_DIR_OUT)

linea_servo = chip.get_line(SERVO_LINEA)
linea_servo.request(consumer="Jarvis_Servo", type=gpiod.LINE_REQ_DIR_OUT)

def set_angle(angle):
    """Genera un pulso PWM manual para mover el servo"""
    t_alto = ((angle * 11.11) + 500) / 1000000.0
    t_bajo = 0.02 - t_alto
    for _ in range(15):
        linea_servo.set_value(1)
        sleep(t_alto)
        linea_servo.set_value(0)
        sleep(t_bajo)

# ==========================================
# 2. SILENCIADOR DE ADVERTENCIAS ALSA
# ==========================================
@contextmanager
def suprimir_stderr():
    fd_stderr = 2
    old_stderr = os.dup(fd_stderr)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, fd_stderr)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(old_stderr, fd_stderr)
        os.close(old_stderr)

# ==========================================
# 3. CONFIGURACIÓN DE AUDIO & API (ASSEMBLYAI)
# ==========================================
aai.settings.base_url = "https://api.assemblyai.com"
aai.settings.api_key = "abd3cd8bcd7b4b42a9ba8069cc189ecf"

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 4
WAVE_OUTPUT_FILENAME = "comando_jarvis.wav"

def buscar_indice_ugreen():
    device_index = None
    with suprimir_stderr():
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            if "USB Audio" in dev_info['name'] or "C-Media" in dev_info['name']:
                if dev_info['maxInputChannels'] > 0:
                    device_index = i
                    break
        p.terminate()
    return device_index

def grabar_comando(device_idx):
    with suprimir_stderr():
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, input_device_index=device_idx, frames_per_buffer=CHUNK)
    
    print("\n[JARVIS] >>> Escuchando... Di tu comando ('Open' / 'Close')")
    frames = []
    for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("[JARVIS] >>> Procesando audio...")
    with suprimir_stderr():
        stream.stop_stream()
        stream.close()
        p.terminate()

    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

# ==========================================
# 4. HILO DE MONITOREO CONTINUO (GET REQ)
# ==========================================
def hilo_monitoreo_api():
    """Revisa constantemente la API y actualiza el hardware físico si el estado cambia"""
    global estado_actual_casco
    payload_req = ''
    headers = {}
    
    print("[MONITOR] >>> Hilo de sincronización con API UACJ iniciado.")
    
    while True:
        conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
        try:
            conn.request("GET", "/ords/uacj/ironman/Jarvis?equipo=Equipo%202", payload_req, headers)
            res = conn.getresponse()
            data = res.read()

            if res.status == 200:
                response_json = json.loads(data)
                payload_str = response_json["items"][0]['payload']
                status_api = json.loads(payload_str)["status"]

                # Solo actuamos si el estado en la nube es diferente al estado físico actual
                if status_api != estado_actual_casco:
                    estado_actual_casco = status_api
                    if status_api == 0:
                        linea_led.set_value(0)
                        set_angle(0)
                        print("\n[HARDWARE] >>> API mandó CERRAR: LED OFF / SERVO 0°")
                    else:
                        linea_led.set_value(1)
                        set_angle(90)
                        print("\n[HARDWARE] >>> API mandó ABRIR: LED ON / SERVO 90°")
                        
        except Exception as e:
            pass # Silencioso para no romper la estética de la consola
        finally:
            conn.close()
        
        sleep(1)  # Consulta la base de datos cada segundo

# ==========================================
# 5. ACTUALIZACIÓN POR VOZ (POST REQ)
# ==========================================
def enviar_post_api(status_val):
    """Actualiza el servidor utilizando el método POST requerido"""
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}
    # Reemplazamos el método PUT por POST manteniendo tu estructura de query parameters
    path = f"/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:{status_val}%7D&id=9133"
    
    try:
        conn.request("POST", path, payload, headers)  # <--- Cambiado a POST
        res = conn.getresponse()
        if res.status == 200:
            print(f"[API POST] >>> Servidor actualizado exitosamente a status: {status_val}")
        else:
            print(f"[API POST] >>> Error de respuesta: {res.status}")
    except Exception as e:
        print(f"[API POST] >>> Error de conexión: {str(e)}")
    finally:
        conn.close()

def procesar_comando_voz():
    """Transcribe y decide el cambio de estado en la nube"""
    config = aai.TranscriptionConfig(
        speech_models=["universal-3-pro", "universal-2"],
        language_detection=True,
        speaker_labels=True,
    )
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(WAVE_OUTPUT_FILENAME, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        print(f"Error en AssemblyAI: {transcript.error}")
        return

    texto = transcript.text.lower()
    print(f"[Jarvis entendió]: '{texto}'")

    if "open" in texto or "abrir" in texto:
        print("-> Lógica por Voz: Solicitando APERTURA en la nube...")
        enviar_post_api(1)  # Sube el cambio a la API, el hilo de monitoreo hará el movimiento físico
        
    elif "close" in texto or "cerrar" in texto:
        print("-> Lógica por Voz: Solicitando CIERRE en la nube...")
        enviar_post_api(0)  # Sube el cambio a la API, el hilo de monitoreo hará el movimiento físico
    else:
        print("-> Comando de voz no reconocido.")

# ==========================================
# 6. ENTRADA PRINCIPAL
# ==========================================
if __name__ == "__main__":
    idx = buscar_indice_ugreen()
    if idx is None:
        print("ERROR: No se detectó el adaptador Ugreen.")
        exit()
        
    print(f"Adaptador de audio detectado en el índice: {idx}")
    
    # Lanzamos el hilo de consulta de API en segundo plano
    monitor_thread = threading.Thread(target=hilo_monitoreo_api, daemon=True)
    monitor_thread.start()
    
    print("Sistemas ciberfísicos listos de manera asíncrona.")
    
    try:
        while True:
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando_voz()
            
    except KeyboardInterrupt:
        print("\nSistemas de Jarvis apagados de forma segura.")