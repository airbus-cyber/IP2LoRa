
import ipaddress
import crc16
from scapy.all import *
import socket
import netfilterqueue
import struct

from libUtils import libUtils




MAC_PREFIX = "10:2a:10:2a:10:00"

# force scapy to send to real eth interface
conf.L3socket = L3RawSocket




"""
Use of NFQUEUE to get IP/LORA packet 
"""
class RecvIpFromDummy(threading.Thread):
    def __init__(self, callback_on_recv, iface="dummy0", log=None):
        threading.Thread.__init__(self)
        self._name = "RecvIpFromDummy"
        self._callback_on_recv = callback_on_recv
        self.log = log
        self._iface = iface
        self._queue_num = 4
        self._isRunning = False


    def _add_netfilter_queue(self):
        os.system("iptables -A OUTPUT -o "+self._iface+" -j NFQUEUE --queue-num "+str(self._queue_num))
        os.system("iptables -A FORWARD -o " + self._iface + " -j NFQUEUE --queue-num " + str(self._queue_num))

    def _del_netfilter_queue(self):
        os.system("iptables -D OUTPUT -o "+self._iface+" -j NFQUEUE --queue-num "+str(self._queue_num))
        os.system("iptables -D FORWARD -o " + self._iface + " -j NFQUEUE --queue-num " + str(self._queue_num))

    def run(self):
        self.log.debug(self._name + ":Starting")
        self._add_netfilter_queue()

        q = netfilterqueue.NetfilterQueue()
        q.bind(self._queue_num, self._callback_on_recv)
        q.run(block=0)
        s = socket.fromfd(q.get_fd(), socket.AF_UNIX, socket.SOCK_STREAM)
        s.setblocking(0)


        self._isRunning = True
        while self._isRunning:
            try:
                q.run_socket(s)
            except Exception as e:
                #self.log.debug(e)
                pass

            time.sleep(0.05)

        s.close()
        q.unbind()
        self.log.debug(self._name + ":End")

        self._del_netfilter_queue()

    def stop(self):
        self._isRunning = False




class Ip2Lora(threading.Thread):
    def __init__(self, config={}):
        threading.Thread.__init__(self)
        self.log = config["log"]
        self._name = config["name"]
        config["name"] = config["deviceClass"].__name__

        self._t_dev = config["deviceClass"](config=config)

        self._ipAddress = config["ipAddress"]
        self._loraAddress = int(self._ipAddress.split(".")[-1])
        self._iface = "dummy"+str(self._loraAddress)
        self._addrLora = self._ip2loraAddr(self._ipAddress)
        self._macAddress = libUtils.int_to_mac(libUtils.mac_to_int(MAC_PREFIX) + self._loraAddress)
        ipIface = ipaddress.IPv4Interface(self._ipAddress + "/28")
        self._ipNetHosts = ipIface.network.hosts()
        self.maxLoraFrameSz = config["maxLoraFrameSz"]
        self.mtu = config["mtu"]

        self._func_compress = None
        if "func_compress" in config:
            self._func_compress=config["func_compress"]
        self._func_cipher = None
        if "func_cipher" in config:
            self._func_cipher = config["func_cipher"]
        self._func_decompress = None
        if "func_decompress" in config:
            self._func_decompress=config["func_decompress"]
        self._func_uncipher = None
        if "func_uncipher" in config:
            self._func_uncipher = config["func_uncipher"]

        #self._routeTable = config["routeTable"] # [[gw1, net1], [gw2, net2], ...]

        self.log.debug("%s: ipAddress: %s - iface:%s - addrLora:%s" % (self._name, self._ipAddress, self._iface, self._addrLora))

        self._isRunning = False

        self._recvBuf = b""

        self._t_recv_ip_from_dummy = RecvIpFromDummy(callback_on_recv=self._cbOnDummyRecvPkt, iface=self._iface, log=self.log)


        self.bUseRohc = config["rohc_compression"]
        if self.bUseRohc:
            from libLora import libRohc

            self.rohc_comp = libRohc.compressor()
            self.rohc_decomp = libRohc.decompressor()




    
    def _ip2loraAddr(self, ip_gw):
        return int(ip_gw.split(".")[-1])


    def _uncompress_ip_headers(self, data):
        if self.bUseRohc:
            from libLora import libRohc
            data = libRohc.decompress(self.rohc_decomp, data)
        return data


    def _compress_ip_headers(self, data):
        if self.bUseRohc:
            from libLora import libRohc
            data = libRohc.compress(self.rohc_comp, data)
        return data



    """
    compress and cipher IP frame
    """
    def _compress_and_cipher(self, data):
        data = self._compress_ip_headers(data)
        flags = 0

        if self._func_compress:
            data_compress = self._func_compress(data)
            self.log.debug("_compress_and_cipher:%s" % (data_compress))
            if len(data_compress) >= len(data):
                self.log.debug("Compression (%d) larger than uncompress (%d)" % (len(data_compress), len(data)))
            else:
                data = data_compress
                flags |= 8

        if self._func_cipher:
            data = self._func_cipher(data)
            flags |= 4

        return flags, data



    """
    uncompress and uncipher IP frame (if needed)
    """
    def _uncompress_and_uncipher(self, data, flags):
        res = False

        # check cipher
        if (flags >> 2) & 1 == 1:
            if self._func_uncipher is None:
                #self.log.debug("%s:uncipher failed: No uncipher function configured" % (self._name))
                return res, None
            try:
                data = self._func_uncipher(data)
            except Exception as e:
                self.log.debug("%s:uncipher failed: %s" % (self._name, str(e)))
                return res, None

        # check compress
        if (flags >> 3) & 1 == 1:
            if self._func_decompress is None:
                #self.log.debug("%s:uncompress failed: No uncompress function configured" % (self._name))
                return res, None
            try:
                data = self._func_decompress(data)
            except Exception as e:
                self.log.debug("%s:uncompress failed: %s" % (self._name, str(e)))
                return res, None

        try:
            data = self._uncompress_ip_headers(data)
        except Exception as e:
            self.log.debug("%s:uncompress ip hdr failed: %s" % (self._name, str(e)))
            return res, None
        
        res = True

        return res, data



    """
    Add arp table for other Lora Node
    => Ensure dummy interface collects frames for remote Lora Node
    """
    def _add_arp_net(self):
        for ip in self._ipNetHosts:
            my_id = int(ip) % 16
            mac = libUtils.int_to_mac(libUtils.mac_to_int(MAC_PREFIX) + my_id)
            os.system("arp -i "+self._iface+" -s "+str(ip)+" "+mac)



    def _rm_dummy_eth(self):
        os.system("rmmod -f dummy")


    """
    Create dummy interface for LoRa/IP interface 
    """
    def _init_dummy_eth(self):
        os.system("rmmod -f dummy 2>/dev/null")
        os.system("modprobe dummy")
        os.system("ip link add "+self._iface+" type dummy")
        os.system("ip link set dev " + self._iface + " address " + self._macAddress)
        os.system("ip link set dev " + self._iface + " mtu " + str(self.mtu))
        os.system("ip addr add "+self._ipAddress+"/28 dev "+self._iface)
        os.system("ip link set "+self._iface+" up")

        self._add_arp_net()



    """
    Translate Mac address to Lora/IP address 
    """
    def _getLoraAddrFromMac(self, mac):
        if MAC_PREFIX.lower().split(":")[:-1] != mac.lower().split(":")[:-1]:
            self.log.debug("Mac not Lora: %s" % mac)
            return None

        addrLora = int(mac.lower().split(":")[-1], 16)
        if addrLora > 14:
            self.log.debug("Lora address is out of range: %d" % addrLora)
            return None

        return addrLora



    """
    Send Data on LoRa Radio network
    """
    def _send_lora(self, data):
        if data:
            nb_seg = math.ceil(len(data) / float(self.maxLoraFrameSz))
            i = 0
            while i < nb_seg:
                self._t_dev.send_radio_frame(data[i * self.maxLoraFrameSz:(i + 1) * self.maxLoraFrameSz])
                i += 1
        return


    
    """
    Send IP frame on LoRa radio network
    """
    def _send_ip2lora(self, frame):
        """
        +0 (2 bytes) sz_data

        +2 (1 byte)
            x... .... ip payload 0:uncompress 1:compress
            .x.. .... ip payload 0:uncipher 1:cipher
            ..x. ....
            ...x ....
            .... xxxx address Lora

        +3 data
        ...
        +sz_frame (2 byte) crc16
        """
        #addrLora = self._getLoraAddrFromMac(frame.dst)
        #if addrLora is None:
        #    return


        # get mac address or IP.dst
        ip_gw = libUtils.get_gateway(frame["IP"].dst)
        if ip_gw is None:
            ip_gw = frame["IP"].dst

        mac_dst = libUtils.get_mac(iface=self._iface, ipaddress=ip_gw)
        if mac_dst is None:
            self.log.warning("%s:_send_ip2lora:Unable to get mac address for %s" % (self._name, ip_gw))
            return

        addrLora = self._getLoraAddrFromMac(mac_dst)
        if addrLora is None:
            self.log.warning("%s:_send_ip2lora:Not a Lora Mac address %s" % (self._name, addrLora))
            return



        # Compress and cipher
        clear_payload = raw(frame)
        flags, data_compress = self._compress_and_cipher(clear_payload)
        sz = len(data_compress)

        if sz > 0xfffe:
            self.log.warning("_send_ip2lora: lora frame sz overflow!")
            return
        sz = struct.pack("H", sz+1)


        addrLora += (flags << 4)
        raw_addr_flags = struct.pack("B", addrLora)
        crc = crc16.crc16xmodem(raw_addr_flags + clear_payload)

        data2send = sz + raw_addr_flags + data_compress + struct.pack("<H", crc)

        self._send_lora(data2send)
        return




    # To delete
    def _workWithArp(self, frame):
        # reply to arp request
        if frame["ARP"].op != 1: # who-has
            return

        ip_req = ipaddress.ip_address(frame["ARP"].pdst)
        if ip_req not in self._ipNetHosts:
            return

        # Send arp mac response for LoRa device
        id_ip_req = int(ip_req) % 16
        mac_req = libUtils.int_to_mac(libUtils.mac_to_int(MAC_PREFIX) + id_ip_arp_req)

        arp_resp = ARP(op=2, hwsrc=mac_req, psrc=str(ip_req), hwdst=frame["ARP"].hwsrc, pdrc=frame["ARP"].psrc)
        sendp(arp_resp)



    # calculate TCP checksum and update frame
    def _checksum_calc(self, frame):
        res = False
        if not frame.haslayer("IP"):

            return res, frame

        if frame.haslayer("TCP"):
            chksum = in4_chksum(socket.IPPROTO_TCP, frame["IP"], raw(frame["TCP"])[:16] + b'\x00\x00' + raw(frame["TCP"])[18:])
            frame["TCP"].chksum = chksum
        else:
            #self.log.debug("%s:no tcp frame:%s" % (self._name, frame.build()))
            pass
        res = True
        return res, frame

    

    """
    Call when receive dummy IP/Lora interface receive frame
    Send IP frame on LoRa radio network
    """
    def _cbOnDummyRecvPkt(self, pkt):

        if pkt.hw_protocol == 0x800:
            # IPv4 frame
            frame = IP(pkt.get_payload())
            self._workWithNetFrame(frame)

        pkt.accept()

        return


    """
    Recalc checksum and send IP frame to LoRa radio network
    """
    def _workWithNetFrame(self, frame):

        if frame.haslayer("IP"):
            # force recalculate checksum
            #   In normal condition, kernel driver will calculate them
            #   But on frame sent from local machine, we capture frame before kernel driver works....
            res, frame = self._checksum_calc(frame)
            if not res:
                return

            self.log.debug("%s:workWithNetFrame:Sending %s" % (self._name, frame.build()))

            self._send_ip2lora(frame)
        else:
            return



    """
    Extract data (IP frame) from (received) LoRa frame
    """
    def _unserialize(self, rawdata, i = 1):
        res = False
        offset = 0


        if len(rawdata) < 5:
            #xself.log.debug("%s:unserialize:frame to short" % (self._name))
            return res, None, offset
        
        sz = struct.unpack("H", rawdata[0:2])[0]


        if sz < 2:
            return res, None, offset

        if i == 0:
            self.log.debug(sz)


        rawdata = rawdata[2:]
        offset += 2


        if len(rawdata) < (sz + 2):
            #self.log.debug("%s:unserialize:frame to short. Expected: 0x%X" % (self._name, sz+2))
            return res, None, offset

        data = rawdata[:sz]
        addr_flags = data[0]
        crc = struct.unpack("<H", rawdata[sz:sz + 2])[0]
        offset += sz + 2


        addrLora = addr_flags & 0xf
        if i == 0:
            self.log.debug(addrLora)
        if addrLora != self._addrLora:
            #self.log.debug("%s:unserialize: bad addr: 0x%X" % (self._name, addrLora))
            return res, None, offset

        flags = (addr_flags & 0xf0) >> 4
        if i == 0:
            self.log.debug(flags)
        r, clear_payload = self._uncompress_and_uncipher(data[1:], flags)
        if not r:
            #self.log.debug("%s:_uncompress_and_uncipher failed" % (self._name))
            return res, None, None

        # check crc
        crc_data = crc16.crc16xmodem(bytes([addr_flags]) + clear_payload)
        if i == 0:
            self.log.debug(crc_data)
            self.log.debug(crc)
            self.log.debug("")
        if crc_data != crc:
            #self.log.debug("%s:unserialize: bad crc Expected: %X Got: %X" % (self._name, crc, crc_data))
            return res, None, None

        res = True
        return res, clear_payload, offset
        
        


    """
    Add received LoRa data in received buffer
    Try to parse received buffer to get a valid Lora/IP frame
    Send Lora/IP frame on classical IP network 
    """
    def _workWithSerialFrame(self):

        self._recvBuf += self._t_dev.recv_radio_frame()

        i = 0
        while i < len(self._recvBuf):
            res, data, offset_end = self._unserialize(self._recvBuf[i:],)
            if res:
                self._recvBuf = self._recvBuf[i + offset_end:]

                frame = IP(data)
                ipdst = frame["IP"].dst

                #send(frame, iface=self._iface)
                #sendp(frame)
                s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
                s.setsockopt(socket.SOL_IP, socket.IP_HDRINCL, 1)
                s.sendto(raw(frame), (ipdst, 0))
                s.close()
                self.log.debug("%s:workWithSerialFrame: net frame sent: %s" % (self._name, raw(frame)))


                # exit func => we will work with following received data on next main loop...
                return
            else:
                # parsing error
                # try to parse at next byte
                i += 1

        return



    def run(self):
        self.log.debug(self._name+":Starting")

        self._t_dev.start()
        while not self._t_dev.isRunning():
            time.sleep(0.1)

        self._isRunning = True

        # Init dummy iface
        self._init_dummy_eth()

        self._t_recv_ip_from_dummy.start()

        while self._isRunning:

            # On recv serial => Send in IP stack
            self._workWithSerialFrame()
            time.sleep(0.01)



        self._t_recv_ip_from_dummy.stop()

        self._rm_dummy_eth()
        self._t_recv_ip_from_dummy.join()
        
        self._t_dev.stop()
        self._t_dev.join()
        self.log.debug(self._name + ":End")





    def stop(self):
        self._isRunning = False





