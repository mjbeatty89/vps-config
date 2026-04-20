resource "docker_image" "ai_server" {
  name         = var.ai_server_image
  keep_locally = true
}

resource "docker_network" "ai_server_private" {
  name = "${var.ai_server_container_name}-network"
}

resource "docker_container" "ai_server" {
  name    = var.ai_server_container_name
  image   = docker_image.ai_server.image_id
  restart = "unless-stopped"

  env = [
    "ENVIRONMENT=${var.environment}",
  ]

  labels {
    label = "environment"
    value = local.common_labels.environment
  }

  labels {
    label = "managed_by"
    value = local.common_labels.managed_by
  }

  labels {
    label = "service"
    value = local.common_labels.service
  }

  networks_advanced {
    name = docker_network.ai_server_private.name
  }

  ports {
    internal = var.ai_server_internal_port
    external = var.ai_server_external_port
    ip       = "127.0.0.1"
    protocol = "tcp"
  }
}
