# Migración a Arquitectura Hexagonal (FastAPI + Mangum)

Este documento describe la migración de `UVA-App-Integrations` de un layout
*una-Lambda-por-endpoint* a **arquitectura hexagonal** con **UNA sola Lambda HTTP**
(FastAPI + Mangum) sirviendo todos los endpoints HTTP, manteniendo las
integraciones NO-HTTP (DynamoDB Stream → Lambda) como Lambdas separadas que
comparten el mismo build.

Patrón replicado de: DeviceDataAccess (PR #23), ConnectionPrediction (PR #8),
UserAPI (PR #12).

## Restricción absoluta cumplida

**NO se tocó nada bajo `test/`.** Las pruebas pasan verdes sin modificación:

```
$ git diff --stat origin/develop -- test/
(vacío)
```

## Estructura objetivo (dentro de `SAM-UVA-App-Integrations/`)

```
src/
  adapters/inbound/events/                      # (placeholder) integraciones por stream/SQS
  adapters/inbound/http/
    app.py                                      # FastAPI app + @app.exception_handler(Exception) -> 502
    routes.py                                   # rutas FastAPI (literal antes que parametrizada)
    event_builder.py                            # seam request->evento proxy / resultado->HTTP
  adapters/outbound/persistence/dynamodb/       # (placeholder)
  adapters/outbound/appsync/                    # (placeholder)
  core/
    domain/ ports/inbound/ ports/outbound/      # (placeholders del patrón)
    use_cases/
      last_connection.py                        # LÓGICA REAL (verbatim) GET /{id_uva}/connection
      create_racimo.py                          # LÓGICA REAL (verbatim) POST /CreateRacimo
      dynamodb_to_sns.py                         # LÓGICA REAL (verbatim) NO-HTTP DeviceDataAccess
      uva_to_cloud.py                            # LÓGICA REAL (verbatim) NO-HTTP Cloud
  lambda_handlers/
    _bootstrap.py                                # alias-módulo `src` para CodeUri: src
    api_handler.py                               # handler = Mangum(app)  (única Lambda HTTP)
    event_ingestor_measurement_handler.py        # entrypoint NO-HTTP (Measurement stream -> SNS)
    event_ingestor_uva_handler.py                # entrypoint NO-HTTP (UVA stream -> Cloud AppSync)
  shared/
  requirements.txt                               # fastapi, mangum, requests, botocore
```

## Mapeo Lambda → Endpoint (antes → después)

| Antes (1 Lambda por endpoint)                     | Después                                                              |
|---------------------------------------------------|---------------------------------------------------------------------|
| `UVALastConnection` → `GET /{id_uva}/connection`  | **Única Lambda HTTP** (`UVALastConnection`, Mangum) ruta FastAPI     |
| `CreateRacimo` → `POST /CreateRacimo`             | **misma** única Lambda HTTP, ruta FastAPI                            |
| `DynamoDBEventProcessorFunction` (Measurement stream → SNS) | sigue separada; `event_ingestor_measurement_handler.handler` |
| `UvaToCloudFunction` (UVA stream → Cloud AppSync) | sigue separada; `event_ingestor_uva_handler.handler`                |

> El logical ID de la función HTTP se mantuvo como **`UVALastConnection`** a
> propósito: el harness e2e (`test/e2e/conftest.py`) escribe el archivo
> `--env-vars` con la clave `UVALastConnection`, y `sam local` aplica variables de
> entorno por logical ID. Conservar ese nombre preserva el mapeo de
> `AppSyncURL` / `ApiKey` sin tocar las pruebas.

## Shims legacy (compatibilidad con integration tests)

Los integration tests importan los handlers por ruta
(`sys.path.insert(...)` + `from <Modulo> import <func>`) y parchean
`<Modulo>.requests.post` por referencia. Por eso cada handler legacy se conserva
**en su ruta / nombre / firma exactos** como un **shim delgado** que:

1. Hace bootstrap de `sys.path` hacia la raíz SAM para que `src` sea importable.
2. Mantiene `import requests` / `import boto3` a nivel de módulo (el objeto
   `requests` es el mismo singleton que usa el use case, así el `patch.object`
   por referencia surte efecto en ambos).
3. Re-exporta `lambda_handler` (y helpers) desde el use case.

Ejemplo (`lambdas/uvaConnection/last_connection.py`):

```python
import os, sys
_SAM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _SAM_ROOT not in sys.path:
    sys.path.insert(0, _SAM_ROOT)

import requests  # noqa  -- patcheado por referencia en los tests
import boto3      # noqa

from src.core.use_cases.last_connection import (
    lambda_handler, get_connection_status, is_within_last_24_hours,
    get_last_connection, get_creation_date,
)
```

La **lógica real se movió verbatim** (sin "mejorar" errores): se conservan las
mismas ramas de excepción (`KeyError`, `AttributeError`, `TypeError`,
`json.JSONDecodeError`, `Exception` con el mensaje exacto) que los tests asertan.

## GOTCHA 1 — alias `src` con `CodeUri: src`

Con `CodeUri: src`, el contenido de `src/` aterriza en la raíz de la tarea Lambda
y `from src.x import` falla con `No module named 'src'`. `lambda_handlers/_bootstrap.py`
registra un alias-módulo `src` cuyo `__path__` es la raíz de la tarea, y se importa
**primero** en cada entrypoint (`api_handler`, `event_ingestor_*`).

## GOTCHA 2 — exception handler (paridad API Gateway)

Los e2e de ESTE repo asertan **HTTP 502** en fallos de backend (p. ej. el bug
conocido: AppSync `getUVA` devuelve `null` → `None.get('createdAt')` →
`AttributeError`). Se añadió en `src/adapters/inbound/http/app.py`:

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    return JSONResponse(status_code=502, content={"message": "Internal server error"})
```

- **Status:** `502`
- **Forma:** `{"message": "Internal server error"}`

Las respuestas 200 de los use cases y los 4xx/404 del router FastAPI (método/ruta
no encontrados) se devuelven normalmente y no se ven afectados.

## Rutas FastAPI

```
POST /CreateRacimo              # literal, declarada primero
GET  /{id_uva}/connection       # parametrizada con sufijo literal /connection
```

El seam `event_builder.build_event` construye un evento proxy estilo API Gateway
(`pathParameters`, `queryStringParameters` con `None` si vacío, `httpMethod`,
`body`) y `to_response` traduce `{"statusCode","body","headers"?}` a `JSONResponse`
conservando status, body (JSON parseado) y headers (p. ej. `Content-Type`). Las
excepciones se dejan propagar al exception handler.

## `template.yaml`

- UNA función HTTP (`UVALastConnection`) con **ambos** eventos `Type: Api`
  (`/{id_uva}/connection` GET y `/CreateRacimo` POST), `Handler:
  lambda_handlers.api_handler.handler`, `CodeUri: src`.
- Dos funciones NO-HTTP separadas conservando sus logical IDs y triggers de
  DynamoDB Stream, `CodeUri: src`, con los nuevos handlers `event_ingestor_*`.
- `runtime: python3.9`. `sam validate --lint` → válido.
- Efecto colateral positivo: al compartir todas las funciones el mismo
  `CodeUri: src`, desaparece el bug de `sam build` (`ConvertError NoneType` al
  escribir `build.toml` con CodeUri compartido y Environment desigual).

## Evidencia de validación local

- **Integration:** `python3 -m pytest test/integration -v` → **40 passed**.
- **E2E local:** `make test-e2e-local` (sam local start-api :3031, Lambda en
  Docker contra el AppSync `main` real) → **16 passed** (incluye casos verdes con
  ids UVA reales y casos rojos 502 de paridad de backend).
- `sam validate --lint` → *valid SAM Template*.
- `git diff --stat origin/develop -- test/` → **vacío** (pruebas byte-idénticas).

## Notas de seguridad

`SAM-UVA-App-Integrations/event/env.json` está gitignored (puede contener claves
de AppSync); se genera en tiempo de test desde `parameters.json`. No se commitea
`.aws-sam/`. Los workflows de deploy existentes (`DeployMain.yml`, `DeployTest.yml`)
no se modificaron.
