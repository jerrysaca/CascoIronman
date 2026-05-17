import gpiod
import pyaudio
import wave
import assemblyai as aai
import http.client
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from time import sleep

# ==========================================
# 0. VARIABLES DE ESTADO GLOBAL
# ==========================================
estado_actual_casco = None  # Monitorea cambios en la API

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

def mover_servo_y_apagar(angle):
    """Manda una ráfaga de 50 pulsos ultra precisos y luego apaga la señal para eliminar el jitter"""
    t_alto = ((angle * 11.11) + 500) / 1000000.0
    t_bajo = 0.02 - t_alto
    
    # 50 pulsos a 20ms = 1 segundo continuo de movimiento continuo con torque máximo
    for _ in range(50):
        start = time.perf_counter()
        linea_servo.set_value(1)
        while (time.perf_counter() - start) < t_alto:
            pass
        linea_servo.set_value(0)
        sleep(t_bajo)
        
    # Al salir del ciclo, la línea se queda en 0 lógico. El servo se relaja y el jitter muere.

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
    """Revisa la API y activa el tren de pulsos transitorio solo si hay cambios"""
    global estado_actual_casco
    payload_req = ''
    headers = {}
    
    print("[MONITOR] >>> Sincronización activa con API UACJ.")
    
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

                if status_api != estado_actual_casco:
                    estado_actual_casco = status_api
                    if status_api == 0:
                        linea_led.set_value(0)
                        print("\n[API -> CAMBIO] >>> Modo CERRAR: Moviendo servo a 0°...")
                        mover_servo_y_apagar(0)  # Mueve durante 1 segundo y apaga la señal
                        print("[HARDWARE] >>> Posición alcanzada. Señal apagada (Jitter eliminado).")
                    else:
                        linea_led.set_value(1)
                        print("\n[API -> CAMBIO] >>> Modo ABRIR: Moviendo servo a 90°...")
                        mover_servo_y_apagar(90) # Mueve durante 1 segundo y apaga la señal
                        print("[HARDWARE] >>> Posición alcanzada. Señal apagada (Jitter eliminado).")
                        
        except Exception as e:
            pass
        finally:
            conn.close()
        
        sleep(1)

# ==========================================
# 5. ENVIAR ACTUALIZACIÓN (POST REQ)
# ==========================================
def enviar_post_api(status_val):
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}
    path = f"/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:{status_val}%7D&id=9133"
    
    try:
        conn.request("POST", path, payload, headers)
        res = conn.getresponse()
    except Exception as e:
        print(f"[API POST] >>> Error de red: {str(e)}")
    finally:
        conn.close()

def procesar_comando_voz():
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
        print("-> Voz: Solicitando APERTURA...")
        enviar_post_api(1)
    elif "close" in texto or "cerrar" in texto:
        print("-> Voz: Solicitando CIERRE...")
        enviar_post_api(0)
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
    
    # Lanzamos el único hilo de fondo para monitorear la API
    api_thread = threading.Thread(target=hilo_monitoreo_api, daemon=True)
    api_thread.start()
    
    print("Sistemas ciberfísicos optimizados listos.")
    
    try:
        while True:
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando_voz()
            
    except KeyboardInterrupt:
        print("\nSistemas de Jarvis apagados de forma segura.")