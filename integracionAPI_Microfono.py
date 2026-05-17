import gpiod
import pyaudio
import wave
import assemblyai as aai
import http.client
import os
import sys
from contextlib import contextmanager
from time import sleep

# ==========================================
# O. SILENCIADOR DE ADVERTENCIAS ALSA (C-Level)
# ==========================================
@contextmanager
def suprimir_stderr():
    """Desvía temporalmente las advertencias de ALSA/JACK a /dev/null"""
    fd_stderr = 2  # Descriptor estándar de error en Linux
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
# 2. CONFIGURACIÓN DE AUDIO & API (ASSEMBLYAI)
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
    """Busca dinámicamente el índice del adaptador USB Ugreen en silencio"""
    device_index = None
    with suprimir_stderr():  # <--- Activamos el silenciador aquí
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
    """Graba el audio desde el micrófono de solapa en silencio"""
    with suprimir_stderr():  # <--- Activamos el silenciador aquí también
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        input_device_index=device_idx,
                        frames_per_buffer=CHUNK)
    
    print("\n[JARVIS] >>> Escuchando... Di tu comando (ej. 'Open' o 'Close')")
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

def enviar_peticion_api(status_val):
    """Envía la actualización de estado a la API de la UACJ"""
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}
    path = f"/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:{status_val}%7D&id=9133"
    
    try:
        conn.request("PUT", path, payload, headers)
        res = conn.getresponse()
        if res.status == 200:
            print("[API UACJ] >>> Estado del casco actualizado correctamente en el servidor.")
        else:
            print(f"[API UACJ] >>> Error al actualizar en servidor: {res.status}")
    except Exception as e:
        print(f"[API UACJ] >>> Error de conexión: {str(e)}")
    finally:
        conn.close()

def procesar_comando():
    """Transcribe el archivo grabado y ejecuta las acciones físicas y remotas"""
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
        print("-> Acción: ABRIENDO MÁSCARA")
        linea_led.set_value(1)       
        set_angle(90)                
        enviar_peticion_api(1)       
        
    elif "close" in texto or "cerrar" in texto:
        print("-> Acción: CERRANDO MÁSCARA")
        linea_led.set_value(0)       
        set_angle(0)                 
        enviar_peticion_api(0)       
        
    else:
        print("-> Comando no reconocido. Intenta de nuevo.")

# ==========================================
# 3. BUCLE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    idx = buscar_indice_ugreen()
    if idx is None:
        print("ERROR: No se detectó el adaptador Ugreen. Revisa el USB.")
        exit()
        
    print(f"Adaptador de audio detectado en el índice: {idx}")
    print("Sistema de control por voz e integración con API UACJ listo.")
    
    try:
        while True:
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando()
            
    except KeyboardInterrupt:
        print("\nSistemas de Jarvis apagados de forma segura.")