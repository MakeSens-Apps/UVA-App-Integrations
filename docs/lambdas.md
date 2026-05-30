# Lambda Functions

This document provides detailed specifications for each Lambda function in the UVA-App-Integrations service.

---

## Function 1: DynamoDBEventProcessorFunction

### Overview
**Name**: DynamoDBEventProcessorFunction
**Purpose**: Process measurement data from DynamoDB Streams and publish to SNS for real-time distribution
**Location**: `SAM-UVA-App-Integrations/lambdas/deviceDataAccess/dynamodb_to_sns.py`

### Trigger

**Type**: DynamoDB Stream
**Source**: Measurement table stream
**Configuration**:
```yaml
Stream ARN: arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
Batch Size: 10
Maximum Batching Window: 10 seconds
Starting Position: LATEST
Event Types: INSERT, MODIFY, REMOVE (filters INSERT only in code)
```

**Sample Event**:
```json
{
  "Records": [
    {
      "eventID": "1",
      "eventName": "INSERT",
      "eventSource": "aws:dynamodb",
      "dynamodb": {
        "NewImage": {
          "id": {"S": "uva123"},
          "type": {"S": "temperature"},
          "ts": {"S": "2024-01-15T10:30:00Z"},
          "data": {"M": {"value": {"N": "36.5"}}},
          "logs": {"L": []}
        }
      }
    }
  ]
}
```

### Expected Inputs

**DynamoDB Stream Record Fields**:
- `eventName`: Event type (INSERT, MODIFY, REMOVE)
- `dynamodb.NewImage`: Record data in DynamoDB format
  - `id` (String): UVA device identifier
  - `type` (String): Measurement type (temperature, pressure, etc.)
  - `ts` (String): ISO 8601 timestamp
  - `data` (Map): Measurement data object
  - `logs` (List): Optional log entries

**Data Type Formats** (DynamoDB native types):
- `S`: String
- `N`: Number (stored as string, needs parsing)
- `M`: Map (nested object)
- `L`: List (array)

### Processing Logic

**Function**: `lambda_handler(event, context)`
```python
def lambda_handler(event, context):
    """
    Main entry point for Lambda function

    Args:
        event: DynamoDB Stream event with Records array
        context: Lambda execution context

    Returns:
        dict: Status code and processing summary
    """
```

**Key Functions**:

1. **`process_data(records)`**
   - Filters records for INSERT events only
   - Extracts NewImage data from each record
   - Calls `remove_data_types()` to transform format
   - Returns list of processed records

2. **`remove_data_types(data)`**
   - Recursively converts DynamoDB format to Python native types
   - Handles String (S), Number (N), Map (M), List (L), Boolean (BOOL)
   - Preserves data structure while removing type annotations

   Example transformation:
   ```python
   # Input
   {"value": {"N": "36.5"}, "unit": {"S": "celsius"}}

   # Output
   {"value": 36.5, "unit": "celsius"}
   ```

3. **`send_message_to_topic_sns(data)`**
   - Converts ISO timestamp to Unix milliseconds
   - Publishes message to SNS topic
   - Adds message attributes: `typeDevice=UVA`, `typeData=RAW`

### Generated Outputs

**SNS Message Structure**:
```json
{
  "id": "uva123",
  "type": "temperature",
  "ts": 1705318200000,
  "data": {
    "value": 36.5,
    "unit": "celsius"
  },
  "logs": []
}
```

**SNS Message Attributes**:
```python
{
  "typeDevice": {"DataType": "String", "StringValue": "UVA"},
  "typeData": {"DataType": "String", "StringValue": "RAW"}
}
```

**CloudWatch Logs**:
- Processed record count
- SNS publish confirmation (MessageId)
- Error details if processing fails

### Required Environment Variables

```bash
TOPIC_SNS_ARN=arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-{env}
```

**Configured via**: SAM template `Ref: TopicSNSDataArn` parameter

### AWS Services Consumed

| Service | Operation | Purpose |
|---------|-----------|---------|
| DynamoDB Streams | GetRecords | Read stream events (automatic) |
| Amazon SNS | Publish | Send processed data to topic |
| CloudWatch Logs | PutLogEvents | Store execution logs |

### IAM Permissions Required

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
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:913045965320:log-group:/aws/lambda/*"
    }
  ]
}
```

### Dependencies

**Python Packages** (from `requirements.txt`):
```
boto3==1.34.29
```

**Standard Library**:
- `json`: JSON parsing
- `datetime`: Timestamp conversion
- `os`: Environment variable access

### Error Handling

- **Invalid record format**: Logs error, skips record, continues processing
- **SNS publish failure**: Raises exception, Lambda retries entire batch
- **Timestamp conversion error**: Logs warning, uses current timestamp

### Performance Characteristics

- **Cold Start**: ~2-3 seconds
- **Warm Execution**: ~200-500ms for 10 records
- **Memory Usage**: ~100-150 MB
- **Timeout**: 600 seconds (configured)

---

## Function 2: UvaToCloudFunction

### Overview
**Name**: UvaToCloudFunction
**Purpose**: Synchronize UVA device data with MakeSensCloud by creating devices and managing locations
**Location**: `SAM-UVA-App-Integrations/lambdas/cloud/uva_to_cloud.py`

### Trigger

**Type**: DynamoDB Stream
**Source**: UVA table stream
**Configuration**:
```yaml
Stream ARN: arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
Batch Size: 10
Maximum Batching Window: 10 seconds
Starting Position: LATEST
Event Types: INSERT, MODIFY
```

### Expected Inputs

**INSERT Event** (New UVA Created):
```json
{
  "eventName": "INSERT",
  "dynamodb": {
    "NewImage": {
      "id": {"S": "uva123"},
      "name": {"S": "Device Floor 3"},
      "racimoID": {"S": "racimo456"}
    }
  }
}
```

**MODIFY Event** (Location Updated):
```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "NewImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4194"}
    }
  }
}
```

### Processing Logic

**Function**: `lambda_handler(event, context)`

**Processing Flow**:
1. Iterate through stream records
2. Check event type (INSERT or MODIFY)
3. Route to appropriate handler

**INSERT Handler**: `process_insert_event(record)`
```python
def process_insert_event(record):
    """
    Creates device in MakeSensCloud

    Steps:
    1. Extract UVA ID and RACIMO ID from record
    2. Query RACIMO table for LinkageCode
    3. Scan Organization table for matching linkage_code
    4. Extract organizationID
    5. Call createDevice GraphQL mutation

    Returns: None (logs success/failure)
    """
```

**Database Queries**:
```python
# Get RACIMO LinkageCode
racimo = dynamodb.get_item(
    TableName=RACIMO_TABLE,
    Key={'id': racimo_id}
)
linkage_code = racimo['Item']['LinkageCode']

# Find Organization
organization = dynamodb.scan(
    TableName=ORGANIZATION_TABLE,
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': linkage_code}
)
org_id = organization['Items'][0]['id']
```

**GraphQL Mutation**:
```graphql
mutation CreateDevice {
  createDevice(
    organizationID: "org123"
    name: "Device Floor 3"
    description: "UVA Device"
    typeDevice: "UVA"
    metadata: "{}"
  ) {
    id
  }
}
```

**MODIFY Handler**: `process_modify_event(record)`
```python
def process_modify_event(record):
    """
    Updates or creates device location

    Steps:
    1. Extract latitude and longitude from record
    2. Validate both coordinates present
    3. Query Location table for existing record (id = A{uvaID})
    4. If exists: call updateLocation
    5. If not exists: call createLocation

    Returns: None (logs success/failure)
    """
```

**Location Validation**:
```python
if 'latitude' not in new_image or 'longitude' not in new_image:
    return  # Skip if incomplete
```

**Location Check**:
```python
location_id = f"A{uva_id}"
existing = dynamodb.get_item(
    TableName=LOCATION_TABLE,
    Key={'id': location_id}
)

if existing:
    update_location(location_id, lat, lng)
else:
    create_location(location_id, lat, lng)
```

### Generated Outputs

**Device Creation Response**:
```json
{
  "data": {
    "createDevice": {
      "id": "device789"
    }
  }
}
```

**Location Creation Response**:
```json
{
  "data": {
    "createLocation": {
      "id": "Auva123",
      "latitude": 37.7749,
      "longitude": -122.4194
    }
  }
}
```

**CloudWatch Logs**:
- Event type and UVA ID
- RACIMO and Organization lookup results
- GraphQL request and response
- Success/error messages

### Required Environment Variables

```bash
# AppSync Endpoint
APPSYNC_GRAPHQL_URL=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql

# API Authentication
APPSYNC_API_KEY=da2-xxxxxxxxxxxxxxxxxxxxx

# DynamoDB Tables
RACIMO_TABLE_NAME=RACIMO-{AppId}-{env}
ORGANIZATION_TABLE_NAME=Organization-{AppId}-{env}
LOCATION_TABLE_NAME=Location-{AppId}-{env}
```

**Configured via**: SAM template parameters and Refs

### AWS Services Consumed

| Service | Operation | Purpose |
|---------|-----------|---------|
| DynamoDB Streams | GetRecords | Read UVA table changes |
| DynamoDB | GetItem | Retrieve RACIMO details |
| DynamoDB | Scan | Find Organization by linkage code |
| DynamoDB | GetItem | Check if Location exists |
| AWS AppSync | GraphQL Mutation | Create/update devices and locations |
| CloudWatch Logs | PutLogEvents | Store execution logs |

### IAM Permissions Required

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

### Dependencies

**Python Packages**:
```
boto3==1.34.29
requests==2.31.0
```

### Error Handling

- **Missing RACIMO**: Logs error, skips device creation
- **Organization not found**: Logs error, skips device creation
- **Invalid location data**: Skips location sync, logs warning
- **GraphQL API error**: Logs full error response, Lambda fails (triggers retry)

### Performance Characteristics

- **Cold Start**: ~3-4 seconds
- **Warm Execution**: 1-2 seconds per device (due to DynamoDB queries + GraphQL calls)
- **Memory Usage**: ~150-200 MB
- **Network Latency**: ~500ms for AppSync calls

---

## Function 3: UVALastConnection

### Overview
**Name**: UVALastConnection
**Purpose**: REST API endpoint to check UVA device connection status
**Location**: `SAM-UVA-App-Integrations/lambdas/uvaConnection/last_connection.py`

### Trigger

**Type**: API Gateway REST API
**HTTP Method**: GET
**Path**: `/{id_uva}/connection`
**Authorization**: AWS_IAM

**Sample Requests**:
```bash
# Single device
GET /uva123/connection

# Multiple devices
GET /all/connection?ids=uva1,uva2,uva3
```

### Expected Inputs

**Path Parameters**:
- `id_uva` (String): UVA device ID or literal "all" for bulk query

**Query String Parameters** (when id_uva = "all"):
- `ids` (String): Comma-separated list of UVA IDs
  - Example: `?ids=uva123,uva456,uva789`

**Event Structure**:
```json
{
  "pathParameters": {
    "id_uva": "uva123"
  },
  "queryStringParameters": {
    "ids": "uva1,uva2"
  }
}
```

### Processing Logic

**Function**: `lambda_handler(event, context)`

**Routing Logic**:
```python
if id_uva == "all":
    # Bulk query mode
    ids = query_params.get('ids', '').split(',')
    return get_connection_status(ids)
else:
    # Single query mode
    return get_connection_status([id_uva])
```

**Connection Check**: `get_connection_status(uva_ids)`
```python
def get_connection_status(uva_ids):
    """
    For each UVA ID:
    1. Call get_last_connection(uva_id)
    2. Check if timestamp within last 24 hours
    3. Build response object

    Returns: {uva_id: {connection: bool, ts: int}}
    """
```

**Get Last Measurement**: `get_last_connection(uva_id)`
```python
def get_last_connection(uva_id):
    """
    Query AppSync for latest measurement

    GraphQL Query:
    measurementsByUvaIDAndTs(
      uvaID: $id
      sortDirection: DESC
      limit: 1
    )

    Fallback: If no measurements, query UVA creation date

    Returns: timestamp_ms (int)
    """
```

**GraphQL Query**:
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

**Fallback Query** (if no measurements):
```graphql
query GetUVA($id: ID!) {
  getUVA(id: $id) {
    createdAt
  }
}
```

**24-Hour Check**:
```python
def is_within_last_24_hours(ts_ms):
    current_ms = time.time() * 1000
    diff_ms = current_ms - ts_ms
    return diff_ms <= 86400000  # 24 hours
```

### Generated Outputs

**Single Device Response**:
```json
{
  "statusCode": 200,
  "body": {
    "uva123": {
      "connection": true,
      "ts": 1705318200000
    }
  }
}
```

**Multiple Devices Response**:
```json
{
  "statusCode": 200,
  "body": {
    "uva123": {"connection": true, "ts": 1705318200000},
    "uva456": {"connection": false, "ts": 1705145000000},
    "uva789": {"connection": true, "ts": 1705318100000}
  }
}
```

**Error Response**:
```json
{
  "statusCode": 500,
  "body": {
    "error": "Failed to query measurements"
  }
}
```

### Required Environment Variables

```bash
# AppSync Endpoint
APPSYNC_GRAPHQL_URL_USER=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql

# API Authentication
APPSYNC_API_KEY_USER=da2-xxxxxxxxxxxxxxxxxxxxx
```

### AWS Services Consumed

| Service | Operation | Purpose |
|---------|-----------|---------|
| API Gateway | Invoke | Receive HTTP requests |
| AWS AppSync | GraphQL Query | Get measurements and UVA details |
| CloudWatch Logs | PutLogEvents | Store execution logs |

### IAM Permissions Required

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["execute-api:Invoke"],
      "Resource": "arn:aws:execute-api:us-east-1:*:*/*/GET/{id_uva}/connection"
    }
  ]
}
```

Note: AppSync access controlled via API Key, not IAM

### Dependencies

**Python Packages**:
```
requests==2.31.0
```

**Standard Library**:
- `json`: Request/response parsing
- `time`: Timestamp calculations
- `os`: Environment variables

### Error Handling

- **Missing path parameter**: Returns 400 Bad Request
- **GraphQL query failure**: Returns 500 Internal Server Error
- **Invalid UVA ID**: Returns empty measurement, falls back to creation date
- **Network timeout**: Retries handled by requests library (default 3 attempts)

### Performance Characteristics

- **Cold Start**: ~2 seconds
- **Warm Execution**: 500-800ms per device
- **Bulk Query**: ~500ms + (100ms × number of devices)
- **Memory Usage**: ~100 MB

---

## Function 4: CreateRacimo

### Overview
**Name**: CreateRacimo
**Purpose**: REST API endpoint to create RACIMO (device cluster) with duplicate prevention
**Location**: `SAM-UVA-App-Integrations/lambdas/createRacimo/create_racimo.py`

### Trigger

**Type**: API Gateway REST API
**HTTP Method**: POST
**Path**: `/CreateRacimo`
**Authorization**: AWS_IAM

**Sample Request**:
```bash
POST /CreateRacimo
Content-Type: application/json
Authorization: AWS4-HMAC-SHA256 ...

{
  "name": "Hospital Floor 3",
  "linkageCode": "HF3-2024-001"
}
```

### Expected Inputs

**Request Body** (JSON):
```json
{
  "name": "string",       // Required: RACIMO display name
  "linkageCode": "string" // Required: Unique identifier for linkage
}
```

**Event Structure**:
```json
{
  "body": "{\"name\":\"Hospital Floor 3\",\"linkageCode\":\"HF3-2024-001\"}"
}
```

### Processing Logic

**Function**: `lambda_handler(event, context)`

**Workflow**:
1. Parse and validate request body
2. Check if RACIMO with linkageCode exists
3. If exists: return existing data
4. If not exists: create new RACIMO
5. Return result

**Validation**:
```python
body = json.loads(event.get('body', '{}'))
name = body.get('name')
linkage_code = body.get('linkageCode')

if not name or not linkage_code:
    return {
        'statusCode': 400,
        'body': {'error': 'Missing required fields'}
    }
```

**Existence Check**: `check_racimo_exists(linkage_code)`
```python
def check_racimo_exists(linkage_code):
    """
    Query AppSync for RACIMO with matching linkageCode

    GraphQL Query:
    listRACIMOS(filter: {LinkageCode: {eq: $code}})

    Returns: RACIMO object if exists, None otherwise
    """
```

**GraphQL Query**:
```graphql
query CheckRACIMO($linkageCode: String!) {
  listRACIMOS(filter: {LinkageCode: {eq: $linkageCode}}) {
    items {
      id
      name
      LinkageCode
      path
    }
  }
}
```

**Create RACIMO**: `create_racimo(name, linkage_code)`
```python
def create_racimo(name, linkage_code):
    """
    Create new RACIMO via AppSync

    GraphQL Mutation:
    createRACIMO(input: {
      name: $name
      LinkageCode: $linkageCode
      path: "racimos/{linkageCode}/config.json"
    })

    Returns: New RACIMO ID
    """
```

**GraphQL Mutation**:
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

**Input Object**:
```json
{
  "name": "Hospital Floor 3",
  "LinkageCode": "HF3-2024-001",
  "path": "racimos/HF3-2024-001/config.json"
}
```

**AWS SigV4 Signing**:
```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def sign_request(method, url, body, headers):
    """
    Sign request with AWS credentials from Lambda execution role

    Uses SigV4Auth with 'appsync' service and 'us-east-1' region
    """
    credentials = boto3.Session().get_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
    return dict(request.headers)
```

### Generated Outputs

**RACIMO Created**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO created successfully",
    "racimo_id": "abc123-def456-789ghi",
    "exists": false
  }
}
```

**RACIMO Already Exists**:
```json
{
  "statusCode": 200,
  "body": {
    "message": "RACIMO already exists",
    "racimo_id": "existing123-456def",
    "exists": true,
    "data": {
      "name": "Hospital Floor 3",
      "LinkageCode": "HF3-2024-001",
      "path": "racimos/HF3-2024-001/config.json"
    }
  }
}
```

**Validation Error**:
```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required fields: name and linkageCode"
  }
}
```

**Server Error**:
```json
{
  "statusCode": 500,
  "body": {
    "error": "Failed to create RACIMO",
    "details": "GraphQL error message"
  }
}
```

### Required Environment Variables

```bash
# AppSync Endpoint
APPSYNC_GRAPHQL_URL_USER=https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
```

Note: API Key not required - uses SigV4 signing instead

### AWS Services Consumed

| Service | Operation | Purpose |
|---------|-----------|---------|
| API Gateway | Invoke | Receive HTTP POST requests |
| AWS AppSync | GraphQL Query | Check RACIMO existence |
| AWS AppSync | GraphQL Mutation | Create new RACIMO |
| AWS STS | GetCallerIdentity | Retrieve credentials for signing (implicit) |
| CloudWatch Logs | PutLogEvents | Store execution logs |

### IAM Permissions Required

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["execute-api:Invoke"],
      "Resource": "arn:aws:execute-api:us-east-1:*/*/POST/CreateRacimo"
    },
    {
      "Effect": "Allow",
      "Action": ["appsync:GraphQL"],
      "Resource": [
        "arn:aws:appsync:us-east-1:*:apis/*/types/Query/fields/listRACIMOS",
        "arn:aws:appsync:us-east-1:*:apis/*/types/Mutation/fields/createRACIMO"
      ]
    }
  ]
}
```

### Dependencies

**Python Packages**:
```
boto3==1.34.29
botocore==1.34.29
requests==2.31.0
```

**Standard Library**:
- `json`: Request/response parsing
- `os`: Environment variables

### Error Handling

- **Missing fields**: Returns 400 with validation error
- **GraphQL query error**: Returns 500 with error details
- **GraphQL mutation error**: Returns 500 with error details
- **Invalid JSON body**: Returns 400 with parse error
- **Authentication failure**: API Gateway returns 403 before Lambda invocation

### Performance Characteristics

- **Cold Start**: ~2-3 seconds
- **Warm Execution (exists)**: ~800ms (query only)
- **Warm Execution (create)**: 1.5-2s (query + mutation)
- **Memory Usage**: ~120 MB

---

## Common Configuration

### Global Lambda Settings (SAM Template)

```yaml
Globals:
  Function:
    Runtime: python3.9
    MemorySize: 520
    Timeout: 600
    Architectures:
      - x86_64
```

### Logging Configuration

All functions log to CloudWatch Logs with format:
```
/aws/lambda/{FunctionName}
```

**Log Retention**: Configured in CloudFormation (default: 7 days)

### Environment-Specific Resources

Lambda functions automatically receive environment-specific parameters during deployment based on git branch:
- `develop` branch → develop environment
- `test` branch → test environment
- `main` branch → production environment

Configuration loaded from `parameters.json` during deployment.

---

## Monitoring and Alerts

### Key Metrics to Monitor

| Metric | Threshold | Alert Action |
|--------|-----------|--------------|
| Lambda Errors | > 5% | Page on-call engineer |
| Lambda Duration | > 30s | Investigate performance |
| Stream Iterator Age | > 10min | Check Lambda throttling |
| Concurrent Executions | > 900 | Review account limits |
| SNS Publish Failures | > 0 | Check topic permissions |

### Troubleshooting Commands

```bash
# View recent logs
aws logs tail /aws/lambda/DynamoDBEventProcessorFunction --follow

# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=UvaToCloudFunction \
  --start-time 2024-01-15T00:00:00Z \
  --end-time 2024-01-15T23:59:59Z \
  --period 3600 \
  --statistics Sum

# Invoke function locally
sam local invoke DynamoDBEventProcessorFunction -e events/test-event.json
```
