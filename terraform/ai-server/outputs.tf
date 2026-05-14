output "ai_server_container_id" {
  description = "ID of the ai-server container"
  value       = docker_container.ai_server.id
}

output "ai_server_container_name" {
  description = "Name of the ai-server container"
  value       = docker_container.ai_server.name
}

output "ai_server_image" {
  description = "Image name used by ai-server"
  value       = docker_image.ai_server.name
}
