# Endpoints y Eventos — UVA-App-Integrations

Este documento describe los puntos de entrada al servicio: los endpoints REST expuestos via API Gateway y los eventos de entrada desde DynamoDB Streams.

---

## API REST (API Gateway)

### Base URL

```
https://{api-id}.execute-api.us-east-1.amazonaws.com/prod
```

El `api-id` es el ID del API Gateway desplegado. Se obtiene del output `ApiEndpoint` del stack CloudFormation:

```bash
aws cloudformation describe-stacks \
  --stack-name SAM-UVA-App-Integrations-{env} \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text
```

### Autenticación

Todos los endpoints requieren autenticación **AWS IAM**. Las peticiones deben firmarse con AWS Signature Version 4.

```
Authorization: AWS4-HMAC-SHA256 Credential=...
```

---

### GET `/{id_uva}/connection`

Verifica si un dispositivo UVA está activamente conectado (última medición en las últimas 24 horas).

**Lambda:** `UVALastConnection`

**Parámetros de ruta:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id_uva` | string | ID del dispositivo UVA, o el literal `all` para consulta masiva |

**Parámetros de query** (solo cuando `id_uva = "all"`):

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `ids` | string | Sí | IDs de UVA separados por coma |

**Ejemplos de solicitud:**

```bash
# Dispositivo único
GET /uva123/connection
Authorization: AWS4-HMAC-SHA256 ...

# Múltiples dispositivos
GET /all/connection?ids=uva123,uva456,uva789
Authorization: AWS4-HMAC-SHA256 ...
```

**Response 200 — Dispositivo único:**

```json
{
  "uva123": {
    "connection": true,
    "ts": 1705318200000
  }
}
```

**Response 200 — Múltiples dispositivos:**

```json
{
  "uva123": {"connection": true, "ts": 1705318200000},
  "uva456": {"connection": false, "ts": 1705145000000},
  "uva789": {"connection": true, "ts": 1705318100000}
}
```

**Response 500:**

```json
{
  "error": "Failed to query measurements"
}
```

**Lógica de conexión:**
- `connection: true` → última medición hace menos de 24 horas
- `connection: false` → última medición hace más de 24 horas, o fallback a fecha de creación

---

### POST `/CreateRacimo`

Crea un nuevo clúster de dispositivos (RACIMO) con prevención de duplicados.

**Lambda:** `CreateRacimo`

**Headers:**

```
Content-Type: application/json
Authorization: AWS4-HMAC-SHA256 ...
```

**Request Body:**

```json
{
  "name": "Hospital Floor 3",
  "linkageCode": "HF3-2024-001"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `name` | string | Sí | Nombre visible del clúster |
| `linkageCode` | string | Sí | Código único para vinculación con Organization |

**Response 200 — RACIMO creado:**

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

**Response 200 — RACIMO ya existe:**

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

**Response 400 — Campos faltantes:**

```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required fields: name and linkageCode"
  }
}
```

**Response 500:**

```json
{
  "statusCode": 500,
  "body": {
    "error": "Failed to create RACIMO",
    "details": "GraphQL error message"
  }
}
```

---

## Eventos de Entrada (DynamoDB Streams)

Además de la API REST, el servicio consume eventos de DynamoDB Streams.

### Stream: Tabla Measurement → DynamoDBEventProcessorFunction

**ARN patrón:**
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
```

**Configuración:**
```yaml
BatchSize: 10
MaximumBatchingWindowInSeconds: 10
StartingPosition: LATEST
```

**Tipos de evento procesados:** Solo `INSERT` (MODIFY y REMOVE son ignorados)

**Ejemplo de evento:**

```json
{
  "Records": [
    {
      "eventName": "INSERT",
      "eventSource": "aws:dynamodb",
      "awsRegion": "us-east-1",
      "dynamodb": {
        "NewImage": {
          "id": {"S": "uva123"},
          "type": {"S": "temperature"},
          "ts": {"S": "2024-01-15T10:30:00Z"},
          "data": {"M": {"value": {"N": "36.5"}, "unit": {"S": "celsius"}}},
          "logs": {"L": []}
        }
      }
    }
  ]
}
```

---

### Stream: Tabla UVA → UvaToCloudFunction

**ARN patrón:**
```
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
```

**Configuración:**
```yaml
BatchSize: 10
MaximumBatchingWindowInSeconds: 10
StartingPosition: LATEST
```

**Tipos de evento procesados:** `INSERT` y `MODIFY`

**Ejemplo INSERT (nuevo dispositivo):**

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

**Ejemplo MODIFY (actualización de ubicación):**

```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "OldImage": {"id": {"S": "uva123"}, "latitude": {"N": "37.7000"}},
    "NewImage": {"id": {"S": "uva123"}, "latitude": {"N": "37.7749"}, "longitude": {"N": "-122.4194"}}
  }
}
```

---

## Operaciones GraphQL Externas

El servicio llama a las siguientes APIs AppSync. No las expone directamente, pero son parte del contrato de integración.

### AppSync MakeSensCloud (usado por UvaToCloudFunction)

| Operación | Tipo | Propósito |
|-----------|------|-----------|
| `createDevice` | Mutación | Registrar dispositivo UVA en la nube |
| `createLocation` | Mutación | Crear coordenadas GPS del dispositivo |
| `updateLocation` | Mutación | Actualizar coordenadas GPS existentes |

### AppSync UVA Service (usado por UVALastConnection y CreateRacimo)

| Operación | Tipo | Propósito | Auth |
|-----------|------|-----------|------|
| `measurementsByUvaIDAndTs` | Consulta | Obtener última medición | API Key |
| `getUVA` | Consulta | Obtener fecha de creación del dispositivo | API Key |
| `listRACIMOS` | Consulta | Verificar existencia de RACIMO | SigV4 |
| `createRACIMO` | Mutación | Crear nuevo clúster | SigV4 |
