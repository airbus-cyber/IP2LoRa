

# IP2LoRa
[![License](https://img.shields.io/badge/license-GPL--3.0-orange.svg)](https://www.gnu.org/licenses/gpl-3.0.txt)

IP2Lora allows making IP communication using wireless LoRa communication.
For more information, read this [article](https://airbus-cyber-security.com/ip2lora/).

<p align="center">
<img src="https://airbus-cyber-security.com/wp-content/uploads/2020/10/lora_modbus_st.gif" width=600>
</p>


## Supported LoRa Devices
| Lora device                                                                      |Supported  |
|----------------------------------------------------------------------------------|-----------|
|[B-L072Z-LRWAN1](https://www.st.com/en/evaluation-tools/b-l072z-lrwan1.html)      | Yes       |
|[WisNode](https://store.rakwireless.com/products/rak811-lpwan-evaluation-board)   | Partially |
|[LoStick](https://ronoth.com/products/lostik)                                     | Partially |


## Installation
```bash
git clone https://github.com/airbus-cyber/ip2lora
pip3 install -r requirements.txt
```
If you need to enable IP headers compression using ROHC,
install [ROHC and python bindings](https://rohc-lib.org/wiki/doku.php?id=python-install)
 
## Usage
Create config.py according to your needs (see examples).
Start IP2LoRa:
```bash
python3 ip2lora.py [-d] config.py
```

If using [B-L072Z-LRWAN1](https://www.st.com/en/evaluation-tools/b-l072z-lrwan1.html), 
you must flash the board with corresponding firmware (see firmware folder).
You just need to copy/paste it to the fake embedded drive. After waiting some seconds, press the reset button of the board.

## Disclaimer
Please note that IP2LoRa is a proof of concept and provided  “as is”. It is made available for use at your own risk.
Also, you must be aware of frequency bands regulations (Ex: in France: https://www.arcep.fr), and duty cycle limitation.




 

