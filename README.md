# UVA-App-Integrations

## Project Description

UVA-App-Integrations is a serverless microservice that bridges the **UVA (Universal Vitals Application)** IoT device ecosystem with MakeSens cloud services. It solves the business problem of **real-time device data synchronization**, **connection monitoring**, and **organizational device management** across distributed sensor networks.

## Purpose

This repository provides the integration layer that:
- Processes and distributes real-time measurement data from UVA devices
- Synchronizes UVA devices with MakeSensCloud for centralized management
- Monitors device connection status for maintenance and alerting
- Manages RACIMO (device cluster) configurations for organizational hierarchy

## Main Functionalities

- **Real-time Data Processing**: Streams device measurements from DynamoDB to SNS for downstream consumers
- **Device Synchronization**: Automatically creates and updates device records in MakeSensCloud when UVA devices are registered
- **Location Management**: Tracks and updates geographic coordinates for UVA devices
- **Connection Monitoring**: REST API endpoint to check if devices are active (connected within last 24 hours)
- **RACIMO Management**: REST API for creating device clusters with linkage codes
- **Multi-Environment Support**: Separate configurations for develop, test, and production environments

## Basic Commands

### Prerequisites
- Python 3.9
- AWS SAM CLI
- AWS credentials configured
- jq (for JSON processing)

### Installation/Setup
```bash
# Clone the repository
git clone <repository-url>
cd UVA-App-Integrations/SAM-UVA-App-Integrations

# Install AWS SAM CLI (if not already installed)
pip install aws-sam-cli

# Install dependencies for local testing
pip install boto3 requests
```

### Deploy to AWS
```bash
# Navigate to SAM directory
cd SAM-UVA-App-Integrations

# Deploy using automated script (detects branch for environment)
./deploy.sh

# Or deploy manually to specific environment
sam build
sam deploy --config-env develop  # or test, main
```

### Local Testing
```bash
# Build the application
sam build

# Invoke a Lambda function locally
sam local invoke DynamoDBEventProcessorFunction -e events/dynamodb-event.json

# Start local API
sam local start-api
```

### Run Tests
```bash
# Navigate to lambda directory
cd SAM-UVA-App-Integrations/lambdas/<function-name>

# Run unit tests (when available)
python -m pytest tests/
```

## General Architecture

### High-Level Components

```
┌─────────────────┐
│  DynamoDB       │
│  - Measurement  │──Stream──┐
│  - UVA          │──Stream──┤
│  - RACIMO       │          │
│  - Organization │          │
│  - Location     │          │
└─────────────────┘          │
                             ▼
                    ┌─────────────────────┐
                    │   Lambda Functions  │
                    │  ┌───────────────┐  │
                    │  │ Device Data   │──┼──► SNS Topic
                    │  │ Processor     │  │
                    │  ├───────────────┤  │
                    │  │ UVA to Cloud  │──┼──► AppSync (Cloud)
                    │  ├───────────────┤  │
                    │  │ Connection    │◄─┼──  API Gateway
                    │  │ Status        │  │
                    │  ├───────────────┤  │
                    │  │ Create        │◄─┼──  API Gateway
                    │  │ RACIMO        │  │
                    │  └───────────────┘  │
                    └─────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  AWS AppSync    │
                    │  (GraphQL APIs) │
                    └─────────────────┘
```

### Data Flow
1. **Measurement Stream**: UVA devices write measurements to DynamoDB → Stream triggers Lambda → Publishes to SNS
2. **Device Sync**: New UVA registered → Stream triggers Lambda → Creates device in MakeSensCloud via GraphQL
3. **Connection Check**: API request → Lambda queries AppSync → Returns connection status
4. **RACIMO Creation**: API request → Lambda checks/creates RACIMO → Returns cluster ID

## Main Technologies

### Cloud Platform
- **AWS Lambda**: Serverless compute for event processing
- **AWS SAM**: Infrastructure as code and deployment
- **Amazon DynamoDB**: NoSQL database with streams
- **Amazon SNS**: Message publishing for real-time data
- **AWS AppSync**: GraphQL API for data synchronization
- **API Gateway**: REST API endpoints
- **AWS IAM**: Authentication and authorization

### Development
- **Python 3.9**: Primary programming language
- **boto3**: AWS SDK for Python
- **requests**: HTTP client for GraphQL operations
- **GitHub Actions**: CI/CD automation

### DevOps
- **CloudFormation**: Infrastructure provisioning
- **Bash**: Deployment automation
- **jq**: JSON parameter processing

## Repository Structure

```
UVA-App-Integrations/
├── .github/workflows/       # CI/CD pipelines for test and main environments
├── SAM-UVA-App-Integrations/
│   ├── lambdas/
│   │   ├── cloud/          # UVA to MakeSensCloud integration
│   │   ├── createRacimo/   # RACIMO cluster management
│   │   ├── deviceDataAccess/# Real-time data streaming
│   │   └── uvaConnection/  # Connection status monitoring
│   ├── deploy.sh           # Automated deployment script
│   ├── parameters.json     # Environment-specific configuration
│   └── template.yaml       # SAM CloudFormation template
├── docs/                   # Detailed technical documentation
└── README.md              # This file
```

## Documentation

For detailed technical documentation, see the `/docs` folder:
- [Architecture](docs/architecture.md) - System design and component diagrams
- [Features](docs/features.md) - Detailed functionality descriptions
- [Lambda Functions](docs/lambdas.md) - Lambda function specifications
- [Database](docs/database.md) - DynamoDB schema and data model
- [Infrastructure](docs/infrastructure.md) - AWS resources and configurations

## License

See [LICENSE.txt](LICENSE.txt) for details.

## Support

For issues or questions, please contact the MakeSens development team.
