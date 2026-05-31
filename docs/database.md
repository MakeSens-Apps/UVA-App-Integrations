# Base de Datos

## Descripción General

UVA-App-Integrations utiliza **Amazon DynamoDB**, un servicio de base de datos NoSQL completamente administrado, para todo el almacenamiento de datos. El sistema interactúa con múltiples tablas para metadatos de dispositivos, mediciones, estructuras organizacionales y ubicaciones.

**Tipo de Base de Datos**: Amazon DynamoDB (NoSQL, Almacén de Clave-Valor y Documentos)
**Región**: us-east-1
**Modo de Facturación**: Bajo demanda o Provisionado (configurado por entorno)

---

## Tablas

### 1. Tabla Measurement

**Propósito**: Almacena datos de sensores en series de tiempo de los dispositivos UVA

**Convención de Nomenclatura**: `Measurement-{AppId}-{env}`
**Ejemplo**: `Measurement-abc123-develop`

#### Esquema

**Clave Primaria**:
- **Clave de Partición**: `id` (String) - Identificador del dispositivo UVA
- **Clave de Ordenación**: `ts` (Number) - Timestamp Unix en milisegundos

**Atributos**:
```json
{
  "id": "String",           // ID del dispositivo UVA (clave de partición)
  "ts": "Number",           // Timestamp Unix en milisegundos (clave de ordenación)
  "type": "String",         // Tipo de medición (temperatura, presión, etc.)
  "data": "Map",            // Payload de la medición (varía según el tipo)
  "logs": "List",           // Entradas de log opcionales
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de Ejemplo**:
```json
{
  "id": "uva123",
  "ts": 1705318200000,
  "type": "temperature",
  "data": {
    "value": 36.5,
    "unit": "celsius",
    "sensorId": "temp_01"
  },
  "logs": [],
  "createdAt": "2024-01-15T10:30:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

#### Índices

**Índices Secundarios Globales (GSI)**:

**uvaID-ts-index** (probablemente existe para consultas):
- **Clave de Partición**: `uvaID` o `id` (String)
- **Clave de Ordenación**: `ts` (Number)
- **Propósito**: Consultar mediciones por ID de dispositivo ordenadas por tiempo
- **Proyección**: ALL

**Patrones de Acceso**:
- Obtener la última medición de un dispositivo: Consulta por `uvaID`, orden DESC, límite 1
- Obtener mediciones en un rango de tiempo: Consulta por `uvaID` con ts BETWEEN
- Procesamiento de stream: DynamoDB Streams captura todos los eventos INSERT

#### Configuración de Stream

**Stream Habilitado**: Sí
**Tipo de Vista del Stream**: NEW_IMAGE (captura el nuevo estado del registro)
**Consumidores**: Lambda DynamoDBEventProcessorFunction

**Patrón ARN**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
```

---

### 2. Tabla UVA

**Propósito**: Registro de dispositivos que almacena metadatos y configuración de UVA

**Convención de Nomenclatura**: `UVA-{AppId}-{env}`
**Ejemplo**: `UVA-abc123-develop`

#### Esquema

**Clave Primaria**:
- **Clave de Partición**: `id` (String) - Identificador único del dispositivo UVA

**Atributos**:
```json
{
  "id": "String",           // ID del dispositivo UVA (clave de partición)
  "name": "String",         // Nombre visible del dispositivo
  "racimoID": "String",     // Clave foránea a la tabla RACIMO
  "latitude": "Number",     // Opcional: Latitud GPS
  "longitude": "Number",    // Opcional: Longitud GPS
  "status": "String",       // Estado del dispositivo (active, inactive, etc.)
  "metadata": "Map",        // Propiedades adicionales del dispositivo
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de Ejemplo**:
```json
{
  "id": "uva123",
  "name": "Device Floor 3 Room 301",
  "racimoID": "racimo456",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "status": "active",
  "metadata": {
    "firmwareVersion": "2.1.3",
    "installDate": "2024-01-10"
  },
  "createdAt": "2024-01-10T08:00:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

#### Índices

**No se documentan índices adicionales** (solo acceso por clave primaria)

**Patrones de Acceso**:
- Obtener UVA por ID: Operación GetItem
- Obtener fecha de creación: Utilizado por UVALastConnection como fallback

#### Configuración de Stream

**Stream Habilitado**: Sí
**Tipo de Vista del Stream**: NEW_AND_OLD_IMAGES (captura el estado antes/después)
**Consumidores**: Lambda UvaToCloudFunction

**Patrón ARN**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
```

**Tipos de Eventos Procesados**:
- **INSERT**: Dispara la creación del dispositivo en MakeSensCloud
- **MODIFY**: Dispara la actualización de ubicación si cambian lat/lng

---

### 3. Tabla RACIMO

**Propósito**: Almacena clústeres/grupos de dispositivos con códigos de vinculación para la jerarquía organizacional

**Convención de Nomenclatura**: `RACIMO-{AppId}-{env}`
**Ejemplo**: `RACIMO-abc123-develop`

#### Esquema

**Clave Primaria**:
- **Clave de Partición**: `id` (String) - Identificador único de RACIMO

**Atributos**:
```json
{
  "id": "String",           // ID de RACIMO (clave de partición)
  "name": "String",         // Nombre visible del clúster
  "LinkageCode": "String",  // Identificador de vinculación único
  "path": "String",         // Ruta del archivo de configuración
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de Ejemplo**:
```json
{
  "id": "racimo456",
  "name": "Hospital Floor 3",
  "LinkageCode": "HF3-2024-001",
  "path": "racimos/HF3-2024-001/config.json",
  "createdAt": "2024-01-05T12:00:00.000Z",
  "updatedAt": "2024-01-05T12:00:00.000Z"
}
```

#### Índices

**Índice Secundario Global** (probable para consultas por LinkageCode):
- **Clave de Partición**: `LinkageCode` (String)
- **Propósito**: Consultar RACIMO por código de vinculación para verificar duplicados
- **Utilizado por**: Lambda CreateRacimo

**Patrones de Acceso**:
- Obtener RACIMO por ID: Operación GetItem (utilizada por UvaToCloudFunction)
- Encontrar RACIMO por LinkageCode: Consulta o Scan con filtro (utilizada por CreateRacimo)

#### Relaciones

**Uno-a-Muchos con UVA**:
- Un RACIMO puede contener múltiples dispositivos UVA
- UVA.racimoID → RACIMO.id (clave foránea)

**Uno-a-Uno con Organization** (vía LinkageCode):
- RACIMO.LinkageCode = Organization.linkage_code
- Se utiliza para asociar dispositivos con organizaciones

---

### 4. Tabla Organization

**Propósito**: Almacena entidades organizacionales para la gestión multi-tenant de dispositivos

**Convención de Nomenclatura**: `Organization-{AppId}-{env}`
**Ejemplo**: `Organization-abc123-develop`

#### Esquema

**Clave Primaria**:
- **Clave de Partición**: `id` (String) - Identificador único de organización

**Atributos**:
```json
{
  "id": "String",           // ID de organización (clave de partición)
  "name": "String",         // Nombre de la organización
  "linkage_code": "String", // Vincula con RACIMO.LinkageCode
  "metadata": "Map",        // Propiedades adicionales de la organización
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de Ejemplo**:
```json
{
  "id": "org789",
  "name": "City General Hospital",
  "linkage_code": "HF3-2024-001",
  "metadata": {
    "address": "123 Medical Center Dr",
    "contactEmail": "admin@cityhospital.com"
  },
  "createdAt": "2024-01-01T00:00:00.000Z",
  "updatedAt": "2024-01-01T00:00:00.000Z"
}
```

#### Índices

**Índice Secundario Global** (recomendado para linkage_code):
- **Clave de Partición**: `linkage_code` (String)
- **Propósito**: Encontrar la organización eficientemente por código de vinculación
- **Nota**: Actualmente se accede mediante operación Scan (ineficiente para tablas grandes)

**Patrones de Acceso**:
- Encontrar organización por linkage_code: **Scan** con FilterExpression (implementación actual)
- Recomendado: Consulta GSI en linkage_code para mejor rendimiento

**Consideración de Rendimiento**:
```python
# Implementación actual (escaneo completo de tabla)
response = dynamodb.scan(
    TableName='Organization-abc123-develop',
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)

# Optimización recomendada: Usar consulta GSI en su lugar
response = dynamodb.query(
    TableName='Organization-abc123-develop',
    IndexName='linkage_code-index',
    KeyConditionExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

---

### 5. Tabla Location

**Propósito**: Almacena coordenadas geográficas de los dispositivos UVA

**Convención de Nomenclatura**: `Location-{AppId}-{env}`
**Ejemplo**: `Location-abc123-develop`

#### Esquema

**Clave Primaria**:
- **Clave de Partición**: `id` (String) - Identificador de ubicación (formato: `A{uvaID}`)

**Atributos**:
```json
{
  "id": "String",           // ID de ubicación = "A" + uvaID (clave de partición)
  "latitude": "Number",     // Latitud GPS
  "longitude": "Number",    // Longitud GPS
  "altitude": "Number",     // Opcional: Altitud en metros
  "accuracy": "Number",     // Opcional: Precisión GPS en metros
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de Ejemplo**:
```json
{
  "id": "Auva123",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "altitude": 15.5,
  "accuracy": 10.0,
  "createdAt": "2024-01-15T10:30:00.000Z",
  "updatedAt": "2024-01-15T14:20:00.000Z"
}
```

#### Convención de ID

**Formato**: `A{uvaID}`
**Ejemplos**:
- UVA ID: `uva123` → Location ID: `Auva123`
- UVA ID: `device456` → Location ID: `Adevice456`

**Propósito**: Crea una relación uno-a-uno con la tabla UVA

#### Patrones de Acceso

- Verificar si existe la ubicación: GetItem por `id`
- Obtener la ubicación del dispositivo: GetItem por `A{uvaID}`
- Actualizar ubicación: PutItem o UpdateItem

#### Relaciones

**Uno-a-Uno con UVA**:
- Location.id = `A{UVA.id}`
- Administrada por UvaToCloudFunction en eventos MODIFY de UVA

---

## Relaciones Entre Tablas

```
Organization
    │
    │ (coincidencia de linkage_code)
    ▼
  RACIMO ──────┐
    │          │
    │ (id)     │
    ▼          │
   UVA         │
    │          │
    │          │ (racimoID FK)
    │          │
    ▼          ▼
Location    Measurement
(A{uvaID})  (uvaID, ts)
```

**Detalles de las Relaciones**:
1. **Organization ↔ RACIMO**: Vinculadas mediante el campo `linkage_code`
2. **RACIMO ↔ UVA**: Uno-a-muchos mediante la clave foránea `racimoID`
3. **UVA ↔ Location**: Uno-a-uno mediante la convención `A{uvaID}`
4. **UVA ↔ Measurement**: Uno-a-muchos mediante la clave de partición `uvaID`

---

## Operaciones de Datos

### Operaciones de Lectura

**GetItem** (eficiente - complejidad O(1)):
```python
# Obtener dispositivo UVA específico
response = dynamodb.get_item(
    TableName='UVA-abc123-develop',
    Key={'id': 'uva123'}
)
```

**Query** (eficiente - usa índices):
```python
# Obtener las últimas mediciones de un dispositivo
response = dynamodb.query(
    TableName='Measurement-abc123-develop',
    IndexName='uvaID-ts-index',
    KeyConditionExpression='uvaID = :id',
    ExpressionAttributeValues={':id': 'uva123'},
    ScanIndexForward=False,  # Orden descendente
    Limit=1
)
```

**Scan** (ineficiente - escaneo completo de tabla):
```python
# Encontrar organización por linkage code (implementación actual)
response = dynamodb.scan(
    TableName='Organization-abc123-develop',
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

### Operaciones de Escritura

**PutItem** (crear o reemplazar):
```python
# Crear nuevo dispositivo UVA
dynamodb.put_item(
    TableName='UVA-abc123-develop',
    Item={
        'id': 'uva123',
        'name': 'Device Floor 3',
        'racimoID': 'racimo456',
        'status': 'active',
        'createdAt': '2024-01-15T10:30:00.000Z'
    }
)
```

**UpdateItem** (modificar atributos específicos):
```python
# Actualizar ubicación del dispositivo
dynamodb.update_item(
    TableName='UVA-abc123-develop',
    Key={'id': 'uva123'},
    UpdateExpression='SET latitude = :lat, longitude = :lng, updatedAt = :now',
    ExpressionAttributeValues={
        ':lat': 37.7749,
        ':lng': -122.4194,
        ':now': '2024-01-15T10:30:00.000Z'
    }
)
```

---

## DynamoDB Streams

### Configuración de Stream

**Tablas con Streams Habilitados**:
1. **Measurement**: Vista NEW_IMAGE
2. **UVA**: Vista NEW_AND_OLD_IMAGES

**Configuración del Stream**:
- **Tamaño de Lote**: 10 registros por invocación de Lambda
- **Ventana de Agrupamiento**: Espera máxima de 10 segundos
- **Posición Inicial**: LATEST (solo nuevos registros)
- **Reintentos**: 3 intentos en caso de fallo de Lambda
- **En caso de fallo**: DLQ (Dead Letter Queue) si está configurada

### Formato de Registro del Stream

**Evento INSERT**:
```json
{
  "eventID": "abc123",
  "eventName": "INSERT",
  "eventVersion": "1.1",
  "eventSource": "aws:dynamodb",
  "awsRegion": "us-east-1",
  "dynamodb": {
    "ApproximateCreationDateTime": 1705318200,
    "Keys": {
      "id": {"S": "uva123"}
    },
    "NewImage": {
      "id": {"S": "uva123"},
      "name": {"S": "Device Floor 3"},
      "racimoID": {"S": "racimo456"}
    },
    "SequenceNumber": "111222333",
    "SizeBytes": 250,
    "StreamViewType": "NEW_IMAGE"
  }
}
```

**Evento MODIFY** (para la tabla UVA):
```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "Keys": {"id": {"S": "uva123"}},
    "OldImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4000"}
    },
    "NewImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4194"}
    }
  }
}
```

---

## Consideraciones de Rendimiento

### Capacidad de Lectura

**Operaciones Query**:
- Consultas de Measurement: ~1-5 RCU por consulta (dependiendo del tamaño de datos)
- GetItem de UVA: 1 RCU por dispositivo
- GetItem de RACIMO: 1 RCU por clúster

**Operaciones Scan**:
- Scan de Organization: Escala con el tamaño de la tabla (ineficiente)
- Recomendación: Agregar GSI en `linkage_code` para consultas O(1)

### Capacidad de Escritura

**Escrituras Disparadas por Stream**:
- INSERT de Measurement: ~100-1000 WCU durante actividad pico de dispositivos
- MODIFY de UVA: ~10-50 WCU durante actualizaciones de ubicación

**Recomendación**: Usar facturación bajo demanda para cargas de trabajo impredecibles

### Latencia

**GetItem**: < 10ms (milisegundos de un solo dígito)
**Query**: 10-50ms (dependiendo del tamaño del resultado)
**Scan**: 100ms - varios segundos (depende del tamaño de la tabla)
**Latencia del Stream**: < 1 segundo (desde el evento del stream hasta la invocación de Lambda)

---

## Retención de Datos

**Tablas**: Sin TTL (Time To Live) configurado
**Datos de Measurement**: Crecen indefinidamente (considerar implementar TTL)

**Recomendación para la Tabla Measurement**:
```python
# Habilitar TTL para eliminar automáticamente mediciones antiguas
# Ejemplo: Eliminar mediciones con más de 90 días
dynamodb.update_time_to_live(
    TableName='Measurement-abc123-develop',
    TimeToLiveSpecification={
        'Enabled': True,
        'AttributeName': 'expirationTime'  # Timestamp Unix
    }
)
```

**Calcular el tiempo de expiración**:
```python
import time

# Establecer expiración a 90 días a partir de ahora
expiration_time = int(time.time()) + (90 * 24 * 60 * 60)

# Agregar al registro de medición
item['expirationTime'] = expiration_time
```

---

## Seguridad

### Cifrado

**En Reposo**: Cifrado por defecto de DynamoDB (claves administradas por AWS)
**En Tránsito**: TLS 1.2+ para todas las llamadas API

### Control de Acceso

**Políticas IAM**: Los roles de ejecución de Lambda tienen permisos detallados

**Política de Ejemplo**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/RACIMO-*"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/Organization-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetRecords",
        "dynamodb:GetShardIterator",
        "dynamodb:DescribeStream"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/*/stream/*"
    }
  ]
}
```

### Respaldo

**Recuperación a Punto en el Tiempo (PITR)**: Recomendada para producción
**Respaldos Bajo Demanda**: Respaldos manuales para lanzamientos importantes

---

## Monitoreo

### Métricas de CloudWatch

**Métricas Clave**:
- `ConsumedReadCapacityUnits`: Monitorear para detectar throttling
- `ConsumedWriteCapacityUnits`: Monitorear para detectar throttling
- `UserErrors`: Errores 400 (problemas de validación)
- `SystemErrors`: Errores 500 (problemas del servicio)
- `SuccessfulRequestLatency`: Rendimiento de las consultas

### Monitoreo del Stream

**Métricas Importantes**:
- `GetRecords.IteratorAgeMilliseconds`: Retraso en el procesamiento del stream
  - Alertar si > 600000 (10 minutos)
- `GetRecords.Success`: Tasa de éxito de lectura del stream

### Alarmas

**Alarmas de CloudWatch Recomendadas**:
```bash
# Alta antigüedad del iterador (retraso del stream)
aws cloudwatch put-metric-alarm \
  --alarm-name "UVA-Stream-Lag" \
  --metric-name GetRecords.IteratorAgeMilliseconds \
  --namespace AWS/DynamoDB \
  --statistic Maximum \
  --period 300 \
  --threshold 600000 \
  --comparison-operator GreaterThanThreshold

# Alta tasa de errores
aws cloudwatch put-metric-alarm \
  --alarm-name "DynamoDB-Errors" \
  --metric-name UserErrors \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 60 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

---

## Recomendaciones de Optimización

1. **Agregar GSI a la Tabla Organization**:
   - Índice: `linkage_code` (clave de partición)
   - Elimina las costosas operaciones Scan
   - Reduce costos y mejora la latencia

2. **Implementar TTL para la Tabla Measurement**:
   - Elimina automáticamente mediciones antiguas
   - Reduce costos de almacenamiento
   - Mantiene el rendimiento a escala

3. **Usar Query en lugar de Scan**:
   - Reemplazar el Scan de Organization con Query en GSI
   - Mejora de rendimiento de 10-100x
   - Menor costo por operación

4. **Considerar el Filtrado de DynamoDB Streams**:
   - Filtrar eventos MODIFY para solo cambios de ubicación
   - Reduce invocaciones innecesarias de Lambda
   - Menor costo de cómputo

5. **Operaciones en Lote**:
   - Usar BatchGetItem para lecturas en volumen
   - Usar BatchWriteItem para escrituras en volumen
   - Reducir la sobrecarga de llamadas API
