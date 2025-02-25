# Simple toolkit to decode & analyze Iridium signals

This collection of tools can be used to parse/decode iridium frames and reassemble higher-level information.

:warning: To use these tools you need raw iridium frames as received/extracted by
 `iridium-extractor` from the [gr-iridium](https://github.com/muccc/gr-iridium) OOT gnuradio module.

## Requisites

 * Python (3.7+) (may work with older 3.x, but this is untested)
 * crcmod

 ### Optional python modules
 These modules are required for some specific tools/features.
 * NumPy (reassembler)
 * matplotlib (iridium-parser --plot & others)
 * astropy
 * skyfield
 * pymap3d
 * pyproj

## License

Unless otherwise noted in a file, everything here is (c) Sec & schneider and licensed under the 2-Clause BSD License

## Tools

This is an oveview over the most relevant scripts in this repo. More detailed information on how to use some of them can be found later on in this README

### iridium-parser.py
Main tool to 'parse' raw iridium bits. Output is an ascii line-based representation of the information contained in each frame.

The output format is described in (FORMAT.md)[FORMAT.md]

#### Example usage

It is assumed that the output of `iridium-extractor` has been written to `output.bits`. Iridium frames can then be decoded with

    python3 iridium-parser.py -p output.bits

if you want to speed up that step (by about 50%) you can install `pypy` and instead run

    pypy3 iridium-parser.py -p output.bits

Output is currently to `stdout` by default.

### reassembler.py
Tool to 'reconstruct' higher level information out of the parsed format produced by `iridium-parser`

Run `reassembler.py -m help` to see all available modes.

#### Example usage

    python3 reassembler.py -m idapp output.parsed
or

    python3 reassembler.py -m acars output.parsed -a nopings

Output is usually to stdout

## Legacy (reference) code

### Frame extraction
There is a legacy (python2) implementation in the  [extractor-python](extractor-python/) subdirectory. It is no longer maintained since 2017, so use at your own risk.

# Main Tools
## iridium-parser

Takes the demodulated bits produced by `iridium-extractor` and tries to parse them into a readable format. For a description of the output ofrmat, see [FORMAT.md](FORMAT.md)


### Usage:

    iridium-parser.py [--options] in.bits > out.parsed

If no input file is specified, input is taken from stdin.

Input files with the extensions `.xz`, `.bz2` and `.gz` will automatically be decompressed

Output is written to stdout

#### Options

##### --stats

Enable incremental statistics output to stderr to see/verify progress of the parsing

##### --uw-ec

Enable error correction in the uniq word. Increases processing time.

##### --harder

Try to decode packets with correctable bit errors at the beginning. Significantly increases processing time.

##### --disable-freqclass

Disable optimisation of parsing simplex/duplex packets. Will increase processing time. May improve parsing if frequencies in your `bits` file are incorrect.

##### --sigmf-annotate=/path/to/recording.sigmf-meta

Will re-write the sigmf-meta file to include annotations for all input bits. The annotations specifies the iridum frame type or reason why parsing failed. It includes the "I:" debug id from the .bits file to identify the spcific frame.

Normal parser output is suppressed when using this switch.

You can view the annotated sigmf recording in [inspectrum](https://github.com/miek/inspectrum) to visually inspect the iridium signals.

#### Filtering options

##### --good

  Only output lines with a confidence of >= 90

##### --confidence=

  Only output lines with greater or equals of the specified confidence

##### --errorfree

   Only output line without uncorrectable errors

##### --perfect

   Only output lines without errors (both uncorrectable & correctable)

##### --errorfile=

   Diverts output lines with uncorrectable errors into the specified file. If no filename is specified, it is automatically generated based off of the input filename.

##### --errorstats

   Prints error statistics to stderr at end of output

# debugging / development

##### --verbose

Currently no effect

##### --output=

Default is "line", other valid options are "err", "sat", "plot", "rxstats".

##### --forcetype=

Forces input to be parsed as specified type. Usually only useful with single lines.

Valid options are MS / TL / RA / BC / LW:<0-7>

##### --filter=

Only process lines matching this filter. Will run faster than "grep"ing the output.

Parameter is "classname[+attr][,check]"

Examples:
  `--filter=IridiumRAMessage,q.ra_alt>100` -- only IRA messages with altitude > 100
  `--filter=IridiumBCMessage+iri_time_ux` -- only IBC messages with iridium timestamps

##### --format=

Output the specified fields (space-separated). Usually specified together with `--filter`.

example:
  `--format=globaltime,iri_time_ux,slot,sv_id,beam_id`

##### --channelize

replace frequency field with `SB.FA|±offset` where SB (subband) is either `S` for Simplex or a number from 1-30 and FA (frequency access) is a number from 1 to 8 (1 to 12 for the simplex SB)
See (parse_channel())[https://github.com/muccc/iridium-toolkit/blob/8505bc5a5a6d6983b078da635794ae5357309304/util.py#L178] for conversion back to frequency.

`frequency = 1615604164 + (FA + 8*SB) * 41667 + offset`

##### --plot=[xfield,yfield]

create 2d plot of numeric data. Honors `--filter=`, requires `--output=plot`

examples:
  `--filter=IridiumBCMessage+iri_time_ux --plot=time,iri_time_ux --output=plot`
  `--filter=IridiumRAMessage --plot=time,frequency --output=plot`


#### broken/undocumented
##### --satclass
##### --voice-dump=

## reassembler
`reassembler.py`

Takes the parsed bits (from `iridium-parser.py`) and reassembles them into higher level protocols.

Supports different modes with the `-m` option.

### Usage:
it is assumed that the output from iridium-parser is in `output.parsed`

    reassembler.py -i output.parsed -m <mode>

Supported modes are currently:

* `ida` - outputs Um Layer 3 messages as hex
* `idapp` - same as above with some light parsing/pretty-printing
* `lap` - GSM-compatible L3 messages as GSMtap compatible `.pcap`
* `page` - paging requests (Ring Alert Channel)
* `msg` - Pager messages
* `burst` - "Global Data Burst" messages assembled from pager messages
* `sbd` - Short Burst Data messages
* `acars` - parsed ACARS SBD messages
* `ppm` - estimation of receiving SDRs PPM frequency offset
* `live-stats` - per 10-minute statistics of received packet type in graphite format
* `live-map` - live update a `sats.json` file for an interactive satellite display.
* `satmap` - tries to map iridium satellite IDs to NORAD-approved names.
  Requires an appropriate TLE file in tracking/iridium-NEXT.tle

# Additional Tools
:warning: These tools are not the main focus of this repository and may not be working out of the box for you.

## Voice Decoding
To listen to voice calls, you will need an AMBE decoder. There are two options:
 - Use tnt's open source AMBE decoder: http://git.osmocom.org/osmo-ir77/tree/codec (`git clone http://git.osmocom.org/osmo-ir77`)
 - Extract an AMBE decoder from a firmware binary. Have a look at the [documentation](ambe_emu/Readme.md) in the `ambe_emu/` directory.

The easier option is to use tnt's AMBE decoder. You can use the extracted decoder if you want to create bit correct output. There almost no audible difference between the two options. Make sure that either `ir77_ambe_decode` or `ambe` is in your `PATH`. Also select the installed one by editing the  `play-iridium-ambe` script.

Make sure that the main folder of the toolkit is in your `PATH` variable: `export PATH=$PATH:<this directory>`

#### Steps to decode voice:
 - Decode your captured and demodulated bits using `iridium-parser` and put the result into a file: `pypy3 iridium-parser.py output.bits > output.parsed`
 - Use `stats-voc.py` to see streams of captured voice frames: `./stats-voc.py output.parsed`
 - Click once left and once right to select an area. `stats-voc.py` will try do decode and play the selected samples using the `play-iridium-ambe` script.
#### Other options
- The `voc-cluster.py` and `vod-cluster.py` scripts try to automatically extract all clusters of `VOC` or `VOD` from a given input file. It will produce `call-0000.parsed` or `fail-0000.parsed` based on whether they can be decoded as voice calls. This uses the `check-sample` script internally and requires `ir77_ambe_decode` to be available.

## mkkml

`mkkml`

Converts IRA frames to a kml file to be viewed in google earth.

Run as `grep ^IRA output.parsed |perl mkkml tracks > output.kml` to display satellite tracks

Run as `grep ^IRA output.parsed |perl mkkml heatmap > output.kml` to create a heatmap of sat positions and downlink positions

The resulting kml files can be viewed in google earth

## beam-plotter

This will generate a picture of the spot beam pattern of a given satellite

Create a suitable input file by running

    iridium-parser.py --filter IridiumRAMessage --format ra_sat,ra_cell,ra_pos_x,ra_pos_y,ra_pos_z,globalns output.bits > output.ira

and then run

    beam-plotter.py [-s satno] output.ira

## beam-reception-plotter
This will generate a reception pattern for each spot beam of a given satellite

This will require a `locations.ini`with your receiver position in it to work properly.

Run as

    beam-reception-plotter.py [-s satno] output.parsed

Depending on when your recording was made and how long it is, selecting the other flight direction with `-d s` may contain more data.

In the resulting window you can click on each line in the legend to toggle specific beams on and off
