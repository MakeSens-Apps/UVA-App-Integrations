# Infrastructure

## Overview

UVA-App-Integrations is deployed using **AWS Serverless Application Model (SAM)**, which provides infrastructure as code using CloudFormation templates. The infrastructure is fully serverless, requiring no server management and scaling automatically based on demand.

**Infrastructure as Code**: AWS SAM (CloudFormation-based)
**Cloud Provider**: Amazon Web Services (AWS)
**Region**: us-east-1 (N. Virginia)
**Account ID**: 913045965320

---

## Infrastructure Components

### 1. AWS Lambda

**Service**: AWS Lambda (Serverless Compute)

**Functions Deployed**:
```yaml
Functions:
  - DynamoDBEventProcessorFunction
  - UvaToCloudFunction
  - UVALastConnection
  - CreateRacimo
```

**Global Configuration** (from SAM template):
```yaml
Globals:
  Function:
    Runtime: python3.9
    MemorySize: 520          # MB
    Timeout: 600             # Seconds (10 minutes)
    Architectures:
      - x86_64
```

**Resource Naming**:
- Pattern: `{FunctionName}-{StackName}-{UniqueId}`
- Example: `DynamoDBEventProcessorFunction-SAM-UVA-App-Integrations-dev-abc123`

**Execution Roles**:
- Auto-created by SAM for each function
- Follows least-privilege principle
- Grants specific permissions via Policies section in template

---

### 2. Amazon DynamoDB

**Service**: Amazon DynamoDB (NoSQL Database)

**Tables** (not managed by this stack - external dependencies):
```
Measurement-{AppId}-{env}
UVA-{AppId}-{env}
RACIMO-{AppId}-{env}
Organization-{AppId}-{env}
Location-{AppId}-{env}
```

**Stream Configuration**:
- **Measurement Stream**: Triggers DynamoDBEventProcessorFunction
- **UVA Stream**: Triggers UvaToCloudFunction
- **Batch Size**: 10 records
- **Batching Window**: 10 seconds
- **Starting Position**: LATEST

**ARN Examples**:
```
arn:aws:dynamodb:us-east-1:913045965320:table/Measurement-abc123-develop/stream/*
arn:aws:dynamodb:us-east-1:913045965320:table/UVA-abc123-develop/stream/*
```

---

### 3. Amazon SNS

**Service**: Amazon SNS (Simple Notification Service)

**Topic** (external dependency):
- **Name**: `RealTimeDeviceData-{env}`
- **Purpose**: Distribute processed measurement data
- **Publisher**: DynamoDBEventProcessorFunction
- **Subscribers**: External (not managed by this stack)

**ARN Pattern**:
```
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-develop
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-test
arn:aws:sns:us-east-1:913045965320:RealTimeDeviceData-main
```

**Message Attributes**:
- `typeDevice`: "UVA"
- `typeData`: "RAW"

---

### 4. AWS AppSync

**Service**: AWS AppSync (GraphQL API)

**APIs** (external dependencies - not managed by this stack):

**MakeSensCloud AppSync**:
```yaml
Purpose: Device and location management
Endpoint: https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
Authentication: API Key
Operations:
  - Mutation: createDevice
  - Mutation: createLocation
  - Mutation: updateLocation
```

**UVA Service AppSync**:
```yaml
Purpose: Measurement queries and RACIMO management
Endpoint: https://{api-id}.appsync-api.us-east-1.amazonaws.com/graphql
Authentication: API Key (queries) / SigV4 (mutations)
Operations:
  - Query: measurementsByUvaIDAndTs
  - Query: getUVA
  - Query: listRACIMOS
  - Mutation: createRACIMO
```

---

### 5. API Gateway

**Service**: Amazon API Gateway (REST API)

**API Configuration**:
```yaml
Type: AWS::Serverless::Api
Name: UvaAppIntegrationsAPI-{env}
Stage: prod
Authorization: AWS_IAM
```

**Endpoints**:
```
GET  /{id_uva}/connection   → UVALastConnection Lambda
POST /CreateRacimo          → CreateRacimo Lambda
```

**Base URL Pattern**:
```
https://{api-id}.execute-api.us-east-1.amazonaws.com/prod
```

**CORS**: Not configured (can be added if needed)

**Throttling**:
- Default AWS account limits
- Rate limit: 10,000 requests per second
- Burst limit: 5,000 requests

---

### 6. CloudWatch Logs

**Service**: Amazon CloudWatch Logs

**Log Groups** (auto-created):
```
/aws/lambda/DynamoDBEventProcessorFunction
/aws/lambda/UvaToCloudFunction
/aws/lambda/UVALastConnection
/aws/lambda/CreateRacimo
```

**Retention**: Default (never expire) - should configure retention policy

**Log Format**: JSON structured logs from Lambda functions

**Recommended Retention**:
```yaml
LogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub "/aws/lambda/${FunctionName}"
    RetentionInDays: 7  # or 14, 30, 60, 90
```

---

## SAM Template Structure

**Location**: `SAM-UVA-App-Integrations/template.yaml`

### Template Sections

**Transform**:
```yaml
Transform: AWS::Serverless-2016-10-31
```
Enables SAM-specific syntax

**Parameters** (Environment-specific values):
```yaml
Parameters:
  # DynamoDB Stream ARNs
  StreamArnDataAccess:
    Type: String
    Description: Measurement table stream ARN

  StreamArnCloud:
    Type: String
    Description: UVA table stream ARN

  # SNS Topic
  TopicSNSDataArn:
    Type: String
    Description: RealTime device data topic ARN

  # AppSync Configuration
  UvaAppsyncUrl:
    Type: String
    Description: UVA service AppSync endpoint

  UvaAppsyncApiKey:
    Type: String
    Description: UVA service API key

  CloudAppsyncUrl:
    Type: String
    Description: Cloud service AppSync endpoint

  CloudAppsyncApiKey:
    Type: String
    Description: Cloud service API key

  # DynamoDB Tables
  RacimoTableName:
    Type: String
    Description: RACIMO table name

  OrganizationTableName:
    Type: String
    Description: Organization table name

  LocationTableName:
    Type: String
    Description: Location table name
```

**Functions** (Simplified example):
```yaml
Resources:
  DynamoDBEventProcessorFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: lambdas/deviceDataAccess/
      Handler: dynamodb_to_sns.lambda_handler
      Environment:
        Variables:
          TOPIC_SNS_ARN: !Ref TopicSNSDataArn
      Events:
        DynamoDBStream:
          Type: DynamoDB
          Properties:
            Stream: !Ref StreamArnDataAccess
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 10
            StartingPosition: LATEST
      Policies:
        - DynamoDBStreamReadPolicy:
            TableName: "*"
            StreamName: "*"
        - SNSPublishMessagePolicy:
            TopicName: !GetAtt TopicSNSDataArn
```

**Outputs**:
```yaml
Outputs:
  ApiEndpoint:
    Description: API Gateway endpoint URL
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/prod/"

  DynamoDBProcessorArn:
    Description: DynamoDB Event Processor Lambda ARN
    Value: !GetAtt DynamoDBEventProcessorFunction.Arn
```

---

## Environment Configuration

### Parameters File

**Location**: `SAM-UVA-App-Integrations/parameters.json`

**Structure**:
```json
{
  "develop": {
    "StreamArnDataAccess": "arn:aws:dynamodb:...",
    "StreamArnCloud": "arn:aws:dynamodb:...",
    "TopicSNSDataArn": "arn:aws:sns:...",
    "UvaAppsyncUrl": "https://...",
    "UvaAppsyncApiKey": "da2-...",
    "CloudAppsyncUrl": "https://...",
    "CloudAppsyncApiKey": "da2-...",
    "RacimoTableName": "RACIMO-abc123-develop",
    "OrganizationTableName": "Organization-abc123-develop",
    "LocationTableName": "Location-abc123-develop"
  },
  "test": { /* same structure */ },
  "main": { /* same structure */ }
}
```

### Environment Mapping

| Git Branch | Environment | Purpose |
|------------|-------------|---------|
| develop    | develop     | Development and feature testing |
| test       | test        | Pre-production validation |
| main       | main        | Production |

**Deployment Behavior**:
- Branch name detected in `deploy.sh` script
- Corresponding parameters loaded from JSON
- SAM deploys with environment-specific resources

---

## IAM Roles and Permissions

### Lambda Execution Roles

**Auto-generated by SAM** for each function with specific policies.

#### DynamoDBEventProcessorFunction Role

**Permissions**:
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
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:913045965320:log-group:/aws/lambda/*"
    }
  ]
}
```

#### UvaToCloudFunction Role

**Permissions**:
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

Note: AppSync access via API Key, not IAM

#### UVALastConnection Role

**Permissions**:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    }
  ]
}
```

Note: AppSync access via API Key

#### CreateRacimo Role

**Permissions**:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["appsync:GraphQL"],
      "Resource": [
        "arn:aws:appsync:us-east-1:*:apis/*/types/Query/*",
        "arn:aws:appsync:us-east-1:*:apis/*/types/Mutation/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    }
  ]
}
```

Uses SigV4 signing for AppSync authentication

### API Gateway Execution Role

**Auto-generated** with permissions to invoke Lambda functions:
```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": [
        "arn:aws:lambda:us-east-1:*:function:UVALastConnection*",
        "arn:aws:lambda:us-east-1:*:function:CreateRacimo*"
      ]
    }
  ]
}
```

---

## Deployment Process

### Automated Deployment (CI/CD)

**Pipeline**: GitHub Actions

**Workflows**:
- `.github/workflows/DeployTest.yml` - Deploy to test environment
- `.github/workflows/DeployMain.yml` - Deploy to production

**Trigger**: Pull request closed (merged) to `test` or `main` branch

**Steps**:
1. Checkout code
2. Configure AWS credentials (from GitHub Secrets)
3. Install Python 3.9 (via pyenv)
4. Install jq (JSON processor)
5. Install AWS SAM CLI
6. Execute `deploy.sh` script

### Deployment Script

**Location**: `SAM-UVA-App-Integrations/deploy.sh`

**Process**:
```bash
#!/bin/bash

# 1. Detect environment from git branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [[ $BRANCH == "develop" ]]; then
  ENV="develop"
elif [[ $BRANCH == "test" ]]; then
  ENV="test"
elif [[ $BRANCH == "main" ]]; then
  ENV="main"
else
  echo "Unknown branch: $BRANCH"
  exit 1
fi

# 2. Load parameters from JSON
PARAMS=$(jq -r ".${ENV}" parameters.json)

# 3. Validate SAM template
sam validate --template template.yaml

# 4. Build Lambda packages
sam build --template template.yaml

# 5. Deploy CloudFormation stack
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "SAM-UVA-App-Integrations-${ENV}" \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --parameter-overrides $(echo $PARAMS | jq -r 'to_entries | map("\(.key)=\(.value)") | join(" ")')
```

**Stack Name Pattern**:
- develop: `SAM-UVA-App-Integrations-develop`
- test: `SAM-UVA-App-Integrations-test`
- main: `SAM-UVA-App-Integrations-main`

### Manual Deployment

```bash
# Navigate to SAM directory
cd SAM-UVA-App-Integrations

# Build
sam build

# Deploy to specific environment
sam deploy \
  --config-env develop \
  --stack-name SAM-UVA-App-Integrations-develop \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

---

## Resource Tagging

**Recommended Tags** (add to SAM template):
```yaml
Tags:
  Project: UVA-App-Integrations
  Environment: !Ref EnvironmentParameter
  ManagedBy: SAM
  CostCenter: IoT-Services
  Owner: MakeSens-DevTeam
```

**Benefits**:
- Cost allocation by environment
- Resource organization
- Access control via tag-based policies

---

## Cost Estimation

### Monthly Cost Breakdown (Approximate)

**AWS Lambda**:
- **Requests**: 10M requests/month
- **Duration**: 500ms average, 520MB memory
- **Cost**: ~$20-30/month

**DynamoDB Streams**:
- **Read requests**: Included with DynamoDB
- **Cost**: $0 (covered by DynamoDB charges)

**API Gateway**:
- **Requests**: 1M API calls/month
- **Cost**: ~$3.50/month

**CloudWatch Logs**:
- **Ingestion**: 10GB/month
- **Storage**: 50GB (no retention policy)
- **Cost**: ~$5-10/month

**Data Transfer**:
- **SNS**: 1M messages/month
- **AppSync**: 1M queries/month
- **Cost**: ~$5-15/month

**Total Estimated Monthly Cost**: $35-60 (excluding DynamoDB and AppSync - managed externally)

### Cost Optimization

1. **Implement CloudWatch Logs retention** (7-30 days)
   - Reduces storage costs by 70-90%

2. **Right-size Lambda memory**
   - Current: 520 MB
   - Test with 256 MB or 384 MB for potential savings

3. **Use Lambda reserved concurrency**
   - Prevents throttling
   - No additional cost

4. **Enable API Gateway caching**
   - Reduce Lambda invocations
   - Cache connection status for 60 seconds

---

## Monitoring and Alarms

### CloudWatch Alarms

**Lambda Function Errors**:
```yaml
FunctionErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub "${FunctionName}-Errors"
    MetricName: Errors
    Namespace: AWS/Lambda
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 5
    ComparisonOperator: GreaterThanThreshold
    Dimensions:
      - Name: FunctionName
        Value: !Ref FunctionName
```

**DynamoDB Stream Lag**:
```yaml
StreamLagAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: UVA-Stream-Iterator-Age
    MetricName: GetRecords.IteratorAgeMilliseconds
    Namespace: AWS/DynamoDB
    Statistic: Maximum
    Period: 300
    Threshold: 600000  # 10 minutes
    ComparisonOperator: GreaterThanThreshold
```

**API Gateway 5xx Errors**:
```yaml
ApiErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: API-Server-Errors
    MetricName: 5XXError
    Namespace: AWS/ApiGateway
    Statistic: Sum
    Period: 60
    Threshold: 10
    ComparisonOperator: GreaterThanThreshold
```

### Dashboards

**Recommended CloudWatch Dashboard** (JSON):
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Invocations", {"stat": "Sum"}],
          [".", "Errors", {"stat": "Sum"}],
          [".", "Duration", {"stat": "Average"}]
        ],
        "period": 300,
        "region": "us-east-1",
        "title": "Lambda Metrics"
      }
    }
  ]
}
```

---

## Security Considerations

### Network Security

**VPC**: Not configured (Lambda runs in AWS-managed VPC)
**Recommendation**: Consider VPC deployment if accessing private resources

**Endpoints**:
- All Lambda → DynamoDB: HTTPS
- All Lambda → AppSync: HTTPS
- All Lambda → SNS: HTTPS
- API Gateway: HTTPS only

### Secrets Management

**Current State**: API keys stored in SAM parameters (plaintext in JSON)

**Recommendation**: Use AWS Secrets Manager
```yaml
Environment:
  Variables:
    APPSYNC_API_KEY: !Sub "{{resolve:secretsmanager:UVA-AppSync-Key:SecretString:api_key}}"
```

**Benefits**:
- Automatic rotation
- Encryption at rest
- Audit logging
- No plaintext in version control

### API Security

**API Gateway**:
- Authorization: AWS_IAM (requires signed requests)
- Prevents anonymous access
- Integrates with AWS IAM users/roles

**Rate Limiting**:
- Default AWS account limits apply
- Recommendation: Configure per-key throttling
  ```yaml
  ApiGatewayUsagePlan:
    Type: AWS::ApiGateway::UsagePlan
    Properties:
      Throttle:
        RateLimit: 100
        BurstLimit: 200
  ```

---

## Disaster Recovery

### Backup Strategy

**Lambda Functions**:
- Code stored in Git (version controlled)
- SAM template in Git (infrastructure as code)
- No backup needed (can redeploy from source)

**CloudFormation Stacks**:
- Export stack templates periodically
- Store in S3 versioned bucket

**Configuration**:
- `parameters.json` in Git
- Secrets in AWS Secrets Manager (auto-backed up)

### Recovery Process

**Full Environment Rebuild**:
```bash
# 1. Restore parameters.json from Git
git checkout main

# 2. Redeploy stack
cd SAM-UVA-App-Integrations
./deploy.sh

# 3. Verify deployment
sam list stack-outputs --stack-name SAM-UVA-App-Integrations-main
```

**RTO (Recovery Time Objective)**: < 30 minutes
**RPO (Recovery Point Objective)**: < 1 hour (last Git commit)

---

## Scaling Considerations

### Lambda Auto-scaling

**Concurrency**:
- Default: 1000 concurrent executions (AWS account limit)
- Reserved concurrency: Not configured
- Provisioned concurrency: Not configured (cold starts acceptable)

**DynamoDB Stream Shards**:
- Each shard: ~2000 records/second
- Lambda concurrency = number of shards
- Auto-scales with DynamoDB table

### API Gateway Scaling

**Limits**:
- Regional endpoint: 10,000 requests/second (default)
- Burst capacity: 5,000 requests
- Can request limit increase via AWS Support

### Bottlenecks

**Current**:
1. **Organization table Scan**: Full table scan for linkage code lookup
   - Solution: Add GSI on `linkage_code`

2. **AppSync API rate limits**: External dependency
   - Solution: Implement exponential backoff and retry

3. **Lambda cold starts**: ~2-3 seconds
   - Solution: Provisioned concurrency (if < 100ms latency required)

---

## Maintenance

### Regular Tasks

**Weekly**:
- Review CloudWatch Logs for errors
- Check Lambda duration metrics (optimize if > 5 seconds)

**Monthly**:
- Review CloudWatch costs (logs storage)
- Update Lambda dependencies (boto3, requests)
- Rotate API keys (if using)

**Quarterly**:
- Review IAM permissions (least privilege)
- Update Python runtime version
- Load test API endpoints

### Updates and Patches

**Lambda Runtime**:
- Current: Python 3.9
- Update process: Change `Runtime` in SAM template → redeploy

**Dependencies**:
```bash
# Update requirements.txt
pip install --upgrade boto3 requests

# Test locally
sam build
sam local invoke FunctionName -e events/test.json

# Deploy
sam deploy
```

**SAM CLI**:
```bash
pip install --upgrade aws-sam-cli
```

---

## Troubleshooting

### Common Issues

**Issue**: Lambda timeout (600s exceeded)
**Solution**:
- Check AppSync/DynamoDB latency
- Review CloudWatch Logs for bottlenecks
- Consider async processing for long operations

**Issue**: DynamoDB Stream iterator age increasing
**Solution**:
- Check Lambda errors (failing functions retry)
- Increase Lambda concurrency
- Review batch size (reduce from 10 to 5)

**Issue**: API Gateway 403 Forbidden
**Solution**:
- Verify AWS credentials (IAM authorization)
- Check API Gateway resource policy
- Ensure request is signed with SigV4

### Debugging Commands

```bash
# View Lambda logs
sam logs -n DynamoDBEventProcessorFunction --tail

# Invoke function locally
sam local invoke UVALastConnection -e events/api-event.json

# Start local API
sam local start-api

# Validate template
sam validate --lint

# Check stack status
aws cloudformation describe-stacks --stack-name SAM-UVA-App-Integrations-develop
```

---

## References

**AWS Documentation**:
- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)

**Internal Documentation**:
- [Architecture](architecture.md)
- [Lambda Functions](lambdas.md)
- [Database Schema](database.md)
