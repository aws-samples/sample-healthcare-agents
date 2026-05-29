# QuickSight VPC Access Setup Guide

## Overview

This document covers the IAM roles, permissions, and configuration needed to enable Amazon QuickSight to access Aurora PostgreSQL in a private VPC.

## Prerequisites

- QuickSight **Enterprise Edition** (VPC connections require Enterprise)
- Aurora PostgreSQL cluster in private VPC
- AWS CLI access with appropriate permissions

## Step 1: QuickSight Service Role

QuickSight needs an IAM service role to create network interfaces in your VPC.

### Check Existing Role

```bash
aws iam list-roles \
  --query 'Roles[?contains(RoleName, `quicksight`)].{Name:RoleName,Arn:Arn}' \
  --output json \
  --profile quicksuite
```

**Expected Output:**
```json
[
  {
    "Name": "aws-quicksight-service-role-v0",
    "Arn": "arn:aws:iam::000000000000:role/service-role/aws-quicksight-service-role-v0"
  }
]
```

### Required Permissions

The QuickSight service role needs these EC2 permissions to create VPC connections:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:ModifyNetworkInterfaceAttribute",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeNetworkInterfaces"
      ],
      "Resource": "*"
    }
  ]
}
```

### Add VPC Permissions to Role

```bash
cat > /tmp/quicksight-vpc-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:ModifyNetworkInterfaceAttribute",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeNetworkInterfaces"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name aws-quicksight-service-role-v0 \
  --policy-name QuickSight-VPC-Connection-Policy \
  --policy-document file:///tmp/quicksight-vpc-policy.json \
  --profile quicksuite
```

## Step 2: Get VPC Configuration

Retrieve your VPC details from SSM parameters:

```bash
# Get VPC subnet IDs
aws ssm get-parameter \
  --name /healthcare-agents-stack/safety_analysis/vpc_subnet_ids \
  --query 'Parameter.Value' \
  --output text \
  --profile quicksuite

# Output: subnet-0c1c2db1776d0124d,subnet-093d1567c6d98b3d1

# Get security group ID
aws ssm get-parameter \
  --name /healthcare-agents-stack/safety_analysis/db_security_group_id \
  --query 'Parameter.Value' \
  --output text \
  --profile quicksuite

# Output: sg-06159205b2f9741d9
```

## Step 3: Create QuickSight VPC Connection

Create a VPC connection that allows QuickSight to reach your private Aurora cluster:

```bash
VPC_CONN_ID="safety-analysis-vpc-$(date +%s)"

aws quicksight create-vpc-connection \
  --aws-account-id 000000000000 \
  --vpc-connection-id "$VPC_CONN_ID" \
  --name "safety-analysis-aurora-vpc" \
  --role-arn "arn:aws:iam::000000000000:role/service-role/aws-quicksight-service-role-v0" \
  --subnet-ids subnet-0c1c2db1776d0124d subnet-093d1567c6d98b3d1 \
  --security-group-ids sg-06159205b2f9741d9 \
  --region us-east-1 \
  --output json

# Save the VPC Connection ID from output
echo "VPC Connection ID: $VPC_CONN_ID"
```

**Expected Output:**
```json
{
  "Status": 202,
  "Arn": "arn:aws:quicksight:us-east-1:000000000000:vpcConnection/safety-analysis-vpc-1769666412",
  "CreationStatus": "CREATION_IN_PROGRESS",
  "AvailabilityStatus": "UNAVAILABLE",
  "RequestId": "..."
}
```

## Step 4: Verify VPC Connection Status

Wait 1-2 minutes, then check status:

```bash
aws quicksight describe-vpc-connection \
  --aws-account-id 000000000000 \
  --vpc-connection-id safety-analysis-vpc-1769666412 \
  --region us-east-1 \
  --query 'VPCConnection.{Name:Name,Status:Status,AvailabilityStatus:AvailabilityStatus}' \
  --output json \
  --profile quicksuite
```

**Expected Output:**
```json
{
  "Name": "safety-analysis-aurora-vpc",
  "Status": "CREATION_SUCCESSFUL",
  "AvailabilityStatus": "AVAILABLE"
}
```

## Step 5: Connect QuickSight to Aurora

### Using QuickSight Console

1. Go to QuickSight: https://us-east-1.quicksight.aws.amazon.com/
2. Click **Datasets** → **New dataset**
3. Select **PostgreSQL**
4. **IMPORTANT**: Click the **"VPC connections"** tab (not "Connection to database")
5. Fill in:
   - **VPC connection**: Select `safety-analysis-aurora-vpc`
   - **Database server**: `healthcare-agents-stack-safety-analysis.cluster-caf4ka0sc2qj.us-east-1.rds.amazonaws.com`
   - **Port**: `5432`
   - **Database name**: `safety_analysis`
   - **Username**: `postgres`
   - **Password**: Get from Secrets Manager (see below)

### Get Database Password

```bash
SECRET_ARN=$(aws ssm get-parameter \
  --name /healthcare-agents-stack/safety_analysis/db_secret_arn \
  --query 'Parameter.Value' \
  --output text \
  --profile quicksuite)

aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --query 'SecretString' \
  --output text \
  --profile quicksuite | jq -r '.password'
```

## What Gets Created

When you create a VPC connection, QuickSight automatically creates:

1. **Elastic Network Interfaces (ENIs)** - One in each specified subnet
2. **Security Group Association** - Attaches ENIs to your security group
3. **Network Routes** - Enables communication between QuickSight and Aurora

### View Created Network Interfaces

```bash
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=*QuickSight*" \
  --query 'NetworkInterfaces[*].{Id:NetworkInterfaceId,Subnet:SubnetId,Status:Status,PrivateIP:PrivateIpAddress}' \
  --output table \
  --profile quicksuite
```

## Security Configuration

### What's Secure ✅

- Aurora remains in **private isolated subnets**
- No public IP addresses
- No internet gateway access
- Only QuickSight ENIs can connect (via security group)
- Data encrypted in transit (SSL/TLS)
- Data encrypted at rest (KMS)

### Aurora Security Group Rules

The Aurora security group allows:
1. ✅ Connections from VPC CIDR (for Lambda replicators)
2. ✅ Connections from QuickSight security group (via VPC connection ENIs)
3. ❌ No public internet access

## Troubleshooting

### Error: "AccessDeniedException: describeSubnets"

**Cause**: QuickSight role lacks EC2 permissions

**Solution**: Add VPC policy to QuickSight role (see Step 1)

### Error: "Connection timeout"

**Cause**: Security group not allowing QuickSight ENIs

**Solution**: Verify security group allows ingress on port 5432 from itself:
```bash
aws ec2 describe-security-groups \
  --group-ids sg-06159205b2f9741d9 \
  --query 'SecurityGroups[0].IpPermissions' \
  --profile quicksuite
```

### VPC Connection stuck in "CREATION_IN_PROGRESS"

**Cause**: IAM role or subnet issues

**Solution**: Check CloudTrail logs for errors:
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=safety-analysis-vpc-1769666412 \
  --profile quicksuite
```

## Cost Considerations

### QuickSight VPC Connection Costs

- **ENI Cost**: ~$0.01/hour per ENI (2 ENIs = ~$0.02/hour)
- **Data Transfer**: Standard VPC data transfer rates apply
- **Monthly Cost**: ~$14.40/month for VPC connection

### Aurora Costs

- Staying in private subnets = **no additional costs**
- Public accessibility would require NAT Gateway (~$32/month + data transfer)

## Cleanup

To delete the VPC connection:

```bash
aws quicksight delete-vpc-connection \
  --aws-account-id 000000000000 \
  --vpc-connection-id safety-analysis-vpc-1769666412 \
  --region us-east-1 \
  --profile quicksuite
```

## Summary Checklist

- [x] QuickSight Enterprise Edition enabled
- [x] QuickSight service role has EC2 VPC permissions
- [x] VPC connection created with correct subnets and security group
- [x] VPC connection status = "AVAILABLE"
- [x] Aurora remains in private subnets (secure)
- [x] QuickSight data source configured with VPC connection
- [x] Connection validated successfully

## Reference

- **VPC Connection ID**: `safety-analysis-vpc-1769666412`
- **VPC Connection Name**: `safety-analysis-aurora-vpc`
- **Aurora Endpoint**: `healthcare-agents-stack-safety-analysis.cluster-caf4ka0sc2qj.us-east-1.rds.amazonaws.com`
- **Database**: `safety_analysis`
- **QuickSight Service Role**: `arn:aws:iam::000000000000:role/service-role/aws-quicksight-service-role-v0`
