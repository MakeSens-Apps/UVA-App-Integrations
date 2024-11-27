import boto3
import os
import json
import requests
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth

def lambda_handler(event, context):
    # Cargar variables de entorno
    graphql_api = os.environ['AppSyncURL']

    body = json.loads(event.get('body'))

    # Obtener el cod de vinculación del racimo
    name =  body.get('name')
    linkage_code = body.get('linkageCode')
    racimo_status = check_racimo_exists(linkage_code, graphql_api)

    if racimo_status['success']:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Racimo ya existe",
                "result": racimo_status['racimo_data']
            }),
            "headers": {
                "Content-Type": "application/json"
            }
        }
    else:  #Crear racimo
        racimo_id = create_racimo(linkage_code, name, graphql_api)

        if racimo_id:
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "success": True,
                    "message": "Racimo creado exitosamente",
                    "racimoId": racimo_id  # Incluir el ID del racimo creado
                }),
                "headers": {
                    "Content-Type": "application/json"
                }
            }
        else:
            # Si no se obtiene un ID, se lanza un error
            raise Exception("Error al crear el racimo. No se recibió el ID esperado.")

def create_racimo(linkage_code, name, graphql_api):
    # Validar si existe un RACIMO
    #graphql_api = "https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql"
    region = "us-east-1"

    query = """
        mutation MyMutation($linkageCode: String!, $name: String!, $configuration: String!) {
            createRACIMO(input: {LinkageCode: $linkageCode, Name: $name, Configuration: $configuration}) {
                id
            }
        }
    """

    # Define las variables
    variables = {
        "linkageCode": linkage_code,  # Asume que `linkage_code` está definido
        "name": name,
        "configuration": f"racimos/{linkage_code}/config.json"    # Asume que `name` está definido
    }

    # Crea el cuerpo de la solicitud con las variables
    post_body = json.dumps({
        "query": query,
        "operationName": "MyMutation",
        "variables": variables
    })

    signed_request = sign_request(graphql_api, "POST", post_body, region)
    response = requests.post(
        signed_request["url"],
        headers=signed_request["headers"],
        data=signed_request["body"]
    )

    # Verificar la respuesta
    if response.status_code == 200:
        response_data = response.json()
        
        # Comprobar si la creación fue exitosa
        if 'data' in response_data and 'createRACIMO' in response_data['data']:
            racimo_id = response_data['data']['createRACIMO']['id']
            return racimo_id  # Solo retornar el ID del racimo
        else:
            # Si no se encuentra el ID en la respuesta, lanzar una excepción
            raise Exception("Error al crear el racimo. No se recibió el ID esperado.")
    else:
        # Si no se obtiene un código 200, lanzar una excepción con el error
        raise Exception(f"Error al procesar la solicitud: {response.status_code} - {response.text}")

def check_racimo_exists(linkage_code, graphql_api):
    # Validar si existe un RACIMO
    #graphql_api = "https://swmmbj4xmfa5pelhgbljkxonuu.appsync-api.us-east-1.amazonaws.com/graphql"
    region = "us-east-1"

    query = """
        query MyQuery($linkageCode: String!) {
            listRACIMOS(filter: {LinkageCode: {eq: $linkageCode}}) {
                startedAt
                items {
                    Name
                    LinkageCode
                }
            }
        }
    """

    # Define las variables
    variables = {
        "linkageCode": linkage_code  # Suponiendo que `linkage_code` está definido en tu código
    }

    # Crea el cuerpo de la solicitud con las variables
    post_body = json.dumps({
        "query": query,
        "operationName": "MyQuery",
        "variables": variables
    })

    signed_request = sign_request(graphql_api, "POST", post_body, region)
    response = requests.post(
        signed_request["url"],
        headers=signed_request["headers"],
        data=signed_request["body"]
    )

    if response.status_code == 200:
        response_data = response.json()

        # Extraer los items de la respuesta
        items = response_data.get("data", {}).get("listRACIMOS", {}).get("items", [])

        # Validar si items está vacío
        if not items:
            result = False
            racimo_data = None  # No hay racimo
        else:
            # Validar que el LinkageCode coincida
            racimo = items[0] 
            if racimo.get("LinkageCode") == linkage_code:
                result = True
                racimo_data = {
                    "Name": racimo.get("Name"),
                    "LinkageCode": racimo.get("LinkageCode")
                }
            else:
                result = False
                racimo_data = None  # No hay racimo con el LinkageCode correcto

        # Devolvemos solo el diccionario con el estado y los datos del racimo
        return {
            "success": result,
            "racimo_data": racimo_data
        }

    else:
        print(f"Error: {response.status_code} - {response.text}")
        raise Exception(f"GraphQL request failed: {response.text}")

def sign_request(url, method, data, region):
    """Firma la solicitud HTTP con IAM usando SigV4."""
    credentials = get_aws_credentials()
    request = AWSRequest(
        method=method.upper(),
        url=url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    SigV4Auth(credentials, "appsync", region).add_auth(request)
    return {
        "url": url,
        "headers": dict(request.headers.items()),
        "body": request.data,
        "method": request.method,
    }

def get_aws_credentials():
    """Obtiene credenciales de AWS desde el entorno."""
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    return credentials

