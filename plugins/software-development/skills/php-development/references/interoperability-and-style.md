# Interoperability and Style

Read this reference for PSR/PER decisions, autoload interoperability, shared interfaces, formatting, comments, or framework boundaries.

## Separate three policy layers

1. PHP language and runtime behavior applies because the code executes as PHP.
2. Composer and PHP-FIG conventions apply only when the repository or interoperability boundary selects them.
3. Framework/CMS conventions apply within that framework's lifecycle and override generic preferences where compatible with language correctness.

PHP-FIG recommendations are interoperability contracts, not requirements that every project implement every PSR.

## Apply interoperability where it exists

- Preserve declared Composer autoloading. Use PSR-4 only where the package selects it; classmaps, files, and legacy loaders may be intentional.
- Implement PSR-3, PSR-7, PSR-11, PSR-15, PSR-17, PSR-18, or other interfaces only at boundaries that require them.
- Respect the selected implementation's immutability, ownership, and exception contracts.
- Do not inject a container everywhere; even PSR-11 discourages service-locator use in ordinary objects.
- Keep framework-native interfaces unless the code must interoperate beyond that framework.

## Preserve style ownership

Determine whether the repository uses Coding Style PER, PSR-12, a framework standard, a legacy PHPCS ruleset, PHP-CS-Fixer, or another formatter. Format the touched scope through the selected tool when required. Do not mix a repository-wide formatting migration into a behavior change.

Style standards do not decide architecture, strict typing, analyzer level, test framework, or documentation density.

Use comments and docblocks for public contracts, invariants, compatibility constraints, workarounds, and analyzer-only information. Avoid syntax narration and duplicated type declarations.

## Route framework policy

Laravel, Symfony, WordPress, Drupal, Magento, Doctrine, Twig, Blade, and other ecosystems own routing, dependency injection, hooks, persistence, escaping, cache, request, worker, and shutdown conventions. Follow each framework's own guidance for them.

Preserve older supported PHP versions where a CMS/plugin ecosystem declares them. Do not modernize syntax, architecture, or style beyond that contract as collateral work.
