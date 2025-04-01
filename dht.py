import serial.tools.list_ports
ports = serial.tools.list_ports.comports()
for port, desc, hwid in sorted(ports):
	print("{}:{} [{}]".format(port, desc, hwid))
import serial
port=serial.Serial("COM5", baudrate=115200)