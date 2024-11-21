import os
import json
import requests
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError


import json

def lambda_handler(event, context):
    """
    Manejador principal para la Lambda. Obtiene el estado de conexión de una UVA 
    basándose en la última medición registrada.

    Args:
        event (dict): Evento recibido, incluye parámetros de entrada.
        context (object): Contexto de ejecución de AWS Lambda.

    Returns:
        dict: Respuesta con el estado HTTP y el cuerpo de la respuesta JSON.
    """
    # Obtener parametros de entorno
        # Configura tus credenciales de AWS y la URL de AppSync
    appsync_url = os.environ['AppSyncURL']
    api_key = os.environ['ApiKey']


    # Obtener el ID de la UVA desde los parámetros de la ruta del evento
    uva_id = event['pathParameters']['id_uva']
    query_params = event.get("queryStringParameters") or {}

    results = {}
    if uva_id == 'all':
        ids_ = query_params.get("id")
        ids = ids_.split(',')
        for id in ids:
            results[id] = get_connection_status(id, appsync_url, api_key)
    else:
        results[uva_id] = get_connection_status(uva_id, appsync_url, api_key)

    # Retornar la respuesta con código HTTP 200 y el resultado en formato JSON
    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }

def get_connection_status(uva_id, appsync_url, api_key):
    """
    Obtiene el estado de conexión de una UVA basada en la última medición registrada.

    Args:
        uva_id (str): Identificador único de la UVA.

    Returns:
        dict: Diccionario con el estado de conexión (`connection`) y el timestamp (`ts`)
              si se encontró la última conexión.
        None: Si no se encontró información de conexión para la UVA especificada.
    """
    # Obtener la última conexión (timestamp en UNIX ms) usando la función auxiliar
    lastConnection = get_last_connection(uva_id, appsync_url, api_key)

    # Validar si se obtuvo la última conexión
    if not lastConnection:
        # validar si fue creada
        return None  # No hay información de conexión

    # Verificar si la última conexión está dentro de las últimas 24 horas
    status = is_within_last_24_hours(lastConnection)

    # Construir el resultado con el estado de conexión y el timestamp
    return {
        "connection": status,  # True si está dentro de las últimas 24 horas, False si no
        "ts": lastConnection   # Timestamp de la última conexión
    }

def is_within_last_24_hours(last_connection):
    """
    Verifica si la última conexión está dentro de las últimas 24 horas (en UTC).

    Args:
        last_connection (int): Timestamp en formato UNIX (milisegundos) de la última conexión.

    Returns:
        bool: True si está dentro de las últimas 24 horas, False en caso contrario.
    """
    now = int(datetime.utcnow().timestamp() * 1000)  # Tiempo actual en UNIX ms (UTC)
    twenty_four_hours_ago = now - (24 * 60 * 60 * 1000)  # Hace 24 horas en ms
    return twenty_four_hours_ago <= last_connection <= now

def get_last_connection(uva_id, appsync_url, api_key):
    """
    Obtiene la última medición registrada para un dispositivo específico (UVA) utilizando una consulta GraphQL.

    Args:
        uva_id (str): Identificador único de la UVA para la cual se desea obtener la última medición.

    Returns:
        int: Timestamp de la última medición en formato UNIX (milisegundos) si existe, o `None` en caso contrario.

    Raises:
        ValueError: Si la respuesta de la API no tiene éxito o si hay un error al procesar los datos.
    """
    # Variables para la consulta
    variables = {
        "uvaID": uva_id
    }

    # Consulta GraphQL
    query = """
    query lastMeasurement($uvaID: ID!) {
        measurementsByUvaIDAndTs(uvaID: $uvaID, sortDirection: DESC, limit: 1) {
            items {
                ts
                createdAt
            }
        }
    }
    """

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key  # Usamos el API Key para autenticarnos
    }

    # Realizar la solicitud POST
    response = requests.post(
        appsync_url,
        headers=headers,
        json={'query': query, 'variables': variables}
    )

    
    if response.status_code == 200:
        data = response.json()
        print(data)
        items = data.get('data', {}).get('measurementsByUvaIDAndTs', {}).get('items', [])
        created_at = items[0].get('createdAt') if items else None
        if created_at:
            return int(datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp() * 1000) if created_at else None
        else:
            creation_date = get_creation_date(uva_id, appsync_url, api_key)
            return creation_date

    else:
        return None

def get_creation_date(uva_id, appsync_url, api_key):
    # Variables para la consulta
    variables = {
        "uvaID": uva_id
    }

    # Consulta GraphQL
    query = """
    query lastMeasurement($uvaID: ID!) {
        getUVA(id: $uvaID) {
            createdAt
        }
    }
    """

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key  # Usamos el API Key para autenticarnos
    }

    # Realizar la solicitud POST
    response = requests.post(
        appsync_url,
        headers=headers,
        json={'query': query, 'variables': variables}
    )
    
    if response.status_code == 200:
        data = response.json()
        created_at = data.get('data', {}).get('getUVA', {}).get('createdAt')
        return int(datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp() * 1000) if created_at else None
    else:
        return None