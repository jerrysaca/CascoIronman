import gpiod
import pyaudio
import wave
import assemblyai as aai
from time import sleep

# ==========================================
# 1. CONFIGURACIÓN DE HARDWARE (gpiod NATIVO)
# ==========================================
SERVO_LINEA = 73   # Pin Físico 7 (PA6)
LED_LINEA = 70    # Pin Físico 11 (PC6)

# Abrimos el chip de control principal de la Orange Pi
chip = gpiod.Chip('gpiochip0')

# Configuramos el LED como salida
linea_led = chip.get_line(LED_LINEA)
linea_led.request(consumer="Jarvis_LED", type=gpiod.LINE_REQ_DIR_OUT)

# Configuramos el Servo como salida
linea_servo = chip.get_line(SERVO_LINEA)
linea_servo.request(consumer="Jarvis_Servo", type=gpiod.LINE_REQ_DIR_OUT)

def set_angle(angle):
    """Genera un pulso PWM manual (Bit-Banging) para mover el servo"""
    t_alto = ((angle * 11.11) + 500) / 1000000.0  # Tiempo en alto (segundos)
    t_bajo = 0.02 - t_alto                        # Periodo total de 20ms (50Hz)
    
    # Mandamos 15 pulsos (suficiente para que el servo llegue a su posición)
    for _ in range(15):
        linea_servo.set_value(1)
        sleep(t_alto)
        linea_servo.set_value(0)
        sleep(t_bajo)

# ==========================================
# 2. CONFIGURACIÓN DE AUDIO & API
# ==========================================
# RECUERDA: Coloca aquí tu API KEY real de AssemblyAI
aai.settings.api_key = "abd3cd8bcd7b4b42a9ba8069cc189ecf" 

FORMAT = pyaudio.paInt16
CHANNELS = 1          # Forzado a Mono (lo que le gustó a tu adaptador)
RATE = 44100          # 44.1 kHz
CHUNK = 1024
RECORD_SECONDS = 4    # Tiempo para decir el comando
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
    
    print("\n[JARVIS] >>> Escuchando... Di tu comando (ej. 'Abrir máscara')")
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

def procesar_comando():
    """Envía el archivo a AssemblyAI y activa los pines de la Orange Pi"""
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(WAVE_OUTPUT_FILENAME)

    if transcript.status == aai.TranscriptStatus.error:
        print(f"Error en AssemblyAI: {transcript.error}")
        return

    texto = transcript.text.lower()
    print(f"[Jarvis entendió]: '{texto}'")

    # Lógica de control por palabras clave
    if "open" in texto or "abrir" in texto or "máscara" in texto and "abre" in texto:
        print("-> Acción: MÁSCARA ABIERTA")
        linea_led.set_value(1)  # Prende ojos
        set_angle(90)           # Abre careta
        
    elif "close" in texto or "cerrar" in texto or "máscara" in texto and "cierra" in texto:
        print("-> Acción: MÁSCARA CERRADA")
        linea_led.set_value(0)  # Apaga ojos
        set_angle(0)            # Cierra careta
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
    print("Sistema listo.")
    
    try:
        while True:
            input("\nPresiona ENTER para hablar...")
            grabar_comando(idx)
            procesar_comando()
            
    except KeyboardInterrupt:
        print("\nSistemas de Jarvis apagados de forma segura.")