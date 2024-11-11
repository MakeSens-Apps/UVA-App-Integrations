import boto3
import os
import json
from datetime import datetime

def lambda_handler(event, context):
    sns_topic_arn = os.environ.get('SNSTopicARN')

    records = event['Records']
    new_records = []
    for record in records:
        new_record = process_data(record)
        new_records.append(new_record)

    # Publicar en el SNS
    attributes = {
        "typeDevice": "UVA",
        "typeData": "RAW"
    }
    print(new_records)
    rta= send_message_to_topic_sns(sns_topic_arn, new_records, attributes)
    print(rta)


def process_data(record):
    """
    Procesa un registro de evento de DynamoDB, transformándolo en un diccionario con el formato esperado.
    
    Esta función toma un registro de evento de DynamoDB, verifica si es de tipo 'INSERT' y,
    de ser así, extrae y transforma los datos relevantes para retornarlos en un nuevo formato.
    Convierte la marca de tiempo 'createdAt' a formato Unix en milisegundos.

    Args:
        record (dict): Un registro de evento de DynamoDB, que contiene los datos del 
                       cambio en la tabla (por ejemplo, tipo de evento, contenido del registro).

    Returns:
        dict or None: Retorna un diccionario con los datos procesados si el evento es de tipo 'INSERT'.
                      Retorna `None` si el evento no es 'INSERT'.
    """
    new_record = None
    
    # Validar que el evento sea de tipo "INSERT"
    if record['eventName'] == 'INSERT': 
        # Remover tipos de datos específicos de DynamoDB en el nuevo registro
        new_image = remove_data_types(record['dynamodb']['NewImage'])
        
        # Convertir 'createdAt' a Unix time en milisegundos
        dt = datetime.strptime(new_image['createdAt'], "%Y-%m-%dT%H:%M:%S.%fZ")
        
        # Crear el nuevo registro con los valores necesarios
        new_record = {
            "id": new_image.get('uvaID'),
            "type": new_image.get('type'),
            "ts": int(dt.timestamp() * 1000),  # Marca de tiempo en Unix en milisegundos
            "data": new_image.get('data', {}),  # Diccionario vacío si 'data' no existe
            "logs": new_image.get('logs', {})   # Diccionario vacío si 'logs' no existe
        }
    
    return new_record

def remove_data_types(data):
    """
    Recorre una estructura de datos que puede ser una lista de diccionarios o un diccionario anidado,
    y elimina los tipos de datos específicos de DynamoDB, convirtiendo valores numéricos a int o float,
    y valores booleanos a True o False.

    Args:
        data (list or dict): Estructura de datos a ser procesada, puede ser una lista de diccionarios o un diccionario anidado.

    Returns:
        list or dict: Estructura de datos procesada sin tipos de datos, con valores numéricos convertidos a int o float,
        y valores booleanos convertidos a True o False.
    """
    
     # Si es una lista de diccionarios
    if isinstance(data, list):  
        new_items = []
        for item in data:
            new_items.append(remove_data_types(item))
        return new_items
        
    # Si es un diccionario
    elif isinstance(data, dict):  
        new_item = {}
        for key, value in data.items():
            data_type, data_value = list(value.items())[0]

            if data_type == 'N':
                try:
                    new_item[key] = int(data_value)
                except ValueError:
                    new_item[key] = float(data_value)
            elif data_type == 'BOOL':
                new_item[key] = data_value == 'true'
            elif data_type == 'M':
                new_item[key] = remove_data_types(data_value)
            else:
                new_item[key] = data_value
        return new_item
    else:
        return 'No se puede procesar, el elemento no es una lista o diccionario con estructura de items dynamo'
    
def send_message_to_topic_sns(topic_arn, message, attributes=None):
    """
    Envía un mensaje a un tema de Amazon Simple Notification Service (SNS).
    Args:
        topic_arn (str): ARN del tema SNS al que se enviará el mensaje.
        message_body (dict o list): Cuerpo del mensaje a enviar en formato JSON.
        message_attributes (dict): Atributos personalizados del mensaje.
    Returns:
        dict: Un diccionario que indica el resultado del envío del mensaje.
            - Si el mensaje se envía correctamente:
                {'statusCode': 200, 'body': 'Mensaje enviado exitosamente al tema SNS.'}
            - Si ocurre un error:
                {'statusCode': Código de error HTTP, 'body': 'Mensaje de error correspondiente.'}
    """
    # Convierte el cuerpo del mensaje a formato JSON
    body = json.dumps(message)
    # Crea una instancia del cliente SNS
    sns = boto3.client('sns')
    # Verifica si el mensaje excede el límite de tamaño máximo de 256 KB
    if len(body.encode('utf-8')) > 256 * 1024:
        return {
            'statusCode': 500,
            'body': f"Tamaño del mensaje = {len(body.encode('utf-8'))} bytes, el cual excede el tamaño máximo."
        }
    else:
        # El mensaje no excede el límite de tamaño, enviarlo completo al tema SNS
        # Incluye message_attributes si se proporcionan
        att_dict = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                att_dict[key] = {"DataType": "String", "StringValue": value}
            elif isinstance(value, bytes):
                att_dict[key] = {"DataType": "Binary", "BinaryValue": value}
        response = sns.publish(
            TopicArn=topic_arn,
            Message=body,
            MessageAttributes=att_dict
        )
        # Verifica si el envío fue exitoso
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return {
                'statusCode': 200,
                'body': 'Mensaje enviado exitosamente al tema SNS.'
            }
        else:
            return {
                'statusCode': response['ResponseMetadata']['HTTPStatusCode'],
                'body': 'Error al enviar el mensaje al tema SNS.'
            }