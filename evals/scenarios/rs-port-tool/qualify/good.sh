# Correct native port (must pass): the reference Rust port in qualify/native, placed at the repository root
# beside the Python package, with its own unit and golden tests. Its manifest is stored as Cargo.toml.in so
# that this repository's CI, which builds every Cargo.toml it finds, leaves it alone.
set -e
dest="${PORT_DIR:-.}"
mkdir -p "$dest"
cp -R "$TRIAL_SCENARIO_DIR/qualify/native/." "$dest/"
mv "$dest/Cargo.toml.in" "$dest/Cargo.toml"
if [ "$dest" = "." ]; then echo "/target/" >> .gitignore; else echo "/$dest/target/" >> .gitignore; fi
git add -A
git commit -q -m "Port reqstat to Rust"
