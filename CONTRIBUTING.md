# Contributing

[English](CONTRIBUTING.md) · [Türkçe](CONTRIBUTING_TR.md) · [Documentation](docs/README.md)

## Report a bug or suggest a feature

Open a GitHub issue describing what you tried, what you expected and what happened. Include the Petrel revision, Pi/OS, display model, relevant Klipper/Happy Hare versions, reproduction steps and a short service-log excerpt. For visual issues, add an original-size screenshot and, when relevant, a photo of the physical display. Remove credentials and private network information.

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
~/petrel-env/bin/python -m unittest discover -s tests -v
~/petrel-env/bin/python -m compileall -q .
```

For manual application testing, stop the installed service first so only one process uses the UART and encoder. Supply your own connection/pin values; running `run.py` directly does not read the service's environment file and its bare UART/button defaults differ from the installer:

```bash
sudo systemctl stop Petrel.service
cd ~/Petrel
~/petrel-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 19 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

After exiting the manual process, restart the installed service with `sudo systemctl start Petrel.service`. Use `run.py --help` for available options; CLI values override environment values. Test movement, calibration and MMU changes on appropriate hardware in addition to automated tests.

## Screenshots and documentation

Capture the screen with the [emulator](docs/ui-emulator.md). Store descriptive filenames in `docs/assets/screens/`, replacing the existing image when it represents the same screen/state. Keep the original **272×480 PNG**; do not upscale, crop or convert it to JPEG. Use consistent display widths in Markdown and meaningful alt text in each language.

Check local links, section anchors, image paths, translated guide pairs and user commands before opening the PR. Documentation-only changes do not need printer regression tests unless they also change behavior.

Use `tools/render_docs_screenshots.py` to regenerate all documentation screens without a printer; the [offline rendering guide](docs/ui-emulator.md#render-documentation-screens-offline) explains the commands and example data. Preserve existing image filenames so forum links keep working.

### Production and validation contracts

Run the [PNG and GIF refresh commands](docs/ui-emulator.md#refresh-pngs-frames-and-gifs) together. Preserve 272×480 panel PNGs; framed 528×900 copies are presentation only. Use one checkout, sample data, scene order and matching EN/TR captions. Original PNG gallery links use repository-relative paths to follow the same branch; copy the opened GitHub page's full address for forum posts.

Print/Tune validation: an After Job click must only send `SET_PIN`, never immediately switch off hardware; older replies must not overwrite a newer edit; rejected values/switches/Pause blink red twice and return to subscribed state; an incomplete hold preserves the draft. Source and hardware checks are in the [test guide](tests/README.md).

For JPEG changes preserve the [fan/button contracts](assets/icons/README.md#print-buttons-switches-and-fan-artwork), font ID 0, baseline 4:2:0 and source/export equivalence. Normal/selected button masks must match. Validate relevant states on the physical panel after emulator review.
