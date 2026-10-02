# Native, and the shared timesheet reader now says why a file cannot be read in words ("no such file or directory")
# instead of Node's error code, for hours check and report too. Must pass: the reason is specified nowhere.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
sed -i "s/super(\`cannot read \${file}: \${cause instanceof Error \&\& 'code' in cause ? String(cause.code) : String(cause)}\`);/super(\`cannot read \${file}: \${cause instanceof Error ? cause.message.replace(\/^\\\\w+: \/, '').replace(\/, \\\\w+ '.*'\$\/, '') : String(cause)}\`);/" src/timesheet.ts
grep -q "cause.message.replace" src/timesheet.ts
git commit -q -am "timesheets: say why a file cannot be read"
