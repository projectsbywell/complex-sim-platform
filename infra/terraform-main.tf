terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "3.0.2"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
  }
  required_version = ">= 1.0"
}

provider "docker" {}

provider "kubernetes" {
  host                   = var.k8s_endpoint
  cluster_ca_certificate = base64decode(var.k8s_ca_cert)
  token                  = var.k8s_token
}

# Variables
variable "k8s_endpoint" {
  description = "Kubernetes API endpoint"
  type        = string
}
variable "k8s_ca_cert" {
  description = "Kubernetes CA certificate (base64)"
  type        = string
}
variable "k8s_token" {
  description = "Kubernetes authentication token"
  type        = string
  sensitive   = true
}
variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}
variable "region" {
  description = "Cloud region"
  type        = string
  default     = "us-east-1"
}

# Local Docker network for dev
resource "docker_network" "simnet" {
  name = "complexsim-net"
  driver = "bridge"
  ipam_config {
    subnet = "172.28.0.0/16"
  }
  labels = {
    project = "complex-sim-platform"
    environment = var.environment
  }
}

# Docker image for API
resource "docker_image" "api" {
  name = "complexsim-api:1.0.0"
}

# API service (local dev)
resource "docker_container" "api" {
  name  = "complexsim-api"
  image = docker_image.api.latest
  ports {
    internal = 8000
    external = 8000
  }
  env_vars = {
    DATABASE_URL = "postgresql://sim:sim@postgres:5432/simdb"
    REDIS_URL    = "redis://redis:6379"
    SIMCORE_PATH = "/app/simulation-core"
  }
  networks_advanced = [{ name = docker_network.simnet.name }]
  restart_policy    = "always"
  depends_on        = [docker_container.postgres, docker_container.redis]
}

# PostgreSQL service
resource "docker_container" "postgres" {
  name  = "complexsim-postgres"
  image = "timescale/timescaledb:latest-pg16"
  ports {
    internal = 5432
    external = 5432
  }
  env_vars = {
    POSTGRES_USER     = "sim"
    POSTGRES_PASSWORD = "simssecret"
    POSTGRES_DB       = "simdb"
  }
  volumes {
    container_path = "/var/lib/postgresql/data"
    host_path      = "./data/pgdata"
  }
  networks_advanced = [{ name = docker_network.simnet.name }]
  restart_policy    = "always"
}

# Redis service
resource "docker_container" "redis" {
  name  = "complexsim-redis"
  image = "redis:7-alpine"
  ports {
    internal = 6379
    external = 6379
  }
  networks_advanced = [{ name = docker_network.simnet.name }]
  restart_policy    = "always"
}

# Kubernetes deployment (production)
resource "kubernetes_deployment" "api" {
  metadata {
    name      = "complexsim-api"
    namespace = "complexsim"
    labels = {
      app = "complexsim-api"
    }
  }
  spec {
    replicas = var.environment == "production" ? 3 : 1
    selector {
      match_labels = { app = "complexsim-api" }
    }
    template {
      metadata {
        labels = { app = "complexsim-api" }
      }
      spec {
        container {
          image = "complexsim-api:1.0.0"
          name  = "api"
          port {
            container_port = 8000
          }
          resources {
            requests {
              cpu    = "250m"
              memory = "256Mi"
            }
            limits {
              cpu    = "1000m"
              memory = "512Mi"
            }
          }
          env {
            name  = "DATABASE_URL"
            value = "postgresql://sim:sim@postgres-sim:5432/simdb"
          }
          env {
            name  = "REDIS_URL"
            value = "redis://redis-sim:6379"
          }
          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 30
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "api" {
  metadata {
    name      = "complexsim-api"
    namespace = "complexsim"
  }
  spec {
    type = "LoadBalancer"
    selector = { app = "complexsim-api" }
    port {
      port        = 80
      target_port = 8000
    }
  }
}

# Outputs
output "api_url" {
  value = kubernetes_service.api.status[0].load_balancer_ingress[0].hostname
}
output "postgres_endpoint" {
  value = "postgres-sim:5432"
}
output "redis_endpoint" {
  value = "redis-sim:6379"
}

# Remote state for multi-team usage
terraform {
  backend "s3" {
    bucket = "complexsim-terraform-state"
    key    = "state/terraform.tfstate"
    region = var.region
  }
}
