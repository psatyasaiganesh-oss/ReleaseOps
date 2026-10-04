variable "aws_region" {
  description = "AWS region for the learning lab"
  type        = string
  default     = "ap-south-1"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "subnet_id" {
  description = "Existing public subnet with an internet gateway route"
  type        = string
}

variable "key_name" {
  description = "Existing EC2 SSH key pair name; do not put a private key in Terraform"
  type        = string
}

variable "admin_cidr" {
  description = "Trusted administrator IPv4 CIDR, normally your public IP /32"
  type        = string

  validation {
    condition     = can(cidrnetmask(var.admin_cidr)) && try(tonumber(split("/", var.admin_cidr)[1]) >= 24, false)
    error_message = "Use a valid trusted IPv4 /24 or narrower CIDR."
  }
}

variable "instance_type" {
  description = "EC2 instance type; this template does not assert free-tier eligibility"
  type        = string
  default     = "t3.micro"
}
