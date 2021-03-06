from picamera import PiCamera
from time import sleep
import copy

class TakeAPicture:

    def __init__(self, path, camera=None):
        self.path = path
        self.camera = camera
        if camera is None:
            self.camera = PiCamera()

    def shoot(self):
        old_res = copy.deepcopy(self.camera.resolution)
        self.camera.resolution = (2592, 1944)
        self.camera.start_preview()
        sleep(5)
        self.camera.capture(self.path)
        self.camera.stop_preview()
        self.camera.resolution = old_res
