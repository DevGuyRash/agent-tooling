# In flight

- Qualify the Playwright runtime on native Windows, including private-desktop popup affinity, foreground behavior, command/argument handling and Job Object teardown; use the shipped qualification command and platform reference.
- Configure and qualify an isolated native macOS session provider, including actual rendering OS, connection compatibility, teardown and owner-loss expiry.
- Qualify Linux WebKit after supplying its required libicu74 and libflite1 dependencies in a suitable environment.
- Enable the isolated-profile Codex marketplace test with a CLI that honors the selected test profile.
