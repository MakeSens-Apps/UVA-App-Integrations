# Despliegue — UVA-App-Integrations

---

## Prerequisitos

| Herramienta | Versión mínima | Propósito |
|-------------|----------------|-----------|
| AWS CLI | 2.x | Autenticación y operaciones AWS |
| AWS SAM CLI | 1.x | Build y deploy de la aplicación |
| Python | 3.9 | Runtime de las funciones Lambda |
| jq | 1.6 | Procesamiento de parámetros JSON en deploy.sh |
| Git | 2.x | Detección del entorno por rama |

---

## Configuración de Credenciales AWS

```bash
aws configure
# AWS Access Key ID: [CONFIGURAR]
# AWS Secret Access Key: [CONFIGURAR]
# Default region name: us-east-1
# Default output format: json
```

Alternativamente, usar variables de entorno:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

---

## Build

```bash
cd SAM-UVA-App-Integrations
sam build
```

El build instala las dependencias de cada `requirements.txt` y prepara los paquetes Lambda.

---

## Despliegue Automatizado (deploy.sh)

**Ubicación:** `SAM-UVA-App-Integrations/deploy.sh`

```bash
cd SAM-UVA-App-Integrations
./deploy.sh
```

El script:
1. Detecta el entorno desde la rama git actual
2. Carga los parámetros desde `parameters.json`
3. Valida la plantilla SAM
4. Ejecuta `sam build`
5. Despliega con `sam deploy` y los parámetros del entorno

**Lógica de detección de entorno:**

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
case $BRANCH in
  develop) ENV="develop" ;;
  test)    ENV="test" ;;
  main)    ENV="main" ;;
  *)       echo "Unknown branch: $BRANCH"; exit 1 ;;
esac
```

**Comando sam deploy generado:**

```bash
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "SAM-UVA-App-Integrations-${ENV}" \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --parameter-overrides $(echo $PARAMS | jq -r 'to_entries | map("\(.key)=\(.value)") | join(" ")')
```

---

## Despliegue Manual (Primera vez)

```bash
cd SAM-UVA-App-Integrations
sam build
sam deploy --guided
```

Parámetros a confirmar durante el deploy guiado:
- **Stack Name:** `SAM-UVA-App-Integrations-{env}` (develop/test/main)
- **AWS Region:** `us-east-1`
- **Confirm changes before deploy:** Yes
- **Allow SAM CLI IAM role creation:** Yes
- **Save arguments to samconfig.toml:** Yes

---

## Despliegue Manual (Subsecuentes)

```bash
cd SAM-UVA-App-Integrations
sam build
sam deploy --config-env develop  # o test, main
```

---

## Pipeline CI/CD (GitHub Actions)

**Workflows:**
- `.github/workflows/DeployTest.yml` — Despliega en entorno `test`
- `.github/workflows/DeployMain.yml` — Despliega en producción (`main`)

**Disparador:** Pull request mergeada en las ramas `test` o `main`.

**Pasos del workflow:**
1. Checkout del código
2. Configurar credenciales AWS (desde GitHub Secrets)
3. Instalar Python 3.9 (vía pyenv)
4. Instalar jq
5. Instalar AWS SAM CLI
6. Ejecutar `./deploy.sh`

---

## Nombres de Stack por Entorno

| Entorno | Stack Name |
|---------|------------|
| develop | `SAM-UVA-App-Integrations-develop` |
| test | `SAM-UVA-App-Integrations-test` |
| main | `SAM-UVA-App-Integrations-main` |

---

## Verificación Post-Deploy

```bash
# Ver outputs del stack (incluye URL de API Gateway)
aws cloudformation describe-stacks \
  --stack-name SAM-UVA-App-Integrations-develop \
  --query "Stacks[0].Outputs" \
  --output table

# Verificar que las Lambdas están activas
aws lambda list-functions \
  --region us-east-1 \
  --query "Functions[?contains(FunctionName, 'SAM-UVA-App-Integrations')].[FunctionName,State]" \
  --output table

# Ver logs recientes de una Lambda
sam logs -n DynamoDBEventProcessorFunction \
  --stack-name SAM-UVA-App-Integrations-develop \
  --tail

# Invocar la Lambda de estado de conexión localmente
sam local invoke UVALastConnection -e events/api-event.json

# Validar la plantilla
sam validate --lint
```

---

## Pruebas Locales

```bash
cd SAM-UVA-App-Integrations

# Compilar
sam build

# Invocar una función Lambda localmente
sam local invoke DynamoDBEventProcessorFunction -e events/dynamodb-event.json
sam local invoke UVALastConnection -e events/api-event.json
sam local invoke CreateRacimo -e events/create-racimo.json

# Iniciar la API local
sam local start-api
# API disponible en: http://127.0.0.1:3000
```

---

## Rollback

**Rollback automático:** CloudFormation hace rollback automático si el despliegue falla.

**Rollback manual a versión anterior:**
```bash
# Ver historial de changesets del stack
aws cloudformation describe-stack-events \
  --stack-name SAM-UVA-App-Integrations-develop \
  --query "StackEvents[?ResourceStatus=='UPDATE_COMPLETE'].[Timestamp,ResourceType]" \
  --output table

# Eliminar el stack completo (precaución: destructivo)
sam delete --stack-name SAM-UVA-App-Integrations-develop
```

---

## Logs en Producción

```bash
# Seguir logs en tiempo real
sam logs -n DynamoDBEventProcessorFunction \
  --stack-name SAM-UVA-App-Integrations-main \
  --tail

# Filtrar errores
sam logs -n UvaToCloudFunction \
  --stack-name SAM-UVA-App-Integrations-main \
  --filter "ERROR"

# Usar AWS CLI directamente
aws logs tail /aws/lambda/DynamoDBEventProcessorFunction --follow
```

---

## Verificar el Estado del Stack

```bash
aws cloudformation describe-stacks \
  --stack-name SAM-UVA-App-Integrations-develop \
  --query "Stacks[0].StackStatus"
```

Estados posibles:
- `CREATE_COMPLETE` / `UPDATE_COMPLETE` — Despliegue exitoso
- `ROLLBACK_COMPLETE` — Fallo con rollback completado
- `UPDATE_ROLLBACK_COMPLETE` — Actualización fallida, revertida

---

## Actualización de Dependencias

```bash
cd SAM-UVA-App-Integrations/lambdas/{nombre-lambda}

# Actualizar requirements.txt
pip install --upgrade boto3 requests

# Probar localmente
cd ../..
sam build
sam local invoke {FunctionName} -e events/test.json

# Desplegar
./deploy.sh
```

---

## Recuperación ante Desastres

**Reconstrucción completa del entorno:**

```bash
# 1. Restaurar código desde Git
git checkout main

# 2. Redesplegar el stack
cd SAM-UVA-App-Integrations
./deploy.sh

# 3. Verificar el despliegue
aws cloudformation describe-stacks \
  --stack-name SAM-UVA-App-Integrations-main \
  --query "Stacks[0].StackStatus"
```

**RTO (Objetivo de Tiempo de Recuperación):** < 30 minutos
**RPO (Objetivo de Punto de Recuperación):** < 1 hora (último commit en Git)

---

## Resolución de Problemas

**Lambda timeout (supera 600s):**
- Revisar latencia de AppSync/DynamoDB en CloudWatch Logs
- Buscar cuellos de botella en el código

**Aumento de IteratorAge del DynamoDB Stream:**
- Verificar errores de Lambda (las funciones con fallos reintentarán)
- Reducir el tamaño del lote (de 10 a 5)
- Aumentar la concurrencia de Lambda

**API Gateway 403 Forbidden:**
- Verificar credenciales AWS (autorización IAM)
- Asegurarse de que la solicitud esté firmada con SigV4

**Diagnóstico general:**

```bash
# Verificar estado del stack
aws cloudformation describe-stacks --stack-name SAM-UVA-App-Integrations-develop

# Ver eventos recientes del stack
aws cloudformation describe-stack-events \
  --stack-name SAM-UVA-App-Integrations-develop \
  --query "StackEvents[0:10].[Timestamp,ResourceType,ResourceStatus,ResourceStatusReason]" \
  --output table

# Validar plantilla antes de desplegar
sam validate --lint

# Verificar métricas de Lambda
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=UvaToCloudFunction \
  --start-time $(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 3600 \
  --statistics Sum
```
