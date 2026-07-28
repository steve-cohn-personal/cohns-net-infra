# AWS Access Strategy

**The goal: no long-lived AWS credential exists anywhere.** Not on a laptop, not in CI, not
in this repository. Humans get short-lived credentials from IAM Identity Center; pipelines get
short-lived credentials from OIDC federation. There is nothing to rotate and nothing to leak.

## Humans — IAM Identity Center

One login. Identity Center lives in the management account and projects *permission sets* into
every member account. Signing in once gives a portal listing every account/role combination
you're entitled to, and the CLI gets the same thing:

```sh
aws sso login --profile cohns-prod
aws sts get-caller-identity --profile cohns-prod
```

Credentials expire (default 8h session, 1h role credentials) and refresh through the browser.
This is the "log in once, switch roles into the others" model — implemented with federation
rather than with `sts:AssumeRole` chaining off a static key.

### Permission sets

| Permission set | Session | Assigned to | Purpose |
| --- | --- | --- | --- |
| `AdministratorAccess` | 8h | management, dev | Org administration; disposable dev sandbox |
| `PowerUserAccess` | 8h | shared-services, stage, prod | Build work; cannot alter IAM or the Org |
| `ReadOnlyAccess` | 8h | all five | Default posture — investigate without risk |
| `Billing` | 8h | management | Cost Explorer and billing console |
| `TerraformExecution` | — | dev, stage, prod | **Deferred to `live/site`** — see note |

The habit worth building: live in `ReadOnlyAccess` and step up deliberately.

> **As-built (2026-07-27):** the four AWS-managed permission sets above exist and are codified in
> `live/org`, assigned to the single `Administrators` group per the matrix (solo-operator model —
> one human gets a menu of roles per account). Sessions are a uniform 8h: for one operator the
> security boundary is the least-privilege split and MFA, not session length; tighten per-set if
> that changes. `AdministratorAccess` is assigned to `management` (not just `dev` as an earlier
> draft had it) because administering the Org requires it. `TerraformExecution` is deferred to
> `live/site`, where its scoped policy can be written against the exact resources the site touches
> — and where it would otherwise duplicate the GitHub OIDC apply roles.

### Generated CLI config

`~/.aws/config` is generated, not hand-edited:

```ini
# sso_region is the Identity Center HOME region (us-east-1) — the identity/
# management plane. The per-profile `region` is where workloads run (us-west-2).
# These are deliberately different; don't "fix" them to match.
[sso-session cohns]
sso_start_url = https://d-xxxxxxxxxx.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile cohns-prod]
sso_session = cohns
sso_account_id = <prod-account-id>
sso_role_name = PowerUserAccess
region = us-west-2

[profile cohns-prod-ro]
sso_session = cohns
sso_account_id = <prod-account-id>
sso_role_name = ReadOnlyAccess
region = us-west-2
```

## Pipelines — GitHub OIDC

GitHub Actions holds **no AWS secret at all**. Each run requests a signed OIDC token from
GitHub; AWS validates it against GitHub's provider and issues temporary credentials. See
[`terraform/modules/github-oidc`](../terraform/modules/github-oidc).

The security of the whole arrangement rests on one condition in the trust policy:

```hcl
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values   = ["repo:steve-cohn-personal/cohns-net-infra:environment:prod"]
}
```

Omit that `sub` condition and the role will accept a token from *any* GitHub repository on
earth. It is the single most important line in this repository.

Roles are scoped per environment and per purpose. The site-deploy role can sync one bucket and
invalidate one distribution — nothing more. A compromised content pipeline defaces the website;
it does not own the account.

## Root

The Organization already existed (created 2019, `o-ajlh1xjt64`), so root was used only to
bootstrap the identity plane, on 2026-07-27:

1. Enable IAM Identity Center in the management account (home region us-east-1)
2. Create the `AdministratorAccess` permission set, an `Administrators` group, and the
   `steve.cohn` user; assign the group into the management account
3. Delete every root access key
4. Sign out

Root now has **no access keys** (confirmed: `iam list-access-keys` returns empty and the old
keys fail with `InvalidClientTokenId`) and keeps MFA enabled. It is console + MFA break-glass
only. There is no legitimate reason for a root access key to exist. An SCP denying root
principal actions in member accounts is still pending (see [roadmap](roadmap.md)).

### Two logins, one email — don't confuse them

Both of the following use the address `you@example.com`, but they are entirely separate
identities in separate credential stores. This trips people up; keep it straight:

| | Root | Identity Center admin |
| --- | --- | --- |
| Sign-in page | AWS root console sign-in | Portal `https://d-xxxxxxxxxx.awsapps.com/start` |
| Login handle | the **email** `you@example.com` | the **username** `steve.cohn` |
| Secret | root password | separate Identity Center password |
| MFA | root's MFA device | its own MFA device |
| When to use | break-glass only (billing, org-wide disasters) | everything, daily, via `aws sso login` |

Reusing the email does not let one identity unlock the other — different sign-in endpoints,
different passwords, different MFA.

## Guardrails

- **SCPs** at the org root: deny leaving the organization, deny disabling CloudTrail/Config,
  deny root principal usage in member accounts, restrict to approved regions.
- **Org-wide CloudTrail** writing to a locked bucket in shared-services.
- **MFA required** for all Identity Center users.
- **State bucket** is versioned, encrypted, TLS-only, and `prevent_destroy`.

## Threat model, briefly

| If this leaks | Impact |
| --- | --- |
| This entire repository | None. It is already public. |
| A deploy role ARN | None. ARNs are not secrets; the trust policy is the control. |
| A developer laptop | Bounded — SSO credentials expire in an hour and re-auth needs MFA. |
| GitHub account | Serious. Hence MFA on GitHub and required reviewers on the prod environment. |
