import cv2
import numpy as np

# 1. Cargar la imagen (Usamos COLOR para evitar problemas con canales alfa)
image = cv2.imread("TralaleroTralala.jpg", cv2.IMREAD_COLOR)

if image is None:
    print("Error: No se pudo cargar la imagen. Verifica el nombre del archivo.")
else:
    # fx y fy son los factores de escala (0.5 es el 50%)
    image = cv2.resize(image, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
    
    # Creamos una copia para no ensuciar la original al dibujar
    img_contornos = image.copy()

    # 2. Convertir a escala de grises
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 3. Aplicar umbral (Threshold)
    # Usamos '_' para ignorar el primer valor devuelto (el valor del umbral)
    _, th = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

    # 4. Encontrar contornos
    # Nota: En versiones modernas de OpenCV, findContours solo devuelve (contornos, jerarquía)
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 5. Dibujar los contornos
    cv2.drawContours(img_contornos, contornos, -1, (0, 255, 0), 3)

    # 6. Mostrar los resultados
    cv2.imshow('1. Original', image)
    cv2.imshow('2. Grises', gray)
    cv2.imshow('3. Binaria (Threshold)', th)
    cv2.imshow('4. Contornos Finales', img_contornos)

    cv2.waitKey(0)
    cv2.destroyAllWindows()