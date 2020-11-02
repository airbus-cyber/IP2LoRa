#!/usr/bin/python3

import time
import argparse
import logging
import sys
import os
import signal
import importlib


from libLora import libDevice
from libLora import libIp2Lora
from libLora import libCipher
from libUtils import libUtils




IS_RUNNING = True

def sigint_handler(signum, frame):
    global IS_RUNNING

    print("Exiting...")
    IS_RUNNING = False



def main():
    global IS_RUNNING

    parser = argparse.ArgumentParser(description="Gateway Lora/IP")
    parser.add_argument('-d', '--debug', default=False, action="store_true", help="Enable debug tracing")
    parser.add_argument('configfile', type=str, help="config file (python module) - must be in the same directory")


    args = parser.parse_args()

    c = args.configfile
    if len(c) > 3:
        if c[-3:] == ".py":
            c = c[:-3]
    try:
        config_user = importlib.import_module(c)
    except Exception as e:
        print("Failed to load config file")
        print(e)
        exit(1)

    if args.debug:
        log_lvl = logging.DEBUG

    else:
        log_lvl = logging.INFO


    if (os.geteuid() != 0):
        print("Error: Must be started with root privileges")
        exit(1)


    log = logging.getLogger()
    log.setLevel(log_lvl)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_lvl)
    formatter = logging.Formatter("%(levelname)s:%(asctime)s:%(message)s")
    handler.setFormatter(formatter)
    log.addHandler(handler)


    if config_user.device == "B-L072Z-LRWAN1":
        deviceClass = libDevice.L072Z
    elif config_user.device == "RAK811":
        deviceClass = libDevice.RAK811
    elif config_user.device == "LoStick":
        deviceClass = libDevice.LoStick
    else:
        log.error("Device not supported")
        exit(1)

    d_configTx = {
        "channel": config_user.channelTx, # Hz
        "modem":1, # LORA
        "power": config_user.TxPower, # 0-14 dBm
        "fdev": 0,
        "bandwidth": config_user.bandwidth, # 0:125kHz, 1:250kHz, 2:500kHz, 3: Reserved
        "datarate": config_user.SF, # SF7..SF12
        "coderate": config_user.coderate, # 1:4/5, 2:4/6, 3:4/7, 4:4/8
        "preambleLen": config_user.preambleLen,
        "fixLen": 0, # Implicit Header mode: 1:Implicit header 0:Explicit header
        "crcOn": 0,
        "freqHopOn": 0,
        "hopPeriod": 0,
        "iqInverted": 0,
        "timeout": 3000
    }


    d_configRx = {
        "channel": config_user.channelRx, # Hz
        "modem": 1, # LORA
        "bandwidth": config_user.bandwidth, # 0:125kHz, 1:250kHz, 2:500kHz, 3: Reserved
        "datarate": config_user.SF, # SF7..SF12
        "coderate": config_user.coderate, # 1:4/5, 2:4/6, 3:4/7, 4:4/8
        "bandwidthAfc": 0,
        "preambleLen": config_user.preambleLen,
        "symbTimeout": 5,
        "fixLen": 0, # Implicit Header mode: 1:Implicit header 0:Explicit header
        "payloadLen": 0,
        "crcOn": 0,
        "freHopOn": 0,
        "hopPeriod": 0,
        "iqInverted": 0,
        "rxContinuous": 1 #true
    }

    baudrate = 115200
    if config_user.device == "LoStick":
        baudrate = 57600

    d_configSerial = {
        "port": config_user.tty,
        "baudrate": baudrate,
        "bytesize": 8,
        "parity": 'N',
        "stopbits": 1,
        "xonxoff": False,
        "rtscts": True,
        "debug": args.debug,
        "log": log,
        "name": config_user.device
    }
    if config_user.device == "B-L072Z-LRWAN1":
        d_configSerial.update({"timeout": 0.05})
    elif config_user.device == "RAK811":
        d_configSerial.update({"timeout": 0.05})
    elif config_user.device == "LoStick":
        d_configSerial.update({"timeout": 0.05})


    d_config = {
        "name": "ip2lora",
        "log": log,
        "debug": args.debug,
        "deviceClass": deviceClass,
        "ipAddress": config_user.ip_address,
        "maxLoraFrameSz": config_user.maxLoraFramesz,
        "mtu": config_user.mtu,
        "configSerial": d_configSerial,
        "configRx": d_configRx,
        "configTx": d_configTx,
    }

    if "rohc_compression" in dir(config_user):
        d_config.update({"rohc_compression": config_user.rohc_compression})
    else:
        d_config.update({"rohc_compression": False})


    if "compress_mode" in dir(config_user):
        if config_user.compress_mode == "zlib":
            d_config.update({"func_decompress": libUtils.zlib_decompress})
            d_config.update({"func_compress": libUtils.zlib_compress})


    cipher = None
    if "cipher_mode" in dir(config_user):
        if config_user.cipher_mode == "xor":
            cipher = libCipher.cipherXor(config_user.cipher_key)

    if cipher:
        d_config.update({"func_cipher": cipher.cipher})
        d_config.update({"func_uncipher": cipher.uncipher})


    ip2lora = libIp2Lora.Ip2Lora(config=d_config)
    ip2lora.start()

    signal.signal(signal.SIGINT, sigint_handler)
    while IS_RUNNING:
        time.sleep(1)

    ip2lora.stop()
    ip2lora.join()


if __name__ == '__main__':
    main()
