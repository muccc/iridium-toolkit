#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <malloc.h>
#include <setjmp.h>
#include <assert.h>
#include <getopt.h>

/* cheap attempt at emulating tms320c54x */
/* just enough to run the IR AMBE Codec decoding */

#define R_SIZE 0xffff
#define S_SIZE 0x8000

//uint16_t ram[R_SIZE];
#include "ram.h"
uint16_t oldram[R_SIZE];
jmp_buf jump[99]; // Max recursion level...
jmp_buf cur_env;
int jp=0;

#define uint40_t uint64_t

uint16_t pc;

uint40_t a;
uint40_t b;

int doit;
int rc;

#define SHIFT(val,shift) (((shift)>0)?((val)<<(shift)):((val)>>-(shift)))

#define imr  ram[0x00]
#define ifr  ram[0x01]
#define st0  ram[0x06]
#define st1  ram[0x07]
#define al   ram[0x08]
#define ah   ram[0x09]
#define ag   ram[0x0a]
#define a ((((uint64_t)ag<<32)|((uint64_t)ah<<16)|al) & 0xffffffffff)
#define sex_a ((int64_t)(((a&(1LL<<39))?0xffffff0000000000:0)|a))
//inline void set_as(uint64_t x) {if(_SXM && x>=0x8000){x|= 0xffffffff0000L };al=x&0xffff;ah=(x>>16)&0xffff;ag=(x>>32)&0xff;};
inline void set_a(uint64_t x) {al=x&0xffff;ah=(x>>16)&0xffff;ag=(x>>32)&0xff;};
#define bl   ram[0x0b]
#define bh   ram[0x0c]
#define bg   ram[0x0d]
#define b ((((uint64_t)bg<<32)|((uint64_t)bh<<16)|bl) & 0xffffffffff)
#define sex_b ((int64_t)(((b&(1LL<<39))?0xffffff0000000000:0)|b))
inline void set_b(uint64_t x) {bl=x&0xffff;bh=(x>>16)&0xffff;bg=(x>>32)&0xff;};
#define t    ram[0x0e]
#define trn  ram[0x0f]
#define ar0  ram[0x10]
#define ar1  ram[0x11]
#define ar2  ram[0x12]
#define ar3  ram[0x13]
#define ar4  ram[0x14]
#define ar5  ram[0x15]
#define ar6  ram[0x16]
#define ar7  ram[0x17]
#define sp   ram[0x18]
#define bk   ram[0x19]
#define brc  ram[0x1a]
#define rsa  ram[0x1b]
#define rea  ram[0x1c]
#define pmst ram[0x1d]
#define xpc  ram[0x1e]

uint16_t pmr_value;

#define C_START 0x380000
#define C_SIZE 18432

#define _ARP  ((st0>>13) &   0x7)
#define _TC   ((st0>>12) &   0x1)
#define _C    ((st0>>11) &   0x1)
#define _OVA  ((st0>>10) &   0x1)
#define _OVB  ((st0>> 9) &   0x1)
#define _DP   ( st0      & 0x1ff)

#define _BRAF ((st1>>15) &   0x1)
#define _CPL  ((st1>>14) &   0x1)
#define _XF   ((st1>>13) &   0x1)
#define _HM   ((st1>>12) &   0x1)
#define _INTM ((st1>>11) &   0x1)
#define _OVM  ((st1>> 9) &   0x1)
#define _SXM  ((st1>> 8) &   0x1)
#define _C16  ((st1>> 7) &   0x1)
#define _FRCT ((st1>> 6) &   0x1)
#define _CMPT ((st1>> 5) &   0x1)
#define _ASM  ((st1&0x10? ((st1&0xf)-16): (st1&0xf)))
#define _ASM_R  ( st1      &  0x1f)

#define SSBX_TC   ((st0|= 1<<12))
#define SSBX_C    ((st0|= 1<<11))
#define SSBX_OVA  ((st0|= 1<<10))
#define SSBX_OVB  ((st0|= 1<< 9))
#define SSBX_BRAF ((st1|= 1<<15))
#define SSBX_CPL  ((st1|= 1<<14))
#define SSBX_XF   ((st1|= 1<<13))
#define SSBX_HM   ((st1|= 1<<12))
#define SSBX_INTM ((st1|= 1<<11))
#define SSBX_OVM  ((st1|= 1<< 9))
#define SSBX_SXM  ((st1|= 1<< 8))
#define SSBX_C16  ((st1|= 1<< 7))
#define SSBX_FRCT ((st1|= 1<< 6))
#define SSBX_CMPT ((st1|= 1<< 5))

#define RSBX_TC   (st0&= ~( 1<<12))
#define RSBX_C    (st0&= ~( 1<<11))
#define RSBX_OVA  (st0&= ~( 1<<10))
#define RSBX_OVB  (st0&= ~( 1<< 9))
#define RSBX_BRAF (st1&= ~( 1<<15))
#define RSBX_CPL  (st1&= ~( 1<<14))
#define RSBX_XF   (st1&= ~( 1<<13))
#define RSBX_HM   (st1&= ~( 1<<12))
#define RSBX_INTM (st1&= ~( 1<<11))
#define RSBX_OVM  (st1&= ~( 1<< 9))
#define RSBX_SXM  (st1&= ~( 1<< 8))
#define RSBX_C16  (st1&= ~( 1<< 7))
#define RSBX_FRCT (st1&= ~( 1<< 6))
#define RSBX_CMPT (st1&= ~( 1<< 5))

#define _IPTR   ((pmst>> 7) & 0x1ff)
#define _MPnMC  ((pmst>> 6) &   0x1)
#define _OVLY   ((pmst>> 5) &   0x1)
#define _AVIS   ((pmst>> 4) &   0x1)
#define _DROM   ((pmst>> 3) &   0x1)
#define _CLKOFF ((pmst>> 2) &   0x1)
#define _SMULT  ((pmst>> 1) &   0x1)
#define _SST    ( pmst      &   0x1)

/*
#define al (a & 0xffff)
#define ah ((a>>16) & 0xffff)
#define ag ((a>>32) & 0xff)

#define bl (b & 0xffff)
#define bh ((b>>16) & 0xffff)
#define bg ((b>>32) & 0xff)
*/

void reset(){
	pc=0x8f33;
	trn=0;
	st0=0x0600; //0x1800;
	st1=0x6908; //0x2900;
	sp=0xe5e6; // 0xe5f8;

	set_a(0);
	set_b(1);
	ar0=0xf305;
	ar1=0xffff;
	ar2=0;
	ar3=0xf20e;
	ar4=0;
	ar5=0xf303;
	ar6=0;
	ar7=0x99ba;

	t=0xfff8;
	pmst=0xffc0;
	bk=0;
	brc=0;
	imr=0;
	rsa=0x9aeb;
	ifr=0;
	rea=0x9afb;
	pmr_value=3;
	SSBX_CPL;
};

void die(char * reason, char * op, char * addr){
	printf("Dieing: %s (Opcode: %s @ %s)\n",reason,op,addr);
	exit(-1);
};

void debug(char* addr,char* op){
	assert(_CPL ==1);
	assert(_C16 ==0);
	assert(_FRCT ==0);
	printf ("\n@ %s ========================================= %s\n",addr,op);
	printf ("PC: %04x SP: %04x A: %010llx B: %010llx ",pc,sp,a,b);
	printf ("ST0: %04x ST1: %04x\n",st0,st1);
	printf ("AR0: %04x AR1: %04x AR2: %04x AR3: %04x AR4: %04x AR5: %04x AR6: %04x AR7: %04x\n",ar0,ar1,ar2,ar3,ar4,ar5,ar6,ar7);
	printf ("@SP: %04x @SP+1: %04x @SP+2: %04x @SP+3: %04x",ram[sp],ram[sp+1],ram[sp+2],ram[sp+3]);
	printf ("\n");
};

uint16_t rev(uint16_t value){
	const uint16_t mask0 = 0x5555;
	const uint16_t mask1 = 0x3333;
	const uint16_t mask2 = 0x0F0F;
	const uint16_t mask3 = 0x00FF;

	value = (((~mask0) & value) >> 1) | ((mask0 & value) << 1);
	value = (((~mask1) & value) >> 2) | ((mask1 & value) << 2);
	value = (((~mask2) & value) >> 4) | ((mask2 & value) << 4);
	value = (((~mask3) & value) >> 8) | ((mask3 & value) << 8);

	return value;
};

uint16_t rcp(uint16_t v1, uint16_t v2){
	return rev(rev(v1)+rev(v2));
};

int dumpram=0;
int logram=1;
int dumppc=1;
int cycle=-1;
FILE *pclogf;
FILE *ramlogf;
int lograminit=0;

void dinit(){
	if (logram){
		if (!ramlogf){
			ramlogf = fopen("ram.log", "w");
		};
	};
	memcpy(oldram,ram,sizeof(ram));
	if (cycle!=-1)
		cycle=(((cycle)/100000)+1)*100000;
	else
		cycle=0;
};

void d(int pc){
	assert(_CPL==1);
	return;

	if (dumpram){
		FILE *fout;
		char fname[99];
		sprintf(fname,"ram-%05d.out",cycle);
		fout = fopen(fname, "wb");
		uint32_t x;
		for (x=0;x<=0xffff;x++){
			fwrite(&ram[x],sizeof(uint16_t),1,fout);
		};
		fclose(fout);
	};
	if (logram && ramlogf){
		uint32_t x;
		for (x=0;x<=0xffff;x++){
			if(ram[x] != oldram[x]){
				fprintf(ramlogf,"%04x=%04x\n",x,ram[x]);
			};
		};
		fprintf(ramlogf,"%05x:(%d)\n",0x30000+pc,cycle);
		fflush(ramlogf);
		memcpy(oldram,ram,sizeof(ram));
	};
	cycle++;
};

void wavhdr(FILE * fout){
	uint16_t ch=1;     /* channels */
	uint32_t sps=8000; /* samples per second */
	uint16_t bps=16;    /* bits per sample */
	uint32_t byps=sps*ch*bps/8; /* bytes per second */
	uint16_t align=ch*bps/8; /* bytes per second */
	uint32_t len;
	uint32_t word;

	fwrite("RIFF",4,1,fout);
	len=0; fwrite(&len,4,1,fout); /* size -8  or data + 36*/
	fwrite("WAVE",4,1,fout);
	fwrite("fmt ",4,1,fout);
	len=  16;fwrite(&len ,4,1,fout); /* fmt len */
	word=  1;fwrite(&word,2,1,fout); /* PCM */
	fwrite(&ch,2,1,fout);
	fwrite(&sps ,4,1,fout);
	fwrite(&byps ,4,1,fout);
	fwrite(&align ,2,1,fout);
	fwrite(&bps ,2,1,fout);
	fwrite("data",4,1,fout);
	len=0;fwrite(&len ,4,1,fout); /* data len */
};

void fixwav(FILE * fout){
	int len=ftell(fout);
	len-=8;
	fseek(fout,4,SEEK_SET);
	fwrite(&len,4,1,fout);
	len-=36;
	fseek(fout,40,SEEK_SET);
	fwrite(&len,4,1,fout);
};

void readmem(char * fname){
	FILE *fin;
	fin = fopen(fname, "rb");
	if (fin==NULL){
		if(ramlogf)
			fprintf(ramlogf,"FnF: %s\n",fname+16);
		exit(1);
	};
	if (ramlogf){
		fprintf(ramlogf,"Rd: %s\n",fname+16);
	};
	/*
	uint32_t x;
	for (x=0;x<=0xffff;x++){
		fread(&ram[x],sizeof(uint16_t),1,fin);
	};
	*/
	if( fread(&ram[0],sizeof(uint16_t),0xffff,fin) ) {}
	fclose(fin);
};

uint16_t bk_fixup(uint16_t index, int16_t step)
{
    uint16_t mask = bk;

	if (bk==0){
		return index+step;
	};

    mask |= (mask >>  1);
    mask |= (mask >>  2);
    mask |= (mask >>  4);
    mask |= (mask >>  8);

    uint16_t circ_index = index & mask;
    circ_index += step;

    circ_index %= bk;

    return (index & ~(mask)) | circ_index;
}


int64_t tmp;
int16_t para_tmp;
#include "image.h"
char fname[99];
void decode (FILE*fin, FILE* fout){
//	readmem("daram.bin");
	reset();
#if DEBUG
	dinit();
#endif
	ram[--sp]=0xc80b;init();
#if DEBUG
	printf("Init done.\n");
#endif

#if DEBUG
	t=0xfff9;
	st0=0x0600;
	ar0=0xf305;
	ar1=0x0137;
	ar2=0;
	ar3=0xf222;
	ar4=0;
	ar5=0xf303;
	ar6=0;
	ar7=0x9a1a;
	bk=0;
	set_a(0xffffffed68);
	set_b(1);
	st1=0x6908;
#endif

#define DATA_START 0xed68

        int frame_num, j;
		uint8_t frame_packed[39];
		uint16_t * frame_bits=&ram[DATA_START];

        /* Process each frame */
        frame_num = 0;

        while (fread(frame_packed, 39, 1, fin) == 1)
        {
#if DEBUG
                /* Progress */
                printf("Frame #%d\n", frame_num++);
#else
				frame_num++;
#endif

                /* Unpack frame LSB first */
                for (j=0; j<312; j++)
                {
                  frame_bits[j] = (frame_packed[j>>3] >> (j & 7)) & 1;
                }

                /* For each subframe */
                for (j=0; j<4; j++)
                {

	
	ram[sp    ]=0x138;
	ram[sp+0x1]=0x1;
	ram[sp+0x2]=0xec00;
	ram[sp+0x3]=0xb4;
	ram[sp+0x4]=0x100;
	ram[sp+0x5]=0x6d;
	ram[sp+0x6]=j;
	ram[sp+0x7]=0x0;
	set_a(DATA_START);


#if DEBUG
	sprintf(fname,"mem-before-work-call-%d-%d.bin",frame_num-1,j);
	readmem(fname);
	dinit();
#endif
	ram[--sp]=0xc804;subframe();
#if DEBUG
	printf("Frame %d.%d done.\n",frame_num-1,j);
#endif
	fwrite(&ram[0xec00],360,1,fout);
				}
		};
		printf("%d frames processed.\n",frame_num);
}

int  main(int argc, char ** argv) {
	int wav=1;
	int opt;
	char *outfile;
	FILE *fin, *fout;

	while ((opt = getopt(argc, argv,"wrh")) != -1) {
		switch (opt) {
			case 'w' : wav = 1;
					   break;
			case 'r' : wav = 0;
					   break;
			default: 
					   fprintf(stderr, "Usage:\n");
					   fprintf(stderr, "\t%s: [-w] [-r] input.dfs\n",argv[0]);
					   exit(EXIT_FAILURE);
		}
	}

	if (optind >= argc) {
		fprintf(stderr, "Expected argument after options\n");
		exit(EXIT_FAILURE);
	}

	/* create output file name */
	outfile=calloc(1,strlen(argv[optind])+4);
	strcpy(outfile, argv[optind]);
	if (strrchr(outfile,'/')!=NULL)
		outfile=1+strrchr(outfile,'/');
	char * ext=strrchr(outfile, '.');
	if(!ext)
		ext=outfile+strlen(outfile);
	if (wav)
		strcpy(ext,".wav");
	else
		strcpy(ext,".out");

	fin = fopen(argv[optind], "rb");
	if (!fin){
		perror("input file");
		exit(1);
	};
	fout = fopen(outfile, "wb");
	if (!fout){
		fprintf(stderr,"output file(\"%s\")",outfile);
		perror("");
		exit(1);
	};

	if (wav)
		wavhdr(fout);

	decode(fin,fout);

	if (wav)
		fixwav(fout);

	fclose(fin);
	fclose(fout);

	return(0);
}

