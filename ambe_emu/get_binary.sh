firmware=IRDM_9601_UpgradTool_TD10003_FIRMWARE.zip
binary=UpgradeTool_TD10003.exe
offset=003faf8 # Start of firmware structure in data section
file=.rdata

if [ ! -f $firmware ] ; then
	echo "Firmware binary missing." >&2
	exit 1
fi

[ ! -d unpack ] && mkdir unpack
cd unpack || exit 1
7z x ../$firmware

if [ ! -f $binary ] ; then
	echo "Could not extract binary" >&2
	echo "Please check above for error messages" >&2
	exit 1
fi
7z x $binary

if [ ! -f $file ] ; then
	echo "Could not extract data section" >&2
	echo "Please check above for error messages" >&2
	exit 1
fi

s=`echo 16i $offset 2/ p|tr a-f A-F|dc`

# Follow the firmware chunk structure
while true ; do 
dd if=$file skip=$s  bs=2 count=3 2>/dev/null | od -A n -x > _hdr
<_hdr read page start len

if [ "$len" = "0000" ] ; then
	echo "End of list" >&2
	break
fi

if [ "$len" = "" ] ; then
	echo "Something went wrong, sorry." >&2
	exit 1
fi

echo page: $page start: $start len: $len

len=`echo "16i $len p" |tr a-f A-F|dc`
start=`echo "16i $start p" |tr a-f A-F|dc`
s=`echo $s 3 + p |dc`

# Data memory
if [ "$page" = "0000" ] ; then
	dd if=$file skip=$s bs=2 count=$len seek=$start of=../daram.bin 2>/dev/null
fi

# Code memory (codec)
if [ "$page" = "0003" ] ; then
	start=`echo $start 16i 8000 - p |dc`
	dd if=$file skip=$s bs=2 count=$len seek=$start of=../saram.bin 2>/dev/null
fi

s=`echo $s $len + p |dc`

done

cd ..
rm -rf unpack
