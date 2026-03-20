import http.client
import json
import math
from urllib.parse import urlencode

def sysCall_init():
    sim = require('sim')
    
    # MEJORA 1: Obtener el handle del motor en la inicializaci?n (sysCall_init)
    # Hacerlo en actuation consume muchos recursos porque se ejecuta en cada frame.
    self.Mcara = sim.getObjectHandle('/Servo') 
    
    # MEJORA 2: Variable para controlar cada cu?nto tiempo llamamos a la API
    self.last_api_call_time = 0

def sysCall_actuation():
    sim = require('sim')
    
    # MEJORA 3: Limitar las llamadas a la API. 
    # sysCall_actuation se ejecuta cada ~50ms. Si haces una petici?n HTTP en cada ciclo, 
    # tu simulaci?n se va a congelar. Aqu? limitamos la llamada a 1 vez por segundo.
    current_time = sim.getSimulationTime()
    if current_time - self.last_api_call_time < 1.0:
        return # Si no ha pasado un segundo, salimos de la funci?n sin llamar a la API
    
    self.last_api_call_time = current_time

    # Petici?n a la API
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload_req = ''
    headers = {}
    
    try:
        conn.request("GET", "/ords/uacj/ironman/Jarvis?equipo=Equipo%202", payload_req, headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            response_json = json.loads(data)
            try:
                payload_str = response_json["items"][0]['payload']
                
                # --- LA SOLUCI?N AL ERROR ---
                # Reemplazamos las comillas escapadas por comillas normales
                clean_payload = payload_str.replace('\\"', '"')
                
                status = json.loads(clean_payload)["status"]
                print(f"Status recibido: {status}")
                
                if self.Mcara != -1:
                    if status == 0:
                        sim.setJointTargetPosition(self.Mcara, math.radians(-0.0))
                        print("Moviendo a -90 grados (Cerrando/Abriendo)")
                    else:
                        sim.setJointTargetPosition(self.Mcara, math.radians(-90.0))
                        print("Moviendo a 0 grados (Abriendo/Cerrando)")
                else:
                    print("Error, no se puede obtener el handle del objeto")
                    
            except(KeyError, IndexError, ValueError) as e:
                print("Error al procesar los datos JSON: ", str(e))
        else:
            print("Error al obtener respuesta de la API: ", res.status)
            
    except Exception as e:
         print("Error de red/conexion: ", str(e))
         
    finally:
        conn.close()

def sysCall_sensing():
    pass

def sysCall_cleanup():
    pass