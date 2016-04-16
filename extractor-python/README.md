# Legacy Python Iridium frame extractor
This is a legacy implementation written in Python and NumPy.

It is provided for reference reasons. Please use the new
GNURadio based code which can be found at
https://github.com/muccc/gr-iridium

The GNURadio based branch offers better performance with
respect to computational effort and results.

### Extracting Iridium packets from raw data

To capture and demodulate Iridium packets use `extractor.py`. You can either process
a file offline or stream data into the tool.

#### Command line options:

##### `-o`, `--offline`: Process a file offline
By default, the extractor will drop samples if the computing power available is
not enough to keep up. If you have an already recorded file, use the `-o`,`--offline`
option to not drop any samples. In this case the extractor will pause reading the
file (or input stream) until it can process more samples again.

##### `-q`: Queue length
The internal queue is filled with samples where the detector has detected activity
in the file. By default it is 12000 elements long (roughly 4 GB at 2 Maps). You can
tweak the length of the queue with this option

##### `-c`: Center frequency
The center frequency of the samples data in Hz.

##### `-r`: Sample rate
The sample rate of the samples in sps

##### `-f`: Input file format
| File Format                                        | `extractor.py` format option |
|----------------------------------------------------|------------------------------|
| complex uint8 (RTLSDR)                             | `rtl`                        |
| complex int8 (hackrf, rad1o)                       | `hackrf`                     |
| complex int16 (USRP with specrec from gr-analysis) | `sc16`                       |
| complex float (GNURadio, `uhd_rx_cfile`)           | `float`                      |

##### `-j`, `--jobs`
The number of processes to spawn which demodulate packets. The detector runs in the main
process.

