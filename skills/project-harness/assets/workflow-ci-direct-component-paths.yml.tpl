# project-harness: managed-file
# Example only: add path filters only when component ownership is stable and a
# skipped run cannot hide a required check.
name: ci

on:
  push:
    branches: [main]
    paths:
      - ".github/workflows/**"
      - "justfile"
      - "backend/**"
      - "frontend/**"
  pull_request:
    paths:
      - ".github/workflows/**"
      - "justfile"
      - "backend/**"
      - "frontend/**"

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
      # Add direct-mode setup/bootstrap steps here.
      - name: Lint
        run: |
          # Add direct formatting/lint commands here.
          echo "replace with repo-specific direct lint steps"

  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
      # Add direct-mode setup/bootstrap steps here.
      - name: Test
        run: |
          # Add direct test commands here.
          echo "replace with repo-specific direct test steps"

  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
      # Add direct-mode setup/bootstrap steps here.
      - name: Build
        run: |
          # Add direct build commands here.
          echo "replace with repo-specific direct build steps"
