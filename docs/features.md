# Funcionalidades

## Descripción General

UVA-App-Integrations provee cuatro funcionalidades principales para gestionar datos de dispositivos IoT y sincronización en el ecosistema MakeSens. Cada funcionalidad está implementada como una función serverless independiente que responde a eventos o solicitudes API específicas.

---

## Funcionalidad 1: Procesamiento de Datos de Dispositivos en Tiempo Real

### Descripción
Procesa y distribuye automáticamente datos de mediciones de dispositivos UVA a consumidores downstream en tiempo real mediante una arquitectura de streaming.

### Valor de Negocio
- Habilita el monitoreo en tiempo real de los datos vitales de los dispositivos
- Desacopla los productores de datos de los consumidores mediante el patrón publicar-suscribir
- Garantiza que los datos de mediciones lleguen inmediatamente a los sistemas de analítica y alertas
- Transforma el formato de datos para compatibilidad multiplataforma

### Casos de Uso

#### CU1.1: Transmitir Medición de Temperatura
**Actor**: Dispositivo UVA
**Disparador**: El dispositivo escribe una lectura de temperatura en la tabla Measurement
**Flujo**:
1. El dispositivo inserta un registro de medición con datos de temperatura
2. DynamoDB Stream captura el evento INSERT
3. Lambda procesa y transforma el formato de datos
4. Lambda publica el mensaje en el topic SNS
5. Los dashboards de monitoreo reciben la actualización en segundos

**Resultado**: Temperatura en tiempo real visible en el dashboard

#### CU1.2: Distribuir Datos de Múltiples Sensores
**Actor**: Múltiples dispositivos UVA
**Disparador**: Lote de mediciones de diferentes sensores
**Flujo**:
1. Múltiples dispositivos insertan mediciones (lote de 10)
2. Lambda recibe los eventos del stream en lote
3. Lambda procesa cada medición de forma independiente
4. Lambda publica todas en SNS en secuencia
5. Múltiples suscriptores reciben los datos (analítica, alertas, almacenamiento)

**Resultado**: Todos los consumidores reciben el conjunto completo de datos

### Flujo de Trabajo

```
┌───────────────┐
│ Dispositivo   │
│ UVA Escribe   │
└───────┬───────┘
        │
        ▼
┌───────────────────┐
│ Tabla Measurement │
│ Evento INSERT     │
└───────┬───────────┘
        │
        ▼
┌─────────────────────────┐
│ Procesamiento Stream    │
│ - Filtrar solo INSERT   │
│ - Remover tipos DynamoDB│
│ - Convertir timestamps  │
└───────┬─────────────────┘
        │
        ▼
┌───────────────────┐
│ Publicación SNS   │
│ Atributos:        │
│ - typeDevice=UVA  │
│ - typeData=RAW    │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Suscriptores      │
│ Downstream        │
└───────────────────┘
```

### Transformaciones de Datos

**Entrada (Formato DynamoDB)**:
```json
{
  "id": {"S": "uva123"},
  "type": {"S": "temperature"},
  "ts": {"S": "2024-01-15T10:30:00Z"},
  "data": {"M": {
    "value": {"N": "36.5"},
    "unit": {"S": "celsius"}
  }}
}
```

**Salida (Mensaje SNS)**:
```json
{
  "id": "uva123",
  "type": "temperature",
  "ts": 1705318200000,
  "data": {
    "value": 36.5,
    "unit": "celsius"
  }
}
```

### Configuración
- **Tamaño de Lote**: 10 registros por invocación de Lambda
- **Ventana de Agrupamiento**: Espera máxima de 10 segundos
- **Atributos del Mensaje**: `typeDevice=UVA`, `typeData=RAW`

---

## Funcionalidad 2: Sincronización de Dispositivos con MakeSensCloud

### Descripción
Crea y actualiza automáticamente registros de dispositivos en MakeSensCloud cuando los dispositivos UVA son registrados o modificados, garantizando que el inventario centralizado de dispositivos esté siempre sincronizado.

### Valor de Negocio
- Mantiene una única fuente de verdad para el inventario de dispositivos
- Elimina el registro manual de dispositivos en la nube
- Propaga automáticamente la jerarquía organizacional (RACIMO → Organization → Device)
- Mantiene los datos de ubicación sincronizados para mapas y geofencing

### Casos de Uso

#### CU2.1: Registrar Nuevo Dispositivo en la Nube
**Actor**: Administrador del Sistema
**Disparador**: Nuevo UVA creado en la base de datos
**Flujo**:
1. El administrador crea un nuevo registro UVA con asociación a RACIMO
2. DynamoDB Stream dispara UvaToCloudFunction
3. Lambda consulta la tabla RACIMO para obtener el LinkageCode
4. Lambda escanea la tabla Organization para encontrar la organización correspondiente
5. Lambda llama a la mutación GraphQL createDevice
6. El dispositivo aparece en la organización de MakeSensCloud

**Resultado**: Dispositivo registrado automáticamente en la nube sin intervención manual

#### CU2.2: Actualizar Ubicación del Dispositivo
**Actor**: Dispositivo UVA o Administrador
**Disparador**: Registro UVA actualizado con coordenadas GPS
**Flujo**:
1. Registro UVA modificado con latitud/longitud
2. DynamoDB Stream dispara UvaToCloudFunction (evento MODIFY)
3. Lambda extrae los datos de ubicación
4. Lambda verifica la tabla Location en busca de un registro existente
5. Si existe: Lambda llama a la mutación updateLocation
6. Si no existe: Lambda llama a la mutación createLocation
7. La ubicación del dispositivo se actualiza en la nube

**Resultado**: Ubicación del dispositivo visible en la interfaz de mapa de la nube

#### CU2.3: Manejar Datos de Ubicación Incompletos
**Actor**: Sistema
**Disparador**: UVA actualizado con datos de ubicación parciales
**Flujo**:
1. Registro UVA actualizado solo con latitud (falta longitud)
2. Lambda valida la completitud de la ubicación
3. Lambda omite la sincronización de ubicación (se requieren ambas coordenadas)
4. Lambda registra una advertencia de datos incompletos

**Resultado**: El sistema previene registros de ubicación inválidos

### Flujo de Trabajo

```
┌─────────────────┐
│ Tabla UVA       │
│ INSERT/MODIFY   │
└────────┬────────┘
         │
         ▼
    ┌────────┐
    │ Tipo   │
    │ Evento?│
    └───┬────┘
        │
    ┌───┴────────────────┐
    │                    │
INSERT│                  │MODIFY
    ▼                    ▼
┌───────────┐      ┌─────────────┐
│ Sync de   │      │ Sync de     │
│ Dispositivo│     │ Ubicación   │
│           │      │             │
│ 1. Obtener│      │ 1. Extraer  │
│ RACIMO    │      │    lat/lng  │
│           │      │             │
│ 2. Obtener│      │ 2. Consultar│
│ Org       │      │    tabla    │
│           │      │    Location │
│ 3. Crear  │      │             │
│ Dispositivo│     │ 3. Crear/   │
│           │      │    Actualizar│
└───────────┘      └─────────────┘
```

### Puntos de Integración

**Tabla RACIMO**:
- Propósito: Recuperar LinkageCode para coincidir con la organización
- Consulta: `GetItem` por RACIMO ID del registro UVA

**Tabla Organization**:
- Propósito: Encontrar la organización por código de vinculación
- Consulta: `Scan` con expresión de filtro `linkage_code = {code}`

**AppSync de MakeSensCloud**:
- `createDevice`: Crea el dispositivo bajo la organización
- `createLocation`: Agrega coordenadas geográficas
- `updateLocation`: Actualiza coordenadas existentes

### Manejo de Errores
- RACIMO no encontrado: Registra el error, omite la creación del dispositivo
- Organización no encontrada: Registra el error, omite la creación del dispositivo
- Error de la API GraphQL: Lambda falla, DynamoDB Stream reintenta
- Datos de ubicación inválidos: Omite la sincronización de ubicación, continúa procesando

---

## Funcionalidad 3: Monitoreo del Estado de Conexión

### Descripción
Provee un endpoint REST API para verificar si los dispositivos UVA están activamente conectados (con medición en las últimas 24 horas) junto con el timestamp de la última actividad.

### Valor de Negocio
- Habilita alertas proactivas de mantenimiento para dispositivos desconectados
- Soporta el monitoreo de SLA para el tiempo de actividad de los dispositivos
- Provee datos para dashboards de salud de dispositivos
- Permite verificaciones de estado masivas para la gestión de flota

### Casos de Uso

#### CU3.1: Verificar Estado de un Solo Dispositivo
**Actor**: Sistema de Monitoreo
**Disparador**: Verificación periódica de salud (cada 5 minutos)
**Flujo**:
1. El sistema envía una solicitud GET a `/{uva_id}/connection`
2. Lambda consulta AppSync por la última medición
3. Lambda compara el timestamp de la medición con la hora actual
4. Si < 24 horas: devuelve `connection: true`
5. Si > 24 horas: devuelve `connection: false`
6. El sistema de monitoreo registra el estado

**Solicitud**:
```
GET /uva123/connection
Authorization: AWS4-HMAC-SHA256 ...
```

**Respuesta**:
```json
{
  "uva123": {
    "connection": true,
    "ts": 1705318200000
  }
}
```

#### CU3.2: Verificación Masiva de Estado
**Actor**: Aplicación Dashboard
**Disparador**: El usuario ve la página de estado de la flota
**Flujo**:
1. El dashboard envía una solicitud GET con múltiples IDs: `?ids=uva1,uva2,uva3`
2. Lambda analiza la lista separada por comas
3. Lambda consulta AppSync por cada UVA
4. Lambda devuelve un objeto de estado con todos los dispositivos
5. El dashboard muestra el estado con código de color (verde/rojo)

**Solicitud**:
```
GET /all/connection?ids=uva123,uva456,uva789
```

**Respuesta**:
```json
{
  "uva123": {"connection": true, "ts": 1705318200000},
  "uva456": {"connection": false, "ts": 1705145000000},
  "uva789": {"connection": true, "ts": 1705318100000}
}
```

#### CU3.3: Fallback a la Fecha de Creación
**Actor**: Sistema de Monitoreo
**Disparador**: El dispositivo aún no tiene mediciones
**Flujo**:
1. El sistema verifica la conexión de un dispositivo recién provisionado
2. Lambda consulta mediciones (devuelve vacío)
3. Lambda recurre a la fecha de creación del UVA
4. Devuelve el timestamp de creación como última actividad
5. El sistema marca como "nuevo dispositivo" según su antigüedad

**Resultado**: Los nuevos dispositivos muestran estado basado en el tiempo de registro

### Flujo de Trabajo

```
Solicitud API
    │
    ▼
┌──────────────┐
│ Analizar Ruta│
│ ¿Simple o    │
│ Múltiple?    │
└──────┬───────┘
       │
   ┌───┴─────────┐
   │             │
Simple         Múltiple
   │             │
   ▼             ▼
┌────────┐   ┌────────────┐
│Consultar│  │ Iterar     │
│AppSync  │  │ cada ID,   │
└───┬────┘  └─────┬──────┘
    │              │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ ¿Mediciones  │
    │ Encontradas? │
    └──────┬───────┘
           │
      ┌────┴────┐
      │         │
     Sí         No
      │         │
      ▼         ▼
   ┌────┐   ┌────────┐
   │ Usar│  │Fallback│
   │ ts  │  │ fecha  │
   │     │  │creación│
   └─┬──┘   └────┬────┘
     │           │
     └─────┬─────┘
           ▼
    ┌──────────────┐
    │ ¿< 24 horas? │
    └──────┬───────┘
           │
           ▼
    Devolver Respuesta
```

### Consulta GraphQL

```graphql
query GetLastMeasurement($uvaID: ID!) {
  measurementsByUvaIDAndTs(
    uvaID: $uvaID
    sortDirection: DESC
    limit: 1
  ) {
    items {
      ts
    }
  }
}
```

### Lógica de Conexión

```python
def is_within_last_24_hours(timestamp_ms):
    current_time = time.time() * 1000
    time_difference = current_time - timestamp_ms
    return time_difference <= 86400000  # 24 horas en milisegundos
```

### Autenticación
- **Método**: AWS_IAM
- **Requisitos**: Solicitud firmada con credenciales AWS válidas
- **Permisos**: El rol de ejecución de API Gateway debe permitir la invocación

---

## Funcionalidad 4: Gestión de Clústeres RACIMO

### Descripción
Provee un endpoint REST API para crear nuevos registros de RACIMO (clúster de dispositivos) con códigos de vinculación, previniendo duplicados y estableciendo rutas de configuración.

### Valor de Negocio
- Simplifica la creación de clústeres a través de la API en lugar del acceso directo a la base de datos
- Previene RACIMOs duplicados con el mismo código de vinculación
- Establece una convención estándar para la ruta de configuración
- Soporta la jerarquía organizacional para despliegues multi-tenant

### Casos de Uso

#### CU4.1: Crear Nuevo RACIMO
**Actor**: Administrador o Sistema de Provisionamiento
**Disparador**: Alta de nuevo cliente/sitio
**Flujo**:
1. El sistema envía una solicitud POST con el nombre del clúster y el código de vinculación
2. Lambda consulta AppSync para verificar si el RACIMO existe
3. No se encuentra un RACIMO existente
4. Lambda crea el RACIMO con la ruta de configuración
5. Lambda devuelve el nuevo RACIMO ID
6. El sistema almacena el ID para la asociación de dispositivos

**Solicitud**:
```json
POST /CreateRacimo
Content-Type: application/json
Authorization: AWS4-HMAC-SHA256 ...

{
  "name": "Hospital Floor 3",
  "linkageCode": "HF3-2024-001"
}
```

**Respuesta**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO created successfully",
    "racimo_id": "abc123-def456",
    "exists": false
  }
}
```

#### CU4.2: Prevenir RACIMO Duplicado
**Actor**: Sistema de Provisionamiento
**Disparador**: Intento accidental de creación duplicada
**Flujo**:
1. El sistema envía una solicitud POST con un código de vinculación existente
2. Lambda consulta AppSync por RACIMO con ese código de vinculación
3. Se encuentra un RACIMO existente
4. Lambda devuelve los datos del RACIMO existente sin crear un duplicado
5. El sistema usa el RACIMO ID existente

**Respuesta**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO already exists",
    "racimo_id": "existing123",
    "exists": true
  }
}
```

#### CU4.3: Manejo de Solicitudes Inválidas
**Actor**: Aplicación Cliente
**Disparador**: Cuerpo de solicitud mal formado
**Flujo**:
1. El cliente envía un POST sin los campos requeridos
2. Lambda valida el cuerpo de la solicitud
3. Se detecta la ausencia de name o linkageCode
4. Lambda devuelve error 400
5. El cliente muestra el error de validación

**Respuesta**:
```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required fields: name and linkageCode"
  }
}
```

### Flujo de Trabajo

```
POST /CreateRacimo
{name, linkageCode}
       │
       ▼
┌──────────────┐
│ Validar      │
│ Cuerpo       │
│ Solicitud    │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Consultar AppSync│
│ listRACIMOS      │
│ filtrar por      │
│ linkageCode      │
└──────┬───────────┘
       │
   ┌───┴─────┐
   │         │
Existe    No Existe
   │         │
   ▼         ▼
┌─────┐  ┌────────────┐
│Devolver│ │ Crear     │
│datos  │ │ RACIMO:    │
│exist  │ │ - name     │
└─────┘  │ - linkage  │
         │ - config   │
         └──────┬─────┘
                │
                ▼
         ┌──────────────┐
         │ Devolver     │
         │ Nuevo ID     │
         └──────────────┘
```

### Operaciones GraphQL

**Verificar Existencia**:
```graphql
query CheckRACIMO($linkageCode: String!) {
  listRACIMOS(filter: {LinkageCode: {eq: $linkageCode}}) {
    items {
      id
      name
      LinkageCode
    }
  }
}
```

**Crear RACIMO**:
```graphql
mutation CreateRACIMO($input: CreateRACIMOInput!) {
  createRACIMO(input: $input) {
    id
    name
    LinkageCode
    path
  }
}
```

### Convención de Ruta de Configuración

**Formato**: `racimos/{linkageCode}/config.json`

**Ejemplo**: Para linkageCode `HF3-2024-001`, la ruta es:
```
racimos/HF3-2024-001/config.json
```

**Propósito**: Ubicación estandarizada en S3 o almacenamiento de configuración para los ajustes del clúster

### Autenticación

**Método**: AWS Signature Version 4 (SigV4)

**Implementación**:
```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Firmar solicitud con credenciales del rol de ejecución de Lambda
request = AWSRequest(method='POST', url=endpoint, data=body, headers=headers)
SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
```

**Ventajas**:
- No se requiere gestión de API keys
- Utiliza permisos del rol IAM
- Más adecuado para entornos de producción

### Escenarios de Error

| Escenario | Código de Estado | Respuesta |
|-----------|------------------|-----------|
| Campos faltantes | 400 | `{"error": "Missing required fields"}` |
| Error en consulta GraphQL | 500 | `{"error": "Failed to check RACIMO"}` |
| Error en creación GraphQL | 500 | `{"error": "Failed to create RACIMO"}` |
| Fallo de autenticación | 403 | Error estándar de API Gateway AWS |

---

## Funcionalidades Transversales

### Soporte Multi-Entorno

Todas las funcionalidades soportan aislamiento por entorno:
- **develop**: Desarrollo y pruebas
- **test**: Validación de pre-producción
- **main**: Producción

El entorno se determina por:
1. Nombre de la rama git durante el despliegue
2. Parámetros cargados desde `parameters.json`
3. ARNs de recursos específicos del entorno

### Registro de Errores

Todas las funcionalidades incluyen registro comprensivo:
- Datos de solicitud/evento (saneados)
- Pasos de procesamiento y decisiones tomadas
- Detalles de errores con trazas de pila
- Duración de la ejecución

Los logs son accesibles vía CloudWatch Logs: `/aws/lambda/{FunctionName}`

### Comportamiento de Reintento

**Funciones Disparadas por DynamoDB Stream**:
- Reintentos automáticos en caso de fallo
- Backoff exponencial
- Máximo de reintentos: 3
- Lotes fallidos enviados a DLQ (si está configurada)

**Funciones Disparadas por API Gateway**:
- Sin reintento automático
- El cliente es responsable de la lógica de reintento
- Operaciones idempotentes (la creación de RACIMO verifica existencia)

### Características de Rendimiento

| Funcionalidad | Latencia Promedio | Throughput Máximo | Cuello de Botella |
|---------------|-------------------|-------------------|-------------------|
| Procesamiento de Datos | < 500ms | 1000 eventos/seg | Shards de DynamoDB Stream |
| Sincronización de Dispositivos | 1-2s | 100 dispositivos/seg | Límites de tasa de la API GraphQL |
| Verificación de Conexión | 500-800ms | 50 req/seg | Rendimiento de consultas AppSync |
| Creación de RACIMO | 800ms-1.5s | 20 req/seg | Mutación + consulta GraphQL |
