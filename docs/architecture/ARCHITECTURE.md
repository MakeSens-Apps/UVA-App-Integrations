# Arquitectura — UVA-App-Integrations

> **Tipo:** Servicio ETL/IoT Serverless (AWS SAM + DynamoDB Streams + SNS + Lambda)
> **Rol en el ecosistema:** Capa de integración entre el ecosistema de dispositivos UVA y los servicios cloud de MakeSens

---

## Descripción General

UVA-App-Integrations implementa una **arquitectura serverless orientada a eventos** en AWS, utilizando DynamoDB Streams como fuente principal de eventos para disparar flujos de procesamiento y sincronización de datos. El sistema integra datos de dispositivos IoT con servicios cloud a través de funciones Lambda, APIs GraphQL de AppSync y mensajería SNS.

| Parámetro | Valor |
|-----------|-------|
| Runtime | Python 3.9 |
| Framework de despliegue | AWS SAM (Serverless Application Model) |
| Región AWS | us-east-1 |
| Account ID | 913045965320 |
| Stack Name | SAM-UVA-App-Integrations-{env} |

---

## Diagrama de Arquitectura

```mermaid
flowchart TD
    subgraph Dispositivos
        UVA[Dispositivos UVA\nSensores IoT]
    end

    subgraph DynamoDB
        MEAS[Tabla Measurement\nStream habilitado]
        UVAT[Tabla UVA\nStream habilitado]
        RACIMO[Tabla RACIMO]
        ORG[Tabla Organization]
        LOC[Tabla Location]
    end

    subgraph Lambda
        PROC[DynamoDBEventProcessorFunction\nDynamoDB → SNS]
        CLOUD[UvaToCloudFunction\nSincronización Cloud]
        CONN[UVALastConnection\nMonitoreo de conexión]
        CRAC[CreateRacimo\nGestión de clústeres]
    end

    subgraph Salidas
        SNS[SNS Topic\nRealTimeDeviceData-env]
        APPSYNC_CLOUD[AppSync MakeSensCloud\nGraphQL API]
        APPSYNC_UVA[AppSync UVA Service\nGraphQL API]
    end

    subgraph API
        APIGW[API Gateway\nUvaAppIntegrationsAPI-env]
    end

    UVA -->|Escribe mediciones| MEAS
    UVA -->|Registro/actualización| UVAT
    MEAS -->|DynamoDB Stream INSERT| PROC
    UVAT -->|DynamoDB Stream INSERT/MODIFY| CLOUD
    PROC -->|Publish typeDevice=UVA, typeData=RAW| SNS
    CLOUD -->|GetItem| RACIMO
    CLOUD -->|Scan linkage_code| ORG
    CLOUD -->|GetItem/PutItem| LOC
    CLOUD -->|createDevice, createLocation, updateLocation| APPSYNC_CLOUD
    APIGW -->|GET /{id_uva}/connection| CONN
    APIGW -->|POST /CreateRacimo| CRAC
    CONN -->|measurementsByUvaIDAndTs, getUVA| APPSYNC_UVA
    CRAC -->|listRACIMOS, createRACIMO SigV4| APPSYNC_UVA
```

---

## Patrón Arquitectónico

El servicio implementa el patrón **Event-Driven ETL serverless**: los streams de DynamoDB actúan como bus de eventos interno; cada evento de cambio en los datos dispara Lambdas independientes que procesan, transforman y sincronizan datos hacia diferentes destinos (SNS para distribución, AppSync para gestión cloud).

---

## Recursos AWS Desplegados

| Recurso | Tipo AWS | Descripción |
|---------|----------|-------------|
| DynamoDBEventProcessorFunction | AWS::Serverless::Function | Procesa streams de Measurement y publica en SNS |
| UvaToCloudFunction | AWS::Serverless::Function | Sincroniza dispositivos UVA con MakeSensCloud |
| UVALastConnection | AWS::Serverless::Function | Endpoint REST para estado de conexión |
| CreateRacimo | AWS::Serverless::Function | Endpoint REST para gestión de clústeres RACIMO |
| UvaAppIntegrationsAPI-{env} | AWS::Serverless::Api | API Gateway REST con autorización AWS_IAM |

**Nota:** Las tablas DynamoDB, los topics SNS y las APIs AppSync son dependencias externas no administradas por este stack.

---

## Mecanismos de Sincronización

| Mecanismo | Origen | Destino | Propósito |
|-----------|--------|---------|-----------|
| DynamoDB Stream (INSERT) | Tabla Measurement | DynamoDBEventProcessorFunction | Procesamiento de mediciones en tiempo real |
| DynamoDB Stream (INSERT/MODIFY) | Tabla UVA | UvaToCloudFunction | Sincronización de dispositivos a la nube |
| SNS Publish | DynamoDBEventProcessorFunction | Topic RealTimeDeviceData-{env} | Fan-out a consumidores downstream |
| HTTP GraphQL (API Key) | UvaToCloudFunction | AppSync MakeSensCloud | Creación/actualización de dispositivos y ubicaciones |
| HTTP GraphQL (API Key) | UVALastConnection | AppSync UVA Service | Consulta de última medición |
| HTTP GraphQL (SigV4) | CreateRacimo | AppSync UVA Service | Creación de clústeres RACIMO |

---

## Separación de Entornos

El sistema soporta tres entornos aislados:

| Entorno | Rama Git | Propósito |
|---------|----------|-----------|
| develop | develop | Desarrollo activo |
| test | test | Pruebas de pre-producción |
| main | main | Producción |

**Estrategia de Aislamiento:**
- Tablas DynamoDB separadas por entorno (`{Tabla}-{AppId}-{env}`)
- Endpoints AppSync separados por entorno
- Topics SNS separados (`RealTimeDeviceData-{env}`)
- API keys específicas por entorno
- Configuraciones de parámetros distintas en `parameters.json`

---

## Arquitectura de Seguridad

### Autenticación y Autorización

**Roles de Ejecución de Lambda:**
- Permisos de lectura del DynamoDB Stream (ARNs de stream específicos)
- Permisos de publicación en SNS (ARNs de topic específicos)
- Acceso a tablas DynamoDB (GetItem, Scan en tablas específicas)

**API Gateway:**
- Autorización: `AWS_IAM`
- Requiere solicitudes firmadas con credenciales AWS (SigV4)

**APIs AppSync:**
- API Key: para la mayoría de operaciones
- AWS SigV4: usado por CreateRacimo para autenticación de producción

### Seguridad de Red

- **VPC:** No utilizada (ejecución pública de Lambda)
- **Cifrado en reposo:** DynamoDB SSE habilitado por defecto
- **Datos en tránsito:** HTTPS/TLS para todas las llamadas API

---

## Consideraciones de Escalabilidad

| Servicio | Comportamiento |
|---------|----------------|
| Lambda | Escala automáticamente; concurrencia máx. default 1000 |
| DynamoDB Streams | Escala con el throughput de la tabla; concurrencia Lambda = número de shards |
| SNS | Soporta millones de mensajes por segundo |
| API Gateway | 10,000 req/seg (límite default cuenta AWS) |

---

## Monitoreo y Observabilidad

**Logs de CloudWatch:**
- Grupos: `/aws/lambda/{FunctionName}`
- Retención: 7 días (configurada en CloudFormation)

**Métricas Clave:**
- Invocaciones, errores y duración de Lambda
- `GetRecords.IteratorAgeMilliseconds` del DynamoDB Stream (alertar si > 600,000 ms)
- Métricas de entrega SNS
- `5XXError` en API Gateway

**Trazabilidad:** No implementada actualmente (considerar AWS X-Ray para trazabilidad distribuida).

---

## Pipeline CI/CD

```
GitHub Push → GitHub Actions → AWS SAM Deploy → Actualización del Stack CloudFormation
    │
    ├─ rama test   → Despliegue en entorno test
    └─ rama main   → Despliegue en producción
```

Workflows:
- `.github/workflows/DeployTest.yml` — Despliega en entorno test
- `.github/workflows/DeployMain.yml` — Despliega en producción

**Disparador:** Pull request mergeada en rama `test` o `main`.
**Rollback:** Automático de CloudFormation en caso de fallo en el despliegue.
