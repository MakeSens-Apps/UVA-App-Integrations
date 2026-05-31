# Infraestructura

## Descripción General

UVA-App-Integrations se despliega usando **AWS Serverless Application Model (SAM)**, que provee infraestructura como código mediante plantillas de CloudFormation. La infraestructura es completamente serverless, no requiere gestión de servidores y escala automáticamente según la demanda.

**Infraestructura como Código**: AWS SAM (basado en CloudFormation)
**Proveedor Cloud**: Amazon Web Services (AWS)
**Región**: us-east-1 (N. Virginia)
**ID de Cuenta**: 913045965320

---

## Componentes de Infraestructura

### 1. AWS Lambda

**Servicio**: AWS Lambda (Cómputo Serverless)

**Funciones Desplegadas**:
```yaml
Functions:
  - DynamoDBEventProcessorFunction
  - UvaToCloudFunction
  - UVALastConnection
  - CreateRacimo
```

**Configuración Global** (desde la plantilla SAM):
```yaml
Globals:
  Function:
    Runtime: python3.9
    MemorySize: 520          # MB
    Timeout: 600             # Segundos (10 minutos)
    Architectures:
      - x86_64
```

**Nomenclatura de Recursos**:
- Patrón: `{FunctionName}-{StackName}-{UniqueId}`
- Ejemplo: `DynamoDBEventProcessorFunction-SAM-UVA-App-Integrations-dev-abc123`

**Roles de Ejecución**:
- Creados automáticamente por SAM para cada función
- Sigue el principio de mínimo privilegio
- Otorga permisos específicos mediante la sección Policies en la plantilla

---

### 2. Amazon DynamoDB

**Servicio**: Amazon DynamoDB (Base de Datos NoSQL)

**Tablas** (no administradas por este stack - dependencias externas):
```
Measurement-{AppId}-{env}
UVA-{AppId}-{env}
RACIMO-{AppId}-{env}
Organization-{AppId}-{env}
Location-{AppId}-{env}
```

**Configuración de Streams**:
- **Stream de Measurement**: Dispara DynamoDBEventProcessorFunction
- **Stream de UVA**: Dispara UvaToCloudFunction
- **Tamaño de Lote**: 10 registros
- **Ventana de Agrupamiento**: 10 segundos
- **Posición Inicial**: LATEST

**Ejemplos de ARN**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-abc123-develop/stream/*
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-abc123-develop/stream/*
```

---

### 3. Amazon SNS

**Servicio**: Amazon SNS (Simple Notification Service)

**Topic** (dependencia externa):
- **Nombre**: `RealTimeDeviceData-{env}`
- **Propósito**: Distribuir datos de mediciones procesados
- **Publicador**: DynamoDBEventProcessorFunction
- **Suscriptores**: Externos (no administrados por este stack)

**Patrón ARN**:
```
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-develop
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-test
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-main
```

**Atributos del Mensaje**:
- `typeDevice`: "UVA"
- `typeData`: "RAW"

---

### 4. AWS AppSync

**Servicio**: AWS AppSync (API GraphQL)

**APIs** (dependencias externas - no administradas por este stack):

**AppSync de MakeSensCloud**:
```yaml
Propósito: Gestión de dispositivos y ubicaciones
Endpoint: https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
Autenticación: API Key
Operaciones:
  - Mutación: createDevice
  - Mutación: createLocation
  - Mutación: updateLocation
```

**AppSync del Servicio UVA**:
```yaml
Propósito: Consultas de mediciones y gestión de RACIMO
Endpoint: https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
Autenticación: API Key (consultas) / SigV4 (mutaciones)
Operaciones:
  - Consulta: measurementsByUvaIDAndTs
  - Consulta: getUVA
  - Consulta: listRACIMOS
  - Mutación: createRACIMO
```

---

### 5. API Gateway

**Servicio**: Amazon API Gateway (REST API)

**Configuración de la API**:
```yaml
Type: AWS::Serverless::Api
Name: UvaAppIntegrationsAPI-{env}
Stage: prod
Authorization: AWS_IAM
```

**Endpoints**:
```
GET  /{id_uva}/connection   → Lambda UVALastConnection
POST /CreateRacimo          → Lambda CreateRacimo
```

**Patrón de URL Base**:
```
https://{api-id}.execute-api.us-east-1.amazonaws.com/prod
```

**CORS**: No configurado (se puede agregar si es necesario)

**Throttling**:
- Se aplican los límites predeterminados de la cuenta AWS
- Límite de tasa: 10,000 solicitudes por segundo
- Límite de burst: 5,000 solicitudes

---

### 6. CloudWatch Logs

**Servicio**: Amazon CloudWatch Logs

**Grupos de Logs** (creados automáticamente):
```
/aws/lambda/DynamoDBEventProcessorFunction
/aws/lambda/UvaToCloudFunction
/aws/lambda/UVALastConnection
/aws/lambda/CreateRacimo
```

**Retención**: Por defecto (nunca expiran) - se debe configurar una política de retención

**Formato de Logs**: Logs estructurados en JSON desde las funciones Lambda

**Retención Recomendada**:
```yaml
LogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub "/aws/lambda/${FunctionName}"
    RetentionInDays: 7  # o 14, 30, 60, 90
```

---

## Estructura de la Plantilla SAM

**Ubicación**: `SAM-UVA-App-Integrations/template.yaml`

### Secciones de la Plantilla

**Transform**:
```yaml
Transform: AWS::Serverless-2016-10-31
```
Habilita la sintaxis específica de SAM

**Parámetros** (valores específicos por entorno):
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

  # Configuración AppSync
  UvaAppsyncUrl:
    Type: String
    Description: Endpoint AppSync del servicio UVA

  UvaAppsyncApiKey:
    Type: String
    Description: API key del servicio UVA

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

**Funciones** (ejemplo simplificado):
```yaml
Resources:
  DynamoDBEventProcessorFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: lambdas/deviceDataAccess/
      Handler: dynamodb_to_sns.lambda_handler
      Environment:
        Variables:
          TOPIC_SNS_ARN: !Ref TopicSNSDataArn
      Events:
        DynamoDBStream:
          Type: DynamoDB
          Properties:
            Stream: !Ref StreamArnDataAccess
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 10
            StartingPosition: LATEST
      Policies:
        - DynamoDBStreamReadPolicy:
            TableName: "*"
            StreamName: "*"
        - SNSPublishMessagePolicy:
            TopicName: !GetAtt TopicSNSDataArn
```

**Outputs**:
```yaml
Outputs:
  ApiEndpoint:
    Description: URL del endpoint de API Gateway
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/prod/"

  DynamoDBProcessorArn:
    Description: ARN de la Lambda DynamoDB Event Processor
    Value: !GetAtt DynamoDBEventProcessorFunction.Arn
```

---

## Configuración de Entornos

### Archivo de Parámetros

**Ubicación**: `SAM-UVA-App-Integrations/parameters.json`

**Estructura**:
```json
{
  "develop": {
    "StreamArnDataAccess": "arn:aws:dynamodb:...",
    "StreamArnCloud": "arn:aws:dynamodb:...",
    "TopicSNSDataArn": "arn:aws:sns:...",
    "UvaAppsyncUrl": "https://...",
    "UvaAppsyncApiKey": "da2-...",
    "CloudAppsyncUrl": "https://...",
    "CloudAppsyncApiKey": "da2-...",
    "RacimoTableName": "RACIMO-abc123-develop",
    "OrganizationTableName": "Organization-abc123-develop",
    "LocationTableName": "Location-abc123-develop"
  },
  "test": { /* misma estructura */ },
  "main": { /* misma estructura */ }
}
```

### Mapeo de Entornos

| Rama Git | Entorno | Propósito |
|----------|---------|-----------|
| develop  | develop | Desarrollo y pruebas de funcionalidades |
| test     | test    | Validación de pre-producción |
| main     | main    | Producción |

**Comportamiento del Despliegue**:
- El nombre de la rama se detecta en el script `deploy.sh`
- Los parámetros correspondientes se cargan desde el JSON
- SAM despliega con los recursos específicos del entorno

---

## Roles y Permisos IAM

### Roles de Ejecución de Lambda

**Generados automáticamente por SAM** para cada función con políticas específicas.

#### Rol de DynamoDBEventProcessorFunction

**Permisos**:
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
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:913045965320:log-group:/aws/lambda/*"
    }
  ]
}
```

#### Rol de UvaToCloudFunction

**Permisos**:
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

Nota: El acceso a AppSync se realiza vía API Key, no IAM

#### Rol de UVALastConnection

**Permisos**:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    }
  ]
}
```

Nota: El acceso a AppSync se controla vía API Key

#### Rol de CreateRacimo

**Permisos**:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["appsync:GraphQL"],
      "Resource": [
        "arn:aws:appsync:us-east-1:*:apis/*/types/Query/*",
        "arn:aws:appsync:us-east-1:*:apis/*/types/Mutation/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    }
  ]
}
```

Utiliza firma SigV4 para la autenticación en AppSync

### Rol de Ejecución de API Gateway

**Generado automáticamente** con permisos para invocar funciones Lambda:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": [
        "arn:aws:lambda:us-east-1:*:function:UVALastConnection*",
        "arn:aws:lambda:us-east-1:*:function:CreateRacimo*"
      ]
    }
  ]
}
```

---

## Proceso de Despliegue

### Despliegue Automatizado (CI/CD)

**Pipeline**: GitHub Actions

**Flujos de Trabajo**:
- `.github/workflows/DeployTest.yml` - Despliega en el entorno test
- `.github/workflows/DeployMain.yml` - Despliega en producción

**Disparador**: Pull request cerrada (mergeada) en la rama `test` o `main`

**Pasos**:
1. Checkout del código
2. Configurar credenciales AWS (desde GitHub Secrets)
3. Instalar Python 3.9 (vía pyenv)
4. Instalar jq (procesador JSON)
5. Instalar AWS SAM CLI
6. Ejecutar el script `deploy.sh`

### Script de Despliegue

**Ubicación**: `SAM-UVA-App-Integrations/deploy.sh`

**Proceso**:
```bash
#!/bin/bash

# 1. Detectar entorno desde la rama git
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [[ $BRANCH == "develop" ]]; then
  ENV="develop"
elif [[ $BRANCH == "test" ]]; then
  ENV="test"
elif [[ $BRANCH == "main" ]]; then
  ENV="main"
else
  echo "Unknown branch: $BRANCH"
  exit 1
fi

# 2. Cargar parámetros desde JSON
PARAMS=$(jq -r ".${ENV}" parameters.json)

# 3. Validar la plantilla SAM
sam validate --template template.yaml

# 4. Compilar los paquetes Lambda
sam build --template template.yaml

# 5. Desplegar el stack de CloudFormation
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "SAM-UVA-App-Integrations-${ENV}" \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --parameter-overrides $(echo $PARAMS | jq -r 'to_entries | map("\(.key)=\(.value)") | join(" ")')
```

**Patrón de Nombre del Stack**:
- develop: `SAM-UVA-App-Integrations-develop`
- test: `SAM-UVA-App-Integrations-test`
- main: `SAM-UVA-App-Integrations-main`

### Despliegue Manual

```bash
# Navegar al directorio SAM
cd SAM-UVA-App-Integrations

# Compilar
sam build

# Desplegar en un entorno específico
sam deploy \
  --config-env develop \
  --stack-name SAM-UVA-App-Integrations-develop \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

---

## Etiquetado de Recursos

**Etiquetas Recomendadas** (agregar a la plantilla SAM):
```yaml
Tags:
  Project: UVA-App-Integrations
  Environment: !Ref EnvironmentParameter
  ManagedBy: SAM
  CostCenter: IoT-Services
  Owner: MakeSens-DevTeam
```

**Beneficios**:
- Asignación de costos por entorno
- Organización de recursos
- Control de acceso mediante políticas basadas en etiquetas

---

## Estimación de Costos

### Desglose de Costos Mensuales (Aproximado)

**AWS Lambda**:
- **Solicitudes**: 10M solicitudes/mes
- **Duración**: 500ms promedio, 520MB de memoria
- **Costo**: ~$20-30/mes

**DynamoDB Streams**:
- **Solicitudes de lectura**: Incluidas con DynamoDB
- **Costo**: $0 (cubierto por los cargos de DynamoDB)

**API Gateway**:
- **Solicitudes**: 1M llamadas API/mes
- **Costo**: ~$3.50/mes

**CloudWatch Logs**:
- **Ingesta**: 10GB/mes
- **Almacenamiento**: 50GB (sin política de retención)
- **Costo**: ~$5-10/mes

**Transferencia de Datos**:
- **SNS**: 1M mensajes/mes
- **AppSync**: 1M consultas/mes
- **Costo**: ~$5-15/mes

**Costo Mensual Total Estimado**: $35-60 (excluyendo DynamoDB y AppSync - administrados externamente)

### Optimización de Costos

1. **Implementar retención de CloudWatch Logs** (7-30 días)
   - Reduce los costos de almacenamiento entre un 70-90%

2. **Ajustar la memoria de Lambda**
   - Actual: 520 MB
   - Probar con 256 MB o 384 MB para posibles ahorros

3. **Usar concurrencia reservada de Lambda**
   - Previene el throttling
   - Sin costo adicional

4. **Habilitar caché en API Gateway**
   - Reduce las invocaciones de Lambda
   - Cachear el estado de conexión por 60 segundos

---

## Monitoreo y Alarmas

### Alarmas de CloudWatch

**Errores en Funciones Lambda**:
```yaml
FunctionErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub "${FunctionName}-Errors"
    MetricName: Errors
    Namespace: AWS/Lambda
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 5
    ComparisonOperator: GreaterThanThreshold
    Dimensions:
      - Name: FunctionName
        Value: !Ref FunctionName
```

**Retraso en DynamoDB Stream**:
```yaml
StreamLagAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: UVA-Stream-Iterator-Age
    MetricName: GetRecords.IteratorAgeMilliseconds
    Namespace: AWS/DynamoDB
    Statistic: Maximum
    Period: 300
    Threshold: 600000  # 10 minutos
    ComparisonOperator: GreaterThanThreshold
```

**Errores 5xx en API Gateway**:
```yaml
ApiErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: API-Server-Errors
    MetricName: 5XXError
    Namespace: AWS/ApiGateway
    Statistic: Sum
    Period: 60
    Threshold: 10
    ComparisonOperator: GreaterThanThreshold
```

### Dashboards

**Dashboard de CloudWatch Recomendado** (JSON):
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Invocations", {"stat": "Sum"}],
          [".", "Errors", {"stat": "Sum"}],
          [".", "Duration", {"stat": "Average"}]
        ],
        "period": 300,
        "region": "us-east-1",
        "title": "Métricas de Lambda"
      }
    }
  ]
}
```

---

## Consideraciones de Seguridad

### Seguridad de Red

**VPC**: No configurada (Lambda ejecuta en VPC administrada por AWS)
**Recomendación**: Considerar despliegue en VPC si se accede a recursos privados

**Endpoints**:
- Todas las Lambda → DynamoDB: HTTPS
- Todas las Lambda → AppSync: HTTPS
- Todas las Lambda → SNS: HTTPS
- API Gateway: Solo HTTPS

### Gestión de Secretos

**Estado Actual**: Las API keys se almacenan en parámetros SAM (texto plano en JSON)

**Recomendación**: Usar AWS Secrets Manager
```yaml
Environment:
  Variables:
    APPSYNC_API_KEY: !Sub "{{resolve:secretsmanager:UVA-AppSync-Key:SecretString:api_key}}"
```

**Beneficios**:
- Rotación automática
- Cifrado en reposo
- Registro de auditoría
- Sin texto plano en control de versiones

### Seguridad de la API

**API Gateway**:
- Autorización: AWS_IAM (requiere solicitudes firmadas)
- Previene el acceso anónimo
- Se integra con usuarios/roles de AWS IAM

**Limitación de Tasa**:
- Se aplican los límites predeterminados de la cuenta AWS
- Recomendación: Configurar throttling por clave
  ```yaml
  ApiGatewayUsagePlan:
    Type: AWS::ApiGateway::UsagePlan
    Properties:
      Throttle:
        RateLimit: 100
        BurstLimit: 200
  ```

---

## Recuperación ante Desastres

### Estrategia de Respaldo

**Funciones Lambda**:
- Código almacenado en Git (versionado)
- Plantilla SAM en Git (infraestructura como código)
- No se requiere respaldo (se puede redesplegar desde el origen)

**Stacks de CloudFormation**:
- Exportar plantillas del stack periódicamente
- Almacenar en bucket S3 con versionado

**Configuración**:
- `parameters.json` en Git
- Secretos en AWS Secrets Manager (respaldados automáticamente)

### Proceso de Recuperación

**Reconstrucción Completa del Entorno**:
```bash
# 1. Restaurar parameters.json desde Git
git checkout main

# 2. Redesplegar el stack
cd SAM-UVA-App-Integrations
./deploy.sh

# 3. Verificar el despliegue
sam list stack-outputs --stack-name SAM-UVA-App-Integrations-main
```

**RTO (Objetivo de Tiempo de Recuperación)**: < 30 minutos
**RPO (Objetivo de Punto de Recuperación)**: < 1 hora (último commit en Git)

---

## Consideraciones de Escalabilidad

### Auto-escalado de Lambda

**Concurrencia**:
- Por defecto: 1000 ejecuciones concurrentes (límite de cuenta AWS)
- Concurrencia reservada: No configurada
- Concurrencia provisionada: No configurada (los arranques en frío son aceptables)

**Shards de DynamoDB Stream**:
- Cada shard: ~2000 registros/segundo
- Concurrencia de Lambda = número de shards
- Escala automáticamente con la tabla DynamoDB

### Escalabilidad de API Gateway

**Límites**:
- Endpoint regional: 10,000 solicitudes/segundo (por defecto)
- Capacidad de burst: 5,000 solicitudes
- Se puede solicitar aumento del límite vía AWS Support

### Cuellos de Botella

**Actuales**:
1. **Scan de la tabla Organization**: Escaneo completo para búsqueda por código de vinculación
   - Solución: Agregar GSI en `linkage_code`

2. **Límites de tasa de la API AppSync**: Dependencia externa
   - Solución: Implementar backoff exponencial y reintento

3. **Arranques en frío de Lambda**: ~2-3 segundos
   - Solución: Concurrencia provisionada (si se requiere latencia < 100ms)

---

## Mantenimiento

### Tareas Regulares

**Semanales**:
- Revisar CloudWatch Logs en busca de errores
- Verificar métricas de duración de Lambda (optimizar si > 5 segundos)

**Mensuales**:
- Revisar costos de CloudWatch (almacenamiento de logs)
- Actualizar dependencias de Lambda (boto3, requests)
- Rotar API keys (si se utilizan)

**Trimestrales**:
- Revisar permisos IAM (mínimo privilegio)
- Actualizar la versión del runtime de Python
- Pruebas de carga en los endpoints API

### Actualizaciones y Parches

**Runtime de Lambda**:
- Actual: Python 3.9
- Proceso de actualización: Cambiar `Runtime` en la plantilla SAM → redesplegar

**Dependencias**:
```bash
# Actualizar requirements.txt
pip install --upgrade boto3 requests

# Probar localmente
sam build
sam local invoke FunctionName -e events/test.json

# Desplegar
sam deploy
```

**SAM CLI**:
```bash
pip install --upgrade aws-sam-cli
```

---

## Resolución de Problemas

### Problemas Comunes

**Problema**: Timeout de Lambda (se supera el límite de 600s)
**Solución**:
- Verificar la latencia de AppSync/DynamoDB
- Revisar CloudWatch Logs en busca de cuellos de botella
- Considerar procesamiento asíncrono para operaciones largas

**Problema**: Aumento de la antigüedad del iterador del DynamoDB Stream
**Solución**:
- Verificar errores de Lambda (las funciones con fallos reintentarán)
- Aumentar la concurrencia de Lambda
- Revisar el tamaño del lote (reducir de 10 a 5)

**Problema**: API Gateway 403 Forbidden
**Solución**:
- Verificar las credenciales AWS (autorización IAM)
- Verificar la política de recursos de API Gateway
- Asegurarse de que la solicitud esté firmada con SigV4

### Comandos de Diagnóstico

```bash
# Ver logs de Lambda
sam logs -n DynamoDBEventProcessorFunction --tail

# Invocar función localmente
sam local invoke UVALastConnection -e events/api-event.json

# Iniciar API local
sam local start-api

# Validar plantilla
sam validate --lint

# Verificar estado del stack
aws cloudformation describe-stacks --stack-name SAM-UVA-App-Integrations-develop
```

---

## Referencias

**Documentación de AWS**:
- [Documentación de AWS SAM](https://docs.aws.amazon.com/serverless-application-model/)
- [Mejores Prácticas de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)

**Documentación Interna**:
- [Arquitectura](architecture.md)
- [Funciones Lambda](lambdas.md)
- [Esquema de Base de Datos](database.md)
