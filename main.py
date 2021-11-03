from picamera.array import PiRGBArray
from picamera import PiCamera
import argparse
import datetime
import imutils
import json
import time
import cv2
import random
import logging
from threading import Thread
from bluetooth import discover_devices
from includes.Motor import Motor
from includes.TakeAPicture import TakeAPicture
from includes.TempImage import TempImage
from includes.ping import ping
import audioop
import pyaudio
import requests
from includes.AudioFile import AudioFile
import boto3
from botocore.client import Config
import subprocess

from os import listdir
from os.path import isfile, join

from ctypes import *

ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

asound = cdll.LoadLibrary('libasound.so')
# Set error handler
asound.snd_lib_error_set_handler(c_error_handler)
# Initialize PyAudio
p = pyaudio.PyAudio()
p.terminate()

# Reset to default error handler
asound.snd_lib_error_set_handler(None)
# Re-initialize
p = pyaudio.PyAudio()
p.terminate()

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.basicConfig(level=logging.INFO)

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument(
    "-c", "--conf",
    help="path to the JSON configuration file",
    default="config.json")
args = vars(ap.parse_args())
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
stop_cause_there_is_silence = True
do_play_warnings = False

last_working_audio_device = None


def check_sound():
    global stop_cause_there_is_silence, stop_cause_somebody_home, conf, last_working_audio_device
    p = pyaudio.PyAudio()
    noise_detected = 0
    stream = None
    while 1:
        if last_working_audio_device is None:
            for i in [2, 1]:
                try:
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=44100,
                        input=True,
                        input_device_index=i,
                        frames_per_buffer=4096
                    )
                except OSError:
                    logging.debug(f"Fail to set input at {i}")
                    pass
                else:
                    last_working_audio_device = i
        else:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                input_device_index=last_working_audio_device,
                frames_per_buffer=4096
            )
        if stream is None:
            logging.info("Did not detect microphone, setting audio detect as true")
            stop_cause_there_is_silence = True
            time.sleep(10)
            continue
        data = stream.read(4096)
        rms = audioop.rms(data, 2)
        stream.close()
        if rms > conf['audio_threshold']:
            logging.debug("{:02d} {}".format(rms, '#' * rms))
            stop_cause_there_is_silence = False
            noise_detected = time.time()
        elif time.time() - noise_detected > 60 \
                and stop_cause_there_is_silence is False \
                and rms < conf['audio_threshold']:
            noise_detected = 0
            stop_cause_there_is_silence = True
        while stop_cause_somebody_home is True:
            time.sleep(10)
        time.sleep(0.1)


def check_bt():
    global stop_cause_somebody_home, allow_macs
    while 1:
        logging.debug("Checking BT devices")
        checker = False
        for addr in allow_macs:
            if ping(addr):
                logging.info("Detected " + str(addr))
                checker = True
        stop_cause_somebody_home = False if checker is False else True
        if stop_cause_somebody_home:
            logging.debug("BT MAC detected")
            try:
                motor = Motor()
                motor.blick()
            except RuntimeError:
                logging.debug("Blick failed!")
            del motor
        time.sleep(60)


def play_warnings():
    global do_play_warnings
    while 1:
        if do_play_warnings:
            onlyfiles = [
                f for f in listdir(
                    './warning_sounds/'
                ) if isfile(join('./warning_sounds/', f))
            ]
            file = onlyfiles[
                int(random.randrange(0, len(onlyfiles)))
            ]
            AudioFile('./warning_sounds/{0}'.format(file)).play().close()
            do_play_warnings = False
        time.sleep(10)


t_check_bt = Thread(target=check_bt)
t_check_bt.start()

t_check_sound = Thread(target=check_sound)
t_check_sound.start()

t_play_warnings = Thread(target=play_warnings)
t_play_warnings.start()

logging.debug("Init ready")

rawCapture.truncate(0)

# capture frames from the camera
for f in camera.capture_continuous(
        rawCapture, format="bgr", use_video_port=True):
    logging.debug("Checking...")
    rawCapture.truncate(0)

    while stop_cause_somebody_home is True:
        time.sleep(10)

    timestamp = datetime.datetime.now()
    text = "Unoccupied"

    # # resize the frame, convert it to grayscale, and blur it
    frame = f.array
    frame = imutils.resize(frame, width=conf["downscale_width"])
    # frame = imutils.rotate(frame, angle=180)

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
    cnts = cnts[1] if imutils.is_cv2() else cnts[0]

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
            (
                "rect_halt: {0} frame_half: {1}"
            ).format(str(rect_halt), str(frame_half))
        )
        if rect_halt > frame_half:
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
        elif rect_halt < frame_half:
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
    logging.debug(
        "text_status: {text} stop_cause_somebody_home: {stop_cause_somebody_home} stop_cause_there_is_silence: {stop_cause_there_is_silence}".format(
            text=text,
            stop_cause_somebody_home=str(stop_cause_somebody_home),
            stop_cause_there_is_silence=str(stop_cause_there_is_silence)
        )
    )
    if text == "Occupied" and stop_cause_there_is_silence is False:
        # check to see if enough time has passed between uploads
        # increment the motion counter
        motionCounter += 1
        # check to see if the number of frames with consistent motion is
        # high enough
        if motionCounter >= conf["min_motion_frames"]:
            # write the image to temporary file
            descriptive_pic_path = TempImage()
            full_pic_path = TempImage(ext="_full.jpg")
            cv2.imwrite(descriptive_pic_path.path, frame)
            TakeAPicture(full_pic_path.path, camera).shoot()

            logging.debug("Writting " + descriptive_pic_path.path)

            if 'aws_access_key_id' in conf and 'aws_secret_access_key' in conf and 'aws_region' in conf and 'aws_bucket' in conf:
                s3 = boto3.client(
                    's3', conf['aws_region'],
                    aws_access_key_id=conf['aws_access_key_id'],
                    # endpoint_url="https://s3.{region}.amazonaws.com".format(region=conf['aws_region']),
                    aws_secret_access_key=conf['aws_secret_access_key'],
                    # config=Config(s3={'addressing_style': 'virtual'})
                )
                for p in [descriptive_pic_path, full_pic_path]:
                    s3.upload_file(p.path, conf['aws_bucket'], p.key)
                    url = s3.generate_presigned_url(
                        ClientMethod='get_object',
                        Params={
                            'Bucket': conf['aws_bucket'],
                            'Key': p.key
                        },
                        ExpiresIn=604800
                    )
                    p.presigned_url = url
                if 'backend_url' in conf and 'backend_api_key' in conf:
                    r = requests.post(
                        conf['backend_url'] + "/incident/",
                        headers={
                            "x-api-Key": conf['backend_api_key'],
                            'Content-type': 'application/json'
                        },
                        json={
                            'timestamp': datetime.datetime.now().isoformat(),
                            'picture': descriptive_pic_path.presigned_url,
                            'full_picture': full_pic_path.presigned_url,
                        }
                    )
                logging.debug("Submitted to backend")
            if isfile("./run_after_notification_script.sh"):
                subprocess.call(
                    "./run_after_notification_script.sh", shell=True
                )
            lastUploaded = timestamp
            motionCounter = 0

            do_play_warnings = True
    # otherwise, the room is not occupied
    else:
        motionCounter = 0
