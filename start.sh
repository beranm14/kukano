#!/bin/bash

cd /home/pi/surveillance;
while [[ 1 ]]; do
	python main.py;
	sleep 60;
done
