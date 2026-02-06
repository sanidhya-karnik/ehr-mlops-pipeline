variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "mimic-mlops"
}

variable "environment" {
  type    = string
  default = "dev"
}

# VPC
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "enable_nat_gateway" {
  type    = bool
  default = true
}

# EKS
variable "kubernetes_version" {
  type    = string
  default = "1.29"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_max_size" {
  type    = number
  default = 5
}

# RDS
variable "rds_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "database_password" {
  type      = string
  sensitive = true
}
