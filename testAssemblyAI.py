# Codigo de prueba para la API de AssemblyAI, se utiliza un archivo de audio para transcribirlo y actualizar la API del casco de Iron Man. 

# Se importa la libreria de AssemblyAI y http.client para hacer actualizaciones a la API
import assemblyai as aai
import http.client
import json
from urllib.parse import urlencode

# Se configuran los parametros de la API, incluyendo la clave de API y la URL base.
aai.settings.base_url = "https://api.assemblyai.com"
aai.settings.api_key = "abd3cd8bcd7b4b42a9ba8069cc189ecf"

# Se especifica el archivo de audio a transcribir, en este caso se utiliza un archivo local.
audio_file = r"C:\Users\gerar\OneDrive\Documentos\UACJ\Decimo Semestre\Diseno Mecatronico\CascoIronman\OpenMask.m4a"

# Se configura la transcripcion, incluyendo los modelos de voz a utilizar, la deteccion de idioma y la identificacion de hablantes.
config = aai.TranscriptionConfig(
    speech_models=["universal-3-pro", "universal-2"],
    language_detection=True,
    speaker_labels=True,
)

# Se realiza la transcripcion del audio utilizando la API de AssemblyAI y se muestra el resultado en terminal.
transcript = aai.Transcriber().transcribe(audio_file, config=config)
if transcript.status == aai.TranscriptStatus.error:
    raise RuntimeError(f"Transcription failed: {transcript.error}")

print(f"\nFull Transcript:\n\n{transcript.text}")

if "open" in transcript.text.lower():
    print("Abriendo mascara")

    # Peticion a la API para actualizar el estado del casco
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}

    try: 
        conn.request
        conn.request("PUT", "/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:1%7D&id=9133", payload, headers)
        res = conn.getresponse()
        data = res.read()

        if res.status == 200:
            print("Estado del casco actualizado correctamente")
        else:
            print("Error al actualizar el estado del casco:", res.status)
    except Exception as e:
        print("Error al realizar la solicitud:", str(e))
    finally:        
        conn.close()                        

elif "close" in transcript.text.lower():
    print("Cerrando mascara")

    # Peticion a la API para actualizar el estado del casco
    conn = http.client.HTTPSConnection("uacj.ivancarvajal.org")
    payload = ''
    headers = {}

    try: 
        conn.request("PUT", "/ords/uacj/ironman/Jarvis?equipo=Equipo%202&payload=%7B%20%22Modelo%22:%20%22MK-50%22,%20%22potencia%22:%201200,%22status%22:0%7D&id=9133", payload, headers)
        res = conn.getresponse()
        data = res.read()

        if res.status == 200:
            print("Estado del casco actualizado correctamente")
        else:
            print("Error al actualizar el estado del casco:", res.status)
    except Exception as e:
        print("Error al realizar la solicitud:", str(e))
    finally:        
        conn.close()

else:
    print("No se reconocio el comando, por favor intente de nuevo")
