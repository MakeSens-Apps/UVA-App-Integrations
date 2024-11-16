import os
import json
import requests
import boto3
from botocore.exceptions import ClientError


def lambda_handler(event, context):
    uva_id = event['pathParameters']['id_uva']

    result = get_last_measurement(uva_id)
    
    # Retornar el resultado a API Gateway (o procesar según sea necesario)
    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }

def get_last_measurement(uva_id):
    """
    Crea un dispositivo en el sistema mediante una mutación GraphQL utilizando autenticación IAM.

    Args:
        uva_id (str): Identificador único del dispositivo a crear. Este valor se usará para el ID, descripción y nombre del dispositivo.
        organization_id (str): Identificador único de la organización a la que pertenece el dispositivo.

    Raises:
        ValueError: Si la respuesta de la API no tiene éxito.
    """
    
    # Configura tus credenciales de AWS y la URL de AppSync
    appsync_url = 'https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql'
    api_key = 'da2-ocpxiy4zsncszex4m7lepzxgnq'

    # Variables para la consulta
    variables = {
        "uvaID": uva_id
    }

    # Consulta GraphQL
    query = """
    query lastMeasurement($uvaID: ID!) {
        measurementsByUvaIDAndTs(uvaID: $uvaID, sortDirection: DESC, limit: 1) {
            startedAt
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

    # Verificar la respuesta
    if response.status_code == 200:
        data = response.json()
        return data
        print("Device created successfully:", data)
    else:
        return None
        print(f"Error al ejecutar la query: {response.status_code}, {response.text}")