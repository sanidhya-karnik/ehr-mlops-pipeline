variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "allowed_security_groups" {
  type = list(string)
}

variable "instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "max_allocated_storage" {
  type    = number
  default = 100
}

variable "database_name" {
  type    = string
  default = "mimic"
}

variable "database_username" {
  type    = string
  default = "mimic"
}

variable "database_password" {
  type      = string
  sensitive = true
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
