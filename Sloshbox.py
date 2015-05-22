#!/usr/bin/env python

# USES:
# Adafruit ADXL345 Triple-Axis Accelerometer - ADXL345 : https://github.com/pimoroni/adxl345
# Fadecandy 8x8 board
# Open Pixel Control

from __future__ import division

# adxl345 library can't import smbus unless in a Linux environment
# this flag tells the code to fake accelerometer data.
# look for it and uncomment appropriate lines when deploying to RPI
RUNNINGONRPI=True

import time
import sys
import optparse
import random
import opc, color_utils
import pytweening
import switch_case
import math

if RUNNINGONRPI:
    import adxl345

try:
    import json
except ImportError:
    import simplejson as json

#-------------------------------------------------------------------------------
# Visualization Tweak Values!
default_fps = 60
timeScale = 0.6
drainAmount = 0.1 # amount to drain from each array square per tick.
wave_spawn_period = 0.2
g_tolerance = 4

color_black = (0,0,0)
color_white = (255,255,255)
color_01 = (250,250,255)
color_02 = (128,128,255)
color_03 = (64,64,128)
color_04 = (32,32,64)

waveIndex = 0
accel_wobble = True
wobble_speed = 0.1

class Wave(object):
    """
    Define a wave
    # 8x base wave directions.
    # LTR, RTL, TTB, BTT UL_DR, UR_DL, DL_UR, DR_UL
    """

    def __init__(self, wave_type = "LTR", speed =1.0, lifetime=100, color=(255,255,255)):
        self.name = "Wave-" + str(waveIndex)
        self.wave_type = "<UNKNOWN>"
        self.SetWaveType(wave_type, True)
        self.speed = speed
        self.lifetime = lifetime
        self.update_timer = 0 # immediate
        self.color = color
        self.delete_flag = False
        self.createdAt = time.time()

    def update(self):
        """

        :return:
        """

        self.x1 += self.x_velocity
        self.x2 += self.x_velocity
        self.y1 += self.y_velocity
        self.y2 += self.y_velocity
        self.CheckWaveConstraints()

    def CheckWaveConstraints(self):
        if self.x1 > LED_xsize and self.x2 > LED_xsize:
            self.delete_flag = True
        if self.x1 < 0 and self.x2 < 0:
            self.delete_flag = True
        if self.y1 > LED_ysize and self.y2 > LED_ysize:
            self.delete_flag = True
        if self.y1 < 0 and self.y2 < 0:
            self.delete_flag = True

    def SetWaveType(self, toset = "LTR", resetcoords = False):
        for case in switch_case.switch(toset):
            if case("LTR"):
                # wave traveling Left to Right
                self.wave_type = toset
                if resetcoords:
                    self.x1 = -1
                    self.y1 = -1
                    self.x2 = -1
                    self.y2 = LED_ysize

                self.x_velocity = 1.0
                self.y_velocity = 0.0
                break

            if case("RTL"):
                # wave traveling Right to Left
                self.wave_type = toset
                if resetcoords:
                    self.x1 = LED_xsize
                    self.y1 = -1
                    self.x2 = LED_xsize
                    self.y2 = LED_ysize

                self.x_velocity = -1.0
                self.y_velocity = 0.0
                break

            if case("TTB"):
                # wave traveling Top to Bottom
                self.wave_type = toset
                if resetcoords:
                    self.x1 = -1
                    self.y1 = -1
                    self.x2 = LED_xsize
                    self.y2 = -1

                self.x_velocity = 0.0
                self.y_velocity = 1.0
                break

            if case("BTT"):
                # wave traveling Bottom to Top
                self.wave_type = toset
                if resetcoords:
                    self.x1 = -1
                    self.y1 = LED_ysize
                    self.x2 = LED_xsize
                    self.y2 = LED_ysize

                self.x_velocity = 0.0
                self.y_velocity = -1.0
                break

            if case():
                self.wave_type = "<unknown>"
                if resetcoords:
                    self.x1 = -1
                    self.y1 = -1
                    self.x2 = -1
                    self.y2 = LED_ysize

                self.x_velocity = 1.0
                self.y_velocity = 0.0
                break

# ------------
# Make 1-2 waves depending on current axes accelerometer sample!
def align(axes):
    """
    :param axes: x,y,z of current sampled accelerometer axis
    :return:
    """
    x,y,z = axes
    retWaves = []
    # http://stackoverflow.com/questions/3755059/3d-accelerometer-calculate-the-orientation

    # roll 0-180 = btt
    # roll 180 - 360 = ttb

    # pitch 0-180 = RTL
    # pitch 180-360 = LTR

    Roll = math.atan2(y, z * 180/math.pi)
    Pitch = math.atan2(-x, math.sqrt(y * y + z * z) * 180/math.pi)

    print "Roll: ", Roll
    print "Pitch: ", Pitch

    # now calculate which wave type this should be.
    radRoll = Roll
    radPitch = Pitch

    if (0 < radRoll < math.pi):
        retWaves.append(Wave("BTT", True))
    elif (-math.pi < radRoll < 0):
        retWaves.append(Wave("TTB", True))

    if (0 < radPitch < math.pi):
        retWaves.append(Wave("RTL", True))
    elif (-math.pi < radPitch < 0):
        retWaves.append(Wave("LTR", True))

    return retWaves

#-------------------------------------------------------------------------------
# command line

default_layout = "/layouts/fadecandy8x8x2.json"
default_server = "localhost:7890"
#default_server = "192.168.0.118:7890"
#default_server = "127.0.0.1:7890"

#-------------------------------------------------------------------------------
# command line

# currently used only to determine if gamma ramping is needed in pixel_color()
live = False

channel = 0 # default fadecandy channel 0

parser = optparse.OptionParser()
parser.add_option('-l', '--layout', dest='layout', default=default_layout,
                    action='store', type='string',
                    help='layout file')
parser.add_option('-s', '--server', dest='server', default=default_server,
                    action='store', type='string',
                    help='ip and port of server')
parser.add_option('-f', '--fps', dest='fps', default=default_fps,
                    action='store', type='int',
                    help='frames per second')

options, args = parser.parse_args()

if not options.layout:
    parser.print_help()
    print
    print 'ERROR: you must specify a layout file using --layout'
    print
    sys.exit(1)

#-------------------------------------------------------------------------------
# parse layout file

print
print '    parsing layout file'
print

# array representing virtual pixels
coordinates = []
for item in json.load(open(options.layout)):
    if 'point' in item:
        coordinates.append(tuple(item['point']))


# use layout "fadecandy8x8.json"
# Fadecandy 8x8 board
LED_xsize = 16
LED_ysize = 8
numLEDs = LED_xsize * LED_ysize

black = [ (0,0,0) ] * numLEDs
white = [ (255,255,255) ] * numLEDs

# The normalArray is a list of floats from 0.0 -> 1.0 that indicates relative pixel 'fullness'
# this array gets translated to the PixelArray for passing to the OPC client.
normalArray = [[0.0 for y in xrange(LED_ysize)] for x in xrange(LED_xsize)]


#-------------------------------------------------------------------------------
# connect to server

client = opc.Client(options.server)
if client.can_connect():
    print '    connected to %s' % options.server
else:
    # can't connect, but keep running in case the server appears later
    print '    WARNING: could not connect to %s' % options.server

#-------------------------------------------------------------------------------
# initialize accelerometer
if RUNNINGONRPI:
    # uncomment this when running on the RPI - can't use smbus
    accelerometer = adxl345.ADXL345()
    print

#-------------------------------------------------------------------------------
# color function

def pixel_color(t, coord, ii):
    """Compute the color of a given pixel.

    t: time in seconds since the program started.
    ii: which pixel this is, starting at 0
    coord: the (x, y, z) position of the pixel as a tuple

    Returns an (r, g, b) tuple in the range 0-255

    """
    x, y, z = coord

    # make x, y, z -> r, g, b sine waves
    r = color_utils.cos(x, offset=t / 4, period=2, minn=0, maxx=1)
    g = color_utils.cos(y, offset=t / 4, period=2, minn=0, maxx=1)
    b = color_utils.cos(z, offset=t / 4, period=2, minn=0, maxx=1)

    # apply gamma curve
    # only do this on live leds, not in the simulator
    if live:
        r, g, b = color_utils.gamma((r, g, b), 2.2)

    return (r*256, g*256, b*256)

#-------------------------------------------------------------------------------
# Drain the normals of each element in handleArray by amount, clamp to 0

def drainNormals(amount):
    # Now find its dimensions
    rows = len(normalArray)
    cols = len(normalArray[0])

    # And now loop over every element
    # Here, we'll add one to each element,
    # just to make a change we can easily see
    for row in xrange(rows):
        for col in xrange(cols):
            # This code will be run rows*cols times, once for each
            # element in the 2d list
            tmp = normalArray[row][col] - amount
            if tmp < 0:
                tmp = 0
            normalArray[row][col] = tmp

    return

#-------------------------------------------------------------------------------
# Make a pixel array from coordinate set

def make_pixelarray(coordinates, t):
    pixel_array = [pixel_color(t * timeScale, coord, ii) for ii, coord in enumerate(coordinates)]
    return pixel_array

#-------------------------------------------------------------------------------
# Make a pixel array from normals, corresponding to coordinate set
def convert2dListToPixels(passArray):
    retarray = []
    for row in passArray:
        for column in row:
            tmp = convertNormalToPixel(column)
            retarray.append(tmp)

    return retarray

#-------------------------------------------------------------------------------
# Make a pixel array from normals, corresponding to coordinate set

def make_pixelarray_from_normals(coordinates):
    # pixel_array = [convertNormalToPixel(getNormalFor(coord)) for ii, coord in enumerate(coordinates)]
    pixel_array = convert2dListToPixels(normalArray)
    return pixel_array

#-------------------------------------------------------------------------------
# For each point in a line, set corresponding point in normalArray to 1.0
def applyNormalPoints(line):
    for point in line:
        x = point[0]
        y = point[1]
        x = clamp(0,x,LED_xsize-1)
        y = clamp(0,y,LED_ysize-1)
        x = int(x)
        y = int(y)
        normalArray[x][y] = 1.0

#-------------------------------------------------------------------------------
# Convert a normal value to a pixel color
def convertNormalToPixel(norm):
    rgb = [0,0,0]

    if norm == 1.0:
        rgb = color_white
    elif norm > 0.9:
        rgb = color_01
    elif norm > 0.8:
        rgb = color_02
    elif norm > 0.4:
        rgb = color_03
    elif norm > 0.2:
        rgb = color_04
    else:
        rgb = color_black

    return rgb

def getNormalFor(coord):
    x,y,z = coord
    norm = normalArray[x][y]
    return norm

#-------------------------------------------------------------------------------
# Make an array of random pixels

def make_pixels_random(n_pixels):
    pixels = []
    for ii in range(n_pixels):
        pixels.append(randomColor())
    return pixels

def randomColor():
    rgb = [random.random()*255, random.random()*255, random.random()*255]
    rgb = tuple(rgb)
    return rgb

#-------------------------------------------------------------------------------
# Merely PRETEND to sample accelerometer and return XYZ values
def sample_accel_FAKE(prev_accel):
    if accel_wobble == True:
        x = clamp(-12, prev_accel[0]+random.uniform(-0.5,0.5), 12)
        y = clamp(-12, prev_accel[1]+random.uniform(-0.5,0.5), 12)
        z = clamp(-12, prev_accel[2]+random.uniform(-0.5,0.5), 12)
    else:
        x = clamp(-12, prev_accel[0] + wobble_speed*2, 12)
        y = clamp(-12, prev_accel[0] + wobble_speed, 12)
        z = clamp(-12, prev_accel[0] + wobble_speed, 12)
    accel_xyz = [ x, y, z]
    accel_xyz = tuple(accel_xyz)
    return accel_xyz

def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))

#-------------------------------------------------------------------------------
# Sample accelerometer and return XYZ values
def sample_accel():
    accel_axes = [0,0,0]
    if RUNNINGONRPI:
        axes = accelerometer.getAxes(True)
        print "ADXL345 on address 0x%x:" % (accelerometer.address)
        print "   x = %.3fG" % ( axes['x'] )
        print "   y = %.3fG" % ( axes['y'] )
        print "   z = %.3fG" % ( axes['z'] )
        accel_axes = tuple(axes['x'], axes['y'], axes['z'])
        print
    else:
        accel_axes = sample_accel_FAKE(accel_axes )

    return accel_axes


#-------------------------------------------------------------------------------
# core pixel loop

print '    sending pixels forever (control-c to exit)...'
print

#-------------------------------------------------------------------------------
# calculate relevant display data

n_pixels = len(coordinates)
start_time = time.time()

# number of seconds in which each wave spawns.
wave_spawn_timer = 0.0
LastWaveCreatedAt = start_time
waveList =[Wave()]
accel_axes = sample_accel_FAKE([0, 0, 0])

while True:
    # update time since loop began
    t = time.time() - start_time

    # if wave timer is reached, check accelerometer and spawn a new wave.
    wave_spawn_timer = time.time() - LastWaveCreatedAt

    if wave_spawn_timer >= wave_spawn_period:
        if RUNNINGONRPI:
            accel_axes = sample_accel()
        else:
            accel_axes = sample_accel_FAKE(accel_axes)

        new_Waves = []
        new_Waves = align(accel_axes)

        for newWave in new_Waves:
            waveIndex += 1
            waveList.append(newWave)
            print 'New Wave(t={0:.4f}) Type: {1}'.format(newWave.createdAt, newWave.wave_type)

        LastWaveCreatedAt = time.time()
        wave_spawn_timer = 0.0

    for wave in waveList:
        wave.update()
        if wave.delete_flag:
            print "Removing Wave: %s" % wave.name
            waveList.remove(wave)

        # create the correct line.
        line = pytweening.getLine(wave.x1, wave.y1, wave.x2, wave.y2)
        applyNormalPoints(line)

    # drain normal values
    drainNormals(drainAmount)

    # calculate pixel color values based on normalArray
    pixels = make_pixelarray_from_normals(coordinates)
    #pixels = make_pixels_random(numLEDs)

    ## Create pixel array and push to client.
    # pixels = make_pixelarray(coordinates, t)
    client.put_pixels(pixels, channel)

    time.sleep(1 / options.fps)