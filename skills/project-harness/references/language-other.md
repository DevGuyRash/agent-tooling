# Ruby, Elixir, Java, and Kotlin Commands

Use this file for the remaining supported ecosystems.

## Ruby

Conservative defaults:

```text
build      bundle exec rake build
test       bundle exec rspec
lint       bundle exec rubocop
fmt        bundle exec rubocop -A
clean      rm -rf pkg tmp log
bootstrap  bundle install
```

If the repo clearly uses Minitest or another task surface, wrap that instead.

## Elixir

```text
build      mix compile
test       mix test
lint       mix credo --strict
fmt        mix format
fmt-check  mix format --check-formatted
clean      mix clean && rm -rf _build deps
bootstrap  mix deps.get && mix compile
```

## Java and Kotlin with Gradle

```text
build      ./gradlew build -x test
test       ./gradlew test
lint       ./gradlew check
fmt        ./gradlew spotlessApply
fmt-check  ./gradlew spotlessCheck
clean      ./gradlew clean
bootstrap  ./gradlew build
```

`spotless*` only makes sense when the repo already uses Spotless.

## Java and Kotlin with Maven

```text
build      mvn compile
test       mvn test
lint       mvn checkstyle:check
clean      mvn clean
bootstrap  mvn install -DskipTests
```

## Framework signals

- Rails
- Phoenix
- Spring Boot

Framework detection matters mainly for deciding whether to add optional
developer recipes, not for changing the canonical top-level harness recipes.

## Rule

For these ecosystems especially, prefer the repo’s existing wrapper scripts
and build files over speculative lint and format defaults.
