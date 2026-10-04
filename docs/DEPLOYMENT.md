# Deployment setup

## Local container host

Use Linux/WSL with Docker Compose v2, Python 3.12+, Bash and `flock`. Keep Docker image updates separate from database recovery. The scripts bind application ports to loopback.

```bash
docker build --build-arg VERSION=1.0.0 -t releaseops:1.0.0 .
PULL_IMAGE=0 bash scripts/deploy.sh staging releaseops:1.0.0
PULL_IMAGE=0 bash scripts/deploy.sh production releaseops:1.0.0
```

Staging: `http://localhost:18081`, token `.deploy/staging/api-token`.
Production lab: `http://localhost:18080`, token `.deploy/production/api-token`.

Each environment uses its own volume (`releaseops_staging_data` or `releaseops_production_data`). Never use `down -v` on a persistent environment unless you intend to delete its stored data.

When pulling from a private registry, first authenticate with credentials allowed to read that image. Do not put a registry token in a Git-tracked file. The GitHub deployment job uses its short-lived `GITHUB_TOKEN` and clears the Docker login afterward.

## Connect GitHub delivery

1. Create a repository and upload this source, including `.github/workflows`, on branch `main`.
2. Enable Actions and package publication. Checks run on pull requests and main pushes. A main push publishes the image after application, container, browser, and infrastructure checks pass.
3. In repository settings, create environments named `staging` and `production`. Restrict deployment branches to `main`. Configure production required reviewers when supported by the repository’s GitHub plan.
4. Use a **private repository** for the learning runner. On the host install Git, Python 3.12+, Docker, Docker Compose v2, and `flock`. Confirm Docker access for the non-root runner user. Docker daemon access is privileged host access.
5. Create `/opt/releaseops/state`, owned by the runner user and mode 700. Keep it outside the repository checkout.
6. Under Settings → Actions → Runners → New self-hosted runner, choose Linux x64 and follow GitHub’s generated install/registration commands. Assign the custom label `releaseops`. Run it as a service using the supplied runner service instructions.
7. Run the workflow on `main` with `deploy_environment=staging`. Once tested, run it with `production`. A digest identifies the exact published image.

The runner needs outbound HTTPS to GitHub/registry and access to the local Docker daemon. It does not need inbound GitHub webhook ports. Never attach this privileged runner to untrusted pull-request jobs. This workflow uses hosted runners for PR checks and permits deployment only from a main-branch manual run.

The workflow deploys the main commit selected at dispatch. To redeploy an older image independently, use the host’s rollback script. Staging promotion and production dispatch are separate runs, so verify the desired main commit before dispatch; this is not an automatic promotion of the exact previously tested staging image across later main changes.

## Optional EC2 host

The Terraform template needs an existing VPC, a public subnet with an internet gateway route, an existing SSH key pair, AWS credentials supplied through the usual AWS credential chain, and the administrator’s public IPv4 `/32`.

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars
# Edit the copied values for your own account and network.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=lab.tfplan
# Review the plan and account costs before running:
terraform apply lab.tfplan
```

Only you can provide actual account/network values. The template installs Docker and creates `/opt/releaseops/state` for `ec2-user`. Reconnect after bootstrap so group membership takes effect. Install Docker Compose from its official release instructions, verify the downloaded release checksum, and check `docker compose version` before registering a runner.

Amazon Linux versions can ship an older default Python. Check `python3 --version` and install/use Python 3.12+ for the app/rehearsal, or run the application in its Python 3.13 container. Host deployment/recording scripts use only standard-library features and do not install Python packages.

The template does not install a runner, run Terraform automatically, create TLS/public application access, claim free-tier eligibility, configure a remote Terraform backend, or create backups. Retain `.terraform.lock.hcl` once `terraform init` generates it. For team use, configure a remote backend and state locking before managing shared infrastructure.

Access the private dashboard with the Terraform output’s SSH tunnel command, substituting your actual private-key path. Open `http://localhost:18081` or `http://localhost:18080` while the tunnel is active.

When finished, review `terraform plan -destroy`, then `terraform destroy`. EC2 replacement or destruction also deletes this template’s root-disk data and Docker volumes: export backups before doing so. Self-hosted runner registration should be removed when you retire the host.

## Reference documentation

- [GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [GitHub self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)
- [Docker Compose readiness waiting](https://docs.docker.com/reference/cli/docker/compose/up/)
- [Docker Compose installation](https://docs.docker.com/compose/install/)
- [Amazon Linux 2023 on EC2](https://docs.aws.amazon.com/linux/al2023/ug/ec2.html)
- [AWS Terraform instance resource](https://registry.terraform.io/providers/hashicorp/aws/6.21.0/docs/resources/instance)
