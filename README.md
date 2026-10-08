pixoo-cli
=========

Push text, scrolling text, images and GIFs to a Divoom Pixoo (the 16×16
one) over Bluetooth LE. From your Mac, from Linux, from a Raspberry Pi 5.

No app. No account. No cloud. Just:

```sh
./pixoo.py text "Hi"
```

Why this exists
---------------

I have a Pixoo on my desk. The only official way to talk to it is Divoom's
phone app.

I wanted my computer (and a Raspberry Pi) to push things to it. Build
status, a clock, a scrolling message, whatever.

There are a few open source projects for Divoom devices. I tried their
protocol. The Pixoo connected, accepted every byte, and did absolutely
nothing.

So we cracked it. It turns out that over Bluetooth LE, this Pixoo ignores
the packet format everyone documents and only listens to a different,
undocumented one. The whole story (with the bytes) is in
[docs/how-we-cracked-it.md](docs/how-we-cracked-it.md). It's a fun read if
you like this kind of thing.

The short version is in [What's different about this one](#whats-different-about-this-one).

Setup
-----

You need Python 3.9+ and two packages: `bleak` (Bluetooth) and `Pillow`
(images). That's it. You don't need to install pixoo-cli itself:
`pixoo.py` runs straight from the folder.

```sh
git clone https://github.com/jonromero/pixoo-cli.git
cd pixoo-cli
```

### macOS

```sh
python3 -m pip install -r requirements.txt
```

The first run asks for Bluetooth permission for your terminal app. Say yes
(System Settings → Privacy & Security → Bluetooth).

### Raspberry Pi 5 (Raspberry Pi OS)

The Pi 5's built-in Bluetooth works; you don't need a dongle.

Raspberry Pi OS won't let you `pip install` into the system Python (PEP
668), so pick one of these.

The distro packages:

```sh
sudo apt install python3-bleak python3-pil
python3 -c "import bleak; print(bleak.__version__)"   # needs 0.22+
```

Or a virtualenv:

```sh
python3 -m venv ~/.venvs/pixoo
~/.venvs/pixoo/bin/pip install -r requirements.txt
~/.venvs/pixoo/bin/python pixoo.py text "Hi"
```

Make sure Bluetooth is on:

```sh
sudo systemctl enable --now bluetooth
bluetoothctl power on
```

You don't need root, and you don't need to pair the Pixoo. The tool
connects directly.

Usage
-----

```sh
./pixoo.py text "Hi"
./pixoo.py text "Hi" --color cyan --bg-color black
./pixoo.py scroll "Hello Pixoo" --color yellow
./pixoo.py scroll "faster" --frame-px 2 --delay-ms 50
./pixoo.py image photo.png
./pixoo.py gif anim.gif
./pixoo.py discover-gatt            # dump the device's GATT services
./pixoo.py --help
```

Colors are `#RRGGBB` or one of: black, white, red, green, blue, yellow,
cyan, magenta, orange, purple, pink.

Images get resized to 16×16 with nearest-neighbor, so pixel art stays
sharp. GIFs keep their own frame timing.

Want to call it from anywhere?

```sh
ln -s "$PWD/pixoo.py" ~/.local/bin/pixoo
pixoo text "Hi"
```

### Which Pixoo?

The first run scans for anything named `Pixoo` or `DIVOOM`. If there's
more than one, it asks you to pick.

After a successful send it saves the address to
`~/.cache/pixoo-cli/last_device`, so the next run skips the scan. Use
`--rescan` if you swap devices or it can't connect.

(The saved address belongs to one machine. macOS gives Bluetooth devices
its own private IDs, while Linux uses the real MAC address, so each machine
keeps its own.)

### Configuration

You can override every default with an environment variable. You probably
won't need to.

| Variable | Default |
| --- | --- |
| `PIXOO_GRID_SIZE` | `16` |
| `PIXOO_SERVICE_UUID` | `49535343-fe7d-4ae5-8fa9-9fafd205e455` |
| `PIXOO_WRITE_CHAR_UUID` | `49535343-8841-43f4-a8d4-ecbe34729bb3` |
| `PIXOO_NOTIFY_CHAR_UUID` | `49535343-1e4d-4bd9-ba61-23c647249616` |
| `PIXOO_DEVICE_NAME_PREFIXES` | `Pixoo,DIVOOM` |
| `PIXOO_CACHE_PATH` | `~/.cache/pixoo-cli/last_device` |

What's different about this one
-------------------------------

If you've read other Divoom projects, here's what changes, and why.

**1. A different packet envelope.** Everyone documents this frame:

```
01 | LEN (2) | CMD | ARGS | CHECKSUM (2) | 02
```

Over BLE, my Pixoo ignores it completely. No reply, no error, nothing. It
only runs commands wrapped like this:

```
FE EF AA 55 | LEN (2) | 01 | SEQ (4) | CMD | ARGS | CHECKSUM (2)

LEN      = len(SEQ + CMD + ARGS) + 3            (little-endian)
CHECKSUM = sum(LEN .. ARGS) & 0xFFFF            (little-endian)
SEQ      = any 32-bit number, echoed back in the ack
```

Inside the envelope, everything is the classic Divoom protocol: same
commands (`0x44` draw picture, `0x49` animation, `0x74` brightness…),
same palette-based image format. Funny detail: the Pixoo *replies* in the
old `01 … 02` format.

**2. Acknowledged writes.** BLE has "fire and forget" writes and
"acknowledged" writes. Fire and forget is faster, and it works for a
single image. A scrolling text is ~80 packets, though, and enough of them
get dropped that the animation never completes. Acknowledged writes fix
it. A long scroll takes a few seconds to upload. Worth it.

**3. Small MTU is fine.** On Linux, BLE usually negotiates tiny packets (20
bytes of payload), so every packet gets split into pieces. I tested this:
the Pixoo's Bluetooth chip is a transparent serial bridge, so it glues the
pieces back together.

Full byte-level reference: the docstring at the top of
[`pixoo_cli/protocol.py`](pixoo_cli/protocol.py).

Is my Pixoo the same as yours?
------------------------------

Mine reports itself as manufacturer `Anyka`, model `1052D`, with an ISSC
"transparent UART" service (`49535343-…`). Divoom ships different chips
and firmware over the years, so yours might talk differently.

If the tool runs without errors but the screen doesn't change, run this:

```sh
./tools/probe.py
```

It sends a brightness command in both packet formats and prints what the
Pixoo answers. That tells you in about 15 seconds which format your
device speaks. (Your screen will blink. That's the point.) Open an issue
with the output and we'll figure it out.

Troubleshooting
---------------

- **"No Pixoo device found"**: is it on? Is it close? Is the Divoom app
  connected to it? The Pixoo takes one BLE connection at a time, so close
  the app.
- **"Connection failed"**: try `--rescan`. The saved address might be
  stale.
- **Runs fine, screen doesn't change**: see [Is my Pixoo the same as
  yours?](#is-my-pixoo-the-same-as-yours)

Project layout
--------------

```
pixoo.py              # the thing you run
pixoo_cli/
  cli.py              # argument parsing, device pick, send
  ble.py              # scan, connect, write (bleak)
  protocol.py         # pixels -> packets. The interesting part.
  text.py             # text -> pixels (Pillow's built-in bitmap font)
  image.py            # images/GIFs -> pixels
  config.py           # defaults + environment overrides
tools/probe.py        # "which protocol does my Pixoo speak?"
docs/                 # how we figured all this out
tests/
```

Development
-----------

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

The tests never touch real hardware. One of them used to, by accident.
That story is in the docs too.

License
-------

MIT. Do whatever you want with it. If you make your Pixoo do something
cool, tell me.
