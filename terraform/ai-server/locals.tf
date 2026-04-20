locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    service     = var.ai_server_container_name
  }
}
