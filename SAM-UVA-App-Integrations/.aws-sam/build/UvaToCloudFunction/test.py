import os
import requests
import boto3
from botocore.exceptions import ClientError

# Inicializar el cliente de DynamoDB
dynamodb = boto3.resource('dynamodb')
def lambda_handler(event, context):
    racimoTable = os.environ['RACIMOTable']
    organizationTable = os.environ['OrganizationTable']
    locationTable =  os.environ['LocationTable']
    appsync_url = os.environ['AppSyncURL']
    api_key = os.environ['ApiKey']
    
    # Evaluar todos los eventos
    records = event['Records']
    for record in records:
        # Si es un INSERT
        if record['eventName'] == 'INSERT': 
            process_insert_event(record, racimoTable, organizationTable, appsync_url, api_key)
        elif record['eventName'] == 'MODIFY': 
            process_modify_event(record, locationTable, appsync_url, api_key)

# Event ISERT
def process_insert_event(record, racimoTable, organizationTable, appsync_url, api_key):
    """
    Procesa un registro de tipo INSERT de DynamoDB Streams.
    Extrae el racimoID del registro y obtiene el LinkageCode de DynamoDB.

    :param record: Registro individual del evento DynamoDB Streams.
    :param racimoTable: Nombre de la tabla DynamoDB.
    :return: El LinkageCode si se encuentra, o un mensaje indicando que no se encontró racimoID.
    """
    #Obtener el Id de la UVA del evento
    uva_id = extract_uva_id(record)

    # Obtener el ID del Racimo del evento
    racimo_id = extract_racimo_id(record)
    if not racimo_id:
        return "No se encontró racimoID en el evento."

    # Obtener el código de vinculación del racimo
    linkage_code = get_linkage_code(racimoTable, racimo_id)
    if not linkage_code:
        return "El RACIMO no tiene un código de vinculación."
    
    # Obtener el ID de la organización asociada a la UVA 
    organization_id = get_organization_id(organizationTable, linkage_code)
    
    # Crear un nuevo dispositivo vinculado a dicha organización
    create_device(uva_id, organization_id, appsync_url, api_key)

# Event MODIFY
def process_modify_event(record,locationTable, appsync_url, api_key):
    uva_id = extract_uva_id(record)
    location = extract_location(record)

    if all(value is not None for value in location.values()):
        # Validar si ya esta la ubicación de la UVA creada
        uva_created = get_uva_location(uva_id, locationTable)
        print(uva_created)
        if uva_created:
            update_location(uva_id, location, appsync_url, api_key)
        else:
            create_location(uva_id, location, appsync_url, api_key)
            

# Service
def extract_location(record):
    """
    Extrae la latitude y latitude de un registro individual de DynamoDB Streams.

    :param record: Registro individual del evento de DynamoDB Streams.
    :return: location si existe, de lo contrario None.
    """
    try:
        location = {}
        if 'NewImage' in record['dynamodb']:
            location['latitude'] = record['dynamodb']['NewImage'].get('latitude', {}).get('S')
            location['longitude'] = record['dynamodb']['NewImage'].get('longitude', {}).get('S')
        return location
    except KeyError as e:
        print(f"Clave faltante en el registro: {e}")
        return None

def extract_uva_id(record):
    """
    Extrae el uva_id de un registro individual de DynamoDB Streams.

    :param record: Registro individual del evento de DynamoDB Streams.
    :return: Valor del uvaID si está presente, de lo contrario None.
    """
    try:
        # Validar que sea un evento con NewImage (INSERT o MODIFY típicamente)
        if 'NewImage' in record['dynamodb']:
            # Extraer el racimoID si está presente
            racimo_id = record['dynamodb']['NewImage'].get('id', {}).get('S')
            return racimo_id
        else:
            print("El registro no contiene una NewImage.")
            return None
    except KeyError as e:
        # Manejar cualquier excepción de clave faltante
        print(f"Clave faltante en el registro: {e}")
        return None
    
def extract_racimo_id(record):
    """
    Extrae el racimoID de un registro individual de DynamoDB Streams.

    :param record: Registro individual del evento de DynamoDB Streams.
    :return: Valor del racimoID si está presente, de lo contrario None.
    """
    try:
        # Validar que sea un evento con NewImage (INSERT o MODIFY típicamente)
        if 'NewImage' in record['dynamodb']:
            # Extraer el racimoID si está presente
            racimo_id = record['dynamodb']['NewImage'].get('racimoID', {}).get('S')
            return racimo_id
        else:
            print("El registro no contiene una NewImage.")
            return None
    except KeyError as e:
        # Manejar cualquier excepción de clave faltante
        print(f"Clave faltante en el registro: {e}")
        return None

def get_linkage_code(table_name, racimo_id):
    """
    Consulta DynamoDB para obtener el código de vinculación (LinkageCode) de un racimo por su ID.

    :param table_name: Nombre de la tabla DynamoDB.
    :param racimo_id: ID del racimo a consultar.
    :return: Código de vinculación (LinkageCode) o None si no existe.
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    try:
        # Obtener el elemento por su clave primaria
        response = table.get_item(
            Key={
                'id': racimo_id  # Clave primaria
            }
        )

        # Retornar el código de vinculación si el elemento existe
        return response['Item'].get('LinkageCode') if 'Item' in response else None

    except ClientError:
        # En caso de error, retornar None
        return None

def get_organization_id(table_name, linkage_code):
    """
    Obtiene el ID de una organización desde una tabla DynamoDB utilizando el valor de `linkage_code`.

    Esta función realiza una operación de escaneo en la tabla DynamoDB, buscando registros que coincidan con el valor
    proporcionado de `linkage_code`. Si encuentra al menos un registro que cumpla con la condición, retorna el `id`
    del primer registro encontrado. Si no encuentra registros o hay un error en el proceso, retorna `None`.

    :param table_name: str
        El nombre de la tabla DynamoDB donde se realizará la búsqueda. Esta tabla debe contener un atributo `linkage_code`.
    
    :param linkage_code: str
        El valor del `linkage_code` que se usará para filtrar los registros de la tabla.

    :return: str | None
        Retorna el valor de `id` del primer registro encontrado que coincida con el `linkage_code`, o `None` si no
        se encontró ningún registro o si ocurrió un error en la operación de DynamoDB.

    :raises: Exception
        En caso de que ocurra un error al interactuar con DynamoDB, la función captura la excepción y la imprime.
    """
    # Crear un cliente de DynamoDB
    dynamodb = boto3.resource('dynamodb')
    # Obtener la tabla específica
    table = dynamodb.Table(table_name)

    try:
        # Realizar un escaneo para buscar elementos con el `linkage_code` proporcionado
        response = table.scan(
            FilterExpression="linkage_code = :value",  # Filtrar registros por `linkage_code`
            ExpressionAttributeValues={":value": linkage_code}  # Asignar el valor de `linkage_code`
        )
        
        # Obtener la lista de elementos que coinciden con el filtro
        items = response.get("Items", [])
        
        # Si se encontraron elementos, retornar el id del primer elemento
        if items:
            return items[0]['id']
        else:
            # Si no se encontraron elementos, imprimir un mensaje y retornar None
            print("No se encontró ningún elemento con el linkage_code proporcionado.")
            return None
    except Exception as e:
        # Si ocurrió un error al interactuar con DynamoDB, imprimir el error y retornar None
        print(f"Error al buscar en DynamoDB: {e}")
        return None

def get_uva_location(uva_id,table_name):
    """
    Consulta DynamoDB para obtener el código de vinculación (LinkageCode) de un racimo por su ID.

    :param table_name: Nombre de la tabla DynamoDB.
    :param racimo_id: ID del racimo a consultar.
    :return: Código de vinculación (LinkageCode) o None si no existe.
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
  
    try:
        # Obtener el elemento por su clave primaria
        response = table.get_item(
            Key={
                'id': f"A{uva_id}"  # Clave primaria
            }
        )
        # Retornar el código de vinculación si el elemento existe
        return 'latitude' in response.get('Item', {})
    except ClientError:
        # En caso de error, retornar None
        return None

    
# mutations

def create_device(uva_id, organization_id, appsync_url, api_key):
    """
    Crea un dispositivo en el sistema mediante una mutación GraphQL.

    Args:
        uva_id (str): Identificador único del dispositivo a crear. Este valor se usará para el ID, descripción y nombre del dispositivo.
        organization_id (str): Identificador único de la organización a la que pertenece el dispositivo.

    Raises:
        ValueError: Si la respuesta de la API no tiene éxito.
    """   

    # La mutación GraphQL para crear un dispositivo
    mutation = """
    mutation createDevice($id: ID!, $description: String!, $organizationDevicesId: ID!, $name: String!, $deviceModelId: ID!) {
        createDevice(input: {id: $id, description: $description, organizationDevicesId: $organizationDevicesId, name: $name, deviceModelId: $deviceModelId}) {
            id
            description
            organizationDevicesId
            name
            deviceModelId
        }
    }
    """

    # Variables para la mutación
    variables = {
        "id": uva_id,
        "description": uva_id,
        "organizationDevicesId": organization_id,
        "name": uva_id,
        "deviceModelId": "UVA"
    }

    # Encabezados con la API Key
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key  # Usamos el API Key para autenticarnos
    }

    # Realizar la solicitud POST
    response = requests.post(
        appsync_url,
        headers=headers,
        json={'query': mutation, 'variables': variables}
    )

    # Verificar la respuesta
    if response.status_code == 200:
        data = response.json()
        print("Device created successfully:", data)
    else:
        print(f"Error al ejecutar la mutación: {response.status_code}, {response.text}")

def create_location(uva_id, location, appsync_url, api_key):
    """
    Crea un dispositivo en el sistema mediante una mutación GraphQL.

    Args:
        uva_id (str): Identificador único del dispositivo a crear. Este valor se usará para el ID, descripción y nombre del dispositivo.
        organization_id (str): Identificador único de la organización a la que pertenece el dispositivo.

    Raises:
        ValueError: Si la respuesta de la API no tiene éxito.
    """
    # La mutación GraphQL para crear un dispositivo
    mutation = """
    mutation createLocation($id: ID!, $deviceLocationsId: ID!, $latitude: Float, $length: Float) {
        createLocation(input: {deviceLocationsId: $deviceLocationsId, latitude: $latitude, length: $length, id: $id}) {
            id
        }
        }
    """

    # Variables para la mutación
    variables = {
        "id": f"A{uva_id}",
        "deviceLocationsId": uva_id,
        "latitude": location['latitude'],
        "length": location['longitude']
    }

    # Encabezados con la API Key
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key  # Usamos el API Key para autenticarnos
    }

    # Realizar la solicitud POST
    response = requests.post(
        appsync_url,
        headers=headers,
        json={'query': mutation, 'variables': variables}
    )

    # Verificar la respuesta
    if response.status_code == 200:
        data = response.json()
        print("Location created successfully:", data)
    else:
        print(f"Error al ejecutar la mutación: {response.status_code}, {response.text}")

def update_location(uva_id, location, appsync_url, api_key ):
    # La mutación GraphQL para crear un dispositivo
    mutation = """
    mutation updateLocation($id: ID!,  $latitude: Float, $length: Float) {
        updateLocation(input: {latitude: $latitude, length: $length, id: $id}) {
            id
          }
        }
    """

    # Variables para la mutación
    variables = {
        "id": f"A{uva_id}",
        "latitude": location['latitude'],
        "length": location['longitude']
    }

    # Encabezados con la API Key
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key  # Usamos el API Key para autenticarnos
    }

    # Realizar la solicitud POST
    response = requests.post(
        appsync_url,
        headers=headers,
        json={'query': mutation, 'variables': variables}
    )

    # Verificar la respuesta
    if response.status_code == 200:
        data = response.json()
        print("Location update successfully:", data)
    else:
        print(f"Error al ejecutar la mutación: {response.status_code}, {response.text}")