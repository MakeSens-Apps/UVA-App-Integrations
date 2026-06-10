# Modelos de Datos — UVA-App-Integrations

UVA-App-Integrations utiliza **Amazon DynamoDB** (NoSQL) para todo el almacenamiento de datos. El servicio interactúa con cinco tablas, de las cuales dos tienen DynamoDB Streams habilitados.

**Tipo de Base de Datos:** Amazon DynamoDB (NoSQL, Clave-Valor y Documentos)
**Región:** us-east-1
**Modo de Facturación:** Bajo demanda o Provisionado (configurado por entorno)

**Nota:** Las tablas DynamoDB son **dependencias externas** no administradas por el stack SAM de este repositorio.

---

## Convención de Nomenclatura

Todas las tablas siguen el patrón:
```
{NombreTabla}-{AppId}-{env}
```

Ejemplos:
- `Measurement-abc123-develop`
- `UVA-abc123-test`
- `RACIMO-abc123-main`

---

## Tabla 1: Measurement

**Propósito:** Almacena datos de sensores en series de tiempo de los dispositivos UVA.

**Clave Primaria:**
- Clave de Partición: `id` (String) — Identificador del dispositivo UVA
- Clave de Ordenación: `ts` (Number) — Timestamp Unix en milisegundos

**Atributos:**

```json
{
  "id": "String",           // ID del dispositivo UVA (clave de partición)
  "ts": "Number",           // Timestamp Unix en milisegundos (clave de ordenación)
  "type": "String",         // Tipo de medición (temperature, pressure, etc.)
  "data": "Map",            // Payload de la medición (varía según el tipo)
  "logs": "List",           // Entradas de log opcionales
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de ejemplo:**

```json
{
  "id": "uva123",
  "ts": 1705318200000,
  "type": "temperature",
  "data": {"value": 36.5, "unit": "celsius", "sensorId": "temp_01"},
  "logs": [],
  "createdAt": "2024-01-15T10:30:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

**Configuración de Stream:**
- **Habilitado:** Sí
- **Tipo de Vista:** `NEW_IMAGE`
- **Consumidor:** `DynamoDBEventProcessorFunction`

**ARN patrón:**
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
```

**Patrones de acceso:**
- Última medición de un dispositivo: Query por `uvaID`, DESC, límite 1
- Mediciones en rango de tiempo: Query por `uvaID` con `ts BETWEEN`
- Procesamiento de stream: `DynamoDB Streams` captura todos los eventos INSERT

---

## Tabla 2: UVA

**Propósito:** Registro de dispositivos con metadatos y configuración de cada dispositivo UVA.

**Clave Primaria:**
- Clave de Partición: `id` (String) — Identificador único del dispositivo UVA

**Atributos:**

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

**Registro de ejemplo:**

```json
{
  "id": "uva123",
  "name": "Device Floor 3 Room 301",
  "racimoID": "racimo456",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "status": "active",
  "metadata": {"firmwareVersion": "2.1.3", "installDate": "2024-01-10"},
  "createdAt": "2024-01-10T08:00:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

**Configuración de Stream:**
- **Habilitado:** Sí
- **Tipo de Vista:** `NEW_AND_OLD_IMAGES`
- **Consumidor:** `UvaToCloudFunction`

**ARN patrón:**
```
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
```

**Tipos de eventos procesados:**
- `INSERT` → Dispara creación del dispositivo en MakeSensCloud
- `MODIFY` → Dispara actualización de ubicación si cambian `latitude`/`longitude`

---

## Tabla 3: RACIMO

**Propósito:** Almacena clústeres/grupos de dispositivos con códigos de vinculación para la jerarquía organizacional.

**Clave Primaria:**
- Clave de Partición: `id` (String) — Identificador único de RACIMO

**Atributos:**

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

**Registro de ejemplo:**

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

**Relaciones:**
- **Uno-a-muchos con UVA:** Un RACIMO puede contener múltiples dispositivos UVA. `UVA.racimoID → RACIMO.id`
- **Uno-a-uno con Organization** (vía LinkageCode): `RACIMO.LinkageCode = Organization.linkage_code`

**Patrones de acceso:**
- `GetItem` por ID (usado por `UvaToCloudFunction`)
- `Scan/Query` con filtro por `LinkageCode` (usado por `CreateRacimo` vía AppSync)

---

## Tabla 4: Organization

**Propósito:** Almacena entidades organizacionales para la gestión multi-tenant de dispositivos.

**Clave Primaria:**
- Clave de Partición: `id` (String) — Identificador único de organización

**Atributos:**

```json
{
  "id": "String",           // ID de organización (clave de partición)
  "name": "String",         // Nombre de la organización
  "linkage_code": "String", // Vincula con RACIMO.LinkageCode
  "metadata": "Map",        // Propiedades adicionales
  "createdAt": "String",    // Timestamp de creación ISO 8601
  "updatedAt": "String"     // Timestamp de actualización ISO 8601
}
```

**Registro de ejemplo:**

```json
{
  "id": "org789",
  "name": "City General Hospital",
  "linkage_code": "HF3-2024-001",
  "metadata": {"address": "123 Medical Center Dr"},
  "createdAt": "2024-01-01T00:00:00.000Z",
  "updatedAt": "2024-01-01T00:00:00.000Z"
}
```

**Patrón de acceso actual (ineficiente):**

```python
# Implementación actual — escaneo completo de tabla
response = dynamodb.scan(
    TableName='Organization-abc123-develop',
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

**Optimización recomendada:** Crear GSI en `linkage_code` para consultas O(1):

```python
response = dynamodb.query(
    TableName='Organization-abc123-develop',
    IndexName='linkage_code-index',
    KeyConditionExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

---

## Tabla 5: Location

**Propósito:** Almacena coordenadas geográficas de los dispositivos UVA.

**Clave Primaria:**
- Clave de Partición: `id` (String) — ID de ubicación con formato `A{uvaID}`

**Atributos:**

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

**Registro de ejemplo:**

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

**Convención de ID:**

| UVA ID | Location ID |
|--------|-------------|
| `uva123` | `Auva123` |
| `device456` | `Adevice456` |

**Patrones de acceso:**
- Verificar si existe: `GetItem` por `id`
- Obtener ubicación del dispositivo: `GetItem` por `A{uvaID}`
- Actualizar: `PutItem` o `UpdateItem`

---

## Relaciones Entre Tablas

```
Organization
    │
    │ (coincidencia de linkage_code)
    ▼
  RACIMO ──────┐
    │           │
    │ (id)      │ (racimoID FK)
    ▼           │
   UVA ─────────┘
    │
    ├──────────────► Location (A{uvaID})
    │
    └──────────────► Measurement (uvaID, ts)
```

**Detalle de las relaciones:**
1. `Organization ↔ RACIMO` — Vinculadas mediante `linkage_code`
2. `RACIMO ↔ UVA` — Uno-a-muchos mediante `racimoID` (clave foránea)
3. `UVA ↔ Location` — Uno-a-uno mediante la convención `A{uvaID}`
4. `UVA ↔ Measurement` — Uno-a-muchos mediante la clave de partición `uvaID/id`

---

## Formatos de Eventos del Stream

**Evento INSERT (formato interno DynamoDB):**

```json
{
  "eventID": "abc123",
  "eventName": "INSERT",
  "eventSource": "aws:dynamodb",
  "awsRegion": "us-east-1",
  "dynamodb": {
    "ApproximateCreationDateTime": 1705318200,
    "Keys": {"id": {"S": "uva123"}},
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

**Evento MODIFY (tabla UVA):**

```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "Keys": {"id": {"S": "uva123"}},
    "OldImage": {"id": {"S": "uva123"}, "latitude": {"N": "37.7749"}, "longitude": {"N": "-122.4000"}},
    "NewImage": {"id": {"S": "uva123"}, "latitude": {"N": "37.7749"}, "longitude": {"N": "-122.4194"}}
  }
}
```

---

## Consideraciones de Rendimiento y Optimización

| Operación | Complejidad | Recomendación |
|-----------|-------------|---------------|
| GetItem en UVA, RACIMO, Location | O(1) | Correcto |
| Query en Measurement por uvaID+ts | O(log n) | Correcto |
| Scan en Organization por linkage_code | O(n) | Agregar GSI en `linkage_code` |

**Recomendaciones pendientes:**
1. Agregar GSI a Organization por `linkage_code` (elimina el Scan costoso)
2. Implementar TTL en tabla Measurement (eliminar mediciones antiguas automáticamente)
3. Considerar filtrado de DynamoDB Streams en UVA para reducir invocaciones de Lambda en MODIFY sin cambios de ubicación

---

## Seguridad

**Cifrado en reposo:** SSE por defecto de DynamoDB (claves administradas por AWS)
**En tránsito:** TLS 1.2+ para todas las llamadas API

**Permisos Lambda por tabla:**

| Lambda | Tabla | Operaciones |
|--------|-------|-------------|
| DynamoDBEventProcessorFunction | Measurement (stream) | GetRecords, GetShardIterator, DescribeStream |
| UvaToCloudFunction | UVA (stream) | GetRecords, GetShardIterator, DescribeStream |
| UvaToCloudFunction | RACIMO, Location | GetItem |
| UvaToCloudFunction | Organization | Scan |
