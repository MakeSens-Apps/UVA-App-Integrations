# System Architecture

## Overview

UVA-App-Integrations implements an **event-driven serverless architecture** on AWS, using DynamoDB Streams as the primary event source to trigger data processing and synchronization workflows. The system integrates IoT device data with cloud services through Lambda functions, AppSync GraphQL APIs, and SNS messaging.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           UVA Device Ecosystem                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          DynamoDB Tables                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ Measurement  │  │     UVA      │  │   RACIMO     │                  │
│  │   (Stream)   │  │   (Stream)   │  │              │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘                  │
│         │                  │                                             │
│         │ Stream Event     │ Stream Event                                │
└─────────┼──────────────────┼─────────────────────────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Lambda Functions Layer                            │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ DynamoDBEventProcessorFunction                                  │    │
│  │  • Reads: Measurement stream                                    │    │
│  │  • Processes: INSERT events                                     │    │
│  │  • Transforms: DynamoDB format → Python types                   │    │
│  │  • Publishes: SNS (RealTimeDeviceData)                         │    │
│  └───────────────────────────────┬────────────────────────────────┘    │
│                                   │                                      │
│  ┌────────────────────────────────▼───────────────────────────────┐    │
│  │ UvaToCloudFunction                                              │    │
│  │  • Reads: UVA stream (INSERT/MODIFY)                           │    │
│  │  • Queries: RACIMO, Organization, Location tables              │    │
│  │  • Creates: Devices in MakeSensCloud via GraphQL               │    │
│  │  • Updates: Location records with coordinates                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ UVALastConnection (API Endpoint)                                 │    │
│  │  • Trigger: API Gateway GET /{id_uva}/connection                │    │
│  │  • Queries: AppSync for latest measurements                     │    │
│  │  • Returns: Connection status (last 24h) + timestamp            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ CreateRacimo (API Endpoint)                                      │    │
│  │  • Trigger: API Gateway POST /CreateRacimo                      │    │
│  │  • Validates: RACIMO existence via GraphQL query                │    │
│  │  • Creates: New RACIMO with linkage code                        │    │
│  │  • Auth: AWS SigV4 signing                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────┬──────────────────────────────┬──────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────────┐
│   Amazon SNS    │          │   AWS AppSync        │
│                 │          │   (GraphQL APIs)     │
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

## Component Details

### 1. Data Storage Layer (DynamoDB)

**Purpose**: Persistent storage for device data, metadata, and organizational structures

**Tables**:
- **Measurement**: Stores time-series sensor data from UVA devices
- **UVA**: Device registry with metadata and configuration
- **RACIMO**: Device clusters/groups with linkage codes
- **Organization**: Organizational entities linked to device clusters
- **Location**: Geographic coordinates for UVA devices

**Stream Configuration**:
- Enabled on: Measurement, UVA tables
- Batch size: 10 records
- Batching window: 10 seconds
- Starting position: LATEST

### 2. Compute Layer (Lambda Functions)

**Execution Configuration**:
- Runtime: Python 3.9
- Memory: 520 MB per function
- Timeout: 600 seconds (10 minutes)
- Architecture: x86_64

**Functions**:
1. **DynamoDBEventProcessorFunction**: Stream-triggered data processor
2. **UvaToCloudFunction**: Stream-triggered device synchronization
3. **UVALastConnection**: API Gateway-triggered connection monitor
4. **CreateRacimo**: API Gateway-triggered cluster manager

### 3. API Layer

**API Gateway**:
- **REST API** with AWS_IAM authorization
- Endpoints:
  - `GET /{id_uva}/connection` → UVALastConnection
  - `POST /CreateRacimo` → CreateRacimo

**AppSync GraphQL**:
- **UVA Service API**: Device and measurement queries/mutations
- **MakeSensCloud API**: Device and location management
- Authentication: API Key (primary), SigV4 (CreateRacimo)

### 4. Messaging Layer

**Amazon SNS**:
- Topic: `RealTimeDeviceData-{env}`
- Publisher: DynamoDBEventProcessorFunction
- Message attributes: `typeDevice=UVA`, `typeData=RAW`
- Purpose: Fan-out device data to multiple subscribers

## Data Flow Diagrams

### Flow 1: Real-time Measurement Processing

```
UVA Device → Measurement Table → DynamoDB Stream
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ Event Processor     │
                              │ Lambda              │
                              │                     │
                              │ 1. Filter INSERT    │
                              │ 2. Transform types  │
                              │ 3. Format timestamp │
                              └─────────┬───────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │ SNS Topic           │
                              │ RealTimeDeviceData  │
                              └─────────────────────┘
                                        │
                                        ▼
                              [ Downstream Consumers ]
```

**Steps**:
1. UVA device writes measurement to DynamoDB
2. DynamoDB Stream captures INSERT event
3. Lambda receives batch of stream records
4. Lambda filters INSERT events only
5. Lambda transforms DynamoDB format to standard JSON
6. Lambda converts ISO timestamps to Unix milliseconds
7. Lambda publishes to SNS with message attributes
8. SNS distributes to all subscribers

### Flow 2: Device Synchronization to Cloud

```
New UVA Created → UVA Table → DynamoDB Stream
                                    │
                                    ▼ (INSERT event)
                          ┌──────────────────────┐
                          │ UvaToCloudFunction   │
                          │                      │
                          │ 1. Extract UVA ID    │
                          │ 2. Get RACIMO ID     │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ Query RACIMO Table   │
                          │ Get LinkageCode      │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ Scan Organization    │
                          │ Match linkage_code   │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │ AppSync GraphQL      │
                          │ createDevice()       │
                          └──────────────────────┘
```

**Steps (INSERT)**:
1. New UVA record created in DynamoDB
2. Stream event triggers Lambda
3. Lambda extracts UVA ID and RACIMO ID
4. Lambda queries RACIMO table for LinkageCode
5. Lambda scans Organization table to find matching organization
6. Lambda calls AppSync createDevice mutation
7. Device registered in MakeSensCloud

**Steps (MODIFY - Location Update)**:
1. UVA record updated with latitude/longitude
2. Stream event triggers Lambda
3. Lambda extracts location data
4. Lambda queries Location table for existing record
5. If exists: calls updateLocation mutation
6. If not exists: calls createLocation mutation

### Flow 3: Connection Status Check

```
Client Request → API Gateway → UVALastConnection Lambda
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │ AppSync GraphQL      │
                              │ Query:               │
                              │ measurementsByUvaID  │
                              │ (limit: 1, desc)     │
                              └─────────┬────────────┘
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │ Check timestamp:     │
                              │ < 24 hours?          │
                              │ Yes → connected=true │
                              │ No → connected=false │
                              └─────────┬────────────┘
                                        │
                                        ▼
                              Return JSON Response
```

**Response Format**:
```json
{
  "uva_123": {
    "connection": true,
    "ts": 1699458000000
  }
}
```

### Flow 4: RACIMO Creation

```
POST /CreateRacimo → API Gateway → CreateRacimo Lambda
  {name, linkageCode}               │
                                    ▼
                          ┌──────────────────────┐
                          │ Query AppSync:       │
                          │ listRACIMOS          │
                          │ filter: linkageCode  │
                          └──────────┬───────────┘
                                     │
                           ┌─────────┴─────────┐
                           │                   │
                    Exists │                   │ Not Exists
                           ▼                   ▼
                  Return existing    ┌──────────────────┐
                  RACIMO data        │ Create RACIMO:   │
                                     │ - name           │
                                     │ - linkageCode    │
                                     │ - configPath     │
                                     └────────┬─────────┘
                                              │
                                              ▼
                                     Return new RACIMO ID
```

## External Integrations

### 1. MakeSensCloud AppSync API

**Endpoint**: Environment-specific GraphQL endpoint
**Authentication**: API Key
**Used By**: UvaToCloudFunction

**Operations**:
- `createDevice(organizationID, name, ...)`
- `createLocation(id, latitude, longitude, ...)`
- `updateLocation(id, latitude, longitude, ...)`

**Purpose**: Centralized device and location management across MakeSens platform

### 2. UVA Service AppSync API

**Endpoint**: Environment-specific GraphQL endpoint
**Authentication**: API Key (queries), SigV4 (mutations)
**Used By**: UVALastConnection, CreateRacimo

**Operations**:
- `measurementsByUvaIDAndTs()`: Query latest measurements
- `getUVA()`: Get UVA device details
- `listRACIMOS()`: Query RACIMOs by linkage code
- `createRACIMO()`: Create new device cluster

**Purpose**: UVA-specific data access and device management

## Security Architecture

### Authentication & Authorization

**Lambda Execution Roles**:
- DynamoDB Stream read permissions (specific stream ARNs)
- SNS publish permissions (specific topic ARNs)
- DynamoDB table access (GetItem, Scan on specific tables)
- AppSync API access (GraphQL operations)

**API Gateway**:
- Authorization: AWS_IAM
- Requires signed requests with AWS credentials
- Prevents unauthorized access to endpoints

**AppSync APIs**:
- **API Key**: Used for most operations (development/testing)
- **AWS SigV4**: Used by CreateRacimo for production-grade auth
- API keys rotated per environment

### Network Security

**VPC**: Not used (public Lambda execution)
**Encryption**:
- DynamoDB: Server-side encryption at rest
- Data in transit: HTTPS/TLS for all API calls

## Environment Separation

The system supports three isolated environments:

| Environment | Branch   | Purpose                    |
|-------------|----------|----------------------------|
| develop     | develop  | Active development         |
| test        | test     | Pre-production testing     |
| main        | main     | Production                 |

**Isolation Strategy**:
- Separate DynamoDB tables per environment
- Separate AppSync endpoints per environment
- Separate SNS topics per environment
- Environment-specific API keys
- Distinct parameter configurations in `parameters.json`

## Scalability Considerations

**Lambda**:
- Auto-scales based on event volume
- Max concurrency: AWS account limits (default 1000)
- Stream batch processing: 10 records per invocation

**DynamoDB**:
- On-demand billing or provisioned capacity
- Streams: Auto-scales with table throughput

**SNS**:
- Highly scalable message distribution
- Supports millions of messages per second

## Monitoring & Observability

**CloudWatch Logs**:
- Lambda function logs (automatic)
- Log retention: Configurable via CloudFormation

**CloudWatch Metrics**:
- Lambda invocations, errors, duration
- DynamoDB Stream iterator age
- SNS message delivery metrics

**Tracing**: Not currently implemented (consider AWS X-Ray for distributed tracing)

## Deployment Architecture

**CI/CD Pipeline**:
```
GitHub Push → GitHub Actions → AWS SAM Deploy → CloudFormation Stack Update
    │
    ├─ test branch   → Deploy to test environment
    └─ main branch   → Deploy to production environment
```

**Deployment Process**:
1. Code pushed to GitHub branch
2. GitHub Actions workflow triggered
3. SAM CLI builds Lambda packages
4. CloudFormation validates template
5. Stack deployed with environment-specific parameters
6. Lambda functions updated with new code
7. API Gateway endpoints configured
8. DynamoDB Stream event mappings created

**Rollback Strategy**: CloudFormation automatic rollback on deployment failure
