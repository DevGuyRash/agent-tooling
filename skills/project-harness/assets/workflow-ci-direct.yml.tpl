# project-harness: managed-file
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
__SETUP_STEPS__
__BOOTSTRAP_STEPS__
__RUN_STEPS__
