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
import logging



# devolver un 1 unidad mas q TIMEOUT




BUFSIZE = 8192 # Tamaño máximo del buffer que se puede utilizar
TIMEOUT_CONNECTION = 20 # Timout para la conexión persistente
MAX_ACCESOS = 10
COOKIE_TIMER = 10

#Expresiones regulares
patron_cabeceras = r'([A-Z].*): (.+)'
er_cabeceras = re.compile(patron_cabeceras)

patron_get = r"(GET) (/.*) (HTTP/1.1)"
er_get = re.compile(patron_get)

patron_cookie = r'(Cookie): (cookie_counter)=(\d+)'
er_cookie = re.compile(patron_cookie)


# Extensiones admitidas (extension, name in HTTP)
filetypes = {"gif":"image/gif", "jpg":"image/jpg", "jpeg":"image/jpeg", "png":"image/png", "htm":"text/htm", 
             "html":"text/html", "css":"text/css", "js":"text/js", "ico":"image/jpg"}

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
        return cs.send(data)
    except BlockingIOError:
        print("Exception: enviar_mensaje(). Resource temporarily unaviable.", file=sys.stderr)


def recibir_mensaje(cs):
    """ Esta función recibe datos a través del socket cs
        Leemos la información que nos llega. recv() devuelve un string con los datos.
    """
    try:
        datos = cs.recv(BUFSIZE)
    except BlockingIOError:
        print("Exception: recibir_mensaje(). Resource temporarily unaviable.", file=sys.stderr)
    
    return datos.decode()


def enviar_recurso(ruta, tam, cabecera, cs):
    '''Esta funcion envia un recurso hacia el cliente teniendo en cuenta el
    tamaño del mismo.
    '''

    if (tam + len(cabecera) <= BUFSIZE):
        # Enviar normal
        with open(ruta, "rb") as f:
            buffer = f.read()
            to_send = cabecera.encode() + buffer
            enviar_mensaje(cs, to_send)   
    else:
        # Enviar un mensaje con la cabecera y despuoes ir leyendo BUFSIZE bytes y escribiendolos en el socket.
        enviar_mensaje(cs, cabecera.encode())
        with open(ruta, "rb") as f:
            while (1):
                buffer = f.read(BUFSIZE)
                if(not buffer):
                    break
                enviar_mensaje(cs, buffer)


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
        if(i.find("Cookie") > -1):
            if(i.find("cookie_counter") > -1):
                cookie = True
                val = int(i.split(sep="=", maxsplit=-1)[1])
                break
    
    
    if(not cookie): 
        print("\n\nEstableciendo cookie...")
        return 1

    if(val < MAX_ACCESOS): 
        return val+1

    return MAX_ACCESOS     

def enviar_error(addr_cliente, ruta, msg, motivo, cs):
    ''' Esta funcion envia una pagina de error hacia el cliente. Se apoya en enviar_recurso().
    '''
    print("\n\nSocket cerrado. Cliente: " + str(addr_cliente), file=sys.stderr)
    print("Motivo: " + motivo, file=sys.stderr)
    ftype = os.path.basename(ruta).split(".")
    ftype = ftype[len(ftype)-1]
    respuesta = msg + "\r\nDate: " + str(datetime.today()) + "\r\nServer: Chapuza SSTT\r\nContent-Length: " + str(os.stat(ruta).st_size) + "\r\n" + "Content-Type: "+ filetypes[ftype] + "\r\nConnection: close\r\n\r\n"
    enviar_recurso(ruta,  os.stat(ruta).st_size, respuesta, cs)

    print("Se procede a enviar la pagina web de error...")
    cerrar_conexion(cs)
    sys.exit(-1)  


def process_web_request(cs, webroot, addr_cliente):
    """ Procesamiento principal de los mensajes recibidos.
        Típicamente se seguirá un procedimiento similar al siguiente (aunque el alumno puede modificarlo si lo desea)
    """    
    try:
        # * Bucle para esperar hasta que lleguen datos en la red a través del socket cs con select()
        while(True):
            #* Se comprueba si hay que cerrar la conexión por exceder TIMEOUT_CONNECTION segundos sin recibir ningún mensaje o hay datos. 
            # Se utiliza select.select
            rsublist, wsublist, xsublist = select.select([cs], [], [], TIMEOUT_CONNECTION)

            # * Si es por timeout, se cierra el socket tras el período de persistencia.
            if(not rsublist):    
                print("\n\nHa saltado el Timeout.", file=sys.stderr)
                cerrar_conexion(cs)
                sys.exit(-1)
                
            # * Si no es por timeout y hay datos en el socket cs.

            # * Leer los datos con recv.
            data = recibir_mensaje(cs)

            if(not data):   
                cerrar_conexion(cs)
                sys.exit(-1)
        
            respuesta = "HTTP/1.1 200 OK\r\nDate: " + str(datetime.today()) + "\r\nServer: Chapuza SSTT\r\nContent-Length: "
            splitted = data.split(sep="\r\n", maxsplit=-1)

            text = ""
            headers = []
            #* Comprobar si la versión de HTTP es 1.1
            res = er_get.fullmatch(splitted[0])
            print("Cliente: " + str(addr_cliente))
            print("\n\nPETICION RECIBIDA: ")
            # * Analizar que la línea de solicitud y comprobar está bien formateada según HTTP 1.1
            if(res):
                text = res.group(2)
                for i in splitted:
                    if (not i):     #i == ""
                        continue
                    print(i)
                    if(i.find("GET") > -1):
                        continue
                    result = er_cabeceras.fullmatch(i)
                    if(not result):
                        print("\n\nERROR CABECERAS.", file=sys.stderr)
                        cerrar_conexion(cs)
                        sys.exit(-1)
                    #* Devuelve una lista con los atributos de las cabeceras.
                    headers.append(i)
                accesos = process_cookies(headers)
                # * Analizar las cabeceras. Imprimir cada cabecera y su valor. Si la cabecera es Cookie comprobar
                if (accesos >= MAX_ACCESOS):
                    
                    enviar_error(addr_cliente, "./errors/403.html", "HTTP/1.1 403 Forbidden", "Maximo de accesos", cs)

                recurso = text
                    
                if(recurso.find("..") > -1):
                    enviar_error(addr_cliente, "./errors/seguridad.html", "HTTP/1.1 403 Forbidden", "Fallo en la seguridad del programa.", cs)

                # Quitamos los parametros de la URL si los hubiera
                recurso = text.split(sep='?', maxsplit=1)[0]

                # * Comprobar si el recurso solicitado es /, En ese caso el recurso es index.html
                if(recurso == '/'): recurso = "/index.html"

                #  * Construir la ruta absoluta del recurso (webroot + recurso solicitado)
                r_solicitado = webroot + recurso

                # * Extraer extensión para obtener el tipo de archivo. Necesario para la cabecera Content-Type
                file_type = os.path.basename(r_solicitado).split(".")
                file_type = file_type[len(file_type)-1]

                # * Comprobar que el recurso (fichero) existe, si no devolver Error 404 "Not found"
                if(not os.path.isfile(r_solicitado)):
                    enviar_error(addr_cliente, "./errors/404.html", "HTTP/1.1 404 Method Not Allowed", "Recurso no existe en el servidor.", cs)


                if(file_type not in filetypes):
                    enviar_error(addr_cliente, "./errors/415.html", "HTTP/1.1 415 Unsopported Media Type" , "Tipo de archivo no permitido.", cs)

                # * Preparar respuesta con código 200. Construir una respuesta que incluya: la línea de respuesta y
                # las cabeceras Date, Server, Connection, Set-Cookie (para la cookie cookie_counter),
                #     Content-Length y Content-Type.
                respuesta = respuesta + str(os.stat(r_solicitado).st_size) + "\r\n"+ "Set-cookie: cookie_counter=" + str(accesos)+ "; Max-Age= "+ str(COOKIE_TIMER) + "\r\n" + "Content-Type: " + filetypes[file_type] + "\r\nKeep-Alive: timeout=" + str(TIMEOUT_CONNECTION+1) + ", max= " + str(MAX_ACCESOS) + "\r\nConnection: Keep-Alive\r\n\r\n"
                print("\n\nRESPUESTA:")
                print(respuesta)

                # * Leer y enviar el contenido del fichero a retornar en el cuerpo de la respuesta.
                enviar_recurso(r_solicitado, os.stat(r_solicitado).st_size, respuesta, cs)
                    
            else:
                sol = splitted[0].split(sep=" ", maxsplit=-1)
                # * Comprobar si es un método GET. Si no devolver un error Error 405 "Method Not Allowed".
                if(sol[0] != "GET" and sol[0] != "POST"):
                    enviar_error(addr_cliente, "./errors/405.html",  "HTTP/1.1 405 Method not allowed" , "Metodo no soportado.", cs)
                elif (sol[0] == "POST"):
                    #Hacer tratamiento con POST
                    found = False
                    er = "./post/error.html"
                    for i in splitted:
                        if(i.find("email=") > -1):
                            found = True
                            if(i.split(sep="%40")[1] == "um.es"):
                                er = "./post/verificado.html"

                    
                    if(not found):
                        enviar_error(addr_cliente, "./post/error.html", "HTTP/1.1 403 Forbidden" , "No se ha enviado el formulario correctamente.", cs)
                    
                    respuesta = respuesta + str(os.stat(er).st_size) + "\r\n" + "Keep-Alive: timeout=" + str(TIMEOUT_CONNECTION+1) + ", max= " + str(MAX_ACCESOS) + "\r\nConnection: Keep-Alive\r\n\r\n"
                    enviar_recurso(er,  os.stat(er).st_size, respuesta, cs)
                if(len(sol) != 3):
                    enviar_error(addr_cliente, "./errors/400.html", "HTTP/1.1 400 Bad Request" , "No se ha seguido el protocolo HTTP/1.1 .", cs)

                elif(sol[2].find("HTTP/") > -1 and sol[0] == "GET"):
                    enviar_error(addr_cliente, "./errors/505.html", "HTTP/1.1 505 Version Not Supported" , "Version de HTTP no soportada.", cs)    

                else:
                    enviar_error(addr_cliente, "./errors/400.html", "HTTP/1.1 400 Bad Request" , "No se ha seguido el protocolo HTTP/1.1 .", cs)
            
    except Exception:
        print("\n\nHa ocurrido un error inesperado.", file=sys.stderr)

        cerrar_conexion(cs)
        sys.exit(-1)


def main():
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

        #Con with, se gestiona tambien los try except.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as s1:
            
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            s1.bind((args.host, args.port))

            s1.listen(64)

            while(True):
                try:
                    new_socket, addr_cliente = s1.accept()
                except socket.error:
                    print("Error: accept del socket", file = sys.stderr)
                    cerrar_conexion(new_socket)
                    

                pid = os.fork()
                if(pid < 0):
                    print("Error en el hijo1", file = sys.stderr)
                elif(pid == 0):
                    cerrar_conexion(s1)      #porque son descriptores de ficheros y no van a usar los sockets correspondientes. s1 lo usa el padre para las peticiones, y el otro lo usa el hijo para crear sus hilicos
                    process_web_request(new_socket, args.webroot, addr_cliente)
                else:                       # proceso padre
                    cerrar_conexion(new_socket)


            
    except KeyboardInterrupt:
        True

if __name__== "__main__":
    main()
