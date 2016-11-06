#!/usr/bin/env python
import struct
import sys

def divide(extract_from, starting_at):
    return extract_from / starting_at, extract_from % starting_at

def partiton(data):
    type = ord(data[0])
    address_book_code = ord(data[1])
    type, address, num2, num3, num4, num5, byte1, byte2 = struct.unpack("<BBQQQHBB", data[:30])

    return type, address, num2, num3, num4, num5, byte1, byte2

#data = "0600f469cb9c821b73002120c79158b2ca8a607d49c83f42c78a342b8214".decode('hex')
#data = "0600904dd7f0841b730001e9d79158b2ca8a809184a43f42c78a342b8204".decode('hex')
#data = "0600bc16ef98891b730061f8bd9158b2ca8acdfb2c503c42c78a342b8214".decode('hex')

data = sys.argv[1].decode('hex')
type, address, num2, num3, num4, num5, byte1, byte2 = partiton(data)

print type, address, num2, num3, num4, num5, byte1, byte2

flag1, num2 = divide(num2, 10000000000000000000)
num6, num2 = divide(num2, 10000000000000000)
num7, num2 = divide(num2, 100000000000000)
num8, num2 = divide(num2, 10000000000)
num9, num2 = divide(num2, 100000000)
num10, num2 = divide(num2, 1000000)
num11, num2 = divide(num2, 100)
num12 = num2

flag2, num3 = divide(num3, 10000000000000000000)
num13, num3 = divide(num3, 100000000000000000)
num14, num3 = divide(num3, 10000000000000)
num15, num3 = divide(num3, 1000000000)
num16, num3 = divide(num3, 10000000)
num17, num3 = divide(num3, 100000)
num18, num3 = divide(num3, 10000)
num19, num3 = divide(num3, 100)
num20 = num3

flag3, num4 = divide(num4, 10000000000000000000)
num21, num4 = divide(num4, 100000000000000)
byte3, num4 = divide(num4, 10000000000000)
num22, num4 = divide(num4, 100000000)
byte4, num4 = divide(num4, 10000000)
num23, num4 = divide(num4, 100)
canned_message_code = num4

num24, num5_x = divide(num5, 1000)
num25, num5_x = divide(num5_x, 10)
num26 = num5_x

sats = byte1 / 10
num27 = byte1 % 10

print "Canned Message Code:", canned_message_code

print "Sats:", sats

print "Time: %d-%02d-%02d %02d:%02d:%02d.%d" %(num15, num24, num25, num13, num16, num17, num18 * 100)

lat = (num10 + num11 / 10000.) / 60. + num9
if flag1:
    lat *= -1
print "Latitude:", lat

lon = (num7 + num8 / 10000.) / 60. + num6
if num6 >= 200:
    lon -= 200
    lon *= -1
print "Longtitude:", lon

altitude = num22/float(10**(5-byte3))
if flag3 == 0:
    altitude *= -1
print "Altitude:", altitude

vervel = num27 * 100 + num26 * 10 + num19/10.
if flag2 == 0:
    vervel *= -1
print "Ver Vel:", vervel

ground_vel = num23 / float(10**(5-byte4))
print "Ground Vel:", ground_vel

course = num21 / 100.
print "Course:", course

hdop = (num12 + num20) / 100.
print "HDOP:", hdop

vdop = num14/ 100.
print "VDOP:", vdop

fix_2d = byte2 & 1 == 1
print "2D Fix:", fix_2d

routing_included = byte2 & 2 == 2
print "Routing Included", routing_included

position_fix = byte2 & 4 == 4
print "Position Fix:", position_fix

free_text_included = byte2 & 8 == 8
print "Free Text Included:", free_text_included

emergency = byte2 & 16 == 16
print "Emergency:", emergency

motion = byte2 & 32 == 32
print "Motion:", motion

emerg_ack = byte2 & 64 == 64
print "Emergency Ack:", emerg_ack

