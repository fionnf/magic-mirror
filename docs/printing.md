# Printing: quality, layout and the printer Pi

Receipts and photobooth strips go to a 58 mm thermal printer (ESC/POS, 384 dots wide at 203 dpi). The printer can be on the wall's Pi, on a second Pi in the room (the author's setup,
over Wi-Fi), on the network, or on Bluetooth: see the table in the panel_setup README, and [printer-pi.md](printer-pi.md) for setting up the second Pi from scratch.

## How a picture becomes paper

`printer.py` composes the picture in **two layers**: a *base* layer with the photographs, and an *ink* layer with everything that must stay crisp (text, frames, number stickers, hearts, sparkles, the QR code).
`print_out.to_1bit()` then dithers only the base and draws the ink on top at full resolution, so small type is never broken up by the halftone. The result is sent to the printer as one 1-bit raster image.

| Setting (env, in `.env`) | Default | Meaning |
|---|---|---|
| `PRINTER_DITHER` | `floyd` | `floyd` (Floyd-Steinberg), `atkinson` (open midtones) or `bayer` (a regular ordered pattern) |
| `PRINTER_SCALE` | `1` | 1 = single dots. 2 = dither at half resolution and print each pixel as a 2 x 2 block (bolder, coarser) |
| `PRINTER_FEED_DOTS` | `90` | Blank paper after a print (8 dots = 1 mm). The cutter sits about 10 mm past the head, so less than ~80 will cut through the picture |
| `PRINTER_QUALITY` | `0` | `1` sends the heat-time and density commands (`PRINTER_HEAT`, `PRINTER_DENSITY`). **Leave it off unless your printer knows them**: the author's printer does not, and printed their bytes as three stray symbols at the top of every slip |
| `PRINTER_WIDTH_DOTS` | `384` | Printable width; 360 if the right edge wraps |
| `PRINTER_VENDOR_ID`, `PRINTER_PRODUCT_ID` | `0x0416`, `0x5011` | USB ids (`lsusb`) |

The photo itself is prepared by `printer._preprocess` from `config.PRINTER_IMAGE_*` (autocontrast, gamma 0.7, brightness 1.1, contrast 1.1, a gentle sharpen).
The message type size is `config.PRINTER_MESSAGE_FONT_SIZE` (24). Printer-width, header (`PRINTER_HEADER`, the street name on the slip) and the other layout constants are in `config.py`.

## Choosing the quality for your printer: the test slip

Thermal printers differ a lot (heat, paper, how much dots bleed). Print the same photo seven ways and pick the best by eye:

```bash
cd ~/magic-mirror && set -a && . ./.env && set +a
python3 tools/print_test_slip.py            # newest photo in photos/ (or --photo file.jpg; --no-print to just write a PNG)
```

The slip (about 29 cm) has A: single dots, Atkinson; **B: single dots, Floyd-Steinberg**; C: single dots, Bayer; D: 2 x 2 blocks, Atkinson; E: 2 x 2 blocks, Bayer; F: single dots Atkinson, lighter; G: single dots Bayer, lighter.
On the author's printer **B** won (it is the default now); the 2 x 2 blocks looked blocky and the original Atkinson a little muddy. Set your winner with `PRINTER_DITHER` and `PRINTER_SCALE` in `.env`
and restart `wall-control`.

## Layouts

- **Receipt** (`_receipt_image`): the street name with a sparkle each side, the date, a portrait photo in a frame with a small heart sticker, and the AI line. With "no comment" there is no text block at all.
- **Photobooth strip** (`render_booth_pil`): a title with hearts and sparkles over a scalloped edge; each photo a portrait (360 x 480 dots, 3:4, the shape of a single printout) in a square frame with a round number sticker;
  under it the pose direction between two sparkles (the type shrinks to fit a long one); a footer with the house, the date and the QR code. 1716 dots (about 21 cm) with a QR code, 1650 without. All of it is shapes and ordinary text, so it prints the same whichever font is installed.
- **The QR code** points at the day's shared Drive folder ([google-drive.md](google-drive.md)); it is drawn with whole-dot modules so it scans off thermal paper (checked by decoding the final 1-bit image). No Drive set up = no QR code and a shorter footer.

## Several printers' worth of options

`WALL_PRINTER` in `.env`: `usb`, `http://<pi>.local:8631` (the print server on a second Pi, with the same `PRINT_KEY` on both sides), `tcp://<ip>:9100` (a network printer) or `serial:/dev/rfcomm0` (Bluetooth).
The app's More tab shows whether the printer answers (`GET /api/printer`).
