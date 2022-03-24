# Simple toolkit to decode Iridium signals

### Requisites

 * Python (3.7+) (may work with older 3.x, but this is untested)
 * NumPy (scipy)
 * crcmod

### License

Unless otherwise noted in a file, everything here is (c) Sec & schneider and licensed under the 2-Clause BSD License

### Example usage
Either extract some Iridium frames from the air or a file using [gr-iridium](https://github.com/muccc/gr-iridium) (recommended) or use the legacy code located in the [extractror-python](extractor-python/) directory if you don't want to install GNURadio (not recommended).

It is assumed that the output of the extractor has been written to `output.bits`. Iridium frames can be decoded with

    python3 iridium-parser.py -p output.bits

if you want to speed up that step you can install `pypy` and instead run

    pypy3 iridium-parser.py -p output.bits

### Frame extraction
See  [gr-iridium](https://github.com/muccc/gr-iridium) (recommended) or [extractor-python](extractor-python/) (not recommended) on how to extract Iridium frames from raw data.

### Voice Decoding
To listen to voice calls, you will need an AMBE decoder. There are two option:
 - Use tnt's open source AMBE decoder: http://git.osmocom.org/osmo-ir77/tree/codec (`git clone http://git.osmocom.org/osmo-ir77`)
 - Extract an AMBE decoder from a firmware binary. Have a look at the [documentation](ambe_emu/Readme.md) in the `ambe_emu/` directory.

The easier option is to use tnt's AMBE decoder. You can use the extracted decoder if you want to create bit correct output. There almost no audible difference between the two options. Make sure that either `ir77_ambe_decode` or `ambe` is in your `PATH`. Also select the installed one in `play-iridium-ambe`.

Make sure that the main folder of the toolkit is in your `PATH` variable: `export PATH=$PATH:<this directory>`

Steps to decode voice:
 - Decode your captured and demodulated bits using `iridium-parser` and put the result into a file: `pypy iridium-parser.py output.bits > output.parsed`
 - Use `stats-voc.py` to see streams of captured voice frames: `./stats-voc.py output.parsed`
 - Click once left and once right to select an area. `stats-voc.py` will try do decode and play the selected samples using the `play-iridium-ambe` script.

### Frame Format
Partial documentation: http://wiki.muc.ccc.de/iridium:toolkit#frame_format

### Main Components

#### Parser

`iridium-parser.py`

Takes the demodulated bits and tries to parse them into a readable format.

Usage: (it is assumed that the output from gr-iridium is in `output.bits`)

    iridium-parser.py [-p] [--harder] output.bits > output.parsed

Some Options:

* `-p` - Only output frames parsed without errors (and error-correction)
* `--harder` - Try extra hard to decode with the use of error-correction (very slow)
* `--uw-ec` - Try to parse lines with errors inside iridium unique word (also slow)
* `--filter <classname>` - Only decode frames of that class (e.g. `IridiumRAMessage`, `IridiumBCMessage`, etc.) (fast)

#### mkkml

`mkkml`

Converts IRA frames to a kml file to be viewed in google earth.

Run as `grep ^IRA output.parsed |perl mkkml tracks > output.kml` to display satellite tracks

Run as `grep ^IRA output.parsed |perl mkkml heatmap > output.kml` to create a heatmap of sat positions and downlink positions

#### Reassembler

`reassembler.py`

Takes the parsed bits (from `iridium-parser.py`) and reassembles them into higher level protocols.

Supports different modes with the `-m` option.

Usage: (it is assumed that the output from iridium-parser is in `output.parsed`)

    reassembler.py -i output.parsed -m <mode>

Supported modes are currently:

* `ida` - outputs Um Layer 3 messages as hex
* `idapp` - same as above with some light parsing/pretty-printing
* `lap` - GSM-compatible L3 messages as GSMtap compatible `.pcap`
* `page` - paging requests (Ring Alert Channel)
* `msg` - Pager messages
* `sbd` - Short Burst Data messages
* `acars` - parsed ACARS SBD messages
* `ppm` - estimation of receiving SDRs PPM frequency offset

