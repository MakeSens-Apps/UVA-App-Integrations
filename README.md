# UVA-App-Integrations

## Descripción del Proyecto

UVA-App-Integrations es un microservicio serverless que conecta el ecosistema de dispositivos IoT **UVA (Universal Vitals Application)** con los servicios cloud de MakeSens. Resuelve el problema de negocio de la **sincronización de datos de dispositivos en tiempo real**, el **monitoreo de conexiones** y la **gestión de dispositivos organizacionales** en redes de sensores distribuidos.

## Propósito

Este repositorio provee la capa de integración que:
- Procesa y distribuye datos de mediciones en tiempo real desde dispositivos UVA
- Sincroniza dispositivos UVA con MakeSensCloud para una gestión centralizada
- Monitorea el estado de conexión de los dispositivos para mantenimiento y alertas
- Gestiona las configuraciones de RACIMO (clúster de dispositivos) para la jerarquía organizacional

## Funcionalidades Principales

- **Procesamiento de Datos en Tiempo Real**: Transmite mediciones de dispositivos desde DynamoDB a SNS para consumidores downstream
- **Sincronización de Dispositivos**: Crea y actualiza automáticamente registros de dispositivos en MakeSensCloud cuando se registran dispositivos UVA
- **Gestión de Ubicación**: Rastrea y actualiza coordenadas geográficas de dispositivos UVA
- **Monitoreo de Conexión**: Endpoint REST API para verificar si los dispositivos están activos (conectados en las últimas 24 horas)
- **Gestión de RACIMO**: REST API para crear clústeres de dispositivos con códigos de vinculación
- **Soporte Multi-Entorno**: Configuraciones separadas para los entornos develop, test y production

## Comandos Básicos

### Prerrequisitos
- Python 3.9
- AWS SAM CLI
- Credenciales de AWS configuradas
- jq (para procesamiento de JSON)

### Instalación/Configuración
```bash
# Clonar el repositorio
git clone <repository-url>
cd UVA-App-Integrations/SAM-UVA-App-Integrations

# Instalar AWS SAM CLI (si no está instalado)
pip install aws-sam-cli

# Instalar dependencias para pruebas locales
pip install boto3 requests
```

### Despliegue en AWS
```bash
# Navegar al directorio SAM
cd SAM-UVA-App-Integrations

# Desplegar usando el script automatizado (detecta la rama para el entorno)
./deploy.sh

# O desplegar manualmente en un entorno específico
sam build
sam deploy --config-env develop  # o test, main
```

### Pruebas Locales
```bash
# Compilar la aplicación
sam build

# Invocar una función Lambda localmente
sam local invoke DynamoDBEventProcessorFunction -e events/dynamodb-event.json

# Iniciar la API local
sam local start-api
```

### Ejecutar Pruebas
```bash
# Navegar al directorio de la lambda
cd SAM-UVA-App-Integrations/lambdas/<function-name>

# Ejecutar pruebas unitarias (cuando estén disponibles)
python -m pytest tests/
```

## Arquitectura General

### Componentes de Alto Nivel

```
┌─────────────────┐
│  DynamoDB       │
│  - Measurement  │──Stream──┐
│  - UVA          │──Stream──┤
│  - RACIMO       │          │
│  - Organization │          │
│  - Location     │          │
└─────────────────┘          │
                             ▼
                    ┌─────────────────────┐
                    │   Lambda Functions  │
                    │  ┌───────────────┐  │
                    │  │ Device Data   │──┼──► SNS Topic
                    │  │ Processor     │  │
                    │  ├───────────────┤  │
                    │  │ UVA to Cloud  │──┼──► AppSync (Cloud)
                    │  ├───────────────┤  │
                    │  │ Connection    │◄─┼──  API Gateway
                    │  │ Status        │  │
                    │  ├───────────────┤  │
                    │  │ Create        │◄─┼──  API Gateway
                    │  │ RACIMO        │  │
                    │  └───────────────┘  │
                    └─────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  AWS AppSync    │
                    │  (GraphQL APIs) │
                    └─────────────────┘
```

### Flujo de Datos
1. **Stream de Mediciones**: Los dispositivos UVA escriben mediciones en DynamoDB → El stream dispara Lambda → Publica en SNS
2. **Sincronización de Dispositivos**: Nuevo UVA registrado → El stream dispara Lambda → Crea el dispositivo en MakeSensCloud vía GraphQL
3. **Verificación de Conexión**: Solicitud API → Lambda consulta AppSync → Devuelve el estado de conexión
4. **Creación de RACIMO**: Solicitud API → Lambda verifica/crea RACIMO → Devuelve el ID del clúster

## Tecnologías Principales

### Plataforma Cloud
- **AWS Lambda**: Cómputo serverless para procesamiento de eventos
- **AWS SAM**: Infraestructura como código y despliegue
- **Amazon DynamoDB**: Base de datos NoSQL con streams
- **Amazon SNS**: Publicación de mensajes para datos en tiempo real
- **AWS AppSync**: API GraphQL para sincronización de datos
- **API Gateway**: Endpoints REST API
- **AWS IAM**: Autenticación y autorización

### Desarrollo
- **Python 3.9**: Lenguaje de programación principal
- **boto3**: SDK de AWS para Python
- **requests**: Cliente HTTP para operaciones GraphQL
- **GitHub Actions**: Automatización CI/CD

### DevOps
- **CloudFormation**: Aprovisionamiento de infraestructura
- **Bash**: Automatización de despliegues
- **jq**: Procesamiento de parámetros JSON

## Estructura del Repositorio

```
UVA-App-Integrations/
├── .github/workflows/       # Pipelines CI/CD para entornos test y main
├── SAM-UVA-App-Integrations/
│   ├── lambdas/
│   │   ├── cloud/          # Integración UVA con MakeSensCloud
│   │   ├── createRacimo/   # Gestión de clústeres RACIMO
│   │   ├── deviceDataAccess/# Streaming de datos en tiempo real
│   │   └── uvaConnection/  # Monitoreo del estado de conexión
│   ├── deploy.sh           # Script de despliegue automatizado
│   ├── parameters.json     # Configuración específica por entorno
│   └── template.yaml       # Plantilla SAM CloudFormation
├── docs/                   # Documentación técnica detallada
└── README.md              # Este archivo
```

## Documentación

Para documentación técnica detallada, consulta la carpeta `/docs`:
- [Índice de documentación](docs/README.md) - Guía de navegación completa
- [Arquitectura](docs/architecture/ARCHITECTURE.md) - Diseño del sistema y diagramas de componentes
- [Módulos Lambda](docs/architecture/MODULES.md) - Especificaciones de las funciones Lambda
- [Endpoints y Eventos](docs/api/ENDPOINTS.md) - API REST y eventos DynamoDB Streams
- [Modelos de Datos](docs/data/MODELS.md) - Esquema DynamoDB y modelo de datos
- [Flujo de Datos](docs/data/FLOW.md) - Flujos de datos extremo a extremo
- [Configuración](docs/configuration/ENVIRONMENT.md) - Variables de entorno y parámetros SAM
- [Despliegue](docs/deployment/DEPLOYMENT.md) - Recursos y proceso de despliegue AWS
- [Operación](docs/operation/FLOW.md) - Ciclo operacional, errores y mantenimiento

## Licencia

Consulta [LICENSE.txt](LICENSE.txt) para más detalles.

## Soporte

Para problemas o preguntas, por favor contacta al equipo de desarrollo de MakeSens.
