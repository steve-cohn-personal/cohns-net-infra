# Ansible

Deliberately thin in phase 1, and this is worth being honest about: a static site on S3 and
CloudFront has nothing to configure. Adding Ansible here just to have Ansible in the repository
would be decoration, and decoration in an infrastructure repo is a liability — it is code
somebody has to read, trust, and maintain.

Ansible earns its place in phase 2, where there are actually machines and services to configure:

- **EKS node bootstrap** — anything Karpenter's AMI doesn't cover: agents, sysctls, log shipping
- **Application configuration** — templating environment config from Terraform outputs
- **Local development environment** — a playbook that stands up the toolchain on a fresh laptop,
  so the setup instructions cannot drift from reality
- **Operational runbooks as playbooks** — certificate rotation, backup restore drills, the
  procedures that are otherwise a wiki page nobody has tested

The division of labour: **Terraform owns what exists, Ansible owns what's inside it.** Blurring
that line is how teams end up with two tools that both half-manage the same resource and
disagree about its state.
