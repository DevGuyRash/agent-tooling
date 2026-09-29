# Helpers shared by the test scripts; each tests/test_*.sh sources this file.

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
PATH=$ROOT/tests/stubs:$PATH
export PATH

WORK=$(mktemp -d "${TMPDIR:-/tmp}/audiobatch-test.XXXXXX") || exit 1
trap 'rm -rf -- "$WORK"' EXIT
cd "$WORK" || exit 1

failures=0

pass() {
    printf 'ok   %s\n' "$1"
}

fail() {
    printf 'FAIL %s\n' "$1"
    failures=$((failures + 1))
}

# check DESCRIPTION COMMAND [ARG...]: the test passes when COMMAND succeeds.
check() {
    description=$1
    shift
    if "$@"; then
        pass "$description"
    else
        fail "$description"
    fi
}

# master NAME: create a (tiny, fake) WAV master NAME.wav.
master() {
    printf 'RIFF....WAVEfmt \n' >"$1.wav"
}

# corrupt NAME: create NAME.wav that is not audio at all.
corrupt() {
    printf 'truncated upload\n' >"$1.wav"
}

done_testing() {
    [ "$failures" -eq 0 ]
}
