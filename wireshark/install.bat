@echo off
mkdir %APPDATA%\Wireshark\plugins
copy HytIPDispatch.lua %APPDATA%\Wireshark\plugins
pause
