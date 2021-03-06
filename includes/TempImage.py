import os
import time


class TempImage:
    def __init__(self, basePath="/mnt", ext=".jpg"):
        # construct the file path
        self.path = "{base_path}/{rand}{ext}".format(
            base_path=basePath,
            rand=str(time.time()), ext=ext
        )
        self.key = "{rand}{ext}".format(
            rand=str(time.time()), ext=ext
        )
        self.presigned_url = ""

    def cleanup(self):
        # remove the file
        os.remove(self.path)
