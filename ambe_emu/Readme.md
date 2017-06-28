This builds an emulated C version of the iridium AMBE codec.

Prerequisites are:

- c54x-objdump

This can be obtained by building binutils with "./configure --target=c54x --program-prefix=c54x"

You can try to use "mk_objdump.sh" which will try to build it for you, assuming you have a compiler installed.

- daram.bin & saram.bin

Program and Data memory of the AMBE codec. These need to be extracted from an Iridium firmware image.

You can try to use "get_binary.sh" which will try to extract it from the TD10003 binary for the 9601 SBD modem.

As any direct links to firmware images seem to result in the images getting taken down, use google to search for
the TD10003 firmware/upgrade.

