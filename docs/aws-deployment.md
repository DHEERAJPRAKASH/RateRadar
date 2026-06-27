# AWS ECS Deployment Guide — RateRadar

> Based on actual production setup (eu-north-1, June 2026)

## Architecture Overview

```
Internet → ALB (port 80)
              ├── /rates/*, /auth/*, /health, /ingestion/*, /admin/* → rateradar-web (Django, port 8000)
              └── /* (default) → rateradar-frontend (Next.js, port 3000)

rateradar-web → RDS PostgreSQL (port 5432)
             → ElastiCache Redis (port 6379)

rateradar-worker (Celery) → Redis → PostgreSQL
rateradar-beat (Celery Beat) → Redis → PostgreSQL
```

![RateRadar AWS Architecture](images/Rate_Radar_AWS_Architecture.png)

---

## Prerequisites

### AWS Resources Needed

- ECR (Elastic Container Registry) — 2 repos
- ECS (Elastic Container Service) — 1 cluster, 4 services
- RDS PostgreSQL
- ElastiCache Redis
- ALB (Application Load Balancer)
- S3 (for seed data)
- IAM roles

### One-Time: Create ECS Service Linked Role

This must exist before creating any ECS cluster. Run in CloudShell:

```bash
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com
```

---

## Step 1 — Create IAM User for GitHub Actions

1. Go to **IAM → Users → Create user**
2. Username: `github-actions-deployer`
3. Attach policies:
   - `AmazonECS_FullAccess`
   - `AmazonEC2ContainerRegistryFullAccess`
   - `AmazonS3FullAccess`
4. Create user → **Security credentials → Create access key**
5. Choose **"Application running outside AWS"** → save the keys

---

## Step 2 — Create ECR Repositories

Go to **ECR → Repositories → Create repository** (do twice, keep defaults, Private):

| Repository name      |
| -------------------- |
| `rateradar-web`      |
| `rateradar-frontend` |

Note your account ID from the URIs: `<account-id>.dkr.ecr.<region>.amazonaws.com`

---

## Step 3 — Create Default VPC (if none exists)

Run in CloudShell:

```bash
aws ec2 create-default-vpc --region eu-north-1
```

---

## Step 4 — Create ECS Cluster

Go to **ECS → Clusters → Create cluster**:

- Name: `rateradar`
- Infrastructure: **AWS Fargate**

> If you get a CloudFormation stack error from a previous failed attempt, go to **CloudFormation → delete the failed stack** first, then retry.

---

## Step 5 — Create Task Execution IAM Role

Go to **IAM → Roles → Create role**:

- Trusted entity: **AWS service → Elastic Container Service Task**
- Attach policy: `AmazonECSTaskExecutionRolePolicy`
- Role name: `ecsTaskExecutionRole`

---

## Step 6 — Create RDS PostgreSQL

Run in CloudShell:

```bash
aws rds create-db-instance \
  --db-instance-identifier rateradar-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username rateradar \
  --master-user-password <your-secure-password> \
  --allocated-storage 20 \
  --region eu-north-1 \
  --no-multi-az \
  --publicly-accessible
```

Wait ~5 minutes. Get the endpoint:

```bash
aws rds describe-db-instances \
  --db-instance-identifier rateradar-db \
  --region eu-north-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```

**Allow port 5432 in security group:**
Go to **RDS → rateradar-db → Connectivity & security → Security group → Inbound rules → Edit**:

- Type: `PostgreSQL`, Port: `5432`, Source: `0.0.0.0/0`

**Create the database:**

```bash
psql -h <rds-endpoint> -U rateradar -d postgres -c "CREATE DATABASE rateradar;"
```

> If psql is unavailable: `sudo yum install -y postgresql15`

---

## Step 7 — Create ElastiCache Redis

Run in CloudShell:

```bash
# Get subnet IDs
aws ec2 describe-subnets --region eu-north-1 --query 'Subnets[*].[SubnetId]' --output text

# Create subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name rateradar-redis-subnet \
  --cache-subnet-group-description "Redis subnet for RateRadar" \
  --subnet-ids <subnet-1> <subnet-2> <subnet-3> \
  --region eu-north-1

# Create Redis cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id rateradar-redis \
  --engine redis \
  --cache-node-type cache.t3.micro \
  --num-cache-nodes 1 \
  --cache-subnet-group-name rateradar-redis-subnet \
  --security-group-ids <default-sg-id> \
  --region eu-north-1
```

Get Redis endpoint:

```bash
aws elasticache describe-cache-clusters \
  --cache-cluster-id rateradar-redis \
  --show-cache-node-info \
  --region eu-north-1 \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
  --output text
```

Allow port 6379 in security group:

```bash
aws ec2 authorize-security-group-ingress \
  --group-id <default-sg-id> \
  --protocol tcp \
  --port 6379 \
  --cidr 0.0.0.0/0 \
  --region eu-north-1
```

---

## Step 8 — Upload Seed Data to S3

```bash
# Create bucket
aws s3 mb s3://rateradar-seed-data --region eu-north-1
```

Via console: **S3 → rateradar-seed-data → Upload** the `rates_seed.parquet` file (32MB, at project root).

---

## Step 9 — Create CloudWatch Log Groups

```bash
aws logs create-log-group --log-group-name /ecs/rateradar-web --region eu-north-1
aws logs create-log-group --log-group-name /ecs/rateradar-frontend --region eu-north-1
aws logs create-log-group --log-group-name /ecs/rateradar-worker --region eu-north-1
aws logs create-log-group --log-group-name /ecs/rateradar-beat --region eu-north-1
```

---

## Step 10 — Task Definition JSON Files

Create these 4 files in your **repo root** (not inside backend/). Replace placeholders with your actual values.

### `rateradar-web.json`

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
      "portMappings": [{ "containerPort": 8000, "protocol": "tcp" }],
      "environment": [
        { "name": "DJANGO_DEBUG", "value": "false" },
        { "name": "DJANGO_SECRET_KEY", "value": "<your-secret-key>" },
        { "name": "DJANGO_ALLOWED_HOSTS", "value": "*" },
        { "name": "POSTGRES_HOST", "value": "<rds-endpoint>" },
        { "name": "POSTGRES_DB", "value": "rateradar" },
        { "name": "POSTGRES_USER", "value": "rateradar" },
        { "name": "POSTGRES_PASSWORD", "value": "<your-db-password>" },
        { "name": "RUN_AUTO_SEED", "value": "1" },
        { "name": "REDIS_URL", "value": "redis://<redis-endpoint>:6379" },
        {
          "name": "CELERY_BROKER_URL",
          "value": "redis://<redis-endpoint>:6379"
        },
        {
          "name": "CELERY_RESULT_BACKEND",
          "value": "redis://<redis-endpoint>:6379"
        },
        { "name": "CORS_ALLOWED_ORIGINS", "value": "http://<alb-dns-name>" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-web",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### `rateradar-frontend.json`

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
      "portMappings": [{ "containerPort": 3000, "protocol": "tcp" }],
      "environment": [
        { "name": "NEXT_PUBLIC_API_BASE_URL", "value": "http://<alb-dns-name>" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-frontend",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### `rateradar-worker.json`

```json
{
  "family": "rateradar-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "worker",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/rateradar-web:latest",
      "essential": true,
      "command": ["celery", "-A", "config", "worker", "-l", "info"],
      "environment": [
        { "name": "DJANGO_DEBUG", "value": "false" },
        { "name": "DJANGO_SECRET_KEY", "value": "<your-secret-key>" },
        { "name": "DJANGO_ALLOWED_HOSTS", "value": "*" },
        { "name": "POSTGRES_HOST", "value": "<rds-endpoint>" },
        { "name": "POSTGRES_DB", "value": "rateradar" },
        { "name": "POSTGRES_USER", "value": "rateradar" },
        { "name": "POSTGRES_PASSWORD", "value": "<your-db-password>" },
        { "name": "RUN_MIGRATIONS", "value": "0" },
        { "name": "RUN_AUTO_SEED", "value": "0" },
        { "name": "REDIS_URL", "value": "redis://<redis-endpoint>:6379" },
        {
          "name": "CELERY_BROKER_URL",
          "value": "redis://<redis-endpoint>:6379"
        },
        {
          "name": "CELERY_RESULT_BACKEND",
          "value": "redis://<redis-endpoint>:6379"
        },
        { "name": "CORS_ALLOWED_ORIGINS", "value": "http://<alb-dns-name>" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-worker",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### `rateradar-beat.json`

```json
{
  "family": "rateradar-beat",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "beat",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/rateradar-web:latest",
      "essential": true,
      "command": [
        "celery",
        "-A",
        "config",
        "beat",
        "-l",
        "info",
        "--scheduler",
        "django_celery_beat.schedulers:DatabaseScheduler"
      ],
      "environment": [
        { "name": "DJANGO_DEBUG", "value": "false" },
        { "name": "DJANGO_SECRET_KEY", "value": "<your-secret-key>" },
        { "name": "DJANGO_ALLOWED_HOSTS", "value": "*" },
        { "name": "POSTGRES_HOST", "value": "<rds-endpoint>" },
        { "name": "POSTGRES_DB", "value": "rateradar" },
        { "name": "POSTGRES_USER", "value": "rateradar" },
        { "name": "POSTGRES_PASSWORD", "value": "<your-db-password>" },
        { "name": "RUN_MIGRATIONS", "value": "0" },
        { "name": "RUN_AUTO_SEED", "value": "0" },
        { "name": "REDIS_URL", "value": "redis://<redis-endpoint>:6379" },
        {
          "name": "CELERY_BROKER_URL",
          "value": "redis://<redis-endpoint>:6379"
        },
        {
          "name": "CELERY_RESULT_BACKEND",
          "value": "redis://<redis-endpoint>:6379"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/rateradar-beat",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

---

## Step 11 — GitHub Actions Workflow

Key things in `.github/workflows/deploy-aws.yml`:

1. `NEXT_PUBLIC_API_BASE_URL` must be passed as a **build-arg** (not just env var) because Next.js bakes it at build time
2. Seed parquet must be downloaded from S3 before building the web image
3. Task definition files are referenced by filename (e.g. `rateradar-web.json`)

```yaml
name: Deploy to AWS ECS

on:
  push:
    branches:
      - main
  workflow_dispatch:

env:
  AWS_REGION: eu-north-1
  ECR_REPOSITORY_WEB: rateradar-web
  ECR_REPOSITORY_FRONTEND: rateradar-frontend
  ECS_CLUSTER: rateradar
  ECS_SERVICE_WEB: rateradar-web
  ECS_SERVICE_FRONTEND: rateradar-frontend
  ECS_TASK_DEFINITION_WEB: rateradar-web.json
  ECS_TASK_DEFINITION_FRONTEND: rateradar-frontend.json

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Download seed data from S3
        run: |
          aws s3 cp s3://rateradar-seed-data/rates_seed.parquet backend/rates_seed.parquet

      - name: Build and push web image
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_WEB }}:latest
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_WEB }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push frontend image
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          push: true
          build-args: |
            NEXT_PUBLIC_API_BASE_URL=http://<alb-dns-name>
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_FRONTEND }}:latest
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_FRONTEND }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Fill in new web image ID in task definition
        id: task-def-web
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: ${{ env.ECS_TASK_DEFINITION_WEB }}
          container-name: web
          image: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_WEB }}:${{ github.sha }}

      - name: Fill in new frontend image ID in task definition
        id: task-def-frontend
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: ${{ env.ECS_TASK_DEFINITION_FRONTEND }}
          container-name: frontend
          image: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY_FRONTEND }}:${{ github.sha }}

      - name: Deploy web to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: ${{ steps.task-def-web.outputs.task-definition }}
          service: ${{ env.ECS_SERVICE_WEB }}
          cluster: ${{ env.ECS_CLUSTER }}
          wait-for-service-stability: true

      - name: Deploy frontend to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: ${{ steps.task-def-frontend.outputs.task-definition }}
          service: ${{ env.ECS_SERVICE_FRONTEND }}
          cluster: ${{ env.ECS_CLUSTER }}
          wait-for-service-stability: true
```

---

## Step 12 — Frontend Dockerfile (critical)

`NEXT_PUBLIC_*` env vars are baked at **build time** in Next.js. The `ARG` must be declared in the **builder stage** before `RUN npm run build`:

```dockerfile
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# MUST be here — before npm run build
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build
```

Default value (`localhost:8000`) is used locally. GitHub Actions overrides via `build-args`.

---

## Step 13 — ALB Setup

### Create Target Groups (IP type, not Instance)

Go to **EC2 → Target Groups → Create** (twice):

| Name                    | Port | Health check path |
| ----------------------- | ---- | ----------------- |
| `rateradar-web-tg`      | 8000 | `/health`         |
| `rateradar-frontend-tg` | 3000 | `/`               |

> Target type must be **IP addresses** for Fargate.
> Don't register targets manually — ECS registers them automatically.

### Create ALB

**EC2 → Load Balancers → Create → Application Load Balancer**:

- Scheme: Internet-facing
- Subnets: all available
- Listener HTTP:80 → default forward to `rateradar-frontend-tg`

### Add API Routing Rule

```bash
LISTENER_ARN=$(aws elbv2 describe-listeners --region eu-north-1 \
  --load-balancer-arn $(aws elbv2 describe-load-balancers --names rateradar-alb \
  --region eu-north-1 --query 'LoadBalancers[0].LoadBalancerArn' --output text) \
  --query 'Listeners[0].ListenerArn' --output text)

aws elbv2 create-rule \
  --listener-arn $LISTENER_ARN \
  --priority 2 \
  --conditions '[{"Field":"path-pattern","Values":["/rates/*","/auth/*","/health","/ingestion/*","/admin/*"]}]' \
  --actions '[{"Type":"forward","TargetGroupArn":"<web-target-group-arn>"}]' \
  --region eu-north-1
```

---

## Step 14 — Create ECS Services

### Web (with ALB)

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-web \
  --task-definition rateradar-web \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-ids>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<web-tg-arn>,containerName=web,containerPort=8000" \
  --region eu-north-1
```

### Frontend (with ALB)

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-frontend \
  --task-definition rateradar-frontend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-ids>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<frontend-tg-arn>,containerName=frontend,containerPort=3000" \
  --region eu-north-1
```

### Worker (no ALB)

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-worker \
  --task-definition rateradar-worker \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-ids>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --region eu-north-1
```

### Beat (no ALB)

```bash
aws ecs create-service \
  --cluster rateradar \
  --service-name rateradar-beat \
  --task-definition rateradar-beat \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-ids>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --region eu-north-1
```

---

## Step 15 — GitHub Secrets

Go to **GitHub repo → Settings → Secrets and variables → Actions**:

| Secret                  | Value               |
| ----------------------- | ------------------- |
| `AWS_ACCESS_KEY_ID`     | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `AWS_REGION`            | `eu-north-1`        |

---

## Step 16 — Register Worker/Beat Task Definitions

These aren't in the GitHub Actions workflow (only web and frontend are). Register manually via CloudShell after pushing the JSON files to GitHub:

```bash
aws ecs register-task-definition \
  --cli-input-json "$(curl -s https://raw.githubusercontent.com/<your-github-username>/<repo>/main/rateradar-worker.json)" \
  --region eu-north-1

aws ecs register-task-definition \
  --cli-input-json "$(curl -s https://raw.githubusercontent.com/<your-github-username>/<repo>/main/rateradar-beat.json)" \
  --region eu-north-1
```

---

## Troubleshooting

### ECS Service Linked Role Missing

```
Unable to assume the service linked role
```

Fix: `aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com`

### CloudFormation Stack Conflict

```
A CloudFormation stack already exists for a failed cluster
```

Fix: Go to **CloudFormation → delete the failed stack**, then retry.

### Container Exit Code 1 — Missing Env Var

Check CloudWatch logs: **CloudWatch → Log groups → /ecs/rateradar-web → latest stream**
Add the missing env var to `rateradar-web.json` and push.

### Health Check Returning 503

The `/health` endpoint checks both DB and Redis. If either is unreachable, it returns 503 and ECS kills the task. Ensure:

- RDS security group allows port 5432
- ElastiCache security group allows port 6379
- Correct env vars: `POSTGRES_HOST`, `REDIS_URL`

### Frontend Still Calling localhost:8000

`NEXT_PUBLIC_*` vars are baked at build time. Must pass via `build-args` in GitHub Actions workflow, not just ECS env vars. If cache is stale, add `no-cache: true` temporarily to the frontend build step.

### ALB 503 — No Healthy Targets

ECS service must be created **with** `--load-balancers` flag pointing to the target group. Services created without it won't register with ALB. Delete and recreate the service with the load balancer attached.

### Parquet Seed File is 0 Bytes

The `rates_seed.parquet` placeholder in `backend/` is empty. The real file is at the project root. Upload it to S3 and add a download step in the workflow before building the web image.

---

## Re-triggering Seed Manually

If seed data is missing after deployment:

```bash
aws ecs run-task \
  --cluster rateradar \
  --task-definition rateradar-web \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-id>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"web","command":["python","manage.py","seed_data","--path","/app/rates_seed.parquet"],"environment":[{"name":"RUN_MIGRATIONS","value":"0"},{"name":"RUN_AUTO_SEED","value":"0"}]}]}' \
  --region eu-north-1
```

Watch worker logs:

```bash
aws logs tail /ecs/rateradar-worker --region eu-north-1 --follow --filter-pattern "seed"
```

---

## Security Hardening (TODO for production)

- Move secrets to **AWS Secrets Manager** or **SSM Parameter Store** instead of plaintext in task definitions
- Restrict security groups to only allow traffic between services (not `0.0.0.0/0`)
- Generate a proper `DJANGO_SECRET_KEY` (50+ random chars)
- Set up HTTPS via ACM + Route 53
- Enable **CloudWatch Container Insights**
- Set log retention (CloudWatch → Log groups → Edit retention)
