# Bootstrap Runbook

One-time setup, from an AWS account with nothing in it to a working pipeline. Follow in order —
several steps genuinely depend on the previous one.

## 0. Prerequisites

```sh
terraform version   # >= 1.10
aws --version       # v2
ansible --version
gh --version
```

## 1. Root, four times, then never again

These four things cannot be done any other way — the Organization must exist before Identity
Center, and Identity Center must exist before there is any non-root identity to use.

Signed into the console **as root**, with MFA on the root account:

1. **AWS Organizations → Create an organization** (choose "All features").
2. **IAM Identity Center → Enable.** Pick `us-west-2` as the identity store region — this is
   effectively permanent.
3. **Create a user** for yourself, **create an `AdministratorAccess` permission set**, and
   assign that user to the management account.
4. **Sign out of root.** Confirm root has no access keys. Store the credentials and MFA device
   somewhere physical.

> **Do not create root access keys.** There is no legitimate use for one, and it is the only
> AWS credential with no possible scope limit.

## 2. Configure SSO on the CLI

```sh
aws configure sso
# start URL:  https://d-xxxxxxxxxx.awsapps.com/start
# region:     us-west-2
# profile:    cohns-mgmt

aws sts get-caller-identity --profile cohns-mgmt
```

That output is the first proof the whole model works.

## 3. Create the member accounts

From `terraform/live/org` (management account), Terraform imports the existing Organization and
creates the four member accounts. Each needs a **unique email address** — the `user+tag@domain`
form works and is the usual approach:

```
you+aws-shared@example.com
you+aws-dev@example.com
you+aws-stage@example.com
you+aws-prod@example.com
```

Account creation is asynchronous and occasionally slow; a few minutes per account is normal.

## 4. Bootstrap the state backend

The chicken-and-egg step. Run in the **shared-services** account:

```sh
cd bootstrap
terraform init            # local state, on purpose
terraform apply
terraform output state_bucket
```

Then uncomment the `backend "s3"` block in `bootstrap/versions.tf`, fill in that bucket name,
and migrate the state into the bucket it just created:

```sh
terraform init -migrate-state
```

Delete the local `terraform.tfstate` afterward. It is already gitignored, but it should not
linger on disk either.

## 5. Register the domain's nameservers

`cohns.net` is registered elsewhere. Create the public hosted zone in shared-services, then
update the nameservers at the registrar to the four Route53 gives you.

**Do this early.** NS propagation can take up to 48 hours, and ACM certificate validation is
blocked until it completes — this is the long pole in the entire phase.

## 6. Delegate the subzones

Create `dev.cohns.net` and `stage.cohns.net` zones in their own accounts, then add the
corresponding NS records to the apex zone in shared-services.

## 7. Create the repo and its environments

```sh
gh repo create steve-cohn-personal/cohns-net-infra --public --source=. --push
```

Then, in repository settings, create the `dev`, `stage`, and `prod` Environments and add a
required reviewer to `prod`. Set each environment's variables (`TF_APPLY_ROLE_ARN`,
`SITE_BUCKET`, `SITE_DISTRIBUTION_ID`) from the Terraform outputs. These are **variables**, not
secrets — none of them is confidential.

## 8. Apply the site

```sh
make init ENV=dev
make plan ENV=dev
make apply ENV=dev
make deploy-site ENV=dev
```

Then stage, then prod.

## Verification

```sh
# TLS and security headers
curl -sI https://www.cohns.net | grep -iE 'strict-transport|content-security|x-frame'

# The origin bucket must NOT be reachable directly
curl -s -o /dev/null -w '%{http_code}\n' https://<bucket>.s3.us-west-2.amazonaws.com/index.html
# expect 403

# No access keys anywhere
aws iam list-users --profile cohns-mgmt          # expect empty
aws iam list-access-keys --user-name <any>       # expect empty
```
