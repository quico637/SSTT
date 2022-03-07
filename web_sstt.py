#eres un penco que flipas

# coding=utf-8
#!/usr/bin/env python3


from posixpath import split
import socket
import selectors    #https://docs.python.org/3/library/selectors.html
import select
import types        # Para definir el tipo de datos data
import argparse     # Leer parametros de ejecución
import os           # Obtener ruta y extension
from datetime import datetime, timedelta # Fechas de los mensajes HTTP
import time         # Timeout conexión
import sys          # sys.exit
import re           # Analizador sintáctico
import logging      # Para imprimir logs



BUFSIZE = 8192 # Tamaño máximo del buffer que se puede utilizar
TIMEOUT_CONNECTION = 20 # Timout para la conexión persistente
MAX_ACCESOS = 10

#Expresiones regulares
patron_cabeceras = r'([A-Z].*): (.+)'
er_cabeceras = re.compile(patron_cabeceras)

patron_get = r"(GET) (/.*) (HTTP/1.1)"
er_get = re.compile(patron_get)

patron_cookie = r'(Cookie): (cookie_counter)=(\d+)'
er_cookie = re.compile(patron_cookie)


# Extensiones admitidas (extension, name in HTTP)
filetypes = {"gif":"image/gif", "jpg":"image/jpg", "jpeg":"image/jpeg", "png":"image/png", "htm":"text/htm", 
             "html":"text/html", "css":"text/css", "js":"text/js"}

# Configuración de logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s.%(msecs)03d] [%(levelname)-7s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()


def enviar_mensaje(cs, data):
    """ Esta función envía datos (data) a través del socket cs
        Devuelve el número de bytes enviados.
    """
    try: 
        return cs.send(data.encode())
    except BlockingIOError:
        print("Exception: enviar_mensaje(). Resource temporarily unaviable.")


def recibir_mensaje(cs):
    """ Esta función recibe datos a través del socket cs
        Leemos la información que nos llega. recv() devuelve un string con los datos.
    """
    try:
        datos = cs.recv(BUFSIZE)
    except BlockingIOError:
        print("Exception: recibir_mensaje(). Resource temporarily unaviable.")
    
    return datos.decode()


def enviar_recurso(ruta, tam, cabecera, cs):

    print("ha entrado en enviar_recurso()")
    if(ruta.find("gif") > -1 or ruta.find("jpg") > -1 or ruta.find("jpeg") > -1 or ruta.find("png") > -1):
        print("ha entrado en enviar_recurso() - imagen")
        enviar_mensaje(cs, cabecera)
        with open(ruta, "rb") as f:
            buffer = "no he leido nada"
            while (buffer):
                buffer = f.read(BUFSIZE)
                cs.send(buffer)
                #print("tola")

    
    if (tam + len(cabecera) <= BUFSIZE):
        # Enviar normal
        print("ha entrado en enviar_recurso() - normal")

        with open(ruta, "r") as f:
            buffer = f.read()
            to_send = cabecera + buffer
            enviar_mensaje(cs, to_send)
            #cs.send(to_send)        
    else:
        # Enviar un mensaje con la cabecera y despuoes ir leyendo BUFSIZE bytes y escribiendolos en el socket.
        print("ha entrado en enviar_recurso() - largo")
        enviar_mensaje(cs, cabecera)
        with open(ruta, "rb") as f:
            buffer = "no he leido nada"
            while (buffer):
                buffer = f.read(BUFSIZE)
                cs.send(buffer)

        


def cerrar_conexion(cs):
    """ Esta función cierra una conexión activa.
    """
    try: 
        cs.close()
    except socket.error:
        pass


def process_cookies(headers):
    """ Esta función procesa la cookie cookie_counter
        1. Se analizan las cabeceras en headers para buscar la cabecera Cookie
        2. Una vez encontrada una cabecera Cookie se comprueba si el valor es cookie_counter
        3. Si no se encuentra cookie_counter , se devuelve 1
        4. Si se encuentra y tiene el valor MAX_ACCESSOS se devuelve MAX_ACCESOS
        5. Si se encuentra y tiene un valor 1 <= x < MAX_ACCESOS se incrementa en 1 y se devuelve el valor
    """
    
    cookie = False
    val = -1

    for i in headers:
        print(i)

    for i in headers:
        if(i.find("Cookie") > -1):

            print("SE HA ENCONTRADO COOKIE")
            if(i.find("cookie_counter") > -1):
                cookie = True
                print("SE ha encontrado cookie_counter")
                print(i)
                val = int(i.split(sep="=", maxsplit=-1)[1])
                #res = er_cookie.fullmatch(i)
                #val = res.group(3)
                #val =
                print("VAL: " + str(val))
                break
    
    
    if(not cookie): 
        return 1

    if(val < MAX_ACCESOS): 
        return val+1


    return MAX_ACCESOS        


def process_web_request(cs, webroot):

    """ Procesamiento principal de los mensajes recibidos.
        Típicamente se seguirá un procedimiento similar al siguiente (aunque el alumno puede modificarlo si lo desea)

        * Bucle para esperar hasta que lleguen datos en la red a través del socket cs con select()

            * Se comprueba si hay que cerrar la conexión por exceder TIMEOUT_CONNECTION segundos
              sin recibir ningún mensaje o hay datos. Se utiliza select.select

            * Si no es por timeout y hay datos en el socket cs.
                * Leer los datos con recv.
                * Analizar que la línea de solicitud y comprobar está bien formateada según HTTP 1.1


                    * Devuelve una lista con los atributos de las cabeceras.
                    * Comprobar si la versión de HTTP es 1.1
                    * Comprobar si es un método GET. Si no devolver un error Error 405 "Method Not Allowed".
                    * Leer URL y eliminar parámetros si los hubiera
                    * Comprobar si el recurso solicitado es /, En ese caso el recurso es index.html
                    * Construir la ruta absoluta del recurso (webroot + recurso solicitado)
                    * Comprobar que el recurso (fichero) existe, si no devolver Error 404 "Not found"
                    * Analizar las cabeceras. Imprimir cada cabecera y su valor. Si la cabecera es Cookie comprobar
                      el valor de cookie_counter para ver si ha llegado a MAX_ACCESOS.
                      Si se ha llegado a MAX_ACCESOS devolver un Error "403 Forbidden"
                    * Obtener el tamaño del recurso en bytes.
                    * Extraer extensión para obtener el tipo de archivo. Necesario para la cabecera Content-Type
                    * Preparar respuesta con código 200. Construir una respuesta que incluya: la línea de respuesta y
                      las cabeceras Date, Server, Connection, Set-Cookie (para la cookie cookie_counter),
                      Content-Length y Content-Type.
                    * Leer y enviar el contenido del fichero a retornar en el cuerpo de la respuesta.
                    * Se abre el fichero en modo lectura y modo binario
                        * Se lee el fichero en bloques de BUFSIZE bytes (8KB)
                        * Cuando ya no hay más información para leer, se corta el bucle

            * Si es por timeout, se cierra el socket tras el período de persistencia.
                * NOTA: Si hay algún error, enviar una respuesta de error con una pequeña página HTML que informe del error.
    """
    #data = recibir_mensaje(cs)
    #enviar_mensaje(cs, data)
    #print(data)

    #try:
    while(True):
        rsublist, wsublist, xsublist = select.select([cs], [], [], TIMEOUT_CONNECTION)
        if(not rsublist):     # en el caso que el select falle
            print("select.select() ha fallado.")
            cerrar_conexion(cs)
            sys.exit()
            

        data = recibir_mensaje(cs)

        if(data):       #data != ""
            respuesta = "HTTP/1.1 200 OK\r\nDate: " + str(datetime.today()) + "\r\nServer: Chapuza SSTT\r\nContent-Length: "
            splitted = data.split(sep="\r\n", maxsplit=-1)

            #splitted = splitted
            print(splitted)


            # Comprobacion de que esta bien la peticion
            text = ""
            headers = []
            res = er_get.fullmatch(splitted[0])
            if(res):
                text = res.group(2)
                for i in splitted:
                    if (not i):     #i == ""
                        continue

                    if(i.find("GET") > -1):
                        continue
                    '''
                    if (i.find("GET") > -1): 
                        text = i.split(sep=" ", maxsplit=-1)
                        if(text[2] != "HTTP/1.1"):
                            salir = True
                            break
                        continue
                    '''
                    print("holaaaaaa" + i)
                    result = er_cabeceras.fullmatch(i)
                    if(not result):
                        print("ERROR CABECERAS")
                        cerrar_conexion(cs)
                        sys.exit(1)
                                
                    headers.append(i)
                    
            else:
                sol = splitted[0].split(sep=" ", maxsplit=-1)
                if(sol[0] != "GET"):
                    print("Error 405: Method not allowed.")
                    er = "./errors/405.html"
                    respuesta = respuesta + str(os.stat(er).st_size) + "\r\n" + "Content-Type: html" + "\r\nKeep-Alive: timeout=" + str(TIMEOUT_CONNECTION) + ", max= " + str(MAX_ACCESOS) + "\r\nConnection: Keep-Alive\r\n\r\n"
                    enviar_recurso(er,  os.stat(er).st_size, respuesta, cs)
                    cerrar_conexion(cs)
                    sys.exit()

                else:
                    print("No se ha seguido el protocolo HTTP 1.1")
                    cerrar_conexion(cs)
                    sys.exit()

            accesos = process_cookies(headers)
            print("SALE DE ACCESOS")
            if (accesos >= MAX_ACCESOS):
                print("Maximo de accesos.")
                er = "./errors/403.html"
                respuesta = respuesta + str(os.stat(er).st_size) + "\r\n" + "Content-Type: html" + "\r\nKeep-Alive: timeout=10, max=100\r\nConnection: Keep-Alive\r\n\r\n"
                enviar_recurso(er,  os.stat(er).st_size, respuesta, cs)
                cerrar_conexion(cs)
                sys.exit()


            recurso = "/index.html"
            if(text != "/"):
                print("NO es el barra hejo")
                print("TEXT: " + text)
                recurso = text.split(sep='?', maxsplit=1)[0]
            elif(recurso.find("..") > -1):
                print("Violando un principio de seguridad basica.")
                er = "./errors/seguridad.html"
                respuesta = respuesta + str(os.stat(er).st_size) + "\r\n" + "Content-Type: html" + "\r\nKeep-Alive: timeout=10, max=100\r\nConnection: Keep-Alive\r\n\r\n"
                enviar_recurso(er,  os.stat(er).st_size, respuesta, cs)
                cerrar_conexion(cs)
                sys.exit()

            if(recurso == '/'): recurso = "/index.html"
            print("\n\nRECURSO:" +  recurso)

            r_solicitado = webroot + recurso
            if(not os.path.isfile(r_solicitado)):
                err = "./errors/404.html"
                respuesta = respuesta + str(os.stat(err).st_size) + "\r\n" + "Content-Type: html" + "\r\nKeep-Alive: timeout=10, max=100\r\nConnection: Keep-Alive\r\n\r\n"
                enviar_recurso(err, os.stat(err).st_size, respuesta, cs)
                cerrar_conexion(cs)
                sys.exit()

            #cuando estoy enviando un error, tengo que seguir teniendo el conexion keep alive?
            file_type = os.path.basename(r_solicitado).split(".")[1]
            if(file_type not in filetypes):
                err = "./errors/415.html"
                respuesta = respuesta + str(os.stat(err).st_size) + "\r\n" + "Content-Type: html" + "\r\nKeep-Alive: timeout=10, max=100\r\nConnection: Keep-Alive\r\n\r\n"
                enviar_recurso(err, os.stat(err).st_size, respuesta, cs)
                cerrar_conexion(cs)
                sys.exit()

            #"Set-cookie: cookie_counter=" + str(accesos) + "\r\n"
            respuesta = respuesta + str(os.stat(r_solicitado).st_size) + "\r\n"+ "Set-cookie: cookie_counter=" + str(accesos) + "\r\n" + "Content-Type: " + file_type + "\r\nKeep-Alive: timeout=" + str(TIMEOUT_CONNECTION) + ", max= " + str(MAX_ACCESOS)+ "\r\nConnection: Keep-Alive\r\n\r\n"
            print(respuesta)
            enviar_recurso(r_solicitado, os.stat(r_solicitado).st_size, respuesta, cs)
            print("HE LLEGAO AL FINAL")

    '''except Exception:
        print("Han cerrao el socket lo mas probable")
           
        #cuando encontramos un error tenemos que cerrar el socket? las 2 opciones son validas. Con un close tienes que hacer un exit Cuando cierro, mandar un conection close y si lo mantienes pues le mandas un conection keep alive
        print(data)
        cerrar_conexion(cs)
        sys.exit()'''


def main():
    """ Función principal del servidor
    """

    try:

        # Argument parser para obtener la ip y puerto de los parámetros de ejecución del programa. IP por defecto 0.0.0.0
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--port", help="Puerto del servidor", type=int, required=True)
        parser.add_argument("-ip", "--host", help="Dirección IP del servidor o localhost", required=True)
        parser.add_argument("-wb", "--webroot", help="Directorio base desde donde se sirven los ficheros (p.ej. /home/user/mi_web)")
        parser.add_argument('--verbose', '-v', action='store_true', help='Incluir mensajes de depuración en la salida')
        args = parser.parse_args()


        if args.verbose:
            logger.setLevel(logging.DEBUG)

        logger.info('Enabling server in address {} and port {}.'.format(args.host, args.port))

        logger.info("Serving files from {}".format(args.webroot))

        """ Funcionalidad a realizar
        * 1. Crea un socket TCP (SOCK_STREAM)
        
        * Permite reusar la misma dirección previamente vinculada a otro proceso. Debe ir antes de sock.bind
        * Vinculamos el socket a una IP y puerto elegidos

        * Escucha conexiones entrantes

        * Bucle infinito para mantener el servidor activo indefinidamente
            - Aceptamos la conexión

            - Creamos un proceso hijo

            - Si es el proceso hijo se cierra el socket del padre y procesar la petición con process_web_request()

            - Si es el proceso padre cerrar el socket que gestiona el hijo.
        """

        # 1

        # try except
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as s1:
            
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            s1.bind((args.host, args.port))

            s1.listen(64)

            while(True):
                try:
                    new_socket, addr_cliente = s1.accept()
                except socket.error:
                    print("Error: accept del socket")
                    cerrar_conexion(new_socket)
                    

                pid = os.fork()
                if(pid < 0):
                    print("Error en el hijo1", file = sys.stderr)
                elif(pid == 0):
                    cerrar_conexion(s1)      #porque son descriptores de ficheros y no van a usar los sockets correspondientes. s1 lo usa el padre para las peticiones, y el otro lo usa el hijo para crear sus hilicos
                    process_web_request(new_socket, args.webroot)
                else:                       # proceso padre
                    cerrar_conexion(new_socket)


            
    except KeyboardInterrupt:
        True

if __name__== "__main__":
    main()
