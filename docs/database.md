# Database

## Overview

UVA-App-Integrations uses **Amazon DynamoDB**, a fully managed NoSQL database service, for all data storage. The system interacts with multiple tables for device metadata, measurements, organizational structures, and locations.

**Database Type**: Amazon DynamoDB (NoSQL, Key-Value and Document Store)
**Region**: us-east-1
**Billing Mode**: On-demand or Provisioned (configured per environment)

---

## Tables

### 1. Measurement Table

**Purpose**: Stores time-series sensor data from UVA devices

**Naming Convention**: `Measurement-{AppId}-{env}`
**Example**: `Measurement-abc123-develop`

#### Schema

**Primary Key**:
- **Partition Key**: `id` (String) - UVA device identifier
- **Sort Key**: `ts` (Number) - Unix timestamp in milliseconds

**Attributes**:
```json
{
  "id": "String",           // UVA device ID (partition key)
  "ts": "Number",           // Unix timestamp milliseconds (sort key)
  "type": "String",         // Measurement type (temperature, pressure, etc.)
  "data": "Map",            // Measurement payload (varies by type)
  "logs": "List",           // Optional log entries
  "createdAt": "String",    // ISO 8601 creation timestamp
  "updatedAt": "String"     // ISO 8601 update timestamp
}
```

**Sample Record**:
```json
{
  "id": "uva123",
  "ts": 1705318200000,
  "type": "temperature",
  "data": {
    "value": 36.5,
    "unit": "celsius",
    "sensorId": "temp_01"
  },
  "logs": [],
  "createdAt": "2024-01-15T10:30:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

#### Indexes

**Global Secondary Indexes (GSI)**:

**uvaID-ts-index** (likely exists for queries):
- **Partition Key**: `uvaID` or `id` (String)
- **Sort Key**: `ts` (Number)
- **Purpose**: Query measurements by device ID sorted by time
- **Projection**: ALL

**Access Patterns**:
- Get latest measurement for device: Query by `uvaID`, sort DESC, limit 1
- Get measurements in time range: Query by `uvaID` with ts BETWEEN
- Stream processing: DynamoDB Streams capture all INSERT events

#### Stream Configuration

**Stream Enabled**: Yes
**Stream View Type**: NEW_IMAGE (captures new record state)
**Consumers**: DynamoDBEventProcessorFunction Lambda

**ARN Pattern**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-{AppId}-{env}/stream/*
```

---

### 2. UVA Table

**Purpose**: Device registry storing UVA metadata and configuration

**Naming Convention**: `UVA-{AppId}-{env}`
**Example**: `UVA-abc123-develop`

#### Schema

**Primary Key**:
- **Partition Key**: `id` (String) - Unique UVA device identifier

**Attributes**:
```json
{
  "id": "String",           // UVA device ID (partition key)
  "name": "String",         // Device display name
  "racimoID": "String",     // Foreign key to RACIMO table
  "latitude": "Number",     // Optional: GPS latitude
  "longitude": "Number",    // Optional: GPS longitude
  "status": "String",       // Device status (active, inactive, etc.)
  "metadata": "Map",        // Additional device properties
  "createdAt": "String",    // ISO 8601 creation timestamp
  "updatedAt": "String"     // ISO 8601 update timestamp
}
```

**Sample Record**:
```json
{
  "id": "uva123",
  "name": "Device Floor 3 Room 301",
  "racimoID": "racimo456",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "status": "active",
  "metadata": {
    "firmwareVersion": "2.1.3",
    "installDate": "2024-01-10"
  },
  "createdAt": "2024-01-10T08:00:00.000Z",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

#### Indexes

**No additional indexes documented** (primary key access only)

**Access Patterns**:
- Get UVA by ID: GetItem operation
- Get creation date: Used by UVALastConnection as fallback

#### Stream Configuration

**Stream Enabled**: Yes
**Stream View Type**: NEW_AND_OLD_IMAGES (captures before/after state)
**Consumers**: UvaToCloudFunction Lambda

**ARN Pattern**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-{AppId}-{env}/stream/*
```

**Event Types Processed**:
- **INSERT**: Triggers device creation in MakeSensCloud
- **MODIFY**: Triggers location update if lat/lng changed

---

### 3. RACIMO Table

**Purpose**: Stores device clusters/groups with linkage codes for organizational hierarchy

**Naming Convention**: `RACIMO-{AppId}-{env}`
**Example**: `RACIMO-abc123-develop`

#### Schema

**Primary Key**:
- **Partition Key**: `id` (String) - Unique RACIMO identifier

**Attributes**:
```json
{
  "id": "String",           // RACIMO ID (partition key)
  "name": "String",         // Cluster display name
  "LinkageCode": "String",  // Unique linkage identifier
  "path": "String",         // Configuration file path
  "createdAt": "String",    // ISO 8601 creation timestamp
  "updatedAt": "String"     // ISO 8601 update timestamp
}
```

**Sample Record**:
```json
{
  "id": "racimo456",
  "name": "Hospital Floor 3",
  "LinkageCode": "HF3-2024-001",
  "path": "racimos/HF3-2024-001/config.json",
  "createdAt": "2024-01-05T12:00:00.000Z",
  "updatedAt": "2024-01-05T12:00:00.000Z"
}
```

#### Indexes

**Global Secondary Index** (likely for LinkageCode queries):
- **Partition Key**: `LinkageCode` (String)
- **Purpose**: Query RACIMO by linkage code for duplicate checking
- **Used By**: CreateRacimo Lambda

**Access Patterns**:
- Get RACIMO by ID: GetItem operation (used by UvaToCloudFunction)
- Find RACIMO by LinkageCode: Query or Scan with filter (used by CreateRacimo)

#### Relationships

**One-to-Many with UVA**:
- One RACIMO can contain multiple UVA devices
- UVA.racimoID → RACIMO.id (foreign key)

**One-to-One with Organization** (via LinkageCode):
- RACIMO.LinkageCode = Organization.linkage_code
- Used to associate devices with organizations

---

### 4. Organization Table

**Purpose**: Stores organizational entities for multi-tenant device management

**Naming Convention**: `Organization-{AppId}-{env}`
**Example**: `Organization-abc123-develop`

#### Schema

**Primary Key**:
- **Partition Key**: `id` (String) - Unique organization identifier

**Attributes**:
```json
{
  "id": "String",           // Organization ID (partition key)
  "name": "String",         // Organization name
  "linkage_code": "String", // Links to RACIMO.LinkageCode
  "metadata": "Map",        // Additional org properties
  "createdAt": "String",    // ISO 8601 creation timestamp
  "updatedAt": "String"     // ISO 8601 update timestamp
}
```

**Sample Record**:
```json
{
  "id": "org789",
  "name": "City General Hospital",
  "linkage_code": "HF3-2024-001",
  "metadata": {
    "address": "123 Medical Center Dr",
    "contactEmail": "admin@cityhospital.com"
  },
  "createdAt": "2024-01-01T00:00:00.000Z",
  "updatedAt": "2024-01-01T00:00:00.000Z"
}
```

#### Indexes

**Global Secondary Index** (recommended for linkage_code):
- **Partition Key**: `linkage_code` (String)
- **Purpose**: Efficiently find organization by linkage code
- **Note**: Currently accessed via Scan operation (inefficient for large tables)

**Access Patterns**:
- Find organization by linkage_code: **Scan** with FilterExpression (current implementation)
- Recommended: Query GSI on linkage_code for better performance

**Performance Consideration**:
```python
# Current implementation (full table scan)
response = dynamodb.scan(
    TableName='Organization-abc123-develop',
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)

# Recommended optimization: Use GSI query instead
response = dynamodb.query(
    TableName='Organization-abc123-develop',
    IndexName='linkage_code-index',
    KeyConditionExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

---

### 5. Location Table

**Purpose**: Stores geographic coordinates for UVA devices

**Naming Convention**: `Location-{AppId}-{env}`
**Example**: `Location-abc123-develop`

#### Schema

**Primary Key**:
- **Partition Key**: `id` (String) - Location identifier (format: `A{uvaID}`)

**Attributes**:
```json
{
  "id": "String",           // Location ID = "A" + uvaID (partition key)
  "latitude": "Number",     // GPS latitude
  "longitude": "Number",    // GPS longitude
  "altitude": "Number",     // Optional: Altitude in meters
  "accuracy": "Number",     // Optional: GPS accuracy in meters
  "createdAt": "String",    // ISO 8601 creation timestamp
  "updatedAt": "String"     // ISO 8601 update timestamp
}
```

**Sample Record**:
```json
{
  "id": "Auva123",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "altitude": 15.5,
  "accuracy": 10.0,
  "createdAt": "2024-01-15T10:30:00.000Z",
  "updatedAt": "2024-01-15T14:20:00.000Z"
}
```

#### ID Convention

**Format**: `A{uvaID}`
**Examples**:
- UVA ID: `uva123` → Location ID: `Auva123`
- UVA ID: `device456` → Location ID: `Adevice456`

**Purpose**: Creates one-to-one relationship with UVA table

#### Access Patterns

- Check if location exists: GetItem by `id`
- Get device location: GetItem by `A{uvaID}`
- Update location: PutItem or UpdateItem

#### Relationships

**One-to-One with UVA**:
- Location.id = `A{UVA.id}`
- Managed by UvaToCloudFunction on UVA MODIFY events

---

## Table Relationships

```
Organization
    │
    │ (linkage_code match)
    ▼
  RACIMO ──────┐
    │          │
    │ (id)     │
    ▼          │
   UVA         │
    │          │
    │          │ (racimoID FK)
    │          │
    ▼          ▼
Location    Measurement
(A{uvaID})  (uvaID, ts)
```

**Relationship Details**:
1. **Organization ↔ RACIMO**: Linked via `linkage_code` field
2. **RACIMO ↔ UVA**: One-to-many via `racimoID` foreign key
3. **UVA ↔ Location**: One-to-one via `A{uvaID}` convention
4. **UVA ↔ Measurement**: One-to-many via `uvaID` partition key

---

## Data Operations

### Read Operations

**GetItem** (efficient - O(1) complexity):
```python
# Get specific UVA device
response = dynamodb.get_item(
    TableName='UVA-abc123-develop',
    Key={'id': 'uva123'}
)
```

**Query** (efficient - uses indexes):
```python
# Get latest measurements for device
response = dynamodb.query(
    TableName='Measurement-abc123-develop',
    IndexName='uvaID-ts-index',
    KeyConditionExpression='uvaID = :id',
    ExpressionAttributeValues={':id': 'uva123'},
    ScanIndexForward=False,  # Descending order
    Limit=1
)
```

**Scan** (inefficient - full table scan):
```python
# Find organization by linkage code (current implementation)
response = dynamodb.scan(
    TableName='Organization-abc123-develop',
    FilterExpression='linkage_code = :code',
    ExpressionAttributeValues={':code': 'HF3-2024-001'}
)
```

### Write Operations

**PutItem** (create or replace):
```python
# Create new UVA device
dynamodb.put_item(
    TableName='UVA-abc123-develop',
    Item={
        'id': 'uva123',
        'name': 'Device Floor 3',
        'racimoID': 'racimo456',
        'status': 'active',
        'createdAt': '2024-01-15T10:30:00.000Z'
    }
)
```

**UpdateItem** (modify specific attributes):
```python
# Update device location
dynamodb.update_item(
    TableName='UVA-abc123-develop',
    Key={'id': 'uva123'},
    UpdateExpression='SET latitude = :lat, longitude = :lng, updatedAt = :now',
    ExpressionAttributeValues={
        ':lat': 37.7749,
        ':lng': -122.4194,
        ':now': '2024-01-15T10:30:00.000Z'
    }
)
```

---

## DynamoDB Streams

### Stream Configuration

**Tables with Streams Enabled**:
1. **Measurement**: NEW_IMAGE view
2. **UVA**: NEW_AND_OLD_IMAGES view

**Stream Settings**:
- **Batch Size**: 10 records per Lambda invocation
- **Batching Window**: 10 seconds maximum wait
- **Starting Position**: LATEST (only new records)
- **Retry**: 3 attempts on Lambda failure
- **On Failure**: DLQ (Dead Letter Queue) if configured

### Stream Record Format

**INSERT Event**:
```json
{
  "eventID": "abc123",
  "eventName": "INSERT",
  "eventVersion": "1.1",
  "eventSource": "aws:dynamodb",
  "awsRegion": "us-east-1",
  "dynamodb": {
    "ApproximateCreationDateTime": 1705318200,
    "Keys": {
      "id": {"S": "uva123"}
    },
    "NewImage": {
      "id": {"S": "uva123"},
      "name": {"S": "Device Floor 3"},
      "racimoID": {"S": "racimo456"}
    },
    "SequenceNumber": "111222333",
    "SizeBytes": 250,
    "StreamViewType": "NEW_IMAGE"
  }
}
```

**MODIFY Event** (for UVA table):
```json
{
  "eventName": "MODIFY",
  "dynamodb": {
    "Keys": {"id": {"S": "uva123"}},
    "OldImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4000"}
    },
    "NewImage": {
      "id": {"S": "uva123"},
      "latitude": {"N": "37.7749"},
      "longitude": {"N": "-122.4194"}
    }
  }
}
```

---

## Performance Considerations

### Read Capacity

**Query Operations**:
- Measurement queries: ~1-5 RCU per query (depending on data size)
- UVA GetItem: 1 RCU per device
- RACIMO GetItem: 1 RCU per cluster

**Scan Operations**:
- Organization scan: Scales with table size (inefficient)
- Recommendation: Add GSI on `linkage_code` for O(1) queries

### Write Capacity

**Stream-triggered Writes**:
- Measurement INSERT: ~100-1000 WCU during peak device activity
- UVA MODIFY: ~10-50 WCU during location updates

**Recommendation**: Use on-demand billing for unpredictable workloads

### Latency

**GetItem**: < 10ms (single-digit milliseconds)
**Query**: 10-50ms (depending on result set size)
**Scan**: 100ms - several seconds (depends on table size)
**Stream Latency**: < 1 second (stream event to Lambda invocation)

---

## Data Retention

**Tables**: No TTL (Time To Live) configured
**Measurement Data**: Grows indefinitely (consider implementing TTL)

**Recommendation for Measurement Table**:
```python
# Enable TTL to automatically delete old measurements
# Example: Delete measurements older than 90 days
dynamodb.update_time_to_live(
    TableName='Measurement-abc123-develop',
    TimeToLiveSpecification={
        'Enabled': True,
        'AttributeName': 'expirationTime'  # Unix timestamp
    }
)
```

**Calculate expiration time**:
```python
import time

# Set expiration to 90 days from now
expiration_time = int(time.time()) + (90 * 24 * 60 * 60)

# Add to measurement record
item['expirationTime'] = expiration_time
```

---

## Security

### Encryption

**At Rest**: DynamoDB default encryption (AWS-managed keys)
**In Transit**: TLS 1.2+ for all API calls

### Access Control

**IAM Policies**: Lambda execution roles have fine-grained permissions

**Example Policy**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/RACIMO-*"
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/Organization-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetRecords",
        "dynamodb:GetShardIterator",
        "dynamodb:DescribeStream"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:913045965320:table/*/stream/*"
    }
  ]
}
```

### Backup

**Point-in-Time Recovery (PITR)**: Recommended for production
**On-Demand Backups**: Manual backups for major releases

---

## Monitoring

### CloudWatch Metrics

**Key Metrics**:
- `ConsumedReadCapacityUnits`: Monitor for throttling
- `ConsumedWriteCapacityUnits`: Monitor for throttling
- `UserErrors`: 400 errors (validation issues)
- `SystemErrors`: 500 errors (service issues)
- `SuccessfulRequestLatency`: Query performance

### Stream Monitoring

**Important Metrics**:
- `GetRecords.IteratorAgeMilliseconds`: Stream processing lag
  - Alert if > 600000 (10 minutes)
- `GetRecords.Success`: Stream read success rate

### Alarms

**Recommended CloudWatch Alarms**:
```bash
# High iterator age (stream lag)
aws cloudwatch put-metric-alarm \
  --alarm-name "UVA-Stream-Lag" \
  --metric-name GetRecords.IteratorAgeMilliseconds \
  --namespace AWS/DynamoDB \
  --statistic Maximum \
  --period 300 \
  --threshold 600000 \
  --comparison-operator GreaterThanThreshold

# High error rate
aws cloudwatch put-metric-alarm \
  --alarm-name "DynamoDB-Errors" \
  --metric-name UserErrors \
  --namespace AWS/DynamoDB \
  --statistic Sum \
  --period 60 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

---

## Optimization Recommendations

1. **Add GSI to Organization Table**:
   - Index: `linkage_code` (partition key)
   - Eliminates expensive Scan operations
   - Reduces costs and improves latency

2. **Implement TTL for Measurement Table**:
   - Automatically delete old measurements
   - Reduces storage costs
   - Maintains performance at scale

3. **Use Query instead of Scan**:
   - Replace Organization Scan with Query on GSI
   - 10-100x performance improvement
   - Lower cost per operation

4. **Consider DynamoDB Streams Filtering**:
   - Filter MODIFY events to only location changes
   - Reduces unnecessary Lambda invocations
   - Lower compute costs

5. **Batch Operations**:
   - Use BatchGetItem for bulk reads
   - Use BatchWriteItem for bulk writes
   - Reduce API call overhead
