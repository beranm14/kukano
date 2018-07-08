# import the necessary packages
# from pyimagesearch.tempimage import TempImage
from picamera.array import PiRGBArray
from picamera import PiCamera
import argparse
# import warnings
import datetime
import imutils
import json
import time
import cv2
import logging
import os
import RPi.GPIO as GPIO
from threading import Thread
from bluetooth import discover_devices


logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.basicConfig(level=logging.DEBUG)


class TempImage:
    def __init__(self, basePath="/mnt", ext=".jpg"):
        # construct the file path
        self.path = "{base_path}/{rand}{ext}".format(
            base_path=basePath,
            rand=str(time.time()), ext=ext)

    def cleanup(self):
        # remove the file
        os.remove(self.path)


class Motor:
    def __init__(self):
        self.coil_A_1_pin = 6
        self.coil_A_2_pin = 13
        self.coil_B_1_pin = 19
        self.coil_B_2_pin = 26
        GPIO.setmode(GPIO.BCM)
        self.StepCount = 8
        self.Seq = range(0, self.StepCount)
        self.Seq[0] = [1, 0, 0, 1]
        self.Seq[1] = [1, 0, 0, 0]
        self.Seq[2] = [1, 1, 0, 0]
        self.Seq[3] = [0, 1, 0, 0]
        self.Seq[4] = [0, 1, 1, 0]
        self.Seq[5] = [0, 0, 1, 0]
        self.Seq[6] = [0, 0, 1, 1]
        self.Seq[7] = [0, 0, 0, 1]
        GPIO.setup(
            self.coil_A_1_pin,
            GPIO.OUT)
        GPIO.setup(
            self.coil_A_2_pin,
            GPIO.OUT)
        GPIO.setup(
            self.coil_B_1_pin,
            GPIO.OUT)
        GPIO.setup(
            self.coil_B_2_pin,
            GPIO.OUT)

    def setStep(self, w1, w2, w3, w4):
        GPIO.setmode(GPIO.BCM)
        GPIO.output(self.coil_A_1_pin, w1)
        GPIO.output(self.coil_A_2_pin, w2)
        GPIO.output(self.coil_B_1_pin, w3)
        GPIO.output(self.coil_B_2_pin, w4)

    def forward(self, delay, steps):
        for i in range(steps):
            for j in range(self.StepCount):
                self.setStep(
                    self.Seq[j][0],
                    self.Seq[j][1],
                    self.Seq[j][2],
                    self.Seq[j][3])
                time.sleep(delay)

    def backward(self, delay, steps):
        for i in range(steps):
            for j in reversed(range(self.StepCount)):
                self.setStep(
                    self.Seq[j][0],
                    self.Seq[j][1],
                    self.Seq[j][2],
                    self.Seq[j][3])
                time.sleep(delay)

    def blick(self):
        GPIO.setmode(GPIO.BCM)
        for i in range(0, 3):
            GPIO.output(self.coil_A_1_pin, 1)
            GPIO.output(self.coil_A_2_pin, 1)
            GPIO.output(self.coil_B_1_pin, 1)
            GPIO.output(self.coil_B_2_pin, 1)
            time.sleep(0.6)
            GPIO.output(self.coil_A_1_pin, 0)
            GPIO.output(self.coil_A_2_pin, 0)
            GPIO.output(self.coil_B_1_pin, 0)
            GPIO.output(self.coil_B_2_pin, 0)
            time.sleep(0.6)

    def one_step_left(self):
        self.backward(5 / 1000.0, 2)

    def one_step_right(self):
        self.forward(5 / 1000.0, 2)

    def __del__(self):
        GPIO.cleanup()


# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument(
    "-c", "--conf",
    help="path to the JSON configuration file",
    default="config.json")
args = vars(ap.parse_args())

# filter warnings, load the configuration and initialize the Dropbox
# client
# warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))

# initialize the camera and grab a reference to the raw camera capture
camera = PiCamera()
camera.resolution = tuple(conf["resolution"])
camera.framerate = conf["fps"]
rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))

time.sleep(conf["camera_warmup_time"])

frame_half = conf["downscale_width"] / 2
allow_macs = conf["allowed_devices"]

avg = None
lastUploaded = datetime.datetime.now()
motionCounter = 0
moved = False

stop_cause_somebody_home = False


def check_bt():
    global stop_cause_somebody_home, allow_macs
    while 1:
        nearby_devices = discover_devices()
        checker = False
        for addr in nearby_devices:
            if addr in allow_macs:
                checker = True
                logging.debug("BT MAC detected " + str(addr))
                break
        stop_cause_somebody_home = False if checker is False else True
        if stop_cause_somebody_home:
            logging.debug("BT MAC detected")
            motor = Motor()
            motor.blick()
            del motor
        time.sleep(60)


t = Thread(target=check_bt)
t.start()

logging.debug("Init ready")

rawCapture.truncate(0)

# capture frames from the camera
# for f in camera.capture_continuous(rawCapture, format="bgr"):
for f in camera.capture_continuous(
        rawCapture, format="bgr", use_video_port=True):
    logging.debug("YES")
    rawCapture.truncate(0)

    while stop_cause_somebody_home is True:
        time.sleep(10)

    timestamp = datetime.datetime.now()
    text = "Unoccupied"

    # # resize the frame, convert it to grayscale, and blur it
    frame = f.array
    frame = imutils.resize(frame, width=conf["downscale_width"])
    frame = imutils.rotate(frame, angle=180)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    # # if the average frame is None, initialize it
    if avg is None:
        print("[INFO] starting background model...")
        avg = gray.copy().astype("float")
        rawCapture.truncate()
        continue

    rawCapture.truncate(0)

    # accumulate the weighted average between the current frame and
    # previous frames, then compute the difference between the current
    # frame and running average
    cv2.accumulateWeighted(gray, avg, 0.5)
    frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

    # threshold the delta image, dilate the thresholded image to fill
    # in holes, then find contours on thresholded image
    thresh = cv2.threshold(
        frameDelta, conf["delta_thresh"], 255,
        cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    cnts = cv2.findContours(
        thresh.copy(), cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if imutils.is_cv2() else cnts[1]

    if moved is True:
        moved = False
        continue
    (x_s, y_s, w_s, h_s) = (0, 0, 0, 0)

    # loop over the contours
    for c in cnts:
        # if the contour is too small, ignore it
        if cv2.contourArea(c) < conf["min_area"]:
            continue

        # compute the bounding box for the contour, draw it on the frame,
        # and update the text
        (x, y, w, h) = cv2.boundingRect(c)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        text = "Occupied"
        if h * w > w_s * h_s:
            (x_s, y_s, w_s, h_s) = (x, y, w, h)

    if x_s * y_s > 0 and h_s * w_s > 100 and h_s * w_s < 40000:
        logging.debug("Coords: " + str((x_s, y_s, w_s, h_s)))
        rect_halt = (2 * x_s + w_s) / 2
        logging.debug("Coords: " + str((x, y, w, h)))
        logging.debug(
            "rect_halt: " +
            str(rect_halt) +
            " frame_half: " +
            str(frame_half))
        if rect_halt < frame_half:
            # turn left
            moved = True
            logging.debug("Turn left")
            motor = Motor()
            if abs(rect_halt - frame_half) > 60:
                motor.one_step_left()
                motor.one_step_left()
                motor.one_step_left()
            if abs(rect_halt - frame_half) > 30:
                motor.one_step_left()
                motor.one_step_left()
            else:
                motor.one_step_left()
            del motor
        elif rect_halt > frame_half:
            # turn right
            moved = True
            logging.debug("Turn right")
            motor = Motor()
            if abs(rect_halt - frame_half) > 60:
                motor.one_step_right()
                motor.one_step_right()
                motor.one_step_right()
            if abs(rect_halt - frame_half) > 30:
                motor.one_step_right()
                motor.one_step_right()
            else:
                motor.one_step_right()
            del motor

    # draw the text and timestamp on the frame
    ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
    cv2.putText(
        frame, "Room Status: {}".format(text), (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(
        frame, ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX,
        0.35, (0, 0, 255), 1)
    # check to see if the room is occupied
    if text == "Occupied":
        # check to see if enough time has passed between uploads
        # increment the motion counter
        motionCounter += 1
        # check to see if the number of frames with consistent motion is
        # high enough
        if motionCounter >= conf["min_motion_frames"]:
            # write the image to temporary file
            t = TempImage()
            cv2.imwrite(t.path, frame)

            logging.debug("Writting " + t.path)

            lastUploaded = timestamp
            motionCounter = 0
    # otherwise, the room is not occupied
    else:
        motionCounter = 0
