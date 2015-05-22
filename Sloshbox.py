#!/usr/bin/env python

# USES:
# Adafruit ADXL345 Triple-Axis Accelerometer - ADXL345 : https://github.com/pimoroni/adxl345
# Fadecandy 8x8 board
# Open Pixel Control

from __future__ import division

# adxl345 library can't import smbus unless in a Linux environment
# this flag tells the code to fake accelerometer data.
# look for it and uncomment appropriate lines when deploying to RPI
RUNNINGONRPI = True

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
    print

try:
    import json
except ImportError:
    import simplejson as json

#-------------------------------------------------------------------------------
# Visualization Tweak Values!
default_fps = 60
timeScale = 0.6
drainAmount = 0.1
# amount to drain from each array square per tick.
wave_spawn_period = 0.1
g_tolerance = 4

color_white = (255,255,255)
color_01 = (60, 43, 212) # 3C2BD4, primary wedding color
color_02 = (39,28,138)
color_03 = (25,18,90)
color_04 = (12,9,43)
color_black = (0,0,0)

waveIndex = 0
accel_wobble = True
wobble_speed = 0.1

# Maximum magnitude = min speed, and vice versa
updateSpeed_min = 0.1
updateSpeed_max = 1

# threshold from flat at which roll/pitch changes are ignored (i.e. rest state)
roll_threshold = math.pi / 36
pitch_threshold = math.pi / 36

# last angle at which we generated a wave
lastRollWave = 0
lastPitchWave = 0

# increment by which angle must change from previous amount to generate a new wave (in radians)
waveAngleIncrement = 0.01

class Wave(object):
    """
    Define a wave
    # 8x base wave directions.
    # LTR, RTL, TTB, BTT UL_DR, UR_DL, DL_UR, DR_UL
    """

    def __init__(self, wave_type = "LTR", speed = 1.0):
        self.name = "Wave-" + str(waveIndex)
        self.wave_type = "<UNKNOWN>"
        self.SetWaveType(wave_type, True)
        self.speed = speed
        self.update_period = self.CalcUpdatePeriod(self.speed);
        self.delete_flag = False
        self.createdAt = time.time()
        self.last_update = self.createdAt #immediate

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

    def TimerUpdate(self):
        # if wave timer is reached, check accelerometer and spawn a new wave.
        if ((time.time() - self.last_update) >= self.update_period):
            self.last_update = time.time()
            self.update()

    def CalcUpdatePeriod(self, speed):
        """
        # returns an update period for this wave based on speed
        # speed is based on magnitude at time of spawn / max magnitude
        # speed = 1.0 is fastest. speed = 0.0 is slowest
        """
        speed = clamp(0,speed,1.0)
        self.update_period = (updateSpeed_max - (pytweening.linear(speed) * (updateSpeed_max-updateSpeed_min)))

# ------------
# Make 1-2 waves depending on current axes accelerometer sample!
def align(axes, rollWave, pitchWave):
    """
    :param axes: x,y,z of current sampled accelerometer axis
    :return:
    """
    x = axes['x']
    y = axes['y']
    z = axes['z']

    retWaves = []
    # http://stackoverflow.com/questions/3755059/3d-accelerometer-calculate-the-orientation
    # math.atan2(y, x) The result is between -pi and pi.
    # NOTE: formerly switch pitch and roll! Our sensor was wired... strangely.

    Pitch = math.atan2(y, z * 180/math.pi)
    Roll = math.atan2(-x, math.sqrt(y * y + z * z) * 180/math.pi)
    Magnitude = GetMagnitude(axes)
    MaxMagnitude = GetMagnitude({"x":g_tolerance, "y":g_tolerance, "z":g_tolerance})

    print "Roll: ", Roll
    print "Pitch: ", Pitch
    print "Magnitude: ", Magnitude
    print "MaxMagnitude", MaxMagnitude

    # now calculate which wave type this should be.
    if not (-roll_threshold <= Roll <= roll_threshold):
        if not ((rollWave - waveAngleIncrement) <= Roll <= (rollWave + waveAngleIncrement)):
            rollWave = Roll
            if (0 <= Roll <= math.pi):
                retWaves.append(Wave("TTB", Magnitude / MaxMagnitude))
            elif (-math.pi <= Roll <= 0):
                retWaves.append(Wave("BTT", Magnitude / MaxMagnitude))

    if not (-pitch_threshold <= Pitch <= pitch_threshold):
        if not ((pitchWave - waveAngleIncrement) <= Pitch <= (pitchWave + waveAngleIncrement)):
            pitchWave = Pitch
            if (0 <= Pitch <= math.pi):
                retWaves.append(Wave("RTL", Magnitude / MaxMagnitude))
            elif (-math.pi <= Pitch <= 0):
                retWaves.append(Wave("LTR", Magnitude / MaxMagnitude))

    return retWaves

#-------------------------------------------------------------------------------
# command line

default_layout = "layouts/fadecandy8x8x2.json"
if RUNNINGONRPI:
    default_server = "localhost:7890"
else:
    default_server = "localhost:7890"
    # default_server = "192.168.0.118:7890"

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
normalArray = [[0.0 for x in range(LED_xsize)] for y in range(LED_ysize)]


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

    # loop over every element
    for row in range(rows):
        for col in range(cols):
            tmp = normalArray[row][col] - amount
            if tmp < 0:
                tmp = 0
            normalArray[row][col] = tmp

#-------------------------------------------------------------------------------
# Make a pixel array from coordinate set

def make_pixelarray(coordinates, t):
    pixel_array = [pixel_color(t * timeScale, coord, ii) for ii, coord in enumerate(coordinates)]
    return pixel_array

    FadeCandyList = []
    nextFadeCandyID = 0

class FadeCandy(object):
    """
    Define a single Fadecandy board virtual object for mapping from pixelarray.
    """
    def __init__(self, x=0, y=0, id=0):
        self.ID = id

        self.x = x
        self.y = y
        self.xsize = 8
        self.ysize = 8
        self.array = [[0 for y in range(self.ysize)] for x in range(self.xsize)]

    def Map(self, targetArray):
        """
        copies pixels from the targetArray into self array
        :param targetArray:
        :return:
        """
        # print "Map: ({0}, {1}) -> {2}, {3}".format(len(targetArray), len(targetArray[0]), self.x, self.y)

        for ii in range(self.ysize):
            #row
            for jj in range(self.xsize):
                #col
                # print "Mapping: target({0},{1})={2} -> self({3},{4})".format(self.y+ii, self.x+jj, targetArray[self.y+ii][self.x+jj], ii, jj)
                if ((self.y + ii) < len(targetArray)):
                    if ((self.x + jj) < len(targetArray[0])):
                        self.array[ii][jj] = targetArray[(self.y + ii)][(self.x + jj)]
                    else:
                        # mapped coordinates are outside targetarray
                        self.array[ii][jj] = color_white
                else:
                    # mapped coordinates are outside targetarray
                    self.array[ii][jj] = color_white

    def serialize(self):
        retlist = []

        for i in range(len(self.array)):
            for j in range(len(self.array[i])):
                retlist.append(self.array[i][j])

        return retlist

FadeCandyList = []
nextFadeCandyID = 0
FadeCandyList.append(FadeCandy(0,0, nextFadeCandyID))

nextFadeCandyID += 1
FadeCandyList.append(FadeCandy(8,0, nextFadeCandyID))

#-------------------------------------------------------------------------------
# Make a pixel array from normals, corresponding to coordinate set
def convert2dListToPixels(passArray):
    # print "Converting: passArray[{0}][{1}]".format(LED_ysize, LED_xsize)
    # copy passed array for returning values.
    retArray = [[(0,0,0) for x in range(LED_xsize)] for y in range(LED_ysize)]
    # print "RetArray:", retArray
    # iterate over each element in passArray, convert its value to pixel color and store in retArray
    for row in range(len(passArray)):
        for column in range(len(passArray[row])):
            tmp = convertNormalToPixel(passArray[row][column])
            retArray[row][column] = tmp

    return retArray

#-------------------------------------------------------------------------------
# Make a pixel array from normals, corresponding to coordinate set

def make_pixelarray_from_normals(coordinates):
    # convert our list of normal values into an equivalent list of pixel colors
    pixel_array = convert2dListToPixels(normalArray)

    serialized_array = []

    # map our fadecandy boards to the pixel array
    for fc in FadeCandyList:
        fc.Map(pixel_array)
        for pixel in fc.serialize():
            serialized_array.append(pixel)

    # print "SA len(%i)=" % len(serialized_array), serialized_array
    return serialized_array

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
        normalArray[y][x] = 1.0

#-------------------------------------------------------------------------------
# Convert a normal value to a pixel color
def convertNormalToPixel(norm):
    rgb = [0,0,0]

    if norm == 1.0:
        rgb = color_white
    elif norm > 0.8:
        rgb = color_01
    elif norm > 0.6:
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
    norm = normalArray[y][x]
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
        x = clamp(-12, prev_accel['x']+random.uniform(-0.5,0.5), 12)
        y = clamp(-12, prev_accel['y']+random.uniform(-0.5,0.5), 12)
        z = clamp(-12, prev_accel['z']+random.uniform(-0.5,0.5), 12)
    else:
        x = clamp(-12, prev_accel['x'] + wobble_speed*2, 12)
        y = clamp(-12, prev_accel['y'] + wobble_speed, 12)
        z = clamp(-12, prev_accel['z'] + wobble_speed, 12)
    accel_xyz = {"x": x,"y": y, "z": z}
    return accel_xyz

def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))

#-------------------------------------------------------------------------------
# Sample accelerometer and return XYZ values
def sample_accel():
    accel_axes = {"x": 0, "y": 0, "z": 0}
    if RUNNINGONRPI:
        axes = accelerometer.getAxes(True)
        print "ADXL345 on address 0x%x:" % (accelerometer.address)
        print "   x = %.3fG" % ( axes['x'] )
        print "   y = %.3fG" % ( axes['y'] )
        print "   z = %.3fG" % ( axes['z'] )
        accel_axes = {"x": axes['x'],"y": axes['y'],"z": axes['z']}
        print
    else:
        accel_axes = sample_accel_FAKE(accel_axes )

    return accel_axes

def GetUnitVector(axes):
    magnitude = GetMagnitude(axes)
    unit_axes = {"x": axes['x'] / magnitude, "y": axes['y']/ magnitude, "z": axes['z'] / magnitude}
    return unit_axes

def GetMagnitude(axes):
    x = (axes['x'])
    y = (axes['y'])
    z = (axes['z'])
    magnitude  = math.sqrt(math.pow(x,2) + math.pow(y,2) + math.pow(z,2))
    return magnitude

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
accel_axes = sample_accel_FAKE({"x": 0, "y": 0, "z": 0})

while True:
    # update time since loop began
    t = time.time() - start_time

    # if wave timer is reached, check accelerometer and spawn a new wave.
    wave_spawn_timer = time.time() - LastWaveCreatedAt

    if wave_spawn_timer >= wave_spawn_period:
        if RUNNINGONRPI:
            accel_axes = sample_accel()
            print
        else:
            accel_axes = sample_accel_FAKE(accel_axes)

        new_Waves = []
        new_Waves = align(accel_axes,lastRollWave, lastPitchWave)

        for newWave in new_Waves:
            waveIndex += 1
            waveList.append(newWave)
            print 'New Wave(t={0:.4f}) Type: {1}'.format(newWave.createdAt, newWave.wave_type)

        LastWaveCreatedAt = time.time()
        wave_spawn_timer = 0.0

    for wave in waveList:
        wave.TimerUpdate()
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