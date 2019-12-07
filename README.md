# HytBridge
Open source communication tools for use with Hytera DMR repeaters.

# Functions
- Read audio and QSO meta data like source and destination DMR-IDs/TGs from repeater.
- Transmit audio to be sent on RF by repeater.
- Help debug network problems.

The software uses the IP-dispatch UDP/IP network interface to access decompressed PCM-data.
This is NOT an implementation of the IPSC protocol used to connect multiple repeaters as IPSC
is much more complicated and transmits AMBE-coded compressed voice data which is hard to
use in open source software due to patent restrictions.

# Current State
Current Project State: Under construction, not yet functional.

You'll need some basic understanding on how software development works in order to use this
software as it is in a very early state.

Parts of the documentation are still in german as I had no time to translate it yet.

# Author
Main Development: Lars Struß, DK7LST (http://www.dk7lst.de/)

Please understand that I can not provide support for this project as it is just a hobby project in my spare time.

# License
Open Source licensed under GPL v3, see "LICENSE"-file.

The software is intended for educational/scientific purpose in the context of amateur radio.
Use at your own risk!
Live the ham spirit and share your knowledge for a better world!
