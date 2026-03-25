import gpiozero as gz
from gpiozero import LED, AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory
from time import sleep
import http.client
import json
import math
from urllib.parse import urlencode

fabrica_pines = PiGPIOFactory()
servo_mascara = AngularServo(19, min_angle=0, max_angle=180, pin_factory=fabrica_pines)
led = LED(21)

payload_req = ''
headers = {}

while True:
    # Peticion a la API
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")

    try:
        conn.request("GET", "/ords/uacj/ironman/Jarvis?equipo=Equipo%202", payload_req, headers)
        res = conn.getresponse()
        data = res.read()

        if res.status == 200:
            response_json = json.loads(data)
            try:
                payload_str = response_json["items"][0]['payload']
                status = json.loads(payload_str)["status"]

                if status == 0:
                    led.off()
                    servo_mascara.angle = 0
                    print("LED OFF")
                else:
                    led.on()
                    servo_mascara.angle = 90
                    print("LED ON")
                    
            except (KeyError, IndexError, ValueError) as e:
                print("Error al acceder a los datos de la respuesta:", e)
        else:         
            print("Error en la solicitud:", res.status)
    except Exception as e:
        print("Error al realizar la solicitud:", str(e))
        sleep(5)  # Esperar antes de intentar nuevamente
    finally:
        conn.close()            
