variable "ai_server_container_name" {
  description = "Name for the ai-server container"
  type        = string
  default     = "ai-server"
}

variable "ai_server_external_port" {
  description = "Host port exposed for ai-server"
  type        = number
  default     = 8080

  validation {
    condition     = var.ai_server_external_port >= 1 && var.ai_server_external_port <= 65535
    error_message = "ai_server_external_port must be in the range 1-65535."
  }
}

variable "ai_server_image" {
  description = "Container image used for ai-server"
  type        = string
  default     = "nginx:stable-alpine"
}

variable "ai_server_internal_port" {
  description = "Container port exposed by ai-server"
  type        = number
  default     = 80

  validation {
    condition     = var.ai_server_internal_port >= 1 && var.ai_server_internal_port <= 65535
    error_message = "ai_server_internal_port must be in the range 1-65535."
  }
}

variable "docker_host" {
  description = "Docker daemon endpoint used by the provider"
  type        = string
  default     = "unix:///var/run/docker.sock"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}
