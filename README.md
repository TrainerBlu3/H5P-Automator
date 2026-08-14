# H5P Automator

Downloads H5P activities from a Moodle course and inserts/embeds them into the
matching Brightspace (D2L) course's modules — a standalone app built around
the H5P pipeline originally developed in `brightspace-page-automator`.

## What it does

1. Logs into Brightspace and Moodle (credentials saved locally, or log in by
   hand in the browser window that opens).
2. Fetches the Brightspace course's module/topic structure.
3. Scrapes the matching Moodle course for H5P activities.
4. Downloads each H5P activity and embeds it into the matching Brightspace
   module, matching Moodle topics to Brightspace modules by name.

The automation logic (`src/h5p_handler.py`, `src/content_checker.py`,
`src/h5p_runner.py`) is copied unmodified from `brightspace-page-automator`
— this app only adds a purpose-built single-window GUI around it.

## Setup

Requires Python 3.10+.

**Linux/macOS:**
```bash
./setup.sh
```

**Windows:**
```
setup.bat
```

Both scripts create a virtual environment, install `requirements.txt`, and run
`playwright install chromium` (Playwright's bundled Chromium is what drives
the browser automation — this is a separate download from your system
Chrome/Chromium and is required).

## Running

**Linux/macOS:**
```bash
./run.sh
```

**Windows:**
```
run.bat
```

Or manually, once the virtual environment is set up:
```bash
source .venv/bin/activate   # .venv\Scripts\activate.bat on Windows
python gui_h5p.py
```

## Using the app

1. Click the gear icon (bottom-left) to open **Settings** and enter your
   Brightspace username/password (and Microsoft SSO email/password, if your
   institution routes Brightspace login through SSO) and your Moodle
   username/password. Click **Save**.
2. Back on the main window, paste the **Brightspace course URL** and the
   matching **Moodle course URL**.
3. Use the **Log in** buttons next to the Moodle/Brightspace rows to open a
   browser window and establish a session (or just click **Run** — it will
   prompt for login as needed).
4. Click **Run**. The app fetches the Brightspace structure, then pauses
   with a **Ready — Scrape Now** button before scraping Moodle (useful if you
   want to double-check you're on the right course page first). It pauses
   again with **Ready — Download H5P** / **Skip H5P** before downloading and
   embedding H5P activities.
5. Watch progress in the log panel.

The "Skip grade item" checkboxes next to each platform row are placeholders
for a future grade-item-skip feature — they're stored in the config file but
don't currently change any behavior.

## Releases (Windows / macOS builds)

Tagged pushes build standalone desktop binaries via GitHub Actions
(`.github/workflows/release.yml`) — no Python install required for end users.

To cut a release:

```bash
git tag v1.0.1
git push origin v1.0.1
```

This triggers a build on `windows-latest` and `macos-latest` that packages the
app with PyInstaller (`H5PAutomator.exe` / `H5PAutomator.app`) and attaches
the zipped binaries to a **draft** GitHub Release (`generate_release_notes`
fills in the changelog) — nothing goes live until you review and publish the
draft yourself.

You can also trigger `Actions → Release → Run workflow` manually to build and
inspect artifacts without pushing a tag or touching releases.

Notes on the packaged build:
- On first launch, the app downloads Playwright's Chromium build itself
  (there's no `run.bat`/`run.sh` wrapper to do it for a packaged exe/app) —
  a one-time ~1 minute step shown in a progress dialog.
- No custom app icon is bundled yet (`assets/icon.ico` referenced in
  `gui/constants.py` doesn't exist) — add one there and pass
  `--icon assets/icon.ico` / `--icon assets/icon.icns` in the workflow's
  PyInstaller commands to brand the build.

## Where data lives

All credentials, the saved browser session, and downloaded H5P files live in
your OS's per-user app-data directory — never in this repository:

- Linux/macOS: `~/.local/share/H5PAutomator/`
- Windows: `%APPDATA%\H5PAutomator\`

Credentials are stored as **plaintext JSON** (`config.json` in that
directory) — this keeps the dependency footprint small (no `keyring`), but
means anyone with access to your user account can read them. Use the
**Clear Session** button in Settings to remove the saved browser session
(cookies) at any time; delete `config.json` directly to remove saved
credentials.

## Project layout

```
gui_h5p.py              Entry point — single-window PyQt6 GUI
gui/
  theme.py               Colors + Qt stylesheet helpers (green theme)
  constants.py            Userdata dir, config/session file paths
  settings_dialog.py      Settings dialog (credentials, session management)
src/
  h5p_runner.py            run_h5p_only() — the standalone H5P pipeline entrypoint
  h5p_handler.py           H5PHandler — H5P download + Brightspace embed logic
  content_checker.py       ContentChecker — Brightspace TOC fetch + Moodle scrape
  content_matcher.py       Text-matching helpers used by content_checker
  js_helpers.py            Shared browser-side JS snippets
  browser.py               Playwright launch + Brightspace login flow
  moodle_login.py          Standalone Moodle login flow (for the main window's
                            Moodle "Log in" button)
  config.py                Userdata dir + session file path
```

## Known gaps / TODOs

- "Skip grade item" checkboxes are stored but not yet wired to any real
  gradebook-skip behavior (out of scope for this extraction — see spec).
- Moodle and Brightspace share a single Playwright storage-state session
  file, since `run_h5p_only()` logs into both within the same browser
  context. The two status dots in the main window both reflect that one
  file's existence — there's no independent "is Moodle logged in right now"
  check separate from Brightspace.
- Login URLs (`learn.okanagancollege.ca`, `mymoodle.okanagan.bc.ca`) are
  hardcoded, carried over as-is from the source repo. Adapting this app for
  a different institution means editing `src/browser.py` and
  `src/moodle_login.py`.
