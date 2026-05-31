# Funciones Lambda

Este documento provee especificaciones detalladas de cada función Lambda en el servicio UVA-App-Integrations.

---

## Función 1: DynamoDBEventProcessorFunction

### Descripción General
**Nombre**: DynamoDBEventProcessorFunction
**Propósito**: Procesar datos de mediciones desde DynamoDB Streams y publicar en SNS para distribución en tiempo real
**Ubicación**: `SAM-UVA-App-Integrations/lambdas/deviceDataAccess/dynamodb_to_sns.py`

### Disparador

**Tipo**: DynamoDB Stream
**Fuente**: Stream de la tabla Measurement
**Configuración**:
```yaml
Stream ARN: arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
Batch Size: 10
Maximum Batching Window: 10 segundos
Starting Position: LATEST
Event Types: INSERT, MODIFY, REMOVE (filtra solo INSERT en el código)
```

**Evento de Ejemplo**:
```json
{
  "Records": [
    {
      "eventID": "1",
      "eventName": "INSERT",
      "eventSource": "aws:dynamodb",
      "dynamodb": {
        "NewImage": {
          "id": {"S": "uva123"},
          "type": {"S": "temperature"},
          "ts": {"S": "2024-01-15T10:30:00Z"},
          "data": {"M": {"value": {"N": "36.5"}}},
          "logs": {"L": []}
        }
      }
    }
  ]
}
```

### Entradas Esperadas

**Campos del Registro del DynamoDB Stream**:
- `eventName`: Tipo de evento (INSERT, MODIFY, REMOVE)
- `dynamodb.NewImage`: Datos del registro en formato DynamoDB
  - `id` (String): Identificador del dispositivo UVA
  - `type` (String): Tipo de medición (temperature, pressure, etc.)
  - `ts` (String): Timestamp ISO 8601
  - `data` (Map): Objeto con los datos de la medición
  - `logs` (List): Entradas de log opcionales

**Formatos de Tipos de Datos** (tipos nativos de DynamoDB):
- `S`: String
- `N`: Número (almacenado como string, requiere parseo)
- `M`: Map (objeto anidado)
- `L`: List (array)

### Lógica de Procesamiento

**Función**: `lambda_handler(event, context)`
```python
def lambda_handler(event, context):
    """
    Punto de entrada principal de la función Lambda

    Args:
        event: Evento del DynamoDB Stream con array de Records
        context: Contexto de ejecución de Lambda

    Returns:
        dict: Código de estado y resumen del procesamiento
    """
```

**Funciones Principales**:

1. **`process_data(records)`**
   - Filtra los registros solo para eventos INSERT
   - Extrae datos NewImage de cada registro
   - Llama a `remove_data_types()` para transformar el formato
   - Devuelve la lista de registros procesados

2. **`remove_data_types(data)`**
   - Convierte recursivamente el formato DynamoDB a tipos Python nativos
   - Maneja String (S), Number (N), Map (M), List (L), Boolean (BOOL)
   - Preserva la estructura de datos eliminando las anotaciones de tipo

   Transformación de ejemplo:
   ```python
   # Entrada
   {"value": {"N": "36.5"}, "unit": {"S": "celsius"}}

   # Salida
   {"value": 36.5, "unit": "celsius"}
   ```

3. **`send_message_to_topic_sns(data)`**
   - Convierte el timestamp ISO a milisegundos Unix
   - Publica el mensaje en el topic SNS
   - Agrega atributos del mensaje: `typeDevice=UVA`, `typeData=RAW`

### Salidas Generadas

**Estructura del Mensaje SNS**:
```json
{
  "id": "uva123",
  "type": "temperature",
  "ts": 1705318200000,
  "data": {
    "value": 36.5,
    "unit": "celsius"
  },
  "logs": []
}
```

**Atributos del Mensaje SNS**:
```python
{
  "typeDevice": {"DataType": "String", "StringValue": "UVA"},
  "typeData": {"DataType": "String", "StringValue": "RAW"}
}
```

**Logs de CloudWatch**:
- Conteo de registros procesados
- Confirmación de publicación en SNS (MessageId)
- Detalles del error si el procesamiento falla

### Variables de Entorno Requeridas

```bash
TOPIC_SNS_ARN=arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-{env}
```

**Configurado vía**: Parámetro `Ref: TopicSNSDataArn` en la plantilla SAM

### Servicios AWS Consumidos

| Servicio | Operación | Propósito |
|---------|-----------|---------|
| DynamoDB Streams | GetRecords | Leer eventos del stream (automático) |
| Amazon SNS | Publish | Enviar datos procesados al topic |
| CloudWatch Logs | PutLogEvents | Almacenar logs de ejecución |

### Permisos IAM Requeridos

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetRecords",
        "dynamodb:GetShardIterator",
        "dynamodb:DescribeStream",
        "dynamodb:ListStreams"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-*/stream/*"
    },
    {
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:913045965320:log-group:/aws/lambda/*"
    }
  ]
}
```

### Dependencias

**Paquetes Python** (desde `requirements.txt`):
```
boto3==1.34.29
```

**Librería Estándar**:
- `json`: Parseo de JSON
- `datetime`: Conversión de timestamps
- `os`: Acceso a variables de entorno

### Manejo de Errores

- **Formato de registro inválido**: Registra el error, omite el registro, continúa procesando
- **Fallo al publicar en SNS**: Lanza excepción, Lambda reintenta el lote completo
- **Error de conversión de timestamp**: Registra advertencia, usa el timestamp actual

### Características de Rendimiento

- **Arranque en Frío**: ~2-3 segundos
- **Ejecución en Caliente**: ~200-500ms para 10 registros
- **Uso de Memoria**: ~100-150 MB
- **Timeout**: 600 segundos (configurado)

---

## Función 2: UvaToCloudFunction

### Descripción General
**Nombre**: UvaToCloudFunction
**Propósito**: Sincronizar datos de dispositivos UVA con MakeSensCloud creando dispositivos y gestionando ubicaciones
**Ubicación**: `SAM-UVA-App-Integrations/lambdas/cloud/uva_to_cloud.py`

### Disparador

**Tipo**: DynamoDB Stream
**Fuente**: Stream de la tabla UVA
**Configuración**:
```yaml
Stream ARN: arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
Batch Size: 10
Maximum Batching Window: 10 segundos
Starting Position: LATEST
Event Types: INSERT, MODIFY
```

### Entradas Esperadas

**Evento INSERT** (Nuevo UVA Creado):
```json
{
  "eventName": "INSERT",
  "dynamodb": {
    "NewImage": {
      "id": {"S": "uva123"},
      "name": {"S": "Device Floor 3"},
      "racimoID": {"S": "racimo456"}
    }
  }
}
```

**Evento MODIFY** (Ubicación Actualizada):
```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "NewImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4194"}
    }
  }
}
```

### Lógica de Procesamiento

**Función**: `lambda_handler(event, context)`

**Flujo de Procesamiento**:
1. Iterar sobre los registros del stream
2. Verificar el tipo de evento (INSERT o MODIFY)
3. Enrutar al manejador correspondiente

**Manejador INSERT**: `process_insert_event(record)`
```python
def process_insert_event(record):
    """
    Crea el dispositivo en MakeSensCloud

    Pasos:
    1. Extraer UVA ID y RACIMO ID del registro
    2. Consultar la tabla RACIMO por LinkageCode
    3. Escanear la tabla Organization para encontrar la linkage_code correspondiente
    4. Extraer organizationID
    5. Llamar a la mutación GraphQL createDevice

    Devuelve: None (registra éxito/fallo)
    """
```

**Consultas a la Base de Datos**:
```python
# Obtener LinkageCode del RACIMO
racimo = dynamodb.get_item(
    TableName=RACIMO_TABLE,
    Key={'id': racimo_id}
)
linkage_code = racimo['Item']['LinkageCode']

# Encontrar la Organización
organization = dynamodb.scan(
    TableName=ORGANIZATION_TABLE,
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': linkage_code}
)
org_id = organization['Items'][0]['id']
```

**Mutación GraphQL**:
```graphql
mutation CreateDevice {
  createDevice(
    organizationID: "org123"
    name: "Device Floor 3"
    description: "UVA Device"
    typeDevice: "UVA"
    metadata: "{}"
  ) {
    id
  }
}
```

**Manejador MODIFY**: `process_modify_event(record)`
```python
def process_modify_event(record):
    """
    Actualiza o crea la ubicación del dispositivo

    Pasos:
    1. Extraer latitud y longitud del registro
    2. Validar que ambas coordenadas estén presentes
    3. Consultar la tabla Location por el registro existente (id = A{uvaID})
    4. Si existe: llamar a updateLocation
    5. Si no existe: llamar a createLocation

    Devuelve: None (registra éxito/fallo)
    """
```

**Validación de Ubicación**:
```python
if 'latitude' not in new_image or 'longitude' not in new_image:
    return  # Omitir si está incompleto
```

**Verificación de Ubicación**:
```python
location_id = f"A{uva_id}"
existing = dynamodb.get_item(
    TableName=LOCATION_TABLE,
    Key={'id': location_id}
)

if existing:
    update_location(location_id, lat, lng)
else:
    create_location(location_id, lat, lng)
```

### Salidas Generadas

**Respuesta de Creación de Dispositivo**:
```json
{
  "data": {
    "createDevice": {
      "id": "device789"
    }
  }
}
```

**Respuesta de Creación de Ubicación**:
```json
{
  "data": {
    "createLocation": {
      "id": "Auva123",
      "latitude": 37.7749,
      "longitude": -122.4194
    }
  }
}
```

**Logs de CloudWatch**:
- Tipo de evento y UVA ID
- Resultados de la búsqueda de RACIMO y Organization
- Solicitud y respuesta GraphQL
- Mensajes de éxito/error

### Variables de Entorno Requeridas

```bash
# Endpoint AppSync
APPSYNC_GRAPHQL_URL=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql

# Autenticación API
APPSYNC_API_KEY=da2-xxxxxxxxxxxxxxxxxxxxx

# Tablas DynamoDB
RACIMO_TABLE_NAME=RACIMO-{AppId}-{env}
ORGANIZATION_TABLE_NAME=Organization-{AppId}-{env}
LOCATION_TABLE_NAME=Location-{AppId}-{env}
```

**Configurado vía**: Parámetros de la plantilla SAM y Refs

### Servicios AWS Consumidos

| Servicio | Operación | Propósito |
|---------|-----------|---------|
| DynamoDB Streams | GetRecords | Leer cambios de la tabla UVA |
| DynamoDB | GetItem | Obtener detalles del RACIMO |
| DynamoDB | Scan | Encontrar Organization por linkage code |
| DynamoDB | GetItem | Verificar si existe Location |
| AWS AppSync | Mutación GraphQL | Crear/actualizar dispositivos y ubicaciones |
| CloudWatch Logs | PutLogEvents | Almacenar logs de ejecución |

### Permisos IAM Requeridos

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:DescribeStream"],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/UVA-*/stream/*"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/RACIMO-*",
        "arn:aws:dynamodb:us-east-1:*:table/Location-*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/Organization-*"
    }
  ]
}
```

### Dependencias

**Paquetes Python**:
```
boto3==1.34.29
requests==2.31.0
```

### Manejo de Errores

- **RACIMO no encontrado**: Registra el error, omite la creación del dispositivo
- **Organization no encontrada**: Registra el error, omite la creación del dispositivo
- **Datos de ubicación inválidos**: Omite la sincronización de ubicación, registra advertencia
- **Error de la API GraphQL**: Registra la respuesta completa del error, Lambda falla (dispara reintento)

### Características de Rendimiento

- **Arranque en Frío**: ~3-4 segundos
- **Ejecución en Caliente**: 1-2 segundos por dispositivo (debido a las consultas DynamoDB + llamadas GraphQL)
- **Uso de Memoria**: ~150-200 MB
- **Latencia de Red**: ~500ms para llamadas a AppSync

---

## Función 3: UVALastConnection

### Descripción General
**Nombre**: UVALastConnection
**Propósito**: Endpoint REST API para verificar el estado de conexión de los dispositivos UVA
**Ubicación**: `SAM-UVA-App-Integrations/lambdas/uvaConnection/last_connection.py`

### Disparador

**Tipo**: REST API de API Gateway
**Método HTTP**: GET
**Ruta**: `/{id_uva}/connection`
**Autorización**: AWS_IAM

**Solicitudes de Ejemplo**:
```bash
# Dispositivo único
GET /uva123/connection

# Múltiples dispositivos
GET /all/connection?ids=uva1,uva2,uva3
```

### Entradas Esperadas

**Parámetros de Ruta**:
- `id_uva` (String): ID del dispositivo UVA o el literal "all" para consulta masiva

**Parámetros de Cadena de Consulta** (cuando id_uva = "all"):
- `ids` (String): Lista de IDs de UVA separados por comas
  - Ejemplo: `?ids=uva123,uva456,uva789`

**Estructura del Evento**:
```json
{
  "pathParameters": {
    "id_uva": "uva123"
  },
  "queryStringParameters": {
    "ids": "uva1,uva2"
  }
}
```

### Lógica de Procesamiento

**Función**: `lambda_handler(event, context)`

**Lógica de Enrutamiento**:
```python
if id_uva == "all":
    # Modo de consulta masiva
    ids = query_params.get('ids', '').split(',')
    return get_connection_status(ids)
else:
    # Modo de consulta individual
    return get_connection_status([id_uva])
```

**Verificación de Conexión**: `get_connection_status(uva_ids)`
```python
def get_connection_status(uva_ids):
    """
    Para cada UVA ID:
    1. Llamar a get_last_connection(uva_id)
    2. Verificar si el timestamp está dentro de las últimas 24 horas
    3. Construir el objeto de respuesta

    Devuelve: {uva_id: {connection: bool, ts: int}}
    """
```

**Obtener Última Medición**: `get_last_connection(uva_id)`
```python
def get_last_connection(uva_id):
    """
    Consultar AppSync por la última medición

    Consulta GraphQL:
    measurementsByUvaIDAndTs(
      uvaID: $id
      sortDirection: DESC
      limit: 1
    )

    Fallback: Si no hay mediciones, consultar la fecha de creación del UVA

    Devuelve: timestamp_ms (int)
    """
```

**Consulta GraphQL**:
```graphql
query GetLastMeasurement($uvaID: ID!) {
  measurementsByUvaIDAndTs(
    uvaID: $uvaID
    sortDirection: DESC
    limit: 1
  ) {
    items {
      ts
    }
  }
}
```

**Consulta Fallback** (si no hay mediciones):
```graphql
query GetUVA($id: ID!) {
  getUVA(id: $id) {
    createdAt
  }
}
```

**Verificación de 24 Horas**:
```python
def is_within_last_24_hours(ts_ms):
    current_ms = time.time() * 1000
    diff_ms = current_ms - ts_ms
    return diff_ms <= 86400000  # 24 horas
```

### Salidas Generadas

**Respuesta de Dispositivo Único**:
```json
{
  "statusCode": 200,
  "body": {
    "uva123": {
      "connection": true,
      "ts": 1705318200000
    }
  }
}
```

**Respuesta de Múltiples Dispositivos**:
```json
{
  "statusCode": 200,
  "body": {
    "uva123": {"connection": true, "ts": 1705318200000},
    "uva456": {"connection": false, "ts": 1705145000000},
    "uva789": {"connection": true, "ts": 1705318100000}
  }
}
```

**Respuesta de Error**:
```json
{
  "statusCode": 500,
  "body": {
    "error": "Failed to query measurements"
  }
}
```

### Variables de Entorno Requeridas

```bash
# Endpoint AppSync
APPSYNC_GRAPHQL_URL_USER=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql

# Autenticación API
APPSYNC_API_KEY_USER=da2-xxxxxxxxxxxxxxxxxxxxx
```

### Servicios AWS Consumidos

| Servicio | Operación | Propósito |
|---------|-----------|---------|
| API Gateway | Invoke | Recibir solicitudes HTTP |
| AWS AppSync | Consulta GraphQL | Obtener mediciones y detalles del UVA |
| CloudWatch Logs | PutLogEvents | Almacenar logs de ejecución |

### Permisos IAM Requeridos

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["execute-api:Invoke"],
      "Resource": "arn:aws:execute-api:us-east-1:*:*/*/GET/{id_uva}/connection"
    }
  ]
}
```

Nota: El acceso a AppSync está controlado vía API Key, no IAM

### Dependencias

**Paquetes Python**:
```
requests==2.31.0
```

**Librería Estándar**:
- `json`: Parseo de solicitudes/respuestas
- `time`: Cálculos de timestamps
- `os`: Variables de entorno

### Manejo de Errores

- **Parámetro de ruta faltante**: Devuelve 400 Bad Request
- **Fallo en consulta GraphQL**: Devuelve 500 Internal Server Error
- **UVA ID inválido**: Devuelve medición vacía, recurre a la fecha de creación
- **Timeout de red**: Los reintentos son manejados por la librería requests (3 intentos por defecto)

### Características de Rendimiento

- **Arranque en Frío**: ~2 segundos
- **Ejecución en Caliente**: 500-800ms por dispositivo
- **Consulta Masiva**: ~500ms + (100ms × número de dispositivos)
- **Uso de Memoria**: ~100 MB

---

## Función 4: CreateRacimo

### Descripción General
**Nombre**: CreateRacimo
**Propósito**: Endpoint REST API para crear RACIMO (clúster de dispositivos) con prevención de duplicados
**Ubicación**: `SAM-UVA-App-Integrations/lambdas/createRacimo/create_racimo.py`

### Disparador

**Tipo**: REST API de API Gateway
**Método HTTP**: POST
**Ruta**: `/CreateRacimo`
**Autorización**: AWS_IAM

**Solicitud de Ejemplo**:
```bash
POST /CreateRacimo
Content-Type: application/json
Authorization: AWS4-HMAC-SHA256 ...

{
  "name": "Hospital Floor 3",
  "linkageCode": "HF3-2024-001"
}
```

### Entradas Esperadas

**Cuerpo de la Solicitud** (JSON):
```json
{
  "name": "string",       // Requerido: Nombre visible del RACIMO
  "linkageCode": "string" // Requerido: Identificador único para la vinculación
}
```

**Estructura del Evento**:
```json
{
  "body": "{\"name\":\"Hospital Floor 3\",\"linkageCode\":\"HF3-2024-001\"}"
}
```

### Lógica de Procesamiento

**Función**: `lambda_handler(event, context)`

**Flujo de Trabajo**:
1. Parsear y validar el cuerpo de la solicitud
2. Verificar si existe un RACIMO con el linkageCode
3. Si existe: devolver los datos existentes
4. Si no existe: crear el nuevo RACIMO
5. Devolver el resultado

**Validación**:
```python
body = json.loads(event.get('body', '{}'))
name = body.get('name')
linkage_code = body.get('linkageCode')

if not name or not linkage_code:
    return {
        'statusCode': 400,
        'body': {'error': 'Missing required fields'}
    }
```

**Verificación de Existencia**: `check_racimo_exists(linkage_code)`
```python
def check_racimo_exists(linkage_code):
    """
    Consultar AppSync por RACIMO con linkageCode coincidente

    Consulta GraphQL:
    listRACIMOS(filter: {LinkageCode: {eq: $code}})

    Devuelve: Objeto RACIMO si existe, None de lo contrario
    """
```

**Consulta GraphQL**:
```graphql
query CheckRACIMO($linkageCode: String!) {
  listRACIMOS(filter: {LinkageCode: {eq: $linkageCode}}) {
    items {
      id
      name
      LinkageCode
      path
    }
  }
}
```

**Crear RACIMO**: `create_racimo(name, linkage_code)`
```python
def create_racimo(name, linkage_code):
    """
    Crear nuevo RACIMO vía AppSync

    Mutación GraphQL:
    createRACIMO(input: {
      name: $name
      LinkageCode: $linkageCode
      path: "racimos/{linkageCode}/config.json"
    })

    Devuelve: Nuevo RACIMO ID
    """
```

**Mutación GraphQL**:
```graphql
mutation CreateRACIMO($input: CreateRACIMOInput!) {
  createRACIMO(input: $input) {
    id
    name
    LinkageCode
    path
  }
}
```

**Objeto de Entrada**:
```json
{
  "name": "Hospital Floor 3",
  "LinkageCode": "HF3-2024-001",
  "path": "racimos/HF3-2024-001/config.json"
}
```

**Firma AWS SigV4**:
```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def sign_request(method, url, body, headers):
    """
    Firmar solicitud con las credenciales AWS del rol de ejecución de Lambda

    Utiliza SigV4Auth con servicio 'appsync' y región 'us-east-1'
    """
    credentials = boto3.Session().get_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
    return dict(request.headers)
```

### Salidas Generadas

**RACIMO Creado**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO created successfully",
    "racimo_id": "abc123-def456-789ghi",
    "exists": false
  }
}
```

**RACIMO Ya Existe**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO already exists",
    "racimo_id": "existing123-456def",
    "exists": true,
    "data": {
      "name": "Hospital Floor 3",
      "LinkageCode": "HF3-2024-001",
      "path": "racimos/HF3-2024-001/config.json"
    }
  }
}
```

**Error de Validación**:
```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required fields: name and linkageCode"
  }
}
```

**Error del Servidor**:
```json
{
  "statusCode": 500,
  "body": {
    "error": "Failed to create RACIMO",
    "details": "GraphQL error message"
  }
}
```

### Variables de Entorno Requeridas

```bash
# Endpoint AppSync
APPSYNC_GRAPHQL_URL_USER=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
```

Nota: No se requiere API Key - se usa firma SigV4 en su lugar

### Servicios AWS Consumidos

| Servicio | Operación | Propósito |
|---------|-----------|---------|
| API Gateway | Invoke | Recibir solicitudes HTTP POST |
| AWS AppSync | Consulta GraphQL | Verificar existencia del RACIMO |
| AWS AppSync | Mutación GraphQL | Crear nuevo RACIMO |
| AWS STS | GetCallerIdentity | Obtener credenciales para la firma (implícito) |
| CloudWatch Logs | PutLogEvents | Almacenar logs de ejecución |

### Permisos IAM Requeridos

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["execute-api:Invoke"],
      "Resource": "arn:aws:execute-api:us-east-1:*/*/POST/CreateRacimo"
    },
    {
      "Effect": "Allow",
      "Action": ["appsync:GraphQL"],
      "Resource": [
        "arn:aws:appsync:us-east-1:*:apis/*/types/Query/fields/listRACIMOS",
        "arn:aws:appsync:us-east-1:*:apis/*/types/Mutation/fields/createRACIMO"
      ]
    }
  ]
}
```

### Dependencias

**Paquetes Python**:
```
boto3==1.34.29
botocore==1.34.29
requests==2.31.0
```

**Librería Estándar**:
- `json`: Parseo de solicitudes/respuestas
- `os`: Variables de entorno

### Manejo de Errores

- **Campos faltantes**: Devuelve 400 con error de validación
- **Error en consulta GraphQL**: Devuelve 500 con detalles del error
- **Error en mutación GraphQL**: Devuelve 500 con detalles del error
- **Cuerpo JSON inválido**: Devuelve 400 con error de parseo
- **Fallo de autenticación**: API Gateway devuelve 403 antes de la invocación de Lambda

### Características de Rendimiento

- **Arranque en Frío**: ~2-3 segundos
- **Ejecución en Caliente (existe)**: ~800ms (solo consulta)
- **Ejecución en Caliente (crear)**: 1.5-2s (consulta + mutación)
- **Uso de Memoria**: ~120 MB

---

## Configuración Común

### Configuración Global de Lambda (Plantilla SAM)

```yaml
Globals:
  Function:
    Runtime: python3.9
    MemorySize: 520
    Timeout: 600
    Architectures:
      - x86_64
```

### Configuración de Logs

Todas las funciones registran en CloudWatch Logs con el formato:
```
/aws/lambda/{FunctionName}
```

**Retención de Logs**: Configurada en CloudFormation (por defecto: 7 días)

### Recursos Específicos por Entorno

Las funciones Lambda reciben automáticamente los parámetros específicos del entorno durante el despliegue según la rama git:
- Rama `develop` → entorno develop
- Rama `test` → entorno test
- Rama `main` → entorno de producción

La configuración se carga desde `parameters.json` durante el despliegue.

---

## Monitoreo y Alertas

### Métricas Clave a Monitorear

| Métrica | Umbral | Acción de Alerta |
|---------|--------|------------------|
| Errores de Lambda | > 5% | Notificar al ingeniero de guardia |
| Duración de Lambda | > 30s | Investigar rendimiento |
| Antigüedad del Iterador del Stream | > 10min | Verificar throttling de Lambda |
| Ejecuciones Concurrentes | > 900 | Revisar límites de cuenta |
| Fallos de Publicación SNS | > 0 | Verificar permisos del topic |

### Comandos de Diagnóstico

```bash
# Ver logs recientes
aws logs tail /aws/lambda/DynamoDBEventProcessorFunction --follow

# Verificar métricas de Lambda
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=UvaToCloudFunction \
  --start-time 2024-01-15T00:00:00Z \
  --end-time 2024-01-15T23:59:59Z \
  --period 3600 \
  --statistics Sum

# Invocar función localmente
sam local invoke DynamoDBEventProcessorFunction -e events/test-event.json
```
