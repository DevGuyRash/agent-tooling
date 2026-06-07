# project-harness: managed-file
# Example only: adapt this from the artifact-oriented cross-OS template when you
# want tagged GitHub Release assets instead of artifacts only.
name: release-assets-cross-os

on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: write

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
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      # Add your normal setup and bootstrap steps here.
      # Add your build/dist staging steps here.
      - uses: actions/upload-artifact@v4
        with:
          name: dist-${{ matrix.platform_id }}
          path: dist/${{ matrix.platform_id }}
          if-no-files-found: error

  publish:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: dist-release
      - name: Upload assets to the published release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          set -euo pipefail
          find dist-release -type f -print0 | while IFS= read -r -d '' file; do
            gh release upload "${{ github.event.release.tag_name }}" "$file" --clobber
          done
