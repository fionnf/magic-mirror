# A wireless receipt printer: the second Pi

The wall's Pi (`mirror4`) sends every finished picture over Wi-Fi to a small Pi that the printer is plugged into.

1. **Flash the SD card** with Raspberry Pi Imager: *Raspberry Pi OS Lite (64-bit)*. Press the settings button
   (Ctrl+Shift+X) and set: hostname `printpi`, username `pi` and a password, your Wi-Fi name and password (same network as
   the wall), country, and *Enable SSH* (password or your public key).
2. Put the card in the Pi, plug the printer into a USB port, power it on and wait about two minutes.
3. From this laptop, in the repository: `PRINTER_PI=printpi.local ./tools/setup_printer_pi.sh`
   (Bluetooth printer: add `PRINTER_TARGET=serial:/dev/rfcomm0`; Wi-Fi printer with no Pi: set `WALL_PRINTER=tcp://<ip>:9100`
   in the wall's `.env` instead and skip all this).
4. The app's Mirror settings now say "Ready, on another Pi (printpi.local:8631)". Take a photo: it prints.

The shared secret (`PRINT_KEY`) is made by the script and kept in the `.env` of the wall and in the print service on `printpi`.
