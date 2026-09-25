# Isolated browser execution

Native headless execution is the default on supported Linux, Windows, and macOS hosts. It needs the selected Playwright browser and OS dependencies. Isolated headed execution adds a display or session owned by the run so browser windows stay off the user's active desktop.

A Playwright viewport controls document dimensions. `screen` supplies browser-visible screen dimensions. The native display or desktop hosts windows; it has a separate lifecycle and can affect rendering. Device emulation uses the installed Playwright descriptor and retains the real rendering OS. Keep those distinctions with the evidence.

| Host | Isolated headed backend | Setup |
|---|---|---|
| Linux | Private Xvfb server and authorization file | Xvfb and the browser's OS dependencies |
| Windows | Private Win32 desktop with owned Job Object | PowerShell with the Windows desktop and process APIs available |
| macOS | Configured isolated native session provider | Provider module and its native session infrastructure |

The Linux backend has native qualification coverage. Windows private-desktop behavior and a configured macOS provider require native qualification on their target hosts. The checks below describe the properties needed for those environments; structural checks alone establish the helper interfaces.

## Linux

The backend asks Xvfb to allocate an available display and report readiness through `-displayfd`. Each run owns a private X11 authorization file, process identity, and resource directory. Xvfb listens on the local display socket with TCP listening disabled. Display dimensions come from `display`, then effective `screen`, then the viewport with space for browser chrome.

The child browser or command receives the private `DISPLAY` and `XAUTHORITY`. Inherited Wayland settings are removed from that child environment and X11 selection is explicit. The user's environment and active display remain separate. Concurrent runs allocate independent displays and authorization material.

Use the distribution's Xvfb package when setup is authorized. The runtime writes its private Xauthority record directly. The capability command identifies missing executables before starting the browser. Browser shared-library dependencies are described by [Playwright's browser installation guidance](https://playwright.dev/docs/browsers#install-system-dependencies). Playwright's [headed Linux guidance](https://playwright.dev/docs/ci#running-headed) describes Xvfb; the shared runner adds per-run ownership and lifecycle around that platform facility.

Xvfb provides an X display. A desktop environment, compositor, window manager, audio stack, or GPU path can be a separate requirement for a particular product test. Choose and qualify a configured provider when the assignment depends on those components.

## Windows

The PowerShell/C# helper creates a uniquely named desktop in the calling process's window station using `CreateDesktopW`. It starts the child suspended with `STARTUPINFO.lpDesktop` set to that desktop, assigns it to an owned Job Object, then resumes it. The Job Object keeps the child process tree under cleanup ownership; the helper closes process, job, and desktop handles during teardown.

A Win32 desktop is a logical surface for windows and input, not an installed virtual-monitor driver. Only the active input desktop is visible to the user. The helper keeps its desktop inactive. Browser rendering, popup inheritance, desktop access rights, and existing process/job constraints must work in the actual Windows account and runner configuration.

Microsoft's sources describe the platform contracts:

- [Desktops](https://learn.microsoft.com/en-us/windows/win32/winstation/desktops): window ownership, input desktop, and window-station relationship.
- [CreateDesktopW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createdesktopw): desktop creation, access rights, and `CloseDesktop`.
- [STARTUPINFOW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-startupinfow): `lpDesktop` and child process startup.
- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects): descendant membership, limits, and process-tree termination.

## Configured native sessions

A macOS headed session uses an explicit provider for the available isolated native session infrastructure. The same interface can connect another supported host to a workspace, VM, or container provider. The provider supplies the isolation and rendering environment; a Linux-hosted browser remains Linux rendering even when the caller is on macOS.

Pass a module path as `provider` or `--provider`. Its `acquire(options)` returns a lease with:

| Lease field | Contract |
|---|---|
| `identity` | A recoverable identity for the owned session. |
| `renderingOS` | The OS in which the browser actually runs. |
| `capabilities` | `{ isolated: true, headed: true }` for isolated headed requests. |
| `endpoint` | A Playwright browser-server endpoint compatible with `browserType.connect()`. |
| `close()` | Teardown of the owned session, or an equivalent `provider.release(lease)`. |
| `run(command, args, options)` | Optional command execution for `isolate-run`, preserving the supplied cwd, environment, timeout, arguments, and result. |

The endpoint is produced by a compatible Playwright `browserType.launchServer()` environment. Match client and server versions as required by [BrowserType.connect](https://playwright.dev/docs/api/class-browsertype#browser-type-connect). Keep connection credentials in the provider's protected configuration rather than evidence records.

Module providers run under the supervisor so owner loss can trigger teardown. An in-memory provider object uses in-process closure and signal handling; it needs provider-owned lease expiry or another durable cleanup mechanism for uncatchable termination. Providers should make cleanup idempotent and retain enough identity to recover abandoned sessions without guessing which resources belong to them.

## Lifecycle and recovery

Use `withSession` or `try/finally` with `openSession` for browser work, and `runIsolated` for an existing command. Each invocation owns its processes, temporary profile, display/session resources, and authorization material. Completed captures and diagnostic artifacts are retained separately from transient execution resources.

On a command failure, inspect its exit code and evidence. On setup failure, correct the named prerequisite before retrying. On interruption, resume retained evidence according to its pending work; reconstruct the application state before repeating actions. Browser or display startup failure and cancellation follow the same owned teardown path.

`recoverOwnedResources(root)` and the CLI's `recover --root` inspect this runtime's ownership records. Live owners remain intact; stale owned resources can be recovered using their recorded identity. Recovery is scoped to the supplied runtime resource root. A report about uncertain ownership needs investigation rather than a broad process-name cleanup.

## Native qualification

The maintained smoke script exercises a synthetic page and popup, saves captures and environment information, closes the session, and checks browser disconnection, the retained cleanup receipt, and removal of its local execution directory:

```sh
node "<skills-file-root>/../../scripts/qualify-session.mjs" --output "/path/to/new-native-run" --project "/path/to/application" --presentation isolated-headed
```

For a configured native session, add `--provider "/path/to/provider.mjs"`. Use `--playwright` to select a standalone installation. `--help` lists the supported options. The script records its individual checks and remaining native observations with the run. Popup browser-context ownership is observed automatically; native window affinity and foreground behavior require the platform observations below.

Qualify the selected OS, browser, channel, account/session, and provider together. The useful observations are a page and popup rendering on the intended isolated surface, pointer and keyboard input producing the expected result, correct viewport/screen evidence, and the user's foreground desktop remaining unchanged. Exercise normal exit, startup failure, test failure, timeout, cancellation, and owner loss; confirm the owned processes, display or desktop handles, authorization files, and temporary profiles are released while completed evidence survives.

Run two simultaneous sessions to check independent displays or desktops and cleanup. On Windows, inspect descendant-window desktop ownership and Job Object termination. For a macOS provider, establish the reported rendering OS, endpoint compatibility, native session isolation, and provider teardown/expiry. Retain native observations with the run so portability claims match the platform actually exercised.
