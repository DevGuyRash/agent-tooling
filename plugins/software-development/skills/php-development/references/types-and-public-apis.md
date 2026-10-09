# Types and Public APIs

Read this reference for strict typing, coercion, declarations, PHPDoc, signatures, named arguments, inheritance, or compatibility.

## Apply PHP typing accurately

Scalar typing is coercive by default. `declare(strict_types=1)` is per file, affects scalar declarations, and uses the calling file's mode for argument calls. It is not a property attached solely to the function declaration.

Argument scalar coercion follows the caller file. Scalar return enforcement follows the file defining the function. Test both sides of a mixed strict/coercive boundary instead of inferring package-wide behavior from one declaration.

Follow repository policy. Adding strict mode to a legacy caller can change behavior; omitting it from a strict codebase can weaken the intended boundary.

- Use native parameter, return, property, and constant types supported by the minimum PHP version.
- Preserve nullable, union, intersection, DNF, literal, `mixed`, `never`, and variance semantics deliberately.
- Use PHPDoc for analyzer generics, shapes, templates, conditional types, or other information not expressible natively.
- Match the selected PHPStan/Psalm dialect and generated-file ownership.
- Do not duplicate obvious native declarations or claim precision the runtime does not uphold.

## Preserve public API behavior

PHP 8 named arguments bind to parameter names. Treat public names, position, defaults, by-reference markers, and variadics as compatibility surface even where inheritance checks do not catch name changes.

Also preserve:

- Namespace and class names, autoload paths, aliases, visibility, constants, and property initialization.
- Return value and mutation behavior, exception/deprecation behavior, and magic-method signatures.
- Interface, parent, and trait contracts, including covariance, contravariance, and property invariance applicable to the supported version.
- Attributes, reflection metadata, serialization, callable shape, and framework-discovered conventions.

Use deprecation and migration paths for intentional library changes rather than silent signature rewrites.

## Control coercion at boundaries

PHP comparisons and scalar contexts can coerce values. Parse and validate external strings into the intended domain before authorization, identity, range, or persistence decisions. Prefer strict comparison when type identity matters, but do not ban loose comparison where coercion is the explicit contract.

Distinguish missing, `null`, `false`, zero, and empty strings when the domain distinguishes them. Avoid blanket truthiness rewrites that collapse valid states.

## Preserve array identity and presence

PHP array keys normalize values: decimal integer strings can become integers, floats truncate, booleans become `0` or `1`, and `null` becomes an empty string on supported versions. Normalize and validate external identifiers before insertion so distinct source values cannot silently overwrite one slot.

Use `array_key_exists()` when present-with-`null` differs from missing. `isset()` and `??` intentionally collapse those states. Preserve list/map ordering and key shape when serialization, iteration, equality, or consumer code observes them.

Validate required field presence before reading its value or canonicalizing related identity. A default value, `??`, `isset`, or early skip can otherwise convert a schema violation into an accepted null/empty record and can bypass later duplicate or supported-type checks.

## Treat references as explicit aliases

Arrays normally use copy-on-write; PHP references instead bind names to the same variable content, and objects have handle-like mutation semantics. Do not introduce `&` merely to avoid a presumed copy.

A by-reference `foreach` value remains bound to the final element after the loop. `unset()` that loop variable before reuse. Preserve by-reference parameters, returns, array entries, and closure captures as public mutation contracts.

`readonly` prevents property reassignment, not mutation inside a referenced object or resource. Do not advertise deep immutability without enforcing it across the complete reachable state.

## Document durable contracts

Follow repository docblock style. Document analyzer-only types, templates, side effects, ownership, deprecations, and exceptions callers handle. An unaccepted draft standard is not universal PHP policy.
