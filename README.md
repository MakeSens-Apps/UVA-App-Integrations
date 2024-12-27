# UVA-App-Integrations
Este repositorio contiene la integración de UVA-App con otros servicios de MakeSens, diseñada para gestionar datos, realizar procesos de sincronización y conectar servicios mediante AWS Lambda y AWS SAM. Incluye funciones específicas para flujos de trabajo relacionados con UVA-App y su integración con otros sistemas.

## El proyecto está organizado de la siguiente manera:
El proyecto está organizado de la siguiente manera:

- **.github/**
  - **workflows/**
    - `DeployMain.yml`  - Pipeline para despliegues en el entorno `main`
    - `DeployTest.yml`  - Pipeline para despliegues en el entorno `test`

- **SAM-UVA-App-Integrations/**
  - **lambdas/**  - Directorio con funciones Lambda organizadas por servicio
    - **cloud/** - Conectar UVA con MakeSensCloud
      - `__init__.py`
      - `requirements.txt`
      - `uva_to_cloud.py`
    - **createRacimo/** - Crear un nuevo RACIMO
      - `__init__.py`
      - `requirements.txt`
      - `create_racimo.py`
    - **deviceDataAccess/** - Conectar UVA con DeviceDataAccess
      - `__init__.py`
      - `requirements.txt`
      - `dynamodb_to_sns.py`
    - **uvaConnection/** - Conectar UVA con Connection
      - `__init__.py`
      - `requirements.txt`  - Dependencias necesarias para la función `last_connection`
      - `last_connection.py`  - Registra la última conexión de UVA

  - `deploy.sh`  - Script de despliegue automatizado
  - `parameters.json`  - Configuración de parámetros según el entorno
  - `template.yaml`  - Plantilla SAM para definir la infraestructura

- `LICENSE.txt`  - Licencia del proyecto
- `README.md`  - Documentación del repositorio

