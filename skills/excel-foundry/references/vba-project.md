# VBA Project

Supported component handling:

- standard modules
- class modules
- document modules
- UserForms

Project references are queryable through Excel COM when VBA project access is enabled.

Portable exclusions:

- digital signatures
- password-protected VBA projects
- project metadata that Excel COM cannot roundtrip deterministically

When Excel blocks VBA access, fail clearly and tell the user to enable Trust
Center access to the VBA project object model.
