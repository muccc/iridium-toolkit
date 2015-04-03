# Some utility functions to do simple stuff with our .bits files
# Mostly just to do statistics

import re
import datetime
import fileinput

def extract_timestamp(filename, dt):
    mm=re.match("i-(\d+(?:\.\d+)?)-[vbsrtl]1.([a-z])([a-z])",filename)
    if mm:
        b26=(ord(mm.group(2))-ord('a'))*26+ ord(mm.group(3))-ord('a')
        timestamp=float(mm.group(1))+float(dt)/1000+b26*600
        return timestamp

    mm=re.match("i-(\d+(?:\.\d+)?)-[vbsrtl]1(?:-o[+-]\d+)?$",filename)
    if mm:
        timestamp=float(mm.group(1))+float(dt)/1000
        return timestamp

    mm=re.match("(\d\d)-(\d\d)-(20\d\d)T(\d\d)-(\d\d)-(\d\d)-[sr]1",filename)
    if mm:
        month, day, year, hour, minute, second = map(int, mm.groups())
        timestamp=datetime.datetime(year,month,day,hour,minute,second)
        timestamp=(timestamp- datetime.datetime(1970,1,1)).total_seconds()
        timestamp+=float(dt)/1000
        return timestamp

    return 0
  
def parse_line_to_message(line):
    line = line.split()
    if not line[0] == 'RX' and ('A:OK' not in line or len(line) < 10):
        return None
    access = True
    lead_out = 'L:OK' in line
    name = line[1]
    if name == "X":
        timestamp = float(line[2])
    else:
        timestamp = extract_timestamp(name, line[2])
    freq = int(line[3])
    confidence = int(line[6][:-1])
    strength = float(line[7])
    length = int(line[8])
    if name == "X":
        error = line[9]=="True"
        msgtype = line[10]
    else:
        error = False
        msgtype = None

    return {'name': name, 'timestamp':timestamp, 'freq':freq, 'access':access, 'lead_out':lead_out, 'confidence':confidence, 'strength': strength, 'length': length, 'error': error, 'msgtype': msgtype}

def print_message(m):
    print "RAW:", m['name'], m['freq'], "%06d"%m['timestamp'], 'A:%s'%m[access], 'L:%s'%m[lead_out], '%03d%%'%m['confidence'], "%03d"%m['length']

def read_file(filenames):
    messages = []
    for line in fileinput.input(filenames):
        try:
            message = parse_line_to_message(line)
            if message:
                messages.append(message)
        except:
            pass
    return messages
