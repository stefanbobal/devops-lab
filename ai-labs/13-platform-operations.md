# AI Lab 13 – Platform operations

## Goal

Run the homelab like a real internal service: documented, repeatable, with clear rules.

## Concepts

- **Onboarding guide:** a new developer gets a key and makes the first call in 10 minutes, alone.
- **Runbooks:** model upgrade, backend down, GPU overheating, key revocation.
- **Priorities and queueing:** interactive users vs. overnight batch jobs.
- **Infrastructure as Code:** the whole platform can be rebuilt from the repository.

## What you will do

- Write the onboarding guide and test it on the fictional "dev" team.
- Write four runbooks.
- Define a priority policy: who goes first, what runs overnight.
- Make the platform reproducible with docker compose files and an Ansible playbook.
- Perform one model upgrade following your own runbook.

## Done when

- [ ] Onboarding guide works without my help
- [ ] Four runbooks exist and one was used for a real upgrade
- [ ] The platform can be rebuilt from the repository

## Notes

-
