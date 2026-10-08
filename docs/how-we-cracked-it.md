How we cracked the Pixoo's Bluetooth protocol
=============================================

This is the story of how a Pixoo that "connected fine" but showed nothing
ended up scrolling text from my terminal.

I did this in one afternoon, pair-debugging with an AI (Claude Code). It
ran the experiments and I was the eyes on the screen. That detail matters,
you'll see why.

Every byte below is real. It came from my Pixoo.

The starting point
------------------

I had a working Python CLI. It scanned, connected, built packets, sent
them. Exit code 0. Tests green.

The Pixoo did nothing.

Here's the thing about Bluetooth: "it connected" and "it worked" are
completely different statements. And when a device ignores you, it
doesn't tell you. It just sits there.

So: debug.

Step 1: Is it even there?
-------------------------

First suspect is always the boring one. Scan:

```
Pixoo   rssi -61   (plus ~20 other devices, because it's 2026)
```

There it is, strong signal. Connect and list what it offers:

```
Device Information  (0000180a-…)
49535343-fe7d-4ae5-8fa9-9fafd205e455
   49535343-6daa-…  read                       -> "SPP"
   49535343-aca3-…  notify, write
   49535343-1e4d-…  write-without-response, notify
   49535343-8841-…  write-without-response, write
MTU: 515
```

`49535343-…` is a Microchip/ISSC "transparent UART" service. It's a
Bluetooth chip pretending to be a serial cable. `8841` is the one you
write to, and `1e4d` is the one the device talks back on.

Our config had exactly those UUIDs. Connection fine. UUIDs fine.

So the problem was in *what* we were sending.

Step 2: Listen first
--------------------

The single best debugging move with any device: **subscribe to its notify
channel before you send anything.** Divoom devices answer commands. If
you get an answer, the device understood you. If you don't, it didn't.

We sent the simplest command there is, set brightness (`0x74`), in the
classic Divoom format, to every writable characteristic:

```
-> 01 04 00 74 14 8c 00 02
<- (silence)
```

Silence everywhere.

We also read the device info, which turned out to be useful:

```
Manufacturer: Anyka
Model:        1052D
```

Step 3: A hunch
---------------

The classic `01 … 02` frame is what every open source Divoom project
uses, but most of them talk to the device over *classic* Bluetooth
(serial port), not BLE.

Newer Divoom firmware has a second framing that starts with a magic
header: `FE EF AA 55`. (I couldn't find this documented anywhere. It was a
hunch, so we tested it.)

```
-> fe ef aa 55 04 00 74 14 8c 00
<- 01 09 00 04 33 55 14 8c 00 00 35 01 02
<- 01 05 00 04 50 55 ae 00 02
```

**It answered.** First sign of life all afternoon.

We tested every variant on a fresh connection, one at a time, so we'd
know which packet caused which reply:

| What we sent | Reply? |
| --- | --- |
| classic `01 … 02` | nothing |
| `FE EF AA 55`, length = args + 3 | yes |
| `FE EF AA 55`, length = args + 4 | nothing |

So the new header with the right length is at least *parsed*.

Step 4: …but nothing happens
----------------------------

We sent a full red frame in the new format. The device acked it.

I looked at the Pixoo. Unchanged.

Then a bunch of things that also didn't work:

- Classic format, blue frame, acknowledged writes, link held open: **unchanged.**
- Classic format with byte escaping (old Divoom devices escape `01`/`02`/`03`
  inside packets, because those are the start/end markers): green frame,
  **unchanged.**
- Brightness to zero (the most visible test there is) in both formats:
  **never went dark.**

This is where "the AI ran it, I watched it" mattered. Without someone
looking at the actual screen, every one of these would have looked like a
success. Exit code 0, ack received, ship it.

Step 5: Read the reply, not the docs
------------------------------------

Look at the replies again. Every one had the same shape:

```
01 09 00 | 04 33 55 | ?? ?? ?? ?? | checksum | 02
```

`04` means "response", `55` means "OK". And the 4 `??` bytes were always
copied from *our* packet, right after the command byte.

Four bytes, echoed back to the sender. That smells like a **sequence
number**. Our "command byte" wasn't a command at all, and the device was
saying "got packet #(whatever 4 bytes you put there)".

Test it with an unmistakable number:

```
-> fe ef aa 55 08 00 74 44 33 22 11 00 26 01
<- 01 09 00 04 33 55 44 33 22 11 3f 01 02
                     ^^^^^^^^^^^
```

Echoed exactly. Sequence number confirmed.

Still didn't dim, though. The device accepted the packet but didn't run
the command. So the command must live *inside* the payload somewhere.

Step 6: Four guesses, one run
-----------------------------

We tried four ways of nesting the command, back to back, each one
blacking out the screen for 3 seconds. My job: count which one went dark.

```
1: [00] [seq] [74 00]                    -> transport ack only
2: [01] [seq] [74 00]                    -> !!!
3: [00] [seq] [classic packet inside]    -> weird ack
4: [74] [seq] [classic packet inside]    -> transport ack only
```

Number 2:

```
-> fe ef aa 55 09 00 01 03 00 00 00 74 00 81 00
<- 01 09 00 04 33 55 03 00 00 00 98 00 02         transport ack, seq 3
<- 01 06 00 04 32 55 00 91 00 02                  brightness set: 0
<- 01 1b 00 04 46 55 … 00 …                       settings report: brightness 0
   (then on restore)
<- 01 1b 00 04 46 55 … 64 …                       settings report: brightness 100
```

The device didn't just ack. It **changed its brightness and told us
about it**. And I saw it go dark. Two independent confirmations.

So the envelope is:

```
FE EF AA 55 | LEN (2, LE) | 01 | SEQ (4, LE) | CMD | ARGS | CHECKSUM (2, LE)

LEN      = len(SEQ + CMD + ARGS) + 3
CHECKSUM = sum(LEN bytes, 01, SEQ, CMD, ARGS) & 0xFFFF
```

The `01` is a packet type ("this is a command"). Everything inside
(`CMD`, `ARGS`) is the classic Divoom protocol, unchanged.

Step 7: Pixels
--------------

The real test. Draw picture (`0x44`), left half white, right half magenta,
same image encoding as before, just in the new envelope:

```
<- 01 09 00 04 33 55 0a 00 00 00 9f 00 02    transport ack
<- 01 06 00 04 44 55 98 3b 01 02             draw picture: OK
```

White | magenta, on the screen.

Then the real CLI: `pixoo text "Hi" --color cyan` showed a cyan "Hi".

Step 8: Scrolling didn't scroll
-------------------------------

`pixoo scroll "Hello Pixoo"` did nothing. Still the cyan "Hi".

A scroll is an animation: ~68 frames, ~15KB, split into 77 packets.
Replaying them one by one, each got a transport ack… but no "animation OK"
reply. We sent all 77, slowly, with acknowledged writes:

```
<- 01 05 00 04 49 55 a7 00 02     animation (0x49): OK
```

Scrolling.

The difference from the CLI: the CLI used BLE's *write without
response*, fired all 77 packets as fast as possible, and disconnected
immediately. Some packets never made it, so the device never got a
complete animation and quietly gave up. A single image is one packet,
which is why `text` worked and `scroll` didn't.

Fix: acknowledged writes (`response=True`). Slower, reliable.

Step 9: Making it work on a Raspberry Pi
----------------------------------------

I want this running on a Pi 5. Two things could bite:

**Python version.** My Mac had Python 3.14. One file used `Optional` in a
type hint without importing it. Python 3.14 evaluates annotations lazily,
so it never noticed. Python 3.11 (Raspberry Pi OS) would crash on import.
We fixed it and checked the code on 3.9 and 3.12.

**Packet size.** On macOS the link carried 512 bytes per write, so packets
never got split. On Linux, BLE often negotiates the minimum (23-byte MTU,
20 bytes of payload). The code splits packets into pieces that fit, but
that path had never touched the real device. So we forced 20-byte pieces
on the Mac and sent a scroll. It scrolled: the chip is a serial bridge,
so it just reassembles the stream.

Bonus bug: the test that talked to my Pixoo
-------------------------------------------

One unit test was failing, and it wasn't about protocols. It mocked the
Bluetooth *scan*, but there was a real saved device address on disk, so
the code skipped the scan and **connected to my actual Pixoo** from
inside the test suite. Now the test uses a temporary cache path.

What I'd tell you if you're doing this with your own device
-----------------------------------------------------------

1. **Connected ≠ working.** Find a way to observe the result.
2. **Subscribe to notifications before you send anything.** The device's
   replies are the best documentation you'll get.
3. **Send the most boring, most visible command.** Brightness to zero
   beats drawing a picture: it's tiny, and you can't miss it.
4. **One variable per test, fresh connection each time.** Otherwise you
   don't know which packet caused which reply.
5. **Use weird values.** `0x11223344` as a sequence number told us in
   one shot what those 4 bytes were.
6. **Someone has to look at the screen.** An ack only means the packet
   arrived. It doesn't mean anything happened.

If your Pixoo behaves differently, run `tools/probe.py` and open an issue
with the output.
