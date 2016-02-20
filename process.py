#!/usr/bin/python
# usage: ./process.py output.bits
# runs:
#	iridium-parser.py
#	stats-parsed
#	greps for VOC packets
#	voc-cluster
#	bits_to_dfs.py
#	ambe to wav

import os
import sys
import time

DEBUG = 1

runtime = int(time.time())

file_to_process = sys.argv[1]
basedir = "/home/user/sdr/iridium-toolkit/"
print "DEBUG: basedir: " + basedir if DEBUG == 1 else ""

os.system("rm -rf /tmp/samples")
os.system("mkdir -p /tmp/samples")

tmpdir = "tmp" + str(runtime)
print "DEBUG: tmpdir: " + tmpdir if DEBUG == 1 else ""

workdir = basedir + tmpdir
print "DEBUG: workdir: " + workdir if DEBUG == 1 else ""

os.system("mkdir -p " + basedir + tmpdir)
print "DEBUG: made tmpdir: " + tmpdir if DEBUG == 1 else ""

print "DEBUG: running iridium-parser.py" if DEBUG == 1 else ""
os.system("/usr/bin/python2 " + basedir + "iridium-parser.py " + file_to_process + " > " + workdir + "/iridium-packets.txt")

print "DEBUG: running stats-parsed" if DEBUG == 1 else ""
os.system("/bin/sh " + basedir + "stats-parsed " + workdir + "/iridium-packets.txt")

print "DEBUG: running grep voc" if DEBUG == 1 else ""
os.system('grep "VOC" ' + workdir + '/iridium-packets.txt > ' + workdir + '/voc.bits')

print "DEBUG: voc-cluster" if DEBUG == 1 else ""
os.system("/usr/bin/python2 " + basedir + "voc-cluster.py " + workdir + "/voc.bits")

print "DEBUG: ls /tmp/samples: " if DEBUG == 1 else ""
print "------------------------------"
os.system("ls -al /tmp/samples")
print "------------------------------"

print "DEBUG: making workdir samples dir" if DEBUG == 1 else ""
os.system("mkdir -p " + workdir + "/samples")

print "DEBUG: moving samples from /tmp" if DEBUG == 1 else ""
os.system("mv /tmp/samples/*.msg " + workdir + "/samples/")

print "DEBUG: bits to dfs and ambe" if DEBUG == 1 else ""
for filename in os.listdir(workdir + "/samples/"):
	print "PROCESSING FILE: " + filename
	os.system("/usr/bin/python2 " + basedir + "bits_to_dfs.py " + workdir + "/samples/" + filename + " " + workdir + "/samples/" + filename.replace(".msg","") + ".dfs")
	os.system(basedir + "ambe_emu/ambe -w " + workdir + "/samples/" + filename.replace(".msg","") + ".dfs")

current_date = time.strftime("%Y-%m-%d-%H-%M")
print "DEBUG: creating dir: " + basedir + "wavs/" + current_date if DEBUG == 1 else ""
os.system("mkdir -p " + basedir + "wavs/" + current_date)

print "DEBUG: moving wavs" if DEBUG == 1 else ""
os.system("mv " + workdir + "/samples/*.wav " + basedir + "wavs/" + current_date)

print "DEBUG: wavs in " + basedir + "wavs/" + current_date if DEBUG == 1 else ""

print "------------------------------"
os.system("ls -al " + basedir + "wavs/" + current_date)
print "------------------------------"

print "DEBUG: done" if DEBUG == 1 else ""
