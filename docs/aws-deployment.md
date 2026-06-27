# AWS ECS Deployment Guide

## Prerequisites

1. AWS Account with permissions for:
   - ECR (Elastic Container Registry)
   - ECS (Elastic Container Service)
   - IAM (for task execution roles)

2. GitHub repository with the workflow file added

## AWS Resources Setup

### 1. Create ECR Repositories

```bash
# Login to AWS CLI
aws configure

# Create ECR repositories
aws ecr create-repository --repository-name rateradar-web
aws ecr create-repository --repository-name rateradar-frontend

# Note the repository URIs (format: <account-id>.dkr.ecr.<region>.amazonaws.com/<repo-name>)
```

### 2. Create ECS Cluster

```bash
aws ecs create-cluster --cluster-name rateradar
```

### 3. Create Task Execution Role

Create `ecs-task-execution-role.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

```bash
aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document file://ecs-task-execution-role.json
aws iam attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

### 4. Create Task Definitions

#### Web Task Definition (`rateradar-web.json`)

```json
{
  "family": "rateradar-web",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/rateradar-web:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DJANGO_SECRET_KEY",
          "value": "${DJANGO_SECRET_KEY}"
        },
        {
          "name": "DJANGO_DEBUG",
          "value": "false"
        },
        {
          "name": "DJANGO_ALLOWED_HOSTS",
          "value": "yourdomain.com"
        },
        {
          "name": "POSTGRES_HOST",
          "value": "${POSTGRES_HOST}"
        },
        {
          "name": "POSTGRES_DB",
          "value": "${POSTGRES_DB}"
        },
        {
          "name": "POSTGRES_USER",
          "value": "${POSTGRES_USER}"
        },
        {
          "name": "POSTGRES_PASSWORD",
          "value": "${POSTGRES_PASSWORD}"
        },
        {
          "name": "REDIS_URL",
          "value": "${REDIS_URL}"
        },
        {
          "name": "CELERY_BROKER_URL",
          "value": "${REDIS_URL}"
        },
        {
          "name": "CELERY_RESULT_BACKEND",
          "value": "${REDIS_URL}"
        },
        {
          "name": "CORS_ALLOWED_ORIGINS",
          "value": "https://yourdomain.com"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-web",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

#### Frontend Task Definition (`rateradar-frontend.json`)

```json
{
  "family": "rateradar-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/rateradar-frontend:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 3000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "NEXT_PUBLIC_API_BASE_URL",
          "value": "https://api.yourdomain.com"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-frontend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

```bash
# Register task definitions
aws ecs register-task-definition --cli-input-json file://rateradar-web.json
aws ecs register-task-definition --cli-input-json file://rateradar-frontend.json
```

### 5. Create CloudWatch Log Groups

```bash
aws logs create-log-group --log-group-name /ecs/rateradar-web
aws logs create-log-group --log-group-name /ecs/rateradar-frontend
```

### 6. Create ECS Services

#### Web Service

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-web \
  --task-definition rateradar-web \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-abc123,subnet-def456],securityGroups=[sg-abc123],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:<region>:<account-id>:targetgroup/rateradar-web/abc123,containerName=web,containerPort=8000
```

#### Frontend Service

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-frontend \
  --task-definition rateradar-frontend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-abc123,subnet-def456],securityGroups=[sg-abc123],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:<region>:<account-id>:targetgroup/rateradar-frontend/abc123,containerName=frontend,containerPort=3000
```

## GitHub Secrets Configuration

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Description |
|------------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key with ECR/ECS permissions |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION` | AWS region (e.g., `us-east-1`) |

## Environment Variables in ECS

For production, use AWS Systems Manager Parameter Store or Secrets Manager instead of hardcoding in task definitions:

```bash
# Store secrets in Parameter Store
aws ssm put-parameter --name "/rateradar/DJANGO_SECRET_KEY" --value "your-secret-key" --type "SecureString"
aws ssm put-parameter --name "/rateradar/POSTGRES_PASSWORD" --value "your-db-password" --type "SecureString"

# Reference in task definition
"environment": [
  {
    "name": "DJANGO_SECRET_KEY",
    "valueFrom": "arn:aws:ssm:<region>:<account-id>:parameter/rateradar/DJANGO_SECRET_KEY"
  }
]
```

## Load Balancer Setup

### Create Application Load Balancer

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name rateradar-alb \
  --subnets subnet-abc123 subnet-def456 \
  --security-groups sg-abc123

# Create target groups
aws elbv2 create-target-group \
  --name rateradar-web \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-abc123

aws elbv2 create-target-group \
  --name rateradar-frontend \
  --protocol HTTP \
  --port 3000 \
  --vpc-id vpc-abc123

# Create listeners
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=<frontend-target-group-arn>
```

## SSL/TLS Setup

Use AWS Certificate Manager (ACM) for SSL:

```bash
# Request certificate
aws acm request-certificate \
  --domain-name yourdomain.com \
  --validation-method DNS

# Add CNAME record to your DNS provider for validation

# After validation, create HTTPS listener
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=<cert-arn> \
  --default-actions Type=forward,TargetGroupArn=<frontend-target-group-arn>
```

## Database Setup

Use AWS RDS for PostgreSQL:

```bash
# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier rateradar-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username rateradar \
  --master-user-password <secure-password> \
  --allocated-storage 20 \
  --vpc-security-group-ids sg-abc123 \
  --db-subnet-group-name rateradar-subnet-group
```

## Redis Setup

Use AWS ElastiCache for Redis:

```bash
# Create subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name rateradar-redis-subnet \
  --cache-subnet-group-description "Redis subnet for RateRadar" \
  --subnet-ids subnet-abc123 subnet-def456

# Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id rateradar-redis \
  --engine redis \
  --cache-node-type cache.t3.micro \
  --num-cache-nodes 1 \
  --cache-subnet-group-name rateradar-redis-subnet \
  --security-group-ids sg-abc123
```

## Deployment

1. Push to `main` branch
2. GitHub Actions will:
   - Build and push Docker images to ECR
   - Update ECS task definitions
   - Deploy new tasks to ECS services
3. Monitor deployment in GitHub Actions tab

## Cost Optimization

- Use FARGATE SPOT for non-critical workloads (up to 70% savings)
- Set up auto-scaling for ECS services
- Use RDS and ElastiCache reserved instances for long-running
- Enable CloudWatch Logs retention (e.g., 7 days)

## Monitoring

```bash
# Enable CloudWatch Container Insights
aws ecs update-cluster-settings \
  --cluster rateradar \
  --settings name=containerInsights,value=enabled

# Create CloudWatch dashboards for metrics
# - CPU/Memory utilization
# - Request count
# - Error rates
# - Latency
```
