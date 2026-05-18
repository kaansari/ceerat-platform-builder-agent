# Security and RBAC Standard

New modules must use least-privilege RBAC. Plans should name permissions using a
stable module action pattern such as `invoice.read`, `invoice.create`,
`invoice.update`, `invoice.delete`, and `invoice.approve`.

Sensitive actions need separate permissions from read-only access. Mutating AI
agent tools must require explicit permissions and should be auditable.
