import gpiod
import pyaudio
import wave
import assemblyai as aai
import http.client
import json
import os
import sys
import multiprocessing
import time
from contextlib import contextmanager
from time import sleep

# ==========================================
# 1. TRUCO DE CONSOLA: SILENCIADOR DE ALSA
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
# 2. PROCESO AISLADO: GENERADOR PWM (NÚCLEO DEDICADO)
# ==========================================
def proceso_servo_pwm(angulo_compartido):
    """Bucle infinito inmune al GIL. Genera pulso continuo con torque de retención total"""
    import gpiod
    import time
    
    SERVO_LINEA = 73  # Pin Físico 13 (PC9)
    chip = gpiod.Chip('gpiochip0')
    linea_servo = chip.get_line(SERVO_LINEA)
    linea_servo.request(consumer="Jarvis_Servo_RT", type=gpiod.LINE_REQ_DIR_OUT)
    
    while True:
        # Lee el valor del ángulo de la memoria compartida por el OS
        angle = angulo_compartido.value
        
        # Mapeo preciso a segundos
        t_alto = ((angle * 11.11) + 500) / 1000000.0
        t_bajo = 0.02 - t_alto
        
        # Pulso Alto (Busy-Waiting puro sin ceder el núcleo)
        start = time.perf_counter()
        linea_servo.set_value(1)
        while (time.perf_counter() - start) < t_alto:
            pass
        linea_servo.set_value(0)
        
        # Pulso Bajo (Permite respirar al núcleo asignado)
        time.sleep(t_bajo)

# ==========================================
# 3. PROCESO AISLADO: MONITOR DE LA API UACJ
# ==========================================
def proceso_monitor_api(angulo_compartido):
    """Revisa la base de datos remotamente y actualiza el hardware y la memoria del OS"""
    import gpiod
    import http.client
    import json
    import time
    
    LED_LINEA = 70    # Pin Físico 11 (PC6)
    chip = gpiod.Chip('gpiochip0')
    linea_led = chip.get_line(LED_LINEA)
    linea_led.request(consumer="Jarvis_LED_RT", type=gpiod.LINE_REQ_DIR_OUT)
    
    estado_actual_casco = None
    payload_req = ''
    headers = {}
    
    print("[MONITOR] >>> Proceso de sincronización con API UACJ activo.")
    
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
                        angulo_compartido.value = 0  # Actualiza el proceso del servo al instante
                        print("\n[API -> CAMBIO] >>> Estatus 0: Ojos OFF / Servo bloqueado a 0°")
                    else:
                        linea_led.set_value(1)
                        angulo_compartido.value = 90 # Actualiza el proceso del servo al instante
                        print("\n[API -> CAMBIO] >>> Estatus 1: Ojos ON / Servo bloqueado a 90°")
                        
        except Exception as e:
            pass
        finally:
            conn.close()
        
        time.sleep(1)

# ==========================================
# 4. CONFIGURACIÓN DE AUDIO & API GENERAL (PROCESO PRINCIPAL)
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

    print("[JARVIS] >>> Procesando audio en la nube...")
    with suprimir_stderr():
        stream.stop_stream()
        stream.close()
        p.terminate()

    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

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
# 5. PUNTO DE ENTRADA PRINCIPAL
# ==========================================
if __name__ == "__main__":
    idx = buscar_indice_ugreen()
    if idx is None:
        print("ERROR: No se detectó el adaptador Ugreen.")
        exit()
        
    print(f"Adaptador de audio detectado en el índice: {idx}")
    
    # Creamos una variable entera compartida en memoria segura mapeada por el OS ('i' = int)
    angulo_compartido = multiprocessing.Value('i', 0)
    
    # Lanzamos el proceso del Monitor de la API de la UACJ
    p_api = multiprocessing.Process(target=proceso_monitor_api, args=(angulo_compartido,), daemon=True)
    p_api.start()
    
    # Lanzamos el proceso del PWM del servo en un núcleo independiente
    p_pwm = multiprocessing.Process(target=proceso_servo_pwm, args=(angulo_compartido,), daemon=True)
    p_pwm.start()
    
    print("Sistemas distribuidos en procesos independientes multiprocesador listos.")
    
    try:
        while True:
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando_voz()
            
    except KeyboardInterrupt:
        print("\nSistemas de Jarvis apagados de forma segura.")