# Documentación Técnica — UVA-App-Integrations

> **Tipo:** Servicio ETL/IoT Serverless
> **Stack:** AWS SAM + DynamoDB Streams + SNS + Lambda + AppSync
> **Región:** us-east-1

---

## Descripción del Servicio

UVA-App-Integrations es el backend serverless que conecta el ecosistema de dispositivos IoT **UVA (Universal Vitals Application)** con los servicios cloud de MakeSens. Provee la capa de integración para:

- Procesar y distribuir datos de mediciones en tiempo real desde DynamoDB a SNS
- Sincronizar dispositivos UVA con MakeSensCloud para gestión centralizada
- Monitorear el estado de conexión de los dispositivos
- Gestionar la jerarquía organizacional mediante clústeres RACIMO

---

## Índice de Documentación

### Arquitectura
- **[architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md)** — Diseño del sistema, diagrama de arquitectura, recursos AWS, mecanismos de sincronización y seguridad
- **[architecture/MODULES.md](architecture/MODULES.md)** — Especificación detallada de cada función Lambda: disparadores, inputs, lógica de procesamiento, outputs y variables de entorno

### API y Eventos
- **[api/ENDPOINTS.md](api/ENDPOINTS.md)** — Endpoints REST (API Gateway), eventos de entrada (DynamoDB Streams) y operaciones GraphQL externas

### Datos
- **[data/MODELS.md](data/MODELS.md)** — Modelos de las cinco tablas DynamoDB: esquemas, relaciones, streams habilitados y patrones de acceso
- **[data/FLOW.md](data/FLOW.md)** — Flujos de datos extremo a extremo: medición→SNS, sincronización de dispositivos, actualización de ubicación, estado de conexión y creación de RACIMO

### Configuración
- **[configuration/ENVIRONMENT.md](configuration/ENVIRONMENT.md)** — Variables de entorno por Lambda, parámetros SAM, configuración por entorno (develop/test/main), políticas IAM

### Despliegue
- **[deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md)** — Prerequisitos, build, deploy automatizado y manual, CI/CD con GitHub Actions, verificación post-deploy, rollback y resolución de problemas

### Operación
- **[operation/FLOW.md](operation/FLOW.md)** — Ciclo operacional, timing, manejo de errores, limitaciones conocidas, posibles mejoras, mantenimiento y comandos de diagnóstico

---

## Acceso Rápido

### Desplegar el servicio
```bash
cd SAM-UVA-App-Integrations
sam build
./deploy.sh
```
Ver guía completa: [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md)

### Ver logs en producción
```bash
sam logs -n DynamoDBEventProcessorFunction --stack-name SAM-UVA-App-Integrations-main --tail
```

### Verificar estado de conexión de un dispositivo
```bash
GET https://{api-id}.execute-api.us-east-1.amazonaws.com/prod/{uva_id}/connection
Authorization: AWS4-HMAC-SHA256 ...
```
Ver referencia completa: [api/ENDPOINTS.md](api/ENDPOINTS.md)

---

## Estructura de Tablas DynamoDB

| Tabla | Stream | Consumidor Lambda |
|-------|--------|-------------------|
| `Measurement-{AppId}-{env}` | NEW_IMAGE | DynamoDBEventProcessorFunction |
| `UVA-{AppId}-{env}` | NEW_AND_OLD_IMAGES | UvaToCloudFunction |
| `RACIMO-{AppId}-{env}` | No | (lectura por UvaToCloudFunction) |
| `Organization-{AppId}-{env}` | No | (lectura por UvaToCloudFunction) |
| `Location-{AppId}-{env}` | No | (lectura/escritura por UvaToCloudFunction) |

---

## Entornos

| Entorno | Rama | Stack Name |
|---------|------|------------|
| develop | develop | `SAM-UVA-App-Integrations-develop` |
| test | test | `SAM-UVA-App-Integrations-test` |
| main | main | `SAM-UVA-App-Integrations-main` |
