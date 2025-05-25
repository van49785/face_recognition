provider "aws" {
  region = "ap-southeast-1"
}

# VPC
resource "aws_vpc" "attendance_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = "attendance-vpc"
  }
}

# Subnet
resource "aws_subnet" "attendance_subnet" {
  vpc_id                  = aws_vpc.attendance_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "ap-southeast-1a"
  map_public_ip_on_launch = true
  tags = {
    Name = "attendance-subnet"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "attendance_igw" {
  vpc_id = aws_vpc.attendance_vpc.id
  tags = {
    Name = "attendance-igw"
  }
}

# Route Table
resource "aws_route_table" "attendance_route_table" {
  vpc_id = aws_vpc.attendance_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.attendance_igw.id
  }

  tags = {
    Name = "attendance-route-table"
  }
}

# Route Table Association
resource "aws_route_table_association" "attendance_route_table_association" {
  subnet_id      = aws_subnet.attendance_subnet.id
  route_table_id = aws_route_table.attendance_route_table.id
}

# Security Group 
resource "aws_security_group" "attendance_sg" {
  name   = "attendance-sg"
  vpc_id = aws_vpc.attendance_vpc.id

  # HTTP
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP"
  }

  # SSH 
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH"
  }

  # PostgreSQL - Chỉ từ VPC
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
    description = "PostgreSQL"
  }

  # Application port
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Application"
  }

  # All outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "attendance-sg"
  }
}

# IAM Role for EC2
resource "aws_iam_role" "ec2_role" {
  name = "attendance_ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "attendance-ec2-role"
  }
}

# IAM Policy for S3 Access 
resource "aws_iam_policy" "ec2_s3_policy" {
  name        = "attendance_s3_policy"
  description = "Policy for EC2 to access S3"

  # Sửa policy 
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.attendance_bucket.arn,
          "${aws_s3_bucket.attendance_bucket.arn}/*"
        ]
      }
    ]
  })
}

# Attach policy to role 
resource "aws_iam_role_policy_attachment" "ec2_s3_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_s3_policy.arn
}

# IAM Instance Profile 
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "attendance_ec2_profile"
  role = aws_iam_role.ec2_role.name
}

# S3 Bucket 
resource "aws_s3_bucket" "attendance_bucket" {
  bucket = "face-attendance-bucket-${random_string.bucket_suffix.result}"
}

# Random string cho bucket name
resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

# S3 Bucket versioning
resource "aws_s3_bucket_versioning" "attendance_bucket_versioning" {
  bucket = aws_s3_bucket.attendance_bucket.id
  versioning_configuration {
    status = "Suspended"
  }
}

# S3 Bucket public access block
resource "aws_s3_bucket_public_access_block" "attendance_bucket_pab" {
  bucket = aws_s3_bucket.attendance_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Key Pair 
resource "aws_key_pair" "attendance_key" {
  key_name   = "attendance-key"
  public_key = file("./keypair/myKeypair.pub")
}

# EC2 Instance
resource "aws_instance" "attendance_ec2" {
  ami                    = "ami-0afc7fe9be84307e4"
  instance_type          = "t2.micro"
  subnet_id              = aws_subnet.attendance_subnet.id
  vpc_security_group_ids = [aws_security_group.attendance_sg.id]
  key_name               = aws_key_pair.attendance_key.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  # User data 
  user_data = <<-EOF
        #!/bin/bash
        yum update -y
        yum install -y docker
        service docker start
        usermod -a -G docker ec2-user
        
        # Install Docker Compose
        sudo yum install -y libxcrypt-compat
        curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
        
        # Enable Docker to start on boot
        chkconfig docker on
    EOF

  tags = {
    Name = "attendance-ec2"
  }
}

# Outputs
output "vpc_id" {
  value = aws_vpc.attendance_vpc.id
}

output "ec2_public_ip" {
  value = aws_instance.attendance_ec2.public_ip
}

output "s3_bucket_name" {
  value = aws_s3_bucket.attendance_bucket.bucket
}

output "ssh_command" {
  value = "ssh -i ./keypair/myKeypair ec2-user@${aws_instance.attendance_ec2.public_ip}"
}
