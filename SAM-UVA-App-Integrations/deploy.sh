#!/bin/bash

# Detecta la rama activa
ENVIRONMENT=$(git rev-parse --abbrev-ref HEAD)

# Cargar parámetros del entorno desde el archivo JSON
STACK_NAME=$(jq -r ".${ENVIRONMENT}.stack_name" parameters.json)
REGION=$(jq -r ".${ENVIRONMENT}.region" parameters.json)
CONFIRM_CHANGESET=$(jq -r ".${ENVIRONMENT}.confirm_changeset" parameters.json)
CAPABILITIES=$(jq -r ".${ENVIRONMENT}.capabilities" parameters.json)
DISABLE_ROLLBACK=$(jq -r ".${ENVIRONMENT}.disable_rollback" parameters.json)
PARAM_OVERRIDES=$(jq -r ".${ENVIRONMENT}.parameter_overrides" parameters.json)


PARAM_OVERRIDES=$(jq -r "to_entries | map(\"\(.key)=\(.value|tostring)\") | join(\" \")" <<< "$(jq -c .${ENVIRONMENT}.parameter_overrides parameters.json)")

# Ejecuta el despliegue usando SAM y parámetros cargados desde el archivo JSON
sam validate
sam build

sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --confirm-changeset "$CONFIRM_CHANGESET" \
    --capabilities "$CAPABILITIES" \
    --disable-rollback "$DISABLE_ROLLBACK" \
    --parameter-overrides $PARAM_OVERRIDES \
    --resolve-s3 \
    --no-confirm-changeset

echo "Despliegue completado en el entorno '$ENVIRONMENT'."