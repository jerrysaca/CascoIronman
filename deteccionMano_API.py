import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import http.client
import os
import urllib.request

# ==========================================
# 0. DESCARGA AUTOMÁTICA DEL MODELO DE GOOGLE
# ==========================================
MODEL_FILE = 'hand_landmarker.task'
if not os.path.exists(MODEL_FILE):
    print("[SISTEMA] >>> Descargando modelo de MediaPipe...")
    url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    urllib.request.urlretrieve(url, MODEL_FILE)
    print("[SISTEMA] >>> Descarga completa.")

# ==========================================
# 1. CONFIGURACIÓN DE LA API DE LA UACJ
# ==========================================
def enviar_post_api(status_val):
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}
    path = f"/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:{status_val}%7D&id=9133"
    
    try:
        conn.request("POST", path, payload, headers)
        res = conn.getresponse()
        if res.status == 200:
            print(f"[API UACJ] >>> POST exitoso. Estado enviado: {status_val}")
    except Exception as e:
        print(f"[API UACJ] >>> Error de red: {str(e)}")
    finally:
        conn.close()

# ==========================================
# 2. CONFIGURACIÓN DEL DETECTOR (TASKS API)
# ==========================================
base_options = python.BaseOptions(model_asset_path=MODEL_FILE)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1
)
detector = vision.HandLandmarker.create_from_options(options)

# Variable que recordará permanentemente el último comando enviado
estado_anterior = None 
cap = cv2.VideoCapture(0)

print("\n[SISTEMA] >>> Control por histéresis listo. Muestra tu mano...")

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    resultado_deteccion = detector.detect(mp_image)
    
    # Inicializamos el gesto detectado en ESTE frame específico como indefinido (None)
    gesto_frame = None

    # SI SE DETECTA UNA MANO DE FORMA CLARA
    if resultado_deteccion.hand_landmarks:
        landmarks = resultado_deteccion.hand_landmarks[0]
        
        # Dibujamos el esqueleto básico en pantalla
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 4, (255, 0, 0), -1)

        # Contamos dedos extendidos
        dedos_abiertos = 0
        puntas = [8, 12, 16, 20]   
        nudillos = [6, 10, 14, 18] 
        
        for i in range(4):
            if landmarks[puntas[i]].y < landmarks[nudillos[i]].y:
                dedos_abiertos += 1
                
        # --- APLICAMOS FILTRO DE HISTÉRESIS (ZONA MUERTA) ---
        if dedos_abiertos >= 3:
            gesto_frame = 1  # Intención clara: Mano Abierta (Abrir)
        elif dedos_abiertos <= 1:
            gesto_frame = 0  # Intención clara: Puño Cerrado (Cerrar)
        # Si dedos_abiertos == 2, gesto_frame se queda como None (Mantiene estado)

    # ==========================================
    # 3. FILTRO DE TRANSMISIÓN DE DATOS
    # ==========================================
    # Solo si el gesto del frame actual es válido (0 o 1) Y es diferente al último enviado:
    if gesto_frame is not None and gesto_frame != estado_anterior:
        estado_anterior = gesto_frame
        enviar_post_api(gesto_frame)

    # Desplegamos la realimentación visual en la ventana gráfica
    if estado_anterior == 1:
        texto_visual = "CASCO: ABIERTO (Sosteniendo estado)"
        color_visual = (0, 255, 0)
    elif estado_anterior == 0:
        texto_visual = "CASCO: CERRADO (Sosteniendo estado)"
        color_visual = (0, 0, 255)
    else:
        texto_visual = "CASCO: ESPERANDO PRIMER GESTO..."
        color_visual = (0, 255, 255)

    cv2.putText(frame, texto_visual, (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_visual, 2)
    cv2.imshow("Control por Vision - Histéresis", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()