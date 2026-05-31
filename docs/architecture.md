# Arquitectura del Sistema

## Descripción General

UVA-App-Integrations implementa una **arquitectura serverless orientada a eventos** en AWS, utilizando DynamoDB Streams como fuente principal de eventos para disparar flujos de trabajo de procesamiento y sincronización de datos. El sistema integra datos de dispositivos IoT con servicios cloud a través de funciones Lambda, APIs GraphQL de AppSync y mensajería SNS.

## Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Ecosistema de Dispositivos UVA                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Tablas DynamoDB                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ Measurement  │  │     UVA      │  │   RACIMO     │                  │
│  │   (Stream)   │  │   (Stream)   │  │              │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘                  │
│         │                  │                                             │
│         │ Evento Stream    │ Evento Stream                               │
└─────────┼──────────────────┼─────────────────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Capa de Funciones Lambda                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ DynamoDBEventProcessorFunction                                  │    │
│  │  • Lee: Stream de Measurement                                   │    │
│  │  • Procesa: Eventos INSERT                                      │    │
│  │  • Transforma: Formato DynamoDB → Tipos Python                  │    │
│  │  • Publica: SNS (RealTimeDeviceData)                           │    │
│  └───────────────────────────────┬────────────────────────────────┘    │
│                                   │                                      │
│  ┌────────────────────────────────▼───────────────────────────────┐    │
│  │ UvaToCloudFunction                                              │    │
│  │  • Lee: Stream UVA (INSERT/MODIFY)                             │    │
│  │  • Consulta: Tablas RACIMO, Organization, Location             │    │
│  │  • Crea: Dispositivos en MakeSensCloud vía GraphQL             │    │
│  │  • Actualiza: Registros de Location con coordenadas            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ UVALastConnection (Endpoint API)                                 │    │
│  │  • Disparador: API Gateway GET /{id_uva}/connection             │    │
│  │  • Consulta: AppSync para las últimas mediciones                │    │
│  │  • Devuelve: Estado de conexión (últimas 24h) + timestamp       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ CreateRacimo (Endpoint API)                                      │    │
│  │  • Disparador: API Gateway POST /CreateRacimo                   │    │
│  │  • Valida: Existencia de RACIMO vía consulta GraphQL            │    │
│  │  • Crea: Nuevo RACIMO con código de vinculación                 │    │
│  │  • Auth: Firma AWS SigV4                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────┬──────────────────────────────┬──────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│   Amazon SNS    │          │   AWS AppSync        │
│                 │          │   (APIs GraphQL)     │
│ RealTimeDevice  │          │  ┌────────────────┐  │
│ Data Topic      │          │  │ UVA Service    │  │
│                 │          │  │ (UserAPI)      │  │
└─────────────────┘          │  └────────────────┘  │
                              │  ┌────────────────┐  │
                              │  │ MakeSensCloud  │  │
                              │  │ Service        │  │
                              │  └────────────────┘  │
                              └──────────────────────┘
```

## Detalles de los Componentes

### 1. Capa de Almacenamiento de Datos (DynamoDB)

**Propósito**: Almacenamiento persistente de datos de dispositivos, metadatos y estructuras organizacionales

**Tablas**:
- **Measurement**: Almacena datos de sensores en series de tiempo de los dispositivos UVA
- **UVA**: Registro de dispositivos con metadatos y configuración
- **RACIMO**: Clústeres/grupos de dispositivos con códigos de vinculación
- **Organization**: Entidades organizacionales vinculadas a clústeres de dispositivos
- **Location**: Coordenadas geográficas de los dispositivos UVA

**Configuración de Streams**:
- Habilitado en: Tablas Measurement y UVA
- Tamaño de lote: 10 registros
- Ventana de agrupamiento: 10 segundos
- Posición inicial: LATEST

### 2. Capa de Cómputo (Funciones Lambda)

**Configuración de Ejecución**:
- Runtime: Python 3.9
- Memoria: 520 MB por función
- Timeout: 600 segundos (10 minutos)
- Arquitectura: x86_64

**Funciones**:
1. **DynamoDBEventProcessorFunction**: Procesador de datos disparado por stream
2. **UvaToCloudFunction**: Sincronización de dispositivos disparada por stream
3. **UVALastConnection**: Monitor de conexión disparado por API Gateway
4. **CreateRacimo**: Administrador de clústeres disparado por API Gateway

### 3. Capa de API

**API Gateway**:
- **REST API** con autorización AWS_IAM
- Endpoints:
  - `GET /{id_uva}/connection` → UVALastConnection
  - `POST /CreateRacimo` → CreateRacimo

**AppSync GraphQL**:
- **API de Servicio UVA**: Consultas y mutaciones de dispositivos y mediciones
- **API de MakeSensCloud**: Gestión de dispositivos y ubicaciones
- Autenticación: API Key (principal), SigV4 (CreateRacimo)

### 4. Capa de Mensajería

**Amazon SNS**:
- Topic: `RealTimeDeviceData-{env}`
- Publicador: DynamoDBEventProcessorFunction
- Atributos del mensaje: `typeDevice=UVA`, `typeData=RAW`
- Propósito: Distribución en abanico de datos de dispositivos a múltiples suscriptores

## Diagramas de Flujo de Datos

### Flujo 1: Procesamiento de Mediciones en Tiempo Real

```
Dispositivo UVA → Tabla Measurement → DynamoDB Stream
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ Event Processor     │
                              │ Lambda              │
                              │                     │
                              │ 1. Filtrar INSERT   │
                              │ 2. Transformar tipos│
                              │ 3. Formatear ts     │
                              └─────────┬───────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ SNS Topic           │
                              │ RealTimeDeviceData  │
                              └─────────────────────┘
                                        │
                                        ▼
                              [ Consumidores Downstream ]
```

**Pasos**:
1. El dispositivo UVA escribe una medición en DynamoDB
2. DynamoDB Stream captura el evento INSERT
3. Lambda recibe el lote de registros del stream
4. Lambda filtra solo los eventos INSERT
5. Lambda transforma el formato DynamoDB a JSON estándar
6. Lambda convierte los timestamps ISO a milisegundos Unix
7. Lambda publica en SNS con atributos de mensaje
8. SNS distribuye a todos los suscriptores

### Flujo 2: Sincronización de Dispositivos a la Nube

```
Nuevo UVA Creado → Tabla UVA → DynamoDB Stream
                                    │
                                    ▼ (evento INSERT)
                          ┌──────────────────────┐
                          │ UvaToCloudFunction   │
                          │                      │
                          │ 1. Extraer UVA ID    │
                          │ 2. Obtener RACIMO ID │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ Consultar Tabla RACIMO│
                          │ Obtener LinkageCode   │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ Escanear Organization │
                          │ Coincidir linkage_code│
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ AppSync GraphQL      │
                          │ createDevice()       │
                          └──────────────────────┘
```

**Pasos (INSERT)**:
1. Se crea un nuevo registro UVA en DynamoDB
2. El evento de stream dispara Lambda
3. Lambda extrae el ID de UVA y el ID de RACIMO
4. Lambda consulta la tabla RACIMO para obtener el LinkageCode
5. Lambda escanea la tabla Organization para encontrar la organización correspondiente
6. Lambda llama a la mutación createDevice de AppSync
7. El dispositivo queda registrado en MakeSensCloud

**Pasos (MODIFY - Actualización de Ubicación)**:
1. El registro UVA se actualiza con latitud/longitud
2. El evento de stream dispara Lambda
3. Lambda extrae los datos de ubicación
4. Lambda consulta la tabla Location en busca de un registro existente
5. Si existe: llama a la mutación updateLocation
6. Si no existe: llama a la mutación createLocation

### Flujo 3: Verificación del Estado de Conexión

```
Solicitud del Cliente → API Gateway → UVALastConnection Lambda
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │ AppSync GraphQL      │
                              │ Consulta:            │
                              │ measurementsByUvaID  │
                              │ (limit: 1, desc)     │
                              └─────────┬────────────┘
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │ Verificar timestamp: │
                              │ < 24 horas?          │
                              │ Sí → connected=true  │
                              │ No → connected=false │
                              └─────────┬────────────┘
                                        │
                                        ▼
                              Devolver Respuesta JSON
```

**Formato de Respuesta**:
```json
{
  "uva_123": {
    "connection": true,
    "ts": 1699458000000
  }
}
```

### Flujo 4: Creación de RACIMO

```
POST /CreateRacimo → API Gateway → CreateRacimo Lambda
  {name, linkageCode}               │
                                    ▼
                          ┌──────────────────────┐
                          │ Consultar AppSync:   │
                          │ listRACIMOS          │
                          │ filtrar: linkageCode │
                          └──────────┬───────────┘
                                     │
                           ┌─────────┴─────────┐
                           │                   │
                    Existe │                   │ No Existe
                           ▼                   ▼
                  Devolver datos      ┌──────────────────┐
                  del RACIMO          │ Crear RACIMO:    │
                  existente           │ - name           │
                                     │ - linkageCode    │
                                     │ - configPath     │
                                     └────────┬─────────┘
                                              │
                                              ▼
                                     Devolver nuevo RACIMO ID
```

## Integraciones Externas

### 1. API AppSync de MakeSensCloud

**Endpoint**: Endpoint GraphQL específico por entorno
**Autenticación**: API Key
**Utilizado por**: UvaToCloudFunction

**Operaciones**:
- `createDevice(organizationID, name, ...)`
- `createLocation(id, latitude, longitude, ...)`
- `updateLocation(id, latitude, longitude, ...)`

**Propósito**: Gestión centralizada de dispositivos y ubicaciones en la plataforma MakeSens

### 2. API AppSync del Servicio UVA

**Endpoint**: Endpoint GraphQL específico por entorno
**Autenticación**: API Key (consultas), SigV4 (mutaciones)
**Utilizado por**: UVALastConnection, CreateRacimo

**Operaciones**:
- `measurementsByUvaIDAndTs()`: Consulta las últimas mediciones
- `getUVA()`: Obtiene detalles del dispositivo UVA
- `listRACIMOS()`: Consulta RACIMOs por código de vinculación
- `createRACIMO()`: Crea un nuevo clúster de dispositivos

**Propósito**: Acceso a datos específicos de UVA y gestión de dispositivos

## Arquitectura de Seguridad

### Autenticación y Autorización

**Roles de Ejecución de Lambda**:
- Permisos de lectura del DynamoDB Stream (ARNs de stream específicos)
- Permisos de publicación en SNS (ARNs de topic específicos)
- Acceso a tablas DynamoDB (GetItem, Scan en tablas específicas)
- Acceso a la API AppSync (operaciones GraphQL)

**API Gateway**:
- Autorización: AWS_IAM
- Requiere solicitudes firmadas con credenciales AWS
- Previene el acceso no autorizado a los endpoints

**APIs AppSync**:
- **API Key**: Utilizada para la mayoría de las operaciones (desarrollo/pruebas)
- **AWS SigV4**: Utilizada por CreateRacimo para autenticación de nivel productivo
- Las API keys se rotan por entorno

### Seguridad de Red

**VPC**: No utilizada (ejecución pública de Lambda)
**Cifrado**:
- DynamoDB: Cifrado en reposo del lado del servidor
- Datos en tránsito: HTTPS/TLS para todas las llamadas API

## Separación de Entornos

El sistema soporta tres entornos aislados:

| Entorno | Rama     | Propósito                          |
|---------|----------|------------------------------------|
| develop | develop  | Desarrollo activo                  |
| test    | test     | Pruebas de pre-producción          |
| main    | main     | Producción                         |

**Estrategia de Aislamiento**:
- Tablas DynamoDB separadas por entorno
- Endpoints AppSync separados por entorno
- Topics SNS separados por entorno
- API keys específicas por entorno
- Configuraciones de parámetros distintas en `parameters.json`

## Consideraciones de Escalabilidad

**Lambda**:
- Escala automáticamente según el volumen de eventos
- Concurrencia máxima: Límites de cuenta AWS (por defecto 1000)
- Procesamiento en lotes del stream: 10 registros por invocación

**DynamoDB**:
- Facturación bajo demanda o capacidad provisionada
- Streams: Escala automáticamente con el throughput de la tabla

**SNS**:
- Distribución de mensajes altamente escalable
- Soporta millones de mensajes por segundo

## Monitoreo y Observabilidad

**Logs de CloudWatch**:
- Logs de funciones Lambda (automático)
- Retención de logs: Configurable vía CloudFormation

**Métricas de CloudWatch**:
- Invocaciones, errores y duración de Lambda
- Antigüedad del iterador del DynamoDB Stream
- Métricas de entrega de mensajes SNS

**Trazabilidad**: No implementada actualmente (considerar AWS X-Ray para trazabilidad distribuida)

## Arquitectura de Despliegue

**Pipeline CI/CD**:
```
GitHub Push → GitHub Actions → AWS SAM Deploy → Actualización del Stack CloudFormation
    │
    ├─ rama test   → Despliegue en entorno test
    └─ rama main   → Despliegue en producción
```

**Proceso de Despliegue**:
1. Código publicado en la rama de GitHub
2. Se dispara el flujo de trabajo de GitHub Actions
3. SAM CLI compila los paquetes Lambda
4. CloudFormation valida la plantilla
5. Se despliega el stack con parámetros específicos del entorno
6. Las funciones Lambda se actualizan con el nuevo código
7. Se configuran los endpoints de API Gateway
8. Se crean los mapeos de eventos del DynamoDB Stream

**Estrategia de Rollback**: Rollback automático de CloudFormation en caso de fallo en el despliegue
