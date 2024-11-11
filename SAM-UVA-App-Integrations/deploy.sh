#!/bin/bash

# Detecta la rama activa
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Determina el entorno basado en la rama
if [ "$BRANCH" == "develop" ]; then
    ENVIRONMENT="default"  # Usa configuración [default.deploy.parameters] para develop
elif [ "$BRANCH" == "test" ]; then
    ENVIRONMENT="test"  # Usa configuración [test.deploy.parameters] para test
else
    echo "Branch no reconocida para despliegue automatizado: $BRANCH"
    exit 1
fi

# Ejecuta el despliegue usando el entorno detectado
sam validate
sam build
sam deploy --config-env "$ENVIRONMENT" --no-confirm-changeset
