import RPi.GPIO as GPIO
import time


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

    def one_step_left(self):
        self.backward(5 / 1000.0, 10)

    def one_step_right(self):
        self.forward(5 / 1000.0, 10)

    def __del__(self):
        GPIO.cleanup()


motor = Motor()
# motor.one_step_left()
# time.sleep(1)
motor.one_step_right()
# motor.one_step_right()
# time.sleep(1)
# motor.one_step_left()
# motor.forward(5 / 1000.0, 10)
# time.sleep(1)
# motor.backwards(5 / 1000.0, 20)
# time.sleep(1)
# motor.forward(5 / 1000.0, 10)

