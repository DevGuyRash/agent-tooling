# audiobatch

Shell tools that turn WAV masters into the files the publish pipeline uploads: a full-length MP3 and a 30-second preview clip for each episode.

## Usage

```sh
bin/convert SRC OUTDIR
bin/convert-all [-j JOBS] [-o OUTDIR] FILE...
```

`convert` encodes one master. For `masters/ep101.wav` it writes `OUTDIR/ep101.mp3` (192 kb/s) and `OUTDIR/ep101.preview.mp3` (128 kb/s, 30 seconds starting at 0:30). A file counts as converted only when both were written.

`convert-all` converts many masters in parallel, `JOBS` at a time (default 4), into `OUTDIR` (default `./out`). A file that fails does not stop the others. It exits 0 when every file converted, 1 when any conversion failed, and 2 on a usage error. The nightly publish job runs it and uploads `OUTDIR` as soon as it exits 0.

Both tools call `ffmpeg` from `PATH`. `BITRATE` and `PREVIEW_START` override the MP3 bitrate and the preview's start offset in seconds.

## Supported systems

The publish runners use the distribution's `/bin/sh`: dash 0.5.12 on Debian 12 and BusyBox 1.36 ash on Alpine 3.19. Everything here is POSIX sh that runs unchanged on both; there is no bash on the runners.

## Tests

```sh
sh tests/run.sh
```

The tests put a stub `ffmpeg` from `tests/stubs` first on `PATH`, so they run without ffmpeg installed. CI (`.gitlab-ci.yml`) runs the suite on both runner images.
