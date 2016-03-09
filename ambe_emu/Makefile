all:  ambe

image.asm: saram.bin
	./c54x-objdump -b binary -m tms320c54x --adjust-vma=0x38000 -D saram.bin > image.asm

ram.h: daram.bin
	echo "uint16_t ram[R_SIZE]={" > ram.h
	od -A none -v -x  daram.bin|sed 's/^ /0x/;s/ /,0x/g;s/$$/,/' >> ram.h
	echo "};" >> ram.h

image.h: image.asm asm2c.pl
	./asm2c.pl < image.asm > image.h

ambe: ram.h image.h tms320c54x.c
	gcc -gdwarf-4 -g3 -Wall -Wno-unused-label -O3 -o ambe tms320c54x.c

clean:
	${RM} ambe image.h ram.h image.asm

realclean: clean
	${RM} saram.bin daram.bin c54x-objdump
	${RM} -r binutils-gdb
