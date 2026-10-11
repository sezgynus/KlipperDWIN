# Contributing

[English](CONTRIBUTING.md) · [Türkçe](CONTRIBUTING_TR.md) · [Documentation](docs/README.md)

## Report a bug or suggest a feature

Open a GitHub issue describing what you tried, what you expected and what happened. Include the KlipperDWIN revision, Pi/OS, display model, relevant Klipper/Happy Hare versions, reproduction steps and a short service-log excerpt. For visual issues, add an original-size screenshot and, when relevant, a photo of the physical display. Remove credentials and private network information.

Feature proposals should describe the user workflow and the required printer capability. Contributions can include code, documentation, translations, icons or hardware test results.

## Prepare a change

Start a branch from current `master`; keep the change focused and open a pull request explaining the problem, resulting behavior and validation. Use a separate development checkout so Moonraker Update Manager can keep the installed checkout clean. Put machine settings in the external environment file.

For user-visible changes, update the relevant guide and screenshots. **English and Turkish documentation must cover the same features and steps**, use the same screenshots/order and keep on-screen labels unchanged. Current usage belongs in the guides; historical audits are references.

## Development tools

| Tool | What it is for | Where to start |
|---|---|---|
| Optional framebuffer emulator | Capture the running LCD UI for visual review, documentation and bug reports | [Emulator guide](docs/ui-emulator.md) |
| Regression suite | Check a change without connecting to or moving a printer | [Test guide](tests/README.md) |
| JPEG icon packer | Add icons and export the managed library | [Icon source guide](assets/icons/README.md) |
| Service logs | Diagnose startup, connection and operation errors | [Troubleshooting](docs/installation.md#troubleshooting) |

## Run and verify

On an installed Pi, the existing application environment contains the runtime dependencies. Run tests from the development checkout:

```bash
~/klipperdwin-env/bin/python -m unittest discover -s tests -v
~/klipperdwin-env/bin/python -m compileall -q .
```

For manual application testing, stop the installed service first so only one process uses the UART and encoder. Supply your own connection/pin values; running `run.py` directly does not read the service's environment file and its bare UART/button defaults differ from the installer:

```bash
sudo systemctl stop KlipperDWIN.service
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 19 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

After exiting the manual process, restart the installed service with `sudo systemctl start KlipperDWIN.service`. Use `run.py --help` for available options; CLI values override environment values. Test movement, calibration and MMU changes on appropriate hardware in addition to automated tests.

## Screenshots and documentation

Capture the screen with the [emulator](docs/ui-emulator.md). Store descriptive filenames in `docs/assets/screens/`, replacing the existing image when it represents the same screen/state. Keep the original **272×480 PNG**; do not upscale, crop or convert it to JPEG. Use consistent display widths in Markdown and meaningful alt text in each language.

Check local links, section anchors, image paths, translated guide pairs and user commands before opening the PR. Documentation-only changes do not need printer regression tests unless they also change behavior.
