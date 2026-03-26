# project-harness: managed-file
name: dist-cross-os

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: dist-cross-os-${{ github.ref }}
  cancel-in-progress: false

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-latest
            platform_id: linux-x86_64
          - os: windows-latest
            platform_id: windows-x86_64
          - os: macos-latest
            platform_id: macos-arm64
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
__SETUP_STEPS__
__BOOTSTRAP_STEPS__
__DIST_STEPS__
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: dist-${{ matrix.platform_id }}
          path: dist/${{ matrix.platform_id }}
          if-no-files-found: error
          retention-days: 14
