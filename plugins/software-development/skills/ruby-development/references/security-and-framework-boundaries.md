# Security and Framework Boundaries

Read this reference for external commands, serialization, templates, SQL, paths, secrets, dynamic dispatch, Rails, or another framework.

## Treat external data as data

- Prefer direct process APIs with separate arguments, such as appropriate `system`, `spawn`, or Open3 forms; use shell parsing only when shell syntax is required.
- Never load untrusted `Marshal` data. Use safe, explicitly constrained YAML loading for untrusted YAML.
- Parameterize SQL values through the selected database library; allowlist identifiers and query structure that cannot be bound.
- Escape output for its actual HTML, URL, JavaScript, SQL, or protocol context through the owning framework/library.
- Use `SecureRandom` for secrets and tokens, and use constant-time comparison where the selected security library provides it.
- Keep credentials out of source, logs, exceptions, command arguments where exposed, fixtures, and built gems.
- Validate resolved filesystem and archive destinations, including symlinks, before writing beneath a trusted root.

Do not pass user-controlled names to `eval`, constant lookup, `send`, class loading, deserialization, or template compilation without an explicit allowlist and authority model. `public_send` limits visibility but does not authorize arbitrary method names.

## Defer framework policy

Rails, Hanami, Sinatra, Sidekiq, Active Job, Active Record, Sequel, Zeitwerk, and template engines own lifecycle and safety behavior beyond Ruby syntax. When a framework is present:

- Preserve its autoloading, callbacks, transaction, request/job, escaping, and configuration conventions.
- Use its supported parameterization, validation, authorization, and secret interfaces.
- Avoid bypassing lifecycle hooks with generic Ruby cleanup or concurrency patterns.
- Make architectural or framework-specific choices by that framework's conventions.

Do not install Rails service objects, repositories, concerns, interactors, or Active Record patterns as universal Ruby architecture.

## Preserve operational contracts

For commands and workers, treat exit status, streams, signals, retry/idempotency, and shutdown as interfaces. For gems, avoid unexpected network, filesystem, logging, or environment work during `require` unless explicitly documented.

Apply the repository threat model and any dedicated security guidance to security-sensitive work.
