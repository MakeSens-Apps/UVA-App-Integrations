# Features

## Overview

UVA-App-Integrations provides four core features for managing IoT device data and synchronization across the MakeSens ecosystem. Each feature is implemented as an independent serverless function that responds to specific events or API requests.

---

## Feature 1: Real-time Device Data Processing

### Description
Automatically processes and distributes measurement data from UVA devices to downstream consumers in real-time using a streaming architecture.

### Business Value
- Enables real-time monitoring of device vitals
- Decouples data producers from consumers via publish-subscribe pattern
- Ensures measurement data reaches analytics and alerting systems immediately
- Transforms data format for cross-platform compatibility

### Use Cases

#### UC1.1: Stream Temperature Measurement
**Actor**: UVA Device
**Trigger**: Device writes temperature reading to Measurement table
**Flow**:
1. Device inserts measurement record with temperature data
2. DynamoDB Stream captures INSERT event
3. Lambda processes and transforms data format
4. Lambda publishes message to SNS topic
5. Monitoring dashboards receive update within seconds

**Outcome**: Real-time temperature visible in dashboard

#### UC1.2: Distribute Multi-sensor Data
**Actor**: Multiple UVA devices
**Trigger**: Batch of measurements from different sensors
**Flow**:
1. Multiple devices insert measurements (batch of 10)
2. Lambda receives batched stream events
3. Lambda processes each measurement independently
4. Lambda publishes all to SNS in sequence
5. Multiple subscribers receive data (analytics, alerting, storage)

**Outcome**: All consumers receive complete dataset

### Workflow

```
┌───────────────┐
│ UVA Device    │
│ Writes Data   │
└───────┬───────┘
        │
        ▼
┌───────────────────┐
│ Measurement Table │
│ INSERT Event      │
└───────┬───────────┘
        │
        ▼
┌─────────────────────────┐
│ Stream Processing       │
│ - Filter INSERT only    │
│ - Remove DynamoDB types │
│ - Convert timestamps    │
└───────┬─────────────────┘
        │
        ▼
┌───────────────────┐
│ SNS Publish       │
│ Attributes:       │
│ - typeDevice=UVA  │
│ - typeData=RAW    │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ Downstream        │
│ Subscribers       │
└───────────────────┘
```

### Data Transformations

**Input (DynamoDB Format)**:
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

**Output (SNS Message)**:
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

### Configuration
- **Batch Size**: 10 records per Lambda invocation
- **Batching Window**: 10 seconds maximum wait
- **Message Attributes**: `typeDevice=UVA`, `typeData=RAW`

---

## Feature 2: Device Synchronization to MakeSensCloud

### Description
Automatically creates and updates device records in MakeSensCloud when UVA devices are registered or modified, ensuring centralized device inventory stays synchronized.

### Business Value
- Maintains single source of truth for device inventory
- Eliminates manual device registration in cloud
- Automatically propagates organizational hierarchy (RACIMO → Organization → Device)
- Keeps location data synchronized for mapping and geofencing

### Use Cases

#### UC2.1: Register New Device in Cloud
**Actor**: System Administrator
**Trigger**: New UVA created in database
**Flow**:
1. Admin creates new UVA record with RACIMO association
2. DynamoDB Stream triggers UvaToCloudFunction
3. Lambda queries RACIMO table for LinkageCode
4. Lambda scans Organization table to find matching org
5. Lambda calls createDevice GraphQL mutation
6. Device appears in MakeSensCloud organization

**Outcome**: Device automatically registered in cloud without manual intervention

#### UC2.2: Update Device Location
**Actor**: UVA Device or Admin
**Trigger**: UVA record updated with GPS coordinates
**Flow**:
1. UVA record modified with latitude/longitude
2. DynamoDB Stream triggers UvaToCloudFunction (MODIFY event)
3. Lambda extracts location data
4. Lambda checks Location table for existing record
5. If exists: Lambda calls updateLocation mutation
6. If not exists: Lambda calls createLocation mutation
7. Device location updated in cloud

**Outcome**: Device location visible on cloud map interface

#### UC2.3: Handle Incomplete Location Data
**Actor**: System
**Trigger**: UVA updated with partial location data
**Flow**:
1. UVA record updated with only latitude (missing longitude)
2. Lambda validates location completeness
3. Lambda skips location sync (both coordinates required)
4. Lambda logs incomplete data warning

**Outcome**: System prevents invalid location records

### Workflow

```
┌─────────────────┐
│ UVA Table       │
│ INSERT/MODIFY   │
└────────┬────────┘
         │
         ▼
    ┌────────┐
    │ Event  │
    │ Type?  │
    └───┬────┘
        │
    ┌───┴────────────────┐
    │                    │
INSERT│                  │MODIFY
    ▼                    ▼
┌───────────┐      ┌─────────────┐
│ Device    │      │ Location    │
│ Sync      │      │ Sync        │
│           │      │             │
│ 1. Get    │      │ 1. Extract  │
│ RACIMO    │      │    lat/lng  │
│           │      │             │
│ 2. Get    │      │ 2. Query    │
│ Org       │      │    Location │
│           │      │    table    │
│ 3. Create │      │             │
│ Device    │      │ 3. Create/  │
│           │      │    Update   │
└───────────┘      └─────────────┘
```

### Integration Points

**RACIMO Table**:
- Purpose: Retrieve LinkageCode for organization matching
- Query: `GetItem` by RACIMO ID from UVA record

**Organization Table**:
- Purpose: Find organization by linkage code
- Query: `Scan` with filter expression `linkage_code = {code}`

**MakeSensCloud AppSync**:
- `createDevice`: Creates device under organization
- `createLocation`: Adds geographic coordinates
- `updateLocation`: Updates existing coordinates

### Error Handling
- Missing RACIMO: Logs error, skips device creation
- Organization not found: Logs error, skips device creation
- GraphQL API error: Lambda fails, DynamoDB Stream retries
- Invalid location data: Skips location sync, continues processing

---

## Feature 3: Connection Status Monitoring

### Description
Provides a REST API endpoint to check if UVA devices are actively connected (measured within last 24 hours) with timestamp of last activity.

### Business Value
- Enables proactive maintenance alerts for disconnected devices
- Supports SLA monitoring for device uptime
- Provides data for device health dashboards
- Allows bulk status checks for fleet management

### Use Cases

#### UC3.1: Check Single Device Status
**Actor**: Monitoring System
**Trigger**: Periodic health check (every 5 minutes)
**Flow**:
1. System sends GET request to `/{uva_id}/connection`
2. Lambda queries AppSync for latest measurement
3. Lambda compares measurement timestamp to current time
4. If < 24 hours: returns `connection: true`
5. If > 24 hours: returns `connection: false`
6. Monitoring system records status

**Request**:
```
GET /uva123/connection
Authorization: AWS4-HMAC-SHA256 ...
```

**Response**:
```json
{
  "uva123": {
    "connection": true,
    "ts": 1705318200000
  }
}
```

#### UC3.2: Bulk Status Check
**Actor**: Dashboard Application
**Trigger**: User views fleet status page
**Flow**:
1. Dashboard sends GET request with multiple IDs: `?ids=uva1,uva2,uva3`
2. Lambda parses comma-separated list
3. Lambda queries AppSync for each UVA
4. Lambda returns status object with all devices
5. Dashboard displays color-coded status (green/red)

**Request**:
```
GET /all/connection?ids=uva123,uva456,uva789
```

**Response**:
```json
{
  "uva123": {"connection": true, "ts": 1705318200000},
  "uva456": {"connection": false, "ts": 1705145000000},
  "uva789": {"connection": true, "ts": 1705318100000}
}
```

#### UC3.3: Fallback to Creation Date
**Actor**: Monitoring System
**Trigger**: Device has no measurements yet
**Flow**:
1. System checks connection for newly provisioned device
2. Lambda queries measurements (returns empty)
3. Lambda falls back to UVA creation date
4. Returns creation timestamp as last activity
5. System marks as "new device" based on age

**Outcome**: New devices show status based on registration time

### Workflow

```
API Request
    │
    ▼
┌──────────────┐
│ Parse Path   │
│ Single or    │
│ Multiple?    │
└──────┬───────┘
       │
   ┌───┴─────────┐
   │             │
Single         Multiple
   │             │
   ▼             ▼
┌────────┐   ┌────────────┐
│ Query  │   │ Loop each  │
│ AppSync│   │ ID, Query  │
└───┬────┘   └─────┬──────┘
    │              │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ Measurements │
    │ Found?       │
    └──────┬───────┘
           │
      ┌────┴────┐
      │         │
    Yes        No
      │         │
      ▼         ▼
   ┌────┐   ┌────────┐
   │ Use│   │ Fallback│
   │ ts │   │ to UVA  │
   │    │   │ created │
   └─┬──┘   └────┬────┘
     │           │
     └─────┬─────┘
           ▼
    ┌──────────────┐
    │ Check < 24h? │
    └──────┬───────┘
           │
           ▼
    Return Response
```

### GraphQL Query

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

### Connection Logic

```python
def is_within_last_24_hours(timestamp_ms):
    current_time = time.time() * 1000
    time_difference = current_time - timestamp_ms
    return time_difference <= 86400000  # 24 hours in milliseconds
```

### Authentication
- **Method**: AWS_IAM
- **Requirements**: Signed request with valid AWS credentials
- **Permissions**: API Gateway execution role must allow invocation

---

## Feature 4: RACIMO Cluster Management

### Description
Provides a REST API endpoint to create new RACIMO (device cluster) records with linkage codes, preventing duplicates and establishing configuration paths.

### Business Value
- Simplifies cluster creation through API instead of direct database access
- Prevents duplicate RACIMOs with same linkage code
- Establishes standard configuration path convention
- Supports organizational hierarchy for multi-tenant deployments

### Use Cases

#### UC4.1: Create New RACIMO
**Actor**: Admin or Provisioning System
**Trigger**: New customer/site onboarding
**Flow**:
1. System sends POST request with cluster name and linkage code
2. Lambda queries AppSync to check if RACIMO exists
3. No existing RACIMO found
4. Lambda creates RACIMO with configuration path
5. Lambda returns new RACIMO ID
6. System stores ID for device association

**Request**:
```json
POST /CreateRacimo
Content-Type: application/json
Authorization: AWS4-HMAC-SHA256 ...

{
  "name": "Hospital Floor 3",
  "linkageCode": "HF3-2024-001"
}
```

**Response**:
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

#### UC4.2: Prevent Duplicate RACIMO
**Actor**: Provisioning System
**Trigger**: Accidental duplicate creation attempt
**Flow**:
1. System sends POST request with existing linkage code
2. Lambda queries AppSync for RACIMO with linkage code
3. Existing RACIMO found
4. Lambda returns existing RACIMO data without creating duplicate
5. System uses existing RACIMO ID

**Response**:
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

#### UC4.3: Invalid Request Handling
**Actor**: Client Application
**Trigger**: Malformed request body
**Flow**:
1. Client sends POST without required fields
2. Lambda validates request body
3. Missing name or linkageCode detected
4. Lambda returns 400 error
5. Client displays validation error

**Response**:
```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required fields: name and linkageCode"
  }
}
```

### Workflow

```
POST /CreateRacimo
{name, linkageCode}
       │
       ▼
┌──────────────┐
│ Validate     │
│ Request Body │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Query AppSync:   │
│ listRACIMOS      │
│ filter by        │
│ linkageCode      │
└──────┬───────────┘
       │
   ┌───┴─────┐
   │         │
Exists    Not Exists
   │         │
   ▼         ▼
┌─────┐  ┌────────────┐
│Return│ │ Create     │
│Exist │ │ RACIMO:    │
│Data  │ │ - name     │
└─────┘  │ - linkage  │
         │ - config   │
         └──────┬─────┘
                │
                ▼
         ┌──────────────┐
         │ Return New   │
         │ RACIMO ID    │
         └──────────────┘
```

### GraphQL Operations

**Check Existence**:
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

**Create RACIMO**:
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

### Configuration Path Convention

**Format**: `racimos/{linkageCode}/config.json`

**Example**: For linkageCode `HF3-2024-001`, path is:
```
racimos/HF3-2024-001/config.json
```

**Purpose**: Standardized S3 or configuration storage location for cluster settings

### Authentication

**Method**: AWS Signature Version 4 (SigV4)

**Implementation**:
```python
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Sign request with Lambda execution role credentials
request = AWSRequest(method='POST', url=endpoint, data=body, headers=headers)
SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
```

**Benefits**:
- No API key management required
- Uses IAM role permissions
- Better suited for production environments

### Error Scenarios

| Scenario | Status Code | Response |
|----------|-------------|----------|
| Missing fields | 400 | `{"error": "Missing required fields"}` |
| GraphQL query error | 500 | `{"error": "Failed to check RACIMO"}` |
| GraphQL create error | 500 | `{"error": "Failed to create RACIMO"}` |
| Authentication failure | 403 | AWS API Gateway standard error |

---

## Cross-cutting Features

### Multi-Environment Support

All features support environment isolation:
- **develop**: Development and testing
- **test**: Pre-production validation
- **main**: Production

Environment determined by:
1. Git branch name during deployment
2. Parameters loaded from `parameters.json`
3. Environment-specific resource ARNs

### Error Logging

All features include comprehensive logging:
- Request/event data (sanitized)
- Processing steps and decisions
- Error details with stack traces
- Execution duration

Logs accessible via CloudWatch Logs: `/aws/lambda/{FunctionName}`

### Retry Behavior

**DynamoDB Stream Functions**:
- Automatic retries on failure
- Exponential backoff
- Maximum retry attempts: 3
- Failed batches sent to DLQ (if configured)

**API Gateway Functions**:
- No automatic retry
- Client responsible for retry logic
- Idempotent operations (RACIMO creation checks existence)

### Performance Characteristics

| Feature | Avg Latency | Max Throughput | Bottleneck |
|---------|-------------|----------------|------------|
| Data Processing | < 500ms | 1000 events/sec | DynamoDB Stream shards |
| Device Sync | 1-2s | 100 devices/sec | GraphQL API rate limits |
| Connection Check | 500-800ms | 50 req/sec | AppSync query performance |
| RACIMO Creation | 800ms-1.5s | 20 req/sec | GraphQL mutation + query |
