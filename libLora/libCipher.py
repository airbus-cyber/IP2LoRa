from Crypto.Cipher import AES
import struct


class cipherXor():

    def __init__(self, key):
        if type(key) == str:
            self.key = bytes(key, "utf-8")
        elif type(key) == bytes:
            self.key = key
        else:
            raise ValueError("Invalid key format")


    def cipher(self, data):
        if type(data) == str:
            data = bytes(data, "utf-8")
        elif type(data) == bytes:
            pass
        else:
            raise ValueError("Invalid data format")

        keystream = self.key
        while len(keystream) < len(data):
            keystream += self.key

        clear_data = b""
        i = 0
        while i < len(data):
            clear_data += struct.pack("B", (data[i] ^ keystream[i]))
            i += 1

        return clear_data


    def uncipher(self, data):
        return self.cipher(data)
