# Configuración y Variables de Entorno — UVA-App-Integrations

---

## Variables de Entorno por Lambda

### DynamoDBEventProcessorFunction

| Variable | Descripción | Ejemplo | Secreto |
|----------|-------------|---------|---------|
| `TOPIC_SNS_ARN` | ARN del topic SNS para datos en tiempo real | `arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-develop` | No |

**Configurado vía:** Parámetro `TopicSNSDataArn` en la plantilla SAM.

---

### UvaToCloudFunction

| Variable | Descripción | Ejemplo | Secreto |
|----------|-------------|---------|---------|
| `APPSYNC_GRAPHQL_URL` | Endpoint GraphQL de AppSync MakeSensCloud | `https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql` | No |
| `APPSYNC_API_KEY` | API Key de MakeSensCloud | `da2-xxxxxxxxxxxxxxxxxxxx` | **Sí** |
| `RACIMO_TABLE_NAME` | Nombre de la tabla RACIMO | `RACIMO-abc123-develop` | No |
| `ORGANIZATION_TABLE_NAME` | Nombre de la tabla Organization | `Organization-abc123-develop` | No |
| `LOCATION_TABLE_NAME` | Nombre de la tabla Location | `Location-abc123-develop` | No |

**Configurado vía:** Parámetros SAM (`CloudAppsyncUrl`, `CloudAppsyncApiKey`, `RacimoTableName`, `OrganizationTableName`, `LocationTableName`).

---

### UVALastConnection

| Variable | Descripción | Ejemplo | Secreto |
|----------|-------------|---------|---------|
| `APPSYNC_GRAPHQL_URL_USER` | Endpoint GraphQL del servicio UVA | `https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql` | No |
| `APPSYNC_API_KEY_USER` | API Key del servicio UVA | `da2-xxxxxxxxxxxxxxxxxxxx` | **Sí** |

**Configurado vía:** Parámetros SAM (`UvaAppsyncUrl`, `UvaAppsyncApiKey`).

---

### CreateRacimo

| Variable | Descripción | Ejemplo | Secreto |
|----------|-------------|---------|---------|
| `APPSYNC_GRAPHQL_URL_USER` | Endpoint GraphQL del servicio UVA | `https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql` | No |

**Nota:** No requiere API Key — usa AWS SigV4 con las credenciales del rol de ejecución Lambda.

---

## Advertencia de Seguridad

> **Las API keys están actualmente almacenadas como parámetros SAM en texto plano en `parameters.json`.** Este archivo **no debe commitearse** al repositorio con valores reales.
>
> **Recomendación:** Migrar a AWS Secrets Manager:
> ```yaml
> Environment:
>   Variables:
>     APPSYNC_API_KEY: !Sub "{{resolve:secretsmanager:UVA-AppSync-Key:SecretString:api_key}}"
> ```

---

## Configuración de la Plantilla SAM

**Ubicación:** `SAM-UVA-App-Integrations/template.yaml`

### Parámetros de la Plantilla

```yaml
Parameters:
  # ARNs del DynamoDB Stream
  StreamArnDataAccess:
    Type: String
    Description: ARN del stream de la tabla Measurement

  StreamArnCloud:
    Type: String
    Description: ARN del stream de la tabla UVA

  # Topic SNS
  TopicSNSDataArn:
    Type: String
    Description: ARN del topic de datos de dispositivos en tiempo real

  # Configuración AppSync UVA Service
  UvaAppsyncUrl:
    Type: String
    Description: Endpoint AppSync del servicio UVA

  UvaAppsyncApiKey:
    Type: String
    Description: API key del servicio UVA

  # Configuración AppSync MakeSensCloud
  CloudAppsyncUrl:
    Type: String
    Description: Endpoint AppSync del servicio Cloud

  CloudAppsyncApiKey:
    Type: String
    Description: API key del servicio Cloud

  # Tablas DynamoDB
  RacimoTableName:
    Type: String
    Description: Nombre de la tabla RACIMO

  OrganizationTableName:
    Type: String
    Description: Nombre de la tabla Organization

  LocationTableName:
    Type: String
    Description: Nombre de la tabla Location
```

### Configuración Global Lambda

```yaml
Globals:
  Function:
    Runtime: python3.9
    MemorySize: 520       # MB
    Timeout: 600          # Segundos (10 minutos)
    Architectures:
      - x86_64
```

---

## Archivo de Parámetros por Entorno

**Ubicación:** `SAM-UVA-App-Integrations/parameters.json`

```json
{
  "develop": {
    "StreamArnDataAccess": "arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-develop/stream/*",
    "StreamArnCloud": "arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-develop/stream/*",
    "TopicSNSDataArn": "arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-develop",
    "UvaAppsyncUrl": "https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql",
    "UvaAppsyncApiKey": "da2-...",
    "CloudAppsyncUrl": "https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql",
    "CloudAppsyncApiKey": "da2-...",
    "RacimoTableName": "RACIMO-{AppId}-develop",
    "OrganizationTableName": "Organization-{AppId}-develop",
    "LocationTableName": "Location-{AppId}-develop"
  },
  "test": { /* misma estructura con recursos del entorno test */ },
  "main": { /* misma estructura con recursos de producción */ }
}
```

---

## Mapeo de Entornos

| Rama Git | Entorno | Stack Name | Propósito |
|----------|---------|------------|-----------|
| develop | develop | SAM-UVA-App-Integrations-develop | Desarrollo activo |
| test | test | SAM-UVA-App-Integrations-test | Pruebas de pre-producción |
| main | main | SAM-UVA-App-Integrations-main | Producción |

El entorno se detecta automáticamente desde el nombre de la rama en `deploy.sh`:

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
case $BRANCH in
  develop) ENV="develop" ;;
  test)    ENV="test" ;;
  main)    ENV="main" ;;
  *)       echo "Unknown branch: $BRANCH"; exit 1 ;;
esac
```

---

## Políticas IAM por Lambda

### DynamoDBEventProcessorFunction

| Política | Recurso | Permisos |
|----------|---------|----------|
| DynamoDBStreamReadPolicy | `table/Measurement-*/stream/*` | GetRecords, GetShardIterator, DescribeStream, ListStreams |
| SNSPublishMessagePolicy | `RealTimeDeviceData-*` | sns:Publish |
| CloudWatch Logs | `/aws/lambda/*` | CreateLogGroup, CreateLogStream, PutLogEvents |

### UvaToCloudFunction

| Política | Recurso | Permisos |
|----------|---------|----------|
| DynamoDBStreamReadPolicy | `table/UVA-*/stream/*` | GetRecords, GetShardIterator, DescribeStream |
| DynamoDBReadPolicy | `table/RACIMO-*`, `table/Location-*` | dynamodb:GetItem |
| DynamoDBScanPolicy | `table/Organization-*` | dynamodb:Scan |

### UVALastConnection

| Política | Recurso | Permisos |
|----------|---------|----------|
| CloudWatch Logs | `logs:*:*` | CreateLogGroup, CreateLogStream, PutLogEvents |

Nota: El acceso a AppSync está controlado por API Key, no IAM.

### CreateRacimo

| Política | Recurso | Permisos |
|----------|---------|----------|
| AppSync GraphQL | `apis/*/types/Query/fields/listRACIMOS` | appsync:GraphQL |
| AppSync GraphQL | `apis/*/types/Mutation/fields/createRACIMO` | appsync:GraphQL |
| CloudWatch Logs | `logs:*:*` | CreateLogGroup, CreateLogStream, PutLogEvents |

---

## Configuración del API Gateway

```yaml
Type: AWS::Serverless::Api
Name: UvaAppIntegrationsAPI-{env}
Stage: prod
Auth:
  DefaultAuthorizer: AWS_IAM
```

**CORS:** No configurado actualmente.
**Throttling:** Límites por defecto de la cuenta AWS (10,000 req/seg, burst 5,000).

---

## Configuración de Logs

```yaml
LogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub "/aws/lambda/${FunctionName}"
    RetentionInDays: 7
```

**Grupos de logs:**
- `/aws/lambda/DynamoDBEventProcessorFunction`
- `/aws/lambda/UvaToCloudFunction`
- `/aws/lambda/UVALastConnection`
- `/aws/lambda/CreateRacimo`

---

## Etiquetado Recomendado de Recursos

```yaml
Tags:
  Project: UVA-App-Integrations
  Environment: !Ref EnvironmentParameter
  ManagedBy: SAM
  CostCenter: IoT-Services
  Owner: MakeSens-DevTeam
```
