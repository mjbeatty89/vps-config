# ai-server Terraform

This Terraform stack provisions a local Docker-based service named `ai-server`.

## Usage

```bash
terraform init
terraform plan
terraform apply
```

By default, `ai-server` uses `nginx:stable-alpine` and binds to `127.0.0.1:8080`.
