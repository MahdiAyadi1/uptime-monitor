variable "location" {
  type    = string
  default = "westeurope"
}

variable "dns_label" {
  type        = string
  description = "Unique DNS prefix: <label>.<region>.cloudapp.azure.com"
}

variable "ssh_public_key" {
  type = string
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "Who may reach port 22, e.g. 203.0.113.7/32 (or * for anyone)"
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}