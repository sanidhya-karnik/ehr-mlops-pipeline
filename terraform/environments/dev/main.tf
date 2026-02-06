# =============================================================================
# Dev Environment - Combines All Modules
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

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# VPC
module "vpc" {
  source = "../../modules/vpc"

  project              = var.project
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  enable_nat_gateway   = var.enable_nat_gateway
  tags                 = local.common_tags
}

# EKS
module "eks" {
  source = "../../modules/eks"

  project             = var.project
  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  public_subnet_ids   = module.vpc.public_subnet_ids
  private_subnet_ids  = module.vpc.private_subnet_ids
  kubernetes_version  = var.kubernetes_version
  node_instance_types = var.node_instance_types
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
  tags                = local.common_tags

  depends_on = [module.vpc]
}

# S3
module "s3" {
  source = "../../modules/s3"

  project     = var.project
  environment = var.environment
  tags        = local.common_tags
}

# SQS
module "sqs" {
  source = "../../modules/sqs"

  project     = var.project
  environment = var.environment
  tags        = local.common_tags
}

# RDS
module "rds" {
  source = "../../modules/rds"

  project                 = var.project
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.private_subnet_ids
  allowed_security_groups = [module.eks.cluster_security_group_id]
  instance_class          = var.rds_instance_class
  database_name           = "mimic"
  database_username       = "mimic"
  database_password       = var.database_password
  multi_az                = false
  tags                    = local.common_tags

  depends_on = [module.vpc]
}
