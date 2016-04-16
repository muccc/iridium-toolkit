# Simple toolkit to decode Iridium signals

### Requisites

 * Python (2.7)
 * NumPy (scipy)

### License

Unless otherwise noted in a file, everything here is
(c) Sec & schneider
and licensed under the 2-Clause BSD License

### Example usage
#### Capture with [hackrf](https://greatscottgadgets.com/hackrf/) or [rad1o](https://rad1o.badge.events.ccc.de/start) and extractor-python

Note: The rad1o has to be in hackrf-mode

    hackrf_transfer -f 1625800000 -a 1 -l 40 -g 20 -s 2000000 -r /dev/fd3 3>&1 1>&2 | python2 extractor-python/extractor.py -c 1625800000 -r 2000000 -f hackrf --jobs 2 | fgrep "A:OK" >> output.bits

If you built/installed the rad1o branch of the hackrf tools, add `-S 26214400` to the commandline like this:

    hackrf_transfer -f 1625800000 -a 1 -l 40 -g 20 -s 2000000 -S 26214400 -r /dev/fd3 3>&1 1>&2 | python2 extractor-python/extractor.py -c 1625800000 -r 2000000 -f hackrf --jobs 2 | fgrep "A:OK" >> output.bits

This writes to `output.bits`. Iridium frames can be decoded with

    python2 iridium-parser.py output.bits

if you want to speed up that step you can install `pypy` and instead run 

    pypy iridium-parser.py output.bits

### Frame extraction
See the python-extractor [README](python-extractor/README.md)

### Voice Decoding
To listen to voice calls, you will need an AMBE decoder. There are two option:
 - Use tnt's open source AMBE decoder: http://git.osmocom.org/osmo-ir77/tree/codec
 - Extract an AMBE decoder from a firmware binary. Have a look at the [documentation](ambe_emu/Readme.md) in the `ambe_emu/` directory.

The easier option is to use tnt's AMBE decoder. You can use the extracted decoder if you want to create bit correct output. There almost no audible difference between the two options. Make sure that either `ir77_ambe_decode` or `ambe` is in your `PATH`. Also select the installed one in `play-iridium-ambe`.

Make sure that the main folder of the toolkit is in your `PATH` variable: `export PATH=$PATH:<this directory>`

Steps to decode voice:
 - Decode your captured and demodulated bits using `iridium-parser` and put the result into a file: `pypy iridium-parser.py output.bits > output.parsed`
 - Use `voc-stats.py` to see streams of captured voice frames: `./voc-stats.py  output.parsed`
 - Click once left and once right to select an area. `voc-stats.py` will try do decode and play the selected samples using the `play-iridium-ambe` script.


### Main Components

#### Detector
`detector-fft.py`

Searches through the file in 1 ms steps to scan for activity
and copies these parts into snippets called `<rawfilename>-<timestamp>.det`

#### Cut and Downmix

`cut-and-downmix.py`

Mixes the signal down to 0 Hz and cuts the beginning to match
the signal exactly. Output is `<detfile>-f<frequency>.cut`

#### Demod

`demod.py`

Does manual DQPSK demodulation of the signal to stdout.
If enabled inside `demod.py` it also outputs
`<cutfile>.peaks` (for debugging)
`<cutfile>.data` the raw bit stream.

#### Parser

`iridium-parser.py`

Takes the demodulated bits and tries to parse them into a readable format.

Supports some different output formats (`-o` option).

