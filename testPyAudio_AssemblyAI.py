import OPi.GPIO as GPIO
import pyaudio
import wave
import assemblyai as aai
from time import sleep

# ==========================================
# 1. CONFIGURACIÓN DE HARDWARE (Orange Pi)
# ==========================================
SERVO_PIN = 19
LED_PIN = 21

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# Configurar PWM para el servo a 50Hz
pwm_servo = GPIO.PWM(SERVO_PIN, 50)
pwm_servo.start(0)

def set_angle(angle):
    """Mueve el servo al ángulo deseado y corta la señal para evitar jitter"""
    duty = (angle / 18.0) + 2.5
    pwm_servo.ChangeDutyCycle(duty)
    sleep(0.5)  # Tiempo para que el motor se mueva
    pwm_servo.ChangeDutyCycle(0)

# ==========================================
# 2. CONFIGURACIÓN DE AUDIO & API
# ==========================================
aai.settings.api_key = "abd3cd8bcd7b4b42a9ba8069cc189ecf"

FORMAT = pyaudio.paInt16
CHANNELS = 1          # Forzado a Mono como en arecord
RATE = 44100          # 44.1 kHz
CHUNK = 1024
RECORD_SECONDS = 4    # 4 segundos es buen tiempo para un comando corto
WAVE_OUTPUT_FILENAME = "comando_jarvis.wav"

def buscar_indice_ugreen():
    """Busca dinámicamente el índice de la tarjeta USB Ugreen en la Orange Pi"""
    p = pyaudio.PyAudio()
    device_index = None
    
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        # Buscamos por el nombre que le asigna Linux al chip C-Media o USB Audio
        if "USB Audio" in dev_info['name'] or "C-Media" in dev_info['name']:
            if dev_info['maxInputChannels'] > 0:
                device_index = i
                break
                
    p.terminate()
    return device_index

def grabar_comando(device_idx):
    """Graba el audio del micrófono y lo guarda en un archivo .wav"""
    p = pyaudio.PyAudio()
    
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=device_idx,
                    frames_per_buffer=CHUNK)
    
    print("\n[JARVIS] >>> Escuchando... Di un comando (ej. 'Abrir máscara')")
    frames = []

    for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("[JARVIS] >>> Procesando audio...")
    stream.stop_stream()
    stream.close()
    p.terminate()

    # Guardar archivo
    with wave.open(WAVE_OUTPUT_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

def procesar_comando():
    """Envía el audio a AssemblyAI y ejecuta la acción en los pines"""
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(WAVE_OUTPUT_FILENAME)

    if transcript.status == aai.TranscriptStatus.error:
        print(f"Error de transcripción: {transcript.error}")
        return

    texto = transcript.text.lower()
    print(f"[Jarvis escuchó]: '{texto}'")

    # Lógica de control por palabras clave (Soporta inglés y español)
    if "open" in texto or "abrir" in texto or "máscara" in texto and "abre" in texto:
        print("-> Acción: ABRIENDO MÁSCARA")
        GPIO.output(LED_PIN, GPIO.HIGH) # Prende ojos
        set_angle(90)                   # Abre careta (ajusta este ángulo a tu gusto)
        
    elif "close" in texto or "cerrar" in texto or "máscara" in texto and "cierra" in texto:
        print("-> Acción: CERRANDO MÁSCARA")
        GPIO.output(LED_PIN, GPIO.LOW)  # Apaga ojos
        set_angle(0)                    # Cierra careta

    else:
        print("-> Comando no reconocido. Intenta de nuevo.")

# ==========================================
# 3. EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    # Detectar el adaptador de audio antes de iniciar
    idx = buscar_indice_ugreen()
    if idx is None:
        print("ERROR: No se encontró el adaptador USB Ugreen. Verifica la conexión.")
        exit()
        
    print(f"Adaptador de audio detectado en el índice de PyAudio: {idx}")
    print("Sistema de control por voz listo.")
    
    try:
        while True:
            # Puedes activar la grabación con un Enter en la terminal para pruebas
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando()
            
    except KeyboardInterrupt:
        print("\nApagando sistemas Jarvis...")
        pwm_servo.stop()
        GPIO.cleanup()