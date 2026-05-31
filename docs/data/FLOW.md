# Flujo de Datos — UVA-App-Integrations

---

## Flujo de Datos Extremo a Extremo

El servicio gestiona cuatro flujos de datos diferenciados, cada uno disparado por una fuente de evento distinta.

---

## Flujo 1: Procesamiento de Mediciones en Tiempo Real

```mermaid
sequenceDiagram
    participant UVA as Dispositivo UVA
    participant DDB_M as DynamoDB<br/>Tabla Measurement
    participant STREAM_M as DynamoDB Stream<br/>Measurement
    participant PROC as Lambda<br/>DynamoDBEventProcessorFunction
    participant SNS as SNS Topic<br/>RealTimeDeviceData-{env}
    participant CONS as Consumidores<br/>Downstream

    UVA->>DDB_M: INSERT medición<br/>{id, ts, type, data, logs}
    DDB_M->>STREAM_M: Evento INSERT capturado
    STREAM_M->>PROC: Batch de hasta 10 registros<br/>(max. 10 segundos de espera)
    Note over PROC: 1. Filtrar solo INSERT<br/>2. remove_data_types() - quitar tipos DynamoDB<br/>3. Convertir ts ISO → ms Unix<br/>4. Construir mensaje JSON
    PROC->>SNS: Publish con atributos<br/>typeDevice=UVA, typeData=RAW
    SNS->>CONS: Distribución fan-out
```

**Transformación de datos:**

```
Entrada DynamoDB:                    Salida SNS:
{                                    {
  "id": {"S": "uva123"},               "id": "uva123",
  "type": {"S": "temperature"},        "type": "temperature",
  "ts": {"S": "2024-01-15T10:30:00Z"}, "ts": 1705318200000,
  "data": {"M": {                      "data": {
    "value": {"N": "36.5"}               "value": 36.5
  }}                                   }
}                                    }
```

---

## Flujo 2: Sincronización de Dispositivos a la Nube (INSERT)

```mermaid
sequenceDiagram
    participant ADMIN as Administrador
    participant DDB_U as DynamoDB<br/>Tabla UVA
    participant STREAM_U as DynamoDB Stream<br/>UVA
    participant CLOUD as Lambda<br/>UvaToCloudFunction
    participant DDB_R as DynamoDB<br/>Tabla RACIMO
    participant DDB_O as DynamoDB<br/>Tabla Organization
    participant APPSYNC as AppSync<br/>MakeSensCloud

    ADMIN->>DDB_U: INSERT nuevo UVA<br/>{id, name, racimoID}
    DDB_U->>STREAM_U: Evento INSERT capturado
    STREAM_U->>CLOUD: Registro de nuevo UVA
    CLOUD->>DDB_R: GetItem por racimoID
    DDB_R-->>CLOUD: {LinkageCode: "HF3-2024-001"}
    CLOUD->>DDB_O: Scan filtro linkage_code = "HF3-2024-001"
    DDB_O-->>CLOUD: [{id: "org789", ...}]
    CLOUD->>APPSYNC: createDevice(organizationID, name, typeDevice="UVA")
    APPSYNC-->>CLOUD: {id: "device789"}
    Note over CLOUD: Dispositivo registrado en MakeSensCloud
```

---

## Flujo 3: Sincronización de Ubicación (MODIFY)

```mermaid
sequenceDiagram
    participant UVA as Dispositivo UVA
    participant DDB_U as DynamoDB<br/>Tabla UVA
    participant STREAM_U as DynamoDB Stream<br/>UVA
    participant CLOUD as Lambda<br/>UvaToCloudFunction
    participant DDB_L as DynamoDB<br/>Tabla Location
    participant APPSYNC as AppSync<br/>MakeSensCloud

    UVA->>DDB_U: UPDATE latitud/longitud
    DDB_U->>STREAM_U: Evento MODIFY capturado
    STREAM_U->>CLOUD: Registro con OldImage y NewImage
    Note over CLOUD: Verificar que lat Y lng estén presentes
    CLOUD->>DDB_L: GetItem id = "A{uvaID}"
    alt Existe ubicación
        DDB_L-->>CLOUD: Registro existente
        CLOUD->>APPSYNC: updateLocation(id, lat, lng)
    else No existe ubicación
        DDB_L-->>CLOUD: Item no encontrado
        CLOUD->>APPSYNC: createLocation(id="A{uvaID}", lat, lng)
    end
    APPSYNC-->>CLOUD: Confirmación
```

---

## Flujo 4: Verificación de Estado de Conexión

```mermaid
sequenceDiagram
    participant CLIENT as Cliente<br/>Sistema de Monitoreo
    participant APIGW as API Gateway
    participant CONN as Lambda<br/>UVALastConnection
    participant APPSYNC as AppSync<br/>UVA Service

    CLIENT->>APIGW: GET /{id_uva}/connection<br/>Authorization: AWS4-HMAC-SHA256
    APIGW->>CONN: Evento con pathParameters.id_uva
    Note over CONN: Modo simple o masivo (id_uva = "all")
    CONN->>APPSYNC: measurementsByUvaIDAndTs(uvaID, DESC, limit=1)
    alt Hay mediciones
        APPSYNC-->>CONN: [{ts: 1705318200000}]
        Note over CONN: ts < 24h → connection=true
    else Sin mediciones (fallback)
        APPSYNC-->>CONN: items: []
        CONN->>APPSYNC: getUVA(id) → createdAt
        Note over CONN: Usar createdAt como referencia
    end
    CONN-->>APIGW: {uva_id: {connection: bool, ts: int}}
    APIGW-->>CLIENT: 200 OK JSON
```

---

## Flujo 5: Creación de Clúster RACIMO

```mermaid
sequenceDiagram
    participant CLIENT as Cliente<br/>Sistema de Provisionamiento
    participant APIGW as API Gateway
    participant CRAC as Lambda<br/>CreateRacimo
    participant APPSYNC as AppSync<br/>UVA Service (SigV4)

    CLIENT->>APIGW: POST /CreateRacimo<br/>{name, linkageCode}
    APIGW->>CRAC: Evento con body JSON
    Note over CRAC: Validar name y linkageCode
    CRAC->>APPSYNC: listRACIMOS(filter: LinkageCode eq $code)<br/>Autenticación: AWS SigV4
    alt RACIMO existe
        APPSYNC-->>CRAC: [{id, name, LinkageCode, path}]
        CRAC-->>APIGW: {message: "exists", racimo_id, exists: true}
    else RACIMO no existe
        APPSYNC-->>CRAC: items: []
        CRAC->>APPSYNC: createRACIMO(name, LinkageCode, path="racimos/{code}/config.json")
        APPSYNC-->>CRAC: {id: "nuevo-racimo-id"}
        CRAC-->>APIGW: {message: "created", racimo_id, exists: false}
    end
    APIGW-->>CLIENT: 200 OK JSON
```

---

## Flujo de Error: Stream Fallo en Lambda

```mermaid
flowchart TD
    A[Lambda falla al\nprocesar lote] --> B{Reintento automático\nDynamoDB Stream}
    B --> C[Intento 1]
    C -->|Falla| D[Intento 2]
    D -->|Falla| E[Intento 3]
    E -->|Falla| F{DLQ configurada?}
    F -->|Sí| G[Enviar a Dead Letter Queue\npara análisis]
    F -->|No| H[Registro perdido\nSolo CloudWatch Logs]
    C -->|Éxito| I[Procesamiento normal]
    D -->|Éxito| I
    E -->|Éxito| I
```

---

## Flujo de Error: API Gateway

```mermaid
flowchart TD
    A[Solicitud a API Gateway] --> B{Autenticación\nAWS IAM}
    B -->|Inválida| C[403 Forbidden\nAPIGateway level]
    B -->|Válida| D[Invocación de Lambda]
    D --> E{Lambda ejecuta}
    E -->|Error de validación| F[400 Bad Request]
    E -->|Error GraphQL/DynamoDB| G[500 Internal Server Error]
    E -->|Éxito| H[200 OK con body JSON]
```

---

## Latencias Estimadas por Flujo

| Flujo | Fase | Duración aproximada |
|-------|------|---------------------|
| **Flujo 1: Medición→SNS** | Escritura DynamoDB | < 10ms |
| | Latencia del Stream | < 1s |
| | Lambda (warm) | 200-500ms |
| | **Total warm** | **~1-2s** |
| | **Total cold start** | **~4-5s** |
| **Flujo 2: UVA→Cloud (INSERT)** | Lambda (warm) | 1-2s |
| | Llamadas GraphQL | ~500ms |
| **Flujo 4: Estado de conexión** | Lambda (warm) | 500-800ms |
| | **Consulta masiva** | **500ms + 100ms × N dispositivos** |
| **Flujo 5: Creación RACIMO** | Lambda (warm, existe) | ~800ms |
| | Lambda (warm, crea) | 1.5-2s |

---

## Throughput Máximo

| Flujo | Throughput |
|-------|------------|
| Procesamiento de Mediciones | 1000 eventos/seg (limitado por shards del stream) |
| Sincronización de Dispositivos | 100 dispositivos/seg (limitado por GraphQL rate limits) |
| Verificación de Conexión | 50 req/seg (limitado por rendimiento AppSync) |
| Creación de RACIMO | 20 req/seg (limitado por mutación + consulta GraphQL) |
