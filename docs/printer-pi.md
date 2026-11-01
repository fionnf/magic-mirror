# A wireless receipt printer: the second Pi

The wall's Pi sends every finished picture over Wi-Fi to a small Pi that the printer is plugged into (`tools/print_server.py` on port 8631, a shared secret `PRINT_KEY` on both sides).
Printing quality and layout are in [printing.md](printing.md).

## Set it up

1. **Flash the SD card** with Raspberry Pi Imager: *Raspberry Pi OS Lite (64-bit)*. In its settings (Ctrl+Shift+X) set a hostname (the author's is `printer`), user `pi` and a password, your Wi-Fi, and *Enable SSH*.
   No Imager? `tools/flash_sd.sh image.img /dev/diskN` writes an image on a Mac (it refuses anything but a 16-256 GB disk and needs your password for `sudo dd`). You can also unpack the image, mount its boot partition
   and write cloud-init's `user-data` and `network-config` into it (the author did; `network-config` takes the Wi-Fi password as a 64-hex pre-shared key, so the password itself is never stored).
2. Put the card in the Pi, plug the printer into a USB port, power on and wait two or three minutes. Check it is on the network: `ping printer.local`.
3. Let your laptop in: `ssh-copy-id pi@printer.local`, and allow `sudo` without a password for the setup (Imager's user needs a password for `sudo` by default):
   `ssh -t pi@printer.local "echo 'pi ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/010_pi-nopasswd >/dev/null && sudo chmod 440 /etc/sudoers.d/010_pi-nopasswd"`
4. From the laptop, in the repository: `PRINTER_PI=printer.local ./tools/setup_printer_pi.sh`. It copies the print server, installs and starts it as a service (the installer adds `python3-pip` and `python-escpos`, and a udev rule for the printer),
   makes a fresh `PRINT_KEY`, writes `WALL_PRINTER=http://printer.local:8631` and the key into the wall's `.env`, restarts the wall's app and checks the printer from the wall's side.
   Options: `PRINTER_USER`, `WALL_HOST` and `WALL_USER` (the wall's Pi), `PRINTER_TARGET` (`serial:/dev/rfcomm0` for Bluetooth, `tcp://<ip>:9100`).
5. The app's More tab now says "Ready, on another Pi". Take a photo.

## Checking and fixing

- `curl http://printer.local:8631/health` should say `ok usb` (HTTP 200). `503` with "not plugged in" means the Pi does not see the printer: `lsusb` should show `0416:5011` (or your ids).
- The service's log: `ssh pi@printer.local 'journalctl -u print-server -n 20'`. Each job is one `POST /print` line.
- After you change `print_out.py` copy it over and restart: `scp print_out.py pi@printer.local:print-server/ && ssh pi@printer.local 'sudo systemctl restart print-server'`.
  (The dithering happens on the wall's Pi; the printer Pi only receives a finished 1-bit image and drives the printer.)
- Wrong secret = `403`. Re-run the setup script to make a new one on both sides.
