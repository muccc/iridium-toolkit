[ ! -d binutils-gdb ] && git clone --depth=1 git://sourceware.org/git/binutils-gdb.git
if [ ! -d binutils-gdb ] ; then
	echo "Cloning binutils failed." >&2
	exit
fi
cd binutils-gdb
./configure --target=c54x
for a in bfd opcodes libiberty zlib libctf binutils ; do
	(
	cd $a
	sed -i '/^SUBDIRS/s/doc//' Makefile.in
	./configure --target=c54x
	make
	echo $a done
	)
done

cp ./binutils/objdump ../c54x-objdump
