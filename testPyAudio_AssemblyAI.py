import gpiod
import pyaudio
import wave
import assemblyai as aai
import http.client
from time import sleep

# ==========================================
# 1. CONFIGURACIÓN DE HARDWARE (gpiod NATIVO)
# ==========================================
SERVO_LINEA = 73  # Pin Físico 13 (PC9) - Probado y seguro
LED_LINEA = 70    # Pin Físico 11 (PC6) - Probado y seguro

# Abrimos el chip de control principal de la Orange Pi
chip = gpiod.Chip('gpiochip0')

# Configuramos el LED como salida
linea_led = chip.get_line(LED_LINEA)
linea_led.request(consumer="Jarvis_LED", type=gpiod.LINE_REQ_DIR_OUT)

# Configuramos el Servo como salida
linea_servo = chip.get_line(SERVO_LINEA)
linea_servo.request(consumer="Jarvis_Servo", type=gpiod.LINE_REQ_DIR_OUT)

def set_angle(angle):
    """Genera un pulso PWM manual para mover el servo"""
    t_alto = ((angle * 11.11) + 500) / 1000000.0  # Tiempo en alto (segundos)
    t_bajo = 0.02 - t_alto                        # Periodo total de 20ms (50Hz)
    
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
CHANNELS = 1          # Audio Mono para el adaptador Ugreen
RATE = 44100          # 44.1 kHz
CHUNK = 1024
RECORD_SECONDS = 4    # Tiempo para grabar el comando
WAVE_OUTPUT_FILENAME = "comando_jarvis.wav"

def buscar_indice_ugreen():
    """Busca dinámicamente el índice del adaptador USB Ugreen"""
    p = pyaudio.PyAudio()
    device_index = None
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        if "USB Audio" in dev_info['name'] or "C-Media" in dev_info['name']:
            if dev_info['maxInputChannels'] > 0:
                device_index = i
                break
    p.terminate()
    return device_index

def grabar_comando(device_idx):
    """Graba el audio desde el micrófono de solapa"""
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
        linea_led.set_value(1)       # Prende ojos físicos
        set_angle(90)                # Mueve servo físico
        enviar_peticion_api(1)       # Actualiza servidor remoto (status: 1)
        
    elif "close" in texto or "cerrar" in texto:
        print("-> Acción: CERRANDO MÁSCARA")
        linea_led.set_value(0)       # Apaga ojos físicos
        set_angle(0)                 # Mueve servo físico
        enviar_peticion_api(0)       # Actualiza servidor remoto (status: 0)
        
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