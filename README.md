# make-flipbook

Build an animated 3D book for a Ghost HTML card. The book stands on its spine, turns to show the cover, opens, and flips through the first pages.

The script reads two PDFs, a cover wrap and an interior, and writes one self-contained HTML file. Paste the file into a Ghost HTML card. The file needs no external images, scripts, or fonts.

## Requirements

- Python 3 with [Pillow](https://pypi.org/project/pillow/).
- [poppler](https://poppler.freedesktop.org/) for `pdftoppm` and `pdfinfo`.

### Setup on macOS

```bash
brew install poppler
python3 -m venv ~/flipbook-venv
~/flipbook-venv/bin/pip install pillow
```

## Usage

```bash
~/flipbook-venv/bin/python3 make_flipbook.py
```

The script asks for three inputs:

- The book title.
- The cover PDF. Drag the file into the Terminal window to paste its path.
- The interior PDF.

The script writes `<title>-flip.html` to the current directory and opens it in your browser.

## How It Works

- **Cover.** The script finds the printer's fold marks to split the wrap into back, spine, and front panels. It falls back to a spine width you type if it finds no marks.
- **Pages.** The script crops each page to the trim box and tints it cream to match the 3D paper. It embeds at most 10 interior pages.
- **Output.** Every image embeds as a base64 JPEG. CSS 3D transforms and a small script drive the animation.

## Limits

- The cover PDF and the interior PDF must each contain a trim box.
- The script handles one book at a time.
- Each output file grows with the page count, typically about 1 MB.

## Copyright

The output embeds your cover and pages. Build flipbooks only from books that you hold the rights to publish.

## License

MIT. See [LICENSE](LICENSE).
