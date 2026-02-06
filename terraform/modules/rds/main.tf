# =============================================================================
# RDS Module - PostgreSQL Database
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Security Group
resource "aws_security_group" "rds" {
  name        = "${var.project}-${var.environment}-rds-sg"
  description = "RDS security group"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_groups
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-rds-sg" })
}

# Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-db-subnet"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-db-subnet" })
}

# Parameter Group
resource "aws_db_parameter_group" "main" {
  name   = "${var.project}-${var.environment}-pg15"
  family = "postgres15"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  tags = var.tags
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier = "${var.project}-${var.environment}"

  engine         = "postgres"
  engine_version = "15.4"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.database_name
  username = var.database_username
  password = var.database_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.main.name

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  multi_az               = var.multi_az
  publicly_accessible    = false
  skip_final_snapshot    = var.environment != "prod"
  deletion_protection    = var.environment == "prod"

  performance_insights_enabled = true

  tags = merge(var.tags, { Name = "${var.project}-${var.environment}-rds" })
}
