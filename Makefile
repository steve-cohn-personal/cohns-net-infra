.DEFAULT_GOAL := help
SHELL := /bin/bash

# One root module, three environments. ENV selects the tfvars and backend.
ENV      ?= dev
LIVE_DIR := terraform/live/site
TFVARS   := env/$(ENV).tfvars
BACKEND  := env/$(ENV).backend.hcl

VALID_ENVS := dev stage prod

.PHONY: help check-env init plan apply destroy fmt validate lint sso deploy-site clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Set ENV=dev|stage|prod (currently: $(ENV))"

check-env:
	@echo "$(VALID_ENVS)" | tr ' ' '\n' | grep -qx "$(ENV)" \
		|| { echo "ENV must be one of: $(VALID_ENVS)"; exit 1; }
	@test -f "$(LIVE_DIR)/$(TFVARS)" \
		|| { echo "missing $(LIVE_DIR)/$(TFVARS) — copy the .example and fill it in"; exit 1; }

sso: ## Refresh SSO credentials for ENV
	aws sso login --profile cohns-$(ENV)

init: check-env ## Init with the backend for ENV
	cd $(LIVE_DIR) && terraform init -reconfigure -backend-config=$(BACKEND)

plan: check-env ## Plan ENV
	cd $(LIVE_DIR) && terraform plan -var-file=$(TFVARS)

apply: check-env ## Apply ENV
	cd $(LIVE_DIR) && terraform apply -var-file=$(TFVARS)

destroy: check-env ## Destroy ENV (refuses prod)
	@test "$(ENV)" != "prod" || { echo "refusing to destroy prod from make"; exit 1; }
	cd $(LIVE_DIR) && terraform destroy -var-file=$(TFVARS)

fmt: ## Format all Terraform
	terraform fmt -recursive terraform bootstrap

validate: ## Validate every module and root module
	@set -e; for d in bootstrap terraform/modules/* terraform/live/*; do \
		test -f "$$d/versions.tf" || continue; \
		if grep -q 'configuration_aliases' "$$d/versions.tf"; then \
			echo "==> $$d (skipped: declares configuration_aliases, cannot validate as a root"; \
			echo "    module — it is covered by the root modules that consume it)"; \
			continue; \
		fi; \
		echo "==> $$d"; \
		terraform -chdir="$$d" init -backend=false -input=false >/dev/null; \
		terraform -chdir="$$d" validate; \
	done

lint: fmt validate ## fmt + validate

deploy-site: check-env ## Sync site/ to ENV's bucket and invalidate the CDN
	@set -e; \
	bucket=$$(cd $(LIVE_DIR) && terraform output -raw bucket_name); \
	dist=$$(cd $(LIVE_DIR) && terraform output -raw distribution_id); \
	echo "==> syncing to $$bucket"; \
	aws s3 sync site/ "s3://$$bucket/" --delete --profile cohns-$(ENV); \
	echo "==> invalidating $$dist"; \
	aws cloudfront create-invalidation --distribution-id "$$dist" --paths '/*' --profile cohns-$(ENV) >/dev/null

clean: ## Remove local Terraform working directories
	find . -type d -name .terraform -prune -exec rm -rf {} +
