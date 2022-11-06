#!/bin/sh

if [ -d html ] ; then
  cd html
fi



../reassembler.py -m live-map --stats zmq: &
reass=$!

killer(){
    kill $reass
    exit
}
trap killer INT

echo
echo "open http://localhost:8888/map.html in your browser"
echo ""
echo "and make sure 'iridium-parser' is running with -o zmq on this host"
echo

python3 -m http.server --bind 127.0.0.1 8888

kill $reass
