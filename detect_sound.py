import audioop
import pyaudio
import time


p = pyaudio.PyAudio()

while True:
  stream = p.open(format=pyaudio.paInt16,
                  channels=1,
                  rate=44100,
                  input=True,
                  input_device_index=2,
                  frames_per_buffer=4096)

  data = stream.read(4096)
  rms = audioop.rms(data, 2)
  stream.close()
  print("{:02d} {}".format(rms, '#' * rms))
  time.sleep(0.1)

