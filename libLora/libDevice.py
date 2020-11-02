
import serial
import threading
import time
import struct
import random
import math
import re
import ctypes


"""
Calculate duration of LoRa frame transmission
Args:
    PL: payload size in bytes
    SF: SF7...SF12
    EH: 1:Implicit header mode (no hdr) - 0:Explicit header mode
    LDR: Low data rate (0:off 1:on)
    CR: Coding rate (5:4/5 - 6:4/6 - 7:4/7 - 8:4/8)
    BW: Bandwidth in kHz: 125 - 250 - 500
    NP: Number of symbols in preamble 
    
"""
def calc_duration_lora_frame(PL=0, SF=7, EH=0, LDR=0, CR=5, BW=125, NP=8):
    Ts = (2**SF) / float(BW * 1000)

    Tpre = (NP+4.25)*Ts

    Ns = 8 + 1 + math.ceil(((8 * float(PL) - 4 * float(SF) + 28 + 16 - 20 * EH) / (4 * (float(SF) - 2 * LDR))) * float(CR))
    Tpay = Ts * Ns

    Tpacket = Tpre + Tpay

    return Tpacket




"""
Generic serial Device class
"""
class CommSerialDev(threading.Thread):
    def __init__(self, config={}):
        threading.Thread.__init__(self)
        self._name = config["name"]
        self.log = config["log"]
        self._isRunning = False

        try:
            self._serial = serial.Serial(port=config["port"],
                                        baudrate=config["baudrate"],
                                        bytesize=config["bytesize"],
                                        parity=config["parity"],
                                        stopbits=config["stopbits"],
                                        xonxoff=config["xonxoff"],
                                        rtscts=config["rtscts"],
                                        timeout=config["timeout"])
        except Exception as e:
            self.log.error("%s:CommSerialDev_init:Failed to open serial: %s" % (self._name, str(e)))
            exit(1)
        self._lock_serial = threading.Lock()





    def run(self):
        self.log.debug(self._name+":Start")

        self._open()

        if not self._init_stuff():
            raise ValueError("Unable to init LoRa device")

        self._isRunning = True

        while self._isRunning:
            time.sleep(1)

        self._destroy_stuff()
        self._serial.close()
        self.log.debug(self._name + ":End")





    def _open(self):
        self._lock_serial.acquire()
        while not self._serial.is_open:
            self.log.debug(self._name+":Opening...")
            self._serial.open()
        self._lock_serial.release()


    def _init_stuff(self):
        # implemented by child class
        return True

    def _destroy_stuff(self):
        # implemented by child class
        return

    def stop(self):
        self._isRunning = False


    def isRunning(self):
        return self._isRunning


    def send_radio_frame(self, data):
        return self.send_serial(data)


    def recv_radio_frame(self):
        return self.recv_serial()


    def send_serial(self, data):
        self.log.debug(self._name+":Sending: %s", data)
        self._lock_serial.acquire()
        try:
            self._serial.write(data)
        except Exception as e:
            self.log.error("%s:send_serial:Error on serial write: %s" % (self._name, str(e)))
        self._lock_serial.release()



    def recv_serial(self, nb=0x400):
        self._lock_serial.acquire()
        try:
            data = self._serial.read(nb)
        except Exception as e:
            self.log.error("%s:recv_serial:Error on serial read: %s" % (self._name, str(e)))
            data = b""
        self._lock_serial.release()
        if len(data) > 0:
            self.log.debug(self._name+":Recv   : %s", data)
        return data



"""
Serial class for B-L072Z-LRWAN1 board
"""
L072Z_CMD_SEND = b"\x01"
L072Z_CMD_CONFIG = b"\x02"
class L072Z(CommSerialDev):
    def __init__(self, config={}):
        CommSerialDev.__init__(self, config=config["configSerial"])
        self.config_tx = config["configTx"]
        self.config_rx = config["configRx"]
        self.radio_tx_lock = threading.Lock()

        self.recv_radio_frame_lock = threading.Lock() # used to lock normal received when send/recv config

        self.max_time_transmission = calc_duration_lora_frame(PL=config["maxLoraFrameSz"],
                                      SF=self.config_tx["datarate"],
                                      EH=self.config_tx["fixLen"],
                                      LDR=0,
                                      CR=4 + self.config_tx["coderate"],
                                      BW=[125, 250, 500][self.config_tx["bandwidth"]],
                                      NP=self.config_tx["preambleLen"])

        # send periodic small Lora data
        # for unknown reason, on inactivity board not listen until it send a frame...
        # TODO: correct this bug and remove this line
        self._t_sendPeriodicData = sendPeriodicData(t_serial_dev=self, data=b"A", period=30)

    """
    Apply RX and TX configuration on init
    """
    def _init_stuff(self):
        if self.config_tx:
            res = self.set_tx_config()
            if not res:
                return res
        time.sleep(0.5)
        if self.config_rx:
            res = self.set_rx_config()
            if not res:
                return res

        time.sleep(0.5)

        # send periodic small Lora data
        # for unknown reason, on inactivity board not listen until it send a frame...
        # TODO: correct this bug and remove this line
        self._t_sendPeriodicData.start()
        return True

    def _destroy_stuff(self):
        self._t_sendPeriodicData.stop()
        self._t_sendPeriodicData.join()
        return

    """
    Send LoRa frames
    wait until transmission ended
    wait a time slot to give a chance to others LoRa node to reply (avoid collision)
    """
    def send_radio_frame(self, data):
        #self.log.debug(self._name + ":send_radio_frame: begin")
        self.radio_tx_lock.acquire()

        data = L072Z_CMD_SEND + struct.pack("<H", len(data)) + data
        CommSerialDev.send_radio_frame(self, data=data)
        # wait until frame is transmitted
        ts = calc_duration_lora_frame(PL=len(data),
                                      SF=self.config_tx["datarate"],
                                      EH=self.config_tx["fixLen"],
                                      LDR=0,
                                      CR=4+self.config_tx["coderate"],
                                      BW=[125, 250, 500][self.config_tx["bandwidth"]],
                                      NP=self.config_tx["preambleLen"])
        time.sleep(ts)
        # (half-duplex) give a chance to others node to send response
        ts = self.max_time_transmission + ts * random.random()
        #self.log.debug(self._name + ":send_radio_frame:ts: %f", ts)
        time.sleep(ts)

        self.radio_tx_lock.release()
        #self.log.debug(self._name + ":send_radio_frame: end")
        return


    """
    Get LoRa received frame
    """
    def recv_radio_frame(self):
        self.recv_radio_frame_lock.acquire()
        r = CommSerialDev.recv_serial(self)
        self.recv_radio_frame_lock.release()
        return r


    """
    Set Tx Configuration
    (Channel frequency for TX and RX can be different)
    """
    def set_tx_config(self):
        if self.config_tx is None:
            return True

        config = b"TC"
        config += struct.pack("<I", self.config_tx["channel"])
        config += struct.pack("B", self.config_tx["modem"])
        config += struct.pack("B", self.config_tx["power"])
        config += struct.pack("B", self.config_tx["fdev"])
        config += struct.pack("B", self.config_tx["bandwidth"])
        config += struct.pack("B", self.config_tx["datarate"])
        config += struct.pack("B", self.config_tx["coderate"])
        config += struct.pack("B", self.config_tx["preambleLen"])
        config += struct.pack("B", self.config_tx["fixLen"])
        config += struct.pack("B", self.config_tx["crcOn"])
        config += struct.pack("B", self.config_tx["freqHopOn"])
        config += struct.pack("B", self.config_tx["hopPeriod"])
        config += struct.pack("B", self.config_tx["iqInverted"])
        config += struct.pack("<H", self.config_tx["timeout"])

        data = L072Z_CMD_CONFIG + struct.pack("<H", len(config)) + config
        #CommSerialDev.send_radio_frame(self, data=data)
        return self._send_config(data)


    """
    Change TX channel frequency 
    """
    def set_tx_channel(self, channel):

        config = b"Tc"
        config += struct.pack("<I", channel)

        data = L072Z_CMD_CONFIG + struct.pack("<H", len(config)) + config
        # CommSerialDev.send_radio_frame(self, data=data)
        self._send_config(data)


    """
    Set Rx Configuration
    (Channel frequency for TX and RX can be different)
    """
    def set_rx_config(self):
        if self.config_rx is None:
            return True

        config = b"RC"
        config += struct.pack("<I", self.config_rx["channel"])
        config += struct.pack("B", self.config_rx["modem"])
        config += struct.pack("B", self.config_rx["bandwidth"])
        config += struct.pack("B", self.config_rx["datarate"])
        config += struct.pack("B", self.config_rx["coderate"])
        config += struct.pack("B", self.config_rx["bandwidthAfc"])
        config += struct.pack("B", self.config_rx["preambleLen"])
        config += struct.pack("B", self.config_rx["symbTimeout"])
        config += struct.pack("B", self.config_rx["fixLen"])
        config += struct.pack("B", self.config_rx["payloadLen"])
        config += struct.pack("B", self.config_rx["crcOn"])
        config += struct.pack("B", self.config_rx["freHopOn"])
        config += struct.pack("B", self.config_rx["hopPeriod"])
        config += struct.pack("B", self.config_rx["iqInverted"])
        config += struct.pack("B", self.config_rx["rxContinuous"])

        data = L072Z_CMD_CONFIG + struct.pack("<H", len(config)) + config
        #CommSerialDev.send_radio_frame(self, data=data)
        return self._send_config(data)


    """
    Send config to board
    """
    def _send_config(self, raw_config, nbTry=10):
        bConfigOk = False
        self.recv_radio_frame_lock.acquire()
        n = 0
        while not bConfigOk:
            d = self.recv_serial()
            CommSerialDev.send_serial(self, data=raw_config)
            time.sleep(1)
            d = self.recv_serial()
            if d == b"CONFIG_OK":
                bConfigOk = True
                break
            n += 1
            if n >= nbTry:
                break

        self.recv_radio_frame_lock.release()
        return bConfigOk


"""
send one small Lora data
for unknown reason B-L072Z-LRWAN1 board not work until it send a frame...
TODO: correct this bug and remove this class
"""
class sendPeriodicData(threading.Thread):
    def __init__(self, t_serial_dev=None, data=b"IP2LoRa", period=30):
        threading.Thread.__init__(self)
        self._name = "sendPeriodicData"
        self._period = period
        self.t_serial_dev = t_serial_dev
        self.data = data
        self._isRunning = False


    def run(self):

        self._isRunning = True
        i = 0
        while self._isRunning:
            time.sleep(1)
            i += 1
            if i >= self._period:
                self.t_serial_dev.send_radio_frame(self.data)
                i = 0


    def stop(self):
        self._isRunning = False






"""
Serial class for Wisnode board
"""
class RAK811(CommSerialDev):
    def __init__(self, config={}):
        CommSerialDev.__init__(self, config=config["configSerial"])
        self.config_tx = config["configTx"]
        self.config_rx = config["configRx"]
        self.radio_tx_lock = threading.Lock()

        self._recv_radio_frame_lock = threading.Lock()  # used to lock normal received when send/recv config

        self.max_time_transmission = calc_duration_lora_frame(PL=config["maxLoraFrameSz"],
                                                              SF=self.config_tx["datarate"],
                                                              EH=self.config_tx["fixLen"],
                                                              LDR=0,
                                                              CR=4 + self.config_tx["coderate"],
                                                              BW=[125, 250, 500][self.config_tx["bandwidth"]],
                                                              NP=self.config_tx["preambleLen"])
        self._mode_tx_lock = threading.Lock()
        self._mode_tx = False




    """
    On init:
    - Init board (check version, set p2p mode, ...)
    - Set LoRa configuration
    """
    def _init_stuff(self):
        if not self.init_lorap2p():
            return False

        if not self.set_rx_config():
            return False

        self.set_rx_mode()
        return True




    """
    Send AT command to board
    """
    def _send_at_cmd(self, cmd, maxTry=10):
        self._recv_radio_frame_lock.acquire()
        CommSerialDev.send_serial(self, data=b"at+"+bytes(cmd, encoding="utf8")+b"\r\n")
        t = 0
        data = ""
        while t < maxTry:
            bData = CommSerialDev.recv_serial(self)
            if len(bData) > 0:
                data += bData.decode("utf8")
                if re.match(".*OK .*", data, re.MULTILINE|re.DOTALL):
                    self._recv_radio_frame_lock.release()
                    return True, data

            t += 1
        self._recv_radio_frame_lock.release()
        return False, data



    """
    Initialize Board
    - Check version
    - set mode p2p
    - put on no sleep mode
    - set region
    """
    def init_lorap2p(self):

        r, version = self._send_at_cmd("version")
        if r is False:
            self.log.error("%s:Unable to get version (Maybe we are in BOOT mode (at+run))" % self._name)
            if re.match(".* Bootloader .*", version) is None:
                return False
            r, run = self._send_at_cmd("run")
            if r is False:
                return False
            r, version = self._send_at_cmd("version")
            if r is False:
                return False
        if re.match('^.* V3\.0\.0\..*$', version) is None:
            self.log.error("%s:Unsupported version: %s" % (self._name, version))
            return False

        # set mode LoraP2P
        r, work_mode = self._send_at_cmd("set_config=lora:work_mode:1")
        if not r:
            return False

        # set sleep mode wakeup
        r, sleep_mode = self._send_at_cmd("set_config=device:sleep:0")
        if not r:
            return False

        # set region
        if self.config_rx["channel"] >= 433000000 and self.config_rx["channel"] < 868000000:
            r, region = self._send_at_cmd("set_config=lora:region:EU433")
            if not r:
                return False
        else:
            r, region = self._send_at_cmd("set_config=lora:region:EU868")
            if not r:
                return False

        return True





    """
    Send data on LoRa
    """
    def send_radio_frame(self, data):
        # self.log.debug(self._name + ":send_radio_frame: begin")
        self.radio_tx_lock.acquire()

        #if self.config_tx["channel"] != self.config_rx["channel"]:
        #    self.set_tx_config()

        self.set_tx_mode()

        # convert data to hex
        h_data = data.hex()
        cmd = "send=lorap2p:"+data.hex()
        r, resp = self._send_at_cmd(cmd, maxTry=80)
        if not r:
            self.log.warn("%s:send_radio_frame: send frame failed: %s" % (self._name, data.hex()))
            self.set_rx_mode()
            self.radio_tx_lock.release()
            return

        # if self.config_tx["channel"] != self.config_rx["channel"]:
        #    self.set_rx_config()
        self.set_rx_mode()

        """
        # wait until frame is transmitted
        ts = calc_duration_lora_frame(PL=len(data),
                                      SF=self.config_tx["datarate"],
                                      EH=self.config_tx["fixLen"],
                                      LDR=0,
                                      CR=4 + self.config_tx["coderate"],
                                      BW=[125, 250, 500][self.config_tx["bandwidth"]],
                                      NP=self.config_tx["preambleLen"])
        time.sleep(ts)
        """
        # (half-duplex) give a chance to others node to send responses
        ts = self.max_time_transmission
        #self.log.debug(self._name + ":send_radio_frame:ts: %f", ts)
        time.sleep(ts)

        self.radio_tx_lock.release()
        # self.log.debug(self._name + ":send_radio_frame: end")
        return



    """
    Get LoRa received frame
    """
    def recv_radio_frame(self):

        self._recv_radio_frame_lock.acquire()
        data = CommSerialDev.recv_serial(self)
        data = data.decode("utf8")
        re_at = "^at\+recv=.*,.*,(.*):([0-9A-F]+)"
        if re.match(re_at, data) is None:
            # print not a recv frame
            data = b""
            self._recv_radio_frame_lock.release()
            return data


        tmp = re.search(re_at, data)
        sz_data = int(tmp.group(1)) * 2
        data = tmp.group(2)


        maxTry = 5
        t = 0
        while len(data) < sz_data:
            data += CommSerialDev.recv_serial(self, sz_data - len(data)).decode("utf8")
            t += 1
            if t > maxTry:
                self.log.warn("%s:recv_radio_frame: Failed to get complete frame: %s" % (self._name, data))
                data = b""
                self._recv_radio_frame_lock.release()
                return data


        try:
            data = bytes.fromhex(data)
        except Exception as e:
            self.log.warn("%s:recv_radio_frame:Data recv is not a HEX string: %s" % (self._name, data))
            data = b""

        self._recv_radio_frame_lock.release()
        return data



    """
    Set LoRa configuration 
    """
    def set_rx_config(self):

        config = "set_config=lorap2p:"+str(self.config_rx["channel"])+":"+str(self.config_rx["datarate"])+":"+ \
                 str(self.config_rx["bandwidth"])+":"+str(self.config_rx["coderate"])+":"+str(self.config_rx["preambleLen"])+":"+\
                 str(self.config_tx["power"])
        r, resp = self._send_at_cmd(config, maxTry=40)
        if r:
            return True

        self.log.error("%s: set_rx_config Failed" % self._name)
        return False



    """
    Put board on receive LoRa data mode
    """
    def set_rx_mode(self):
        config = "set_config=lorap2p:transfer_mode:1"
        r, resp = self._send_at_cmd(config, maxTry=80)
        if r:
            self._mode_tx_lock.acquire()
            self._mode_tx = False
            self._mode_tx_lock.release()
            return True

        self.log.error("%s: set_rx_mode Failed" % self._name)
        return False



    """
    Put board on transmit LoRa data mode
    """
    def set_tx_mode(self):
        config = "set_config=lorap2p:transfer_mode:2"
        r, resp = self._send_at_cmd(config)
        if r:
            self._mode_tx_lock.acquire()
            self._mode_tx = True
            self._mode_tx_lock.release()
            return True

        self.log.error("%s: set_tx_mode Failed" % self._name)
        return False




"""
Serial class for LoStick
"""
class LoStick(CommSerialDev):
    def __init__(self, config={}):
        CommSerialDev.__init__(self, config=config["configSerial"])
        self.config_tx = config["configTx"]
        self.config_rx = config["configRx"]
        self.radio_tx_lock = threading.Lock()

        self._recv_radio_frame_lock = threading.Lock()  # used to lock normal received when send/recv config

        self.max_time_transmission = calc_duration_lora_frame(PL=config["maxLoraFrameSz"],
                                                              SF=self.config_tx["datarate"],
                                                              EH=self.config_tx["fixLen"],
                                                              LDR=0,
                                                              CR=4 + self.config_tx["coderate"],
                                                              BW=[125, 250, 500][self.config_tx["bandwidth"]],
                                                              NP=self.config_tx["preambleLen"])
        self._mode_tx_lock = threading.Lock()
        self._mode_tx = False


        # TODO add function serial_recv
        # call CommSerialDev.recv_serial
        #
        self._l_recv_serial_queue = []
        self._l_recv_serial_queue_lock = threading.Lock()


    """
    get data from serial
    split on \r\n and store response on queue
    return older response
    """
    def _recv_serial(self):
        data = b""

        self._l_recv_serial_queue_lock.acquire()

        if len(self._l_recv_serial_queue) > 0:
            data = self._l_recv_serial_queue[0]
            self._l_recv_serial_queue = self._l_recv_serial_queue[1:]
            self._l_recv_serial_queue_lock.release()
            #self.log.debug("%s:_recv_serial: %s" % (self._name, data))
            return data


        d = CommSerialDev.recv_serial(self)

        if len(d) > 0:
            # got recv data from serial
            maxTry = 10
            n = 0
            while (len(d) < 2) and (n < maxTry):
                n += 1
                d += CommSerialDev.recv_serial(self)

            # Ensure got one or many complete responses and store them in queue
            while (d[-2:] != b"\r\n") and (n < maxTry):
                n += 1
                d += CommSerialDev.recv_serial(self)

            l = d.split(b"\r\n")
            try:
                l.remove(b"")
            except:
                pass

            try:
                # ignore radio_tx_ok msg
                l.remove(b"radio_tx_ok")
            except:
                pass

            self._l_recv_serial_queue += l

        if len(self._l_recv_serial_queue) > 0:
            data = self._l_recv_serial_queue[0]
            self._l_recv_serial_queue = self._l_recv_serial_queue[1:]
            #self.log.debug("%s:_recv_serial: %s" % (self._name, data))
        self._l_recv_serial_queue_lock.release()

        return data


    def _send_serial(self, data):
        return CommSerialDev.send_serial(self, data=data)


    """
    On init:
    - Init board (check version, set p2p mode, ...)
    - Set LoRa configuration
    """
    def _init_stuff(self):
        if not self.init_lorap2p():
            return False

        self.set_rx_mode()
        return True




    """
    Send command to board
    """
    def _send_cmd(self, cmd, maxTry=10, bExpectOk=False):
        self._recv_radio_frame_lock.acquire()
        self._send_serial(data=bytes(cmd, encoding="utf8")+b"\r\n")
        t = 0
        data = ""
        while t < maxTry:
            bData = self._recv_serial()
            if len(bData) > 0:
                data += bData.decode("utf8")
                if data == "ok":
                    self._recv_radio_frame_lock.release()
                    return True, data
                elif data == "invalid_param":
                    self._recv_radio_frame_lock.release()
                    return False, data
                else:
                    self._recv_radio_frame_lock.release()
                    if bExpectOk:
                        return False, data
                    return True, data
            t += 1
        self._recv_radio_frame_lock.release()
        return False, data



    """
    Initialize Board
    - Check version
    - set mode p2p
    - put on no sleep mode
    - set region
    """
    def init_lorap2p(self):

        r, version = self._send_cmd("sys reset")
        if r is False:
            self.log.error("%s:Unable to get version" % self._name)
            return False
        if re.match("^RN2483 1\.0\.5 .*$", version) is None:
            self.log.error("%s:Version not supported: %s" % (self._name, version))
            return False

        # set mode LoraP2P
        r, data = self._send_cmd("mac pause")
        if not r:
            return False
        r, data = self._send_cmd("radio set mod lora")
        if not r:
            return False
        r, data = self._send_cmd("radio set wdt 0")
        if not r:
            return False
        r, data = self._send_cmd("radio set sync 12")
        if not r:
            return False
        crc = "off"
        if self.config_rx["crcOn"] == 1:
            crc = "on"
        r, data = self._send_cmd("radio set crc "+crc)
        if not r:
            return False

        bandwidth = "125"
        if self.config_rx["bandwidth"] == 0:
            bandwidth = "125"
        elif self.config_rx["bandwidth"] == 1:
            bandwidth = "250"
        elif self.config_rx["bandwidth"] == 2:
            bandwidth = "500"
        # 0:125kHz, 1:250kHz, 2:500kHz
        r, data = self._send_cmd("radio set bw "+bandwidth)
        if not r:
            return False
        r, data = self._send_cmd("radio set rxbw "+bandwidth)
        if not r:
            return False
        r, data = self._send_cmd("radio set sf sf"+str(self.config_rx["datarate"]))
        if not r:
            return False

        coderate = "4/5" # 1:4/5, 2:4/6, 3:4/7, 4:4/8
        if self.config_rx["coderate"] == 1:
            coderate = "4/5"
        elif self.config_rx["coderate"] == 2:
            coderate = "4/6"
        elif self.config_rx["coderate"] == 3:
            coderate = "4/7"
        elif self.config_rx["coderate"] == 4:
            coderate = "4/8"
        r, data = self._send_cmd("radio set cr "+coderate)

        if not r:
            return False
        r, data = self._send_cmd("radio set freq "+str(self.config_rx["channel"]))
        if not r:
            return False


        r, data = self._send_cmd("radio set prlen "+str(self.config_rx["preambleLen"]))
        if not r:
            return False
        r, data = self._send_cmd("radio set pwr "+str(self.config_tx["power"]))
        if not r:
            return False

        return True





    """
    Send data on LoRa
    """
    def send_radio_frame(self, data):
        self.radio_tx_lock.acquire()

        self.set_tx_mode()

        # convert data to hex
        h_data = data.hex()
        cmd = "radio tx "+data.hex()
        r, resp = self._send_cmd(cmd, maxTry=80)
        if not r:
            self.log.warn("%s:send_radio_frame: send frame failed: %s" % (self._name, data.hex()))
            self.set_rx_mode()
            self.radio_tx_lock.release()
            return

        self.set_rx_mode()

        # (half-duplex) give a chance to others node to send responses
        ts = self.max_time_transmission
        #self.log.debug(self._name + ":send_radio_frame:ts: %f", ts)
        time.sleep(ts)

        self.radio_tx_lock.release()
        return


    """
    Get LoRa received frame
    """
    def recv_radio_frame(self):

        self._recv_radio_frame_lock.acquire()
        data = self._recv_serial()
        self._recv_radio_frame_lock.release()

        data = data.decode("utf8")
        if len(data) == 0:
            return b""


        self.set_rx_mode()


        re_at = "^radio_rx  ([0-9A-F]+)"
        if re.match(re_at, data) is None:
            # print not a recv frame
            self.log.debug("%s:recv_radio_frame:Unexpected command recv: %s" % (self._name, data))
            data = b""
            return data


        tmp = re.search(re_at, data)
        data = tmp.group(1)

        try:
            data = bytes.fromhex(data)
        except Exception as e:
            self.log.warn("%s:recv_radio_frame:Data recv is not a HEX string: %s" % (self._name, data))
            data = b""

        return data



    """
    Put board on receive LoRa data mode
    """
    def set_rx_mode(self):
        r = False
        while not r:
            #r, resp = self._send_cmd("radio rxstop", bExpectOk=True)

            r, resp = self._send_cmd("radio rx 0", bExpectOk=True)
            if r:
                self._mode_tx_lock.acquire()
                self._mode_tx = False
                self._mode_tx_lock.release()


        #self.log.error("%s: set_rx_mode Failed" % self._name)
        return r



    """
    Put board on transmit LoRa data mode
    """
    def set_tx_mode(self):
        r, resp = self._send_cmd("radio rxstop", bExpectOk=True)
        if r:
            self._mode_tx_lock.acquire()
            self._mode_tx = True
            self._mode_tx_lock.release()

        #self.log.error("%s: set_tx_mode Failed" % self._name)
        return r


