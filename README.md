# Simple toolset to decode Iridium signals

### Requisites:

 * python (2.7)
 * numpy (scipy)
 * perl (5.x)

### Licence

Unless otherwise noted in a file, everyting here is
(c) Sec & schneider
and licenced under the 2-Clause BSD Licence

### Example usage
#### Capture with [hackrf](https://greatscottgadgets.com/hackrf/) or [rad1o](https://rad1o.badge.events.ccc.de/start) and multiprocessing

Note: The rad1o has to be in hackrf-mode

    hackrf_transfer  -r /dev/stdout -f 1627000000 -a 1 -l 40 -g 20 -s 2000000 | python2 multiprocessing-sec.py -c 1627000000 -r 2000000 -f hackrf --jobs 2 | grep "A:OK" | tee outfile

This writes to `outfile`. Pager messages can be decoded with

    python2 iridium-parser.py outfile

#### Capture with usrp and processing in stages
##### Manual
record with usrp. So far we've used two settings:

The catch-all interesting stuff
 * center frequency: 1626270833
 * sample rate: 2000000 (2M)

or to just catch pager channel stuff and smaller files:
 * center frequency: 1626440000
 * sample rate: 250000 (250k)

The output files are named

`<date>-vX.raw`

X is the X'th file of the day
the v is replaces with an s on the "narrow" receive settings


To process them, there are three stages:

###### stage1:

`detector-fft.py <rawfilename>`

this searches through the file in 5ms steps to scan for activity
and copies these parts into snippets called `<rawfilename>-<timestamp>.det`

###### stage2:

`cut-and-downmix.py <detectorfile>`

this mixes the signal down to 0Hz and cuts the beginning to match
the signal exactly. Output is `<detfile>-f<frequency>.cut`

###### stage3:

`demod.py`

this does manual dqpsk demodulation of the signal and outputs
`<cutfile>.peaks` (for debugging)
`<cutfile>.data` the raw bitstream
and on stdout an ascii summary line.

###### stage4:

gather all the ascii bits in a single file `<rawfilename>.bits`

##### Automatic

To simplify running these tools, there is `doit.pl`.

it runs stage1 (if requested)
then
it runs stage2/3 per output of stage1, up to $ncpu times in paralell
then
run stage4 (if requested)

run it as `doit.pl [-1234] rawfilename`

if you give no options, it tries to autodetect what stages haven't yet run
