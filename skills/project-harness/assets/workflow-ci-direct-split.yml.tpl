# project-harness: managed-file
name: ci

on:
__ON_BLOCK__

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
__LINT_JOB__
__TEST_JOB__
__BUILD_JOB__
