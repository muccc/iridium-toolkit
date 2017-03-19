#!/usr/bin/perl
#
# vim:set ts=4 sw=4:

use strict;

my ($cmds,$cmdsok,$broken,%broken);

my %label;
my $laddr;

my %post;

my $sxm=0;
my %sxm;

my %reach;
my %func; # Function id from static analysis


my %lines;
while(<>){
	chomp;
	s/^\s*//;
	s/\s*$//;

	my ($addr,$hex,$op)=split(/\s+/,$_,3);
	$addr=~/^3(.*):/;
	$laddr=hex("0x".$1);

	if ($op =~ /(.*?)\s*\|\|\s*(.*)/){
		my ($left,$right)=($1,$2);

		my ($cmd,$para)=split(/\s+/,$left,2);
		my (@arg)=split(/,/,$para);

		my ($cmd2,$para2)=split(/\s+/,$right,2);
		my (@arg2)=split(/,/,$para2);

		$lines{$laddr}=[$cmd."_".$cmd2,[@arg,@arg2]];
		next;
	};
	my ($cmd,$para)=split(/\s+/,$op,2);
	my (@arg)=split(/,/,$para);
	$lines{$laddr}=[$cmd,[@arg]];
};

#for (keys %lines){ print "$_: $lines{$_}\n"; };

my @todo=([0x8f33,"init"],[0x8e2b,"subframe"]);

sub subify{
	my $x=shift;
	$x=~s/0x//;
	return "sub_".$x;
};

my %hack=( 0x8fa9 => 1 ); # Manually set start of sub that fails automatic detection
for (keys %hack){
	push @todo, [$_,sprintf("hack_%04x",$_)];
};

my %patch;
sub patch_sub_post{
	my ($addr,$label,$srcaddr)=@_;
	if (defined $func{$addr} && $func{$addr} ne $label){
		printf STDERR "... %04x -> %04x %s/%s\n",$srcaddr,$addr,$func{$addr},$label;
		unshift @{$post{$srcaddr}},"/* PATCH2 */ ".$func{$addr}."();return;"
	};
};
sub add_todo{
	my ($addr,$label,$srcaddr)=@_;
	if (defined $func{$addr} && $func{$addr} ne $label){
		printf STDERR "... %04x -> %04x %s/%s\n",$srcaddr,$addr,$func{$addr},$label;
		$patch{$srcaddr}=$func{$addr}."();return;"
	};
	push @todo,[$addr, $label];
};

# Identify subroutines / jump targets
while ($#todo>=0){
	my $retctr=0;
	my $do = shift@todo;
	my ($addr,$label)=@{$do};
#	printf "Starting @%04x with label $label\n",$addr;
	while (1){
#		printf "0x%04x: %-6s", $addr, $lines{$addr}[0];
		if($func{$addr}){ # Whoa!
			if ($func{$addr} eq $label){
#				print "Label aldready there\n";
				last;
			}else{
				printf STDERR "XXX: Label fail @ %04x: $func{$addr} vs. $label\n",$addr;
				last
			};
		}else{
#			print "setting label $label\n";
			$func{$addr}=$label;
		};
		last if ($lines{$addr}[0] eq "ret");
		if($lines{$addr}[0] eq "retd"){
			$retctr=3;
		};
		if($lines{$addr}[0] eq "call"){
			add_todo(hex($lines{$addr}[1][0]),subify($lines{$addr}[1][0]), $addr);
		};
		if($lines{$addr}[0] eq "calld"){
			add_todo(hex($lines{$addr}[1][0]),subify($lines{$addr}[1][0]), $addr+3);
		};
		if($lines{$addr}[0] eq "cc"){
			add_todo(hex($lines{$addr}[1][0]),subify($lines{$addr}[1][0]), $addr);
		};
		if($lines{$addr}[0] eq "bd"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr+3);
			$retctr=4;
		};
		if($lines{$addr}[0] eq "b"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr);
			$retctr=2;
		};
		if($lines{$addr}[0] eq "bc"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr);
		};
		if($lines{$addr}[0] eq "banz"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr);
		};
		if($lines{$addr}[0] eq "banzd"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr+3);
		};
		if($lines{$addr}[0] eq "bcd"){
			add_todo(hex($lines{$addr}[1][0]),$label, $addr+3);
		};
		if($retctr>0){
			last if( --$retctr == 0);
		};
		patch_sub_post($addr+1,$label,$addr);

		$addr++;
		die if $addr>0xffff;
	};
#	printf "END TODO @ %04x\n",$addr;
};

#print "DONE\n";

if(0){
	print "/*\n";
	for (sort keys %lines){
		printf "%04x: %-10s %s %s\n",$_,$func{$_},$lines{$_}[0],join(" ",@{$lines{$_}[1]//[]});
	};
	print "*/\n";
};

my %labels=map{$_=>1} values%func ;

# Function definitions
#for (keys %labels){ printf "void %s(void);\n",$_;};

my ($addr,$hex,$op);
my ($cmd,$para);
my @arg;


sub set_sxm{
	my ($laddr,$sxm)=@_;
	if($sxm==0){
		return;
	};
	if($sxm==3){
		$sxm{$laddr}=$sxm;
		return;
	};
	if(!defined $sxm{$laddr}){
		$sxm{$laddr}=$sxm;
		return;
	};
	if ($sxm{$laddr}==1 && $sxm==-1){
		print STDERR "$laddr: sxm mismatch @ $laddr\n";
		$sxm{$laddr}=3;
		return;
	}elsif ($sxm{$laddr}==-1 && $sxm==1){
		print STDERR "$laddr: sxm mismatch @ $laddr\n";
		$sxm{$laddr}=3;
		return;
	};
	#print STDERR "sxm ok @ $laddr\n";
};

# XXX:
set_sxm("0x8f33",1);
set_sxm("0x8e2b",1);

# Possibly premature optimisation
#  try to find if sxm is always set or not
for (1..5){
seek(STDIN,0,0);
while(<>){
	chomp;
	s/^\s*//;
	s/\s*$//;

	($addr,$hex,$op)=split(/\s+/,$_,3);
	$addr=~/^3(.*):/;
	$laddr="0x".$1;
	($cmd,$para)=split(/\s+/,$op,2);
#	next if ($para eq "");
	(@arg)=split(/,/,$para);


	if ($cmd =~ /^bc?d?$/ || $cmd =~ /^f?calld?$/ || $cmd =~ /banz/ ){
		$label{$arg[0]}=1;
#		print STDERR "rset @ $arg[0]: $sxm\n";
		set_sxm($arg[0],$sxm);
		$sxm=0;
	};
	$sxm=3 if($sxm{$laddr}==3);
	if ($cmd eq "ssbx" && $arg[1] eq "sxm"){
#		print STDERR "@ $laddr: +1\n";
		$sxm=+1;
	}elsif ($cmd eq "rsbx" && $arg[1] eq "sxm"){
		$sxm=-1;
#		print STDERR "@ $laddr: -1\n";
	}elsif($cmd =~ /^retd?$/){
		$sxm=0;
#		print STDERR "@ $laddr: 0\n";
	};
	$sxm=$sxm{$laddr} if($sxm==0 && defined($sxm{$laddr}));
	set_sxm($laddr,$sxm);
};
};

print "/* ",scalar(keys %label)," jump targets */ \n";
#for my $key (sort keys %label){ print "$key\n"; };

seek(STDIN,0,0);

sub fixaddr{
	$_[0]=~ s/0x//;
};

sub getcond {
	if (0){
		return "";
	}elsif ($_[0] eq "beq"){
		return "b==0";
	}elsif ($_[0] eq "bneq"){
		return "b!=0";
	}elsif ($_[0] eq "blt"){
		return "(b&(1LL<<39))!=0";
	}elsif ($_[0] eq "bgeq"){
		return "((b&(1LL<<39))==0 )";
	}elsif ($_[0] eq "bgt"){
		return "(((b&(1LL<<39))==0 ) && (b!=0))";
	}elsif ($_[0] eq "bleq"){
		return "(((b&(1LL<<39))!=0 ) || (b==0))";

	}elsif ($_[0] eq "aeq"){
		return "a==0";
	}elsif ($_[0] eq "aneq"){
		return "a!=0";
	}elsif ($_[0] eq "alt"){
		return "(a&(1LL<<39))!=0";
	}elsif ($_[0] eq "ageq"){
		return "((a&(1LL<<39))==0 )";
	}elsif ($_[0] eq "agt"){
		return "(((a&(1LL<<39))==0 ) && (a!=0))";
	}elsif ($_[0] eq "aleq"){
		return "(((a&(1LL<<39))!=0 ) || (a==0))";

	}elsif ($_[0] eq "c"){
		return "_C";
	}elsif ($_[0] eq "nc"){
		return "!_C";
	}elsif ($_[0] eq "tc"){
		return "_TC";
	}elsif ($_[0] eq "ntc"){
		return "!_TC";
	}else{
		return qq!die("missing","condition $_[0]","$addr"),1!;
	};
};

sub fixop{
	$_[0]=~ s/^#//;
	$_[0]=~ s/^DP\+(.*)/ram[sp+\1]/;
	$_[0]=~s/([+-])$/\1\1/;
	$_[0]=~ s/^\*(.+)\((.*)\)/ram[\1+\2]/;
	$_[0]=~ s/^\*\((.*)\)/ram[\1]/;
	$_[0]=~ s/^\*(.*)/ram[\1]/;
	$_[0] =~ s/^MMR\((.*)\)/ram[\1]/;
};

my $paralell_post;

# Implemented from http://www.ti.com.cn/cn/lit/ug/spru172c/spru172c.pdf
my %cmds=(
	nop   => ";",
	frame => "sp+=%0;",
	st_sub	  => sub {
				   $_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
				   $_[1]=~ s/^\*(.*)/\1/;
				   $_[0]=~s/^#//;
				   if($_[1]=~s/(\w+)([+-])$/\1/){
				   		$paralell_post="$1$2$2;";
					};
				   my $s1="para_tmp=ram[$_[1]];ram[$_[1]]=($_[0])>>(16-_ASM);";

				my($src,$dst);
				$_[2]=~ s/DP\+(.*)/ram[sp+\1]/;
				if ($_[2]=~s/\*(\w+)([+-])$/*\1/){
					my $zz="$1$2$2;";
					if($zz ne $paralell_post){
						$paralell_post.=$zz;
					}else{
						$_[2]="para_tmp";
					};
				};
				$_[2]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$_[2]=~ s/^\*(.*)/ram[\1]/;
				if($_[3] eq "a"){
					($src,$dst)=qw(b a);
				}else{
					($src,$dst)=qw(a b);
				};
				return $s1."set_$dst(tmp=(($_[2]<<16)-$src));if(tmp<0){RSBX_C;}else{SSBX_C;};".$paralell_post;
				   },
	st_ld	  => sub {
				   $_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
				   $_[1]=~ s/^\*(.*)/\1/;
				   $_[0]=~s/^#//;
				   if($_[1]=~s/(\w+)([+-])$/\1/){
				   		$paralell_post="$1$2$2;";
					};
				   my $s1= "para_tmp=ram[$_[1]];ram[$_[1]]=($_[0])>>(16-_ASM);";
					$_[2]=~s/^#//;
					$_[2]=~ s/DP\+(.*)/ram[sp+\1]/;
					$_[2]=~s/([+-])$/\1\1/;
					$_[2]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
					$_[2]=~s/^\*(.*)/ram[\1]/;
					if($_[3]eq "t"){
						return $s1."t=$_[2];".$paralell_post;
					}else{
						return $s1."set_$_[3]($_[2]<<16);".$paralell_post;
					};
				   },
	st_add	  => sub {
				   $_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
				   $_[1]=~ s/^\*(.*)/\1/;
				   $_[0]=~s/^#//;
				   if($_[1]=~s/(\w+)([+-])$/\1/){
				   		$paralell_post="$1$2$2;";
					};
				   my $s1= "para_tmp=ram[$_[1]];ram[$_[1]]=($_[0])>>(16-_ASM);";
				my($src,$dst);
				$_[2]=~ s/DP\+(.*)/ram[sp+\1]/;
				if ($_[2]=~s/\*(\w+)([+-])$/*\1/){
					my $zz="$1$2$2;";
					if($zz ne $paralell_post){
						$paralell_post.=$zz;
					}else{
						$_[2]="para_tmp";
					};
				};
				$_[2]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$_[2]=~ s/^\*(.*)/ram[\1]/;
				if($_[3] eq "a"){
					($src,$dst)=qw(b a);
				}else{
					($src,$dst)=qw(a b);
				};
				return $s1."set_$dst(tmp=(($_[2]<<16)+$src));if(tmp<0){SSBX_C;}else{RSBX_C;};".$paralell_post;
				   },
	st_mpy	  => sub {
				   $_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
				   $_[1]=~ s/^\*(.*)/\1/;
				   $_[0]=~s/^#//;
				   if($_[1]=~s/(\w+)([+-])$/\1/){
				   		$paralell_post="$1$2$2;";
					};
				   my $s1= "para_tmp=ram[$_[1]];ram[$_[1]]=($_[0])>>(16-_ASM);";
					return "" if $_[0]=~/%/;
					$_[2]=~s/^#//;
					$_[2]=~ s/DP\+(.*)/ram[sp+\1]/;
					$_[2]=~s/([+-])$/\1\1/;
					$_[2]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
					$_[2]=~s/^\*(.*)/ram[\1]/;
					return $s1."if(_SXM){".
					"set_$_[3]((int16_t)t*(int16_t)$_[2]<<_FRCT);".
					"}else{".
					"set_$_[3](t*$_[2]<<_FRCT);".
					"};".$paralell_post;
				   },
	st	  => sub {
					fixop($_[0]);
					fixop($_[1]);
					"$_[1]=$_[0];"
					},
	or	  => sub {
					return "" if $_[0] =~ /%/;
					fixop($_[0]);
					if($_[0] =~ /^[ab]$/){
						return "set_$_[1]($_[1]|$_[0]);";
					}else{
						return "set_$_[1]($_[1]|(uint16_t)$_[0]);";
					};
			},
	sat	  => sub {
				"if($_[0]>0xff80000000){".
					";".
				"}else if($_[0]>0x100000000){".
					"set_$_[0](0xff80000000);".
				"}else if($_[0]>0x7fffffff){".
					"set_$_[0](0x7fffffff);".
				"}else{".
					";".
				"};";
			},
	ldu	  => sub {
				return "" if $_[0]=~/%/;
				fixop($_[0]);
				return "set_$_[1]($_[0]);";
			},
	ld	  => sub {
					my $post;
					my $shift=0;
					return "" if $_[1] =~ /dp/;
					if ($_[0] =~ s/^\*\+(\w+)\((.*)\)/*\1(\2)/){
					   $post="$1+=$2;";
					};
					if ($#_ ==2 && $_[1]=~/^-?\d+$/){
						$shift=$_[1];
						$_[1]=$_[2];
					}elsif ($#_ ==2 && $_[1] eq "ts"){
						#$shift="(int16_t)t";
						$_[0]=~ s/DP\+(.*)/ram[(uint16_t)(sp+\1)]/;
						$_[0]=~s/^\*(.*)/ram[\1]/;

						return "if(_SXM){".
							"set_$_[2](SHIFT((int16_t)$_[0],(int16_t)t));".
						"}else{".
							"set_$_[2](SHIFT($_[0],(int16_t)t));".
						"};";

					}elsif ($#_ == 1 && $_[1] eq "asm"){
						if($_[0] =~ /^[ab]$/){
							return "set_$_[0](_ASM<0?(sex_$_[0]>>(-(_ASM))):($_[0]<<_ASM));";
						};
						$_[0]=~s/^#//;
						$_[0]=~s/([+-])$/\1\1/;
						$_[0]=~ s/DP\+(.*)/ram[(uint16_t)(sp+\1)]/;
						$_[0]=~s/^\*(.*)/ram[\1]/;
						return "st1=(st1&~0x1f)|($_[0]&0x1f);";
					}elsif ($#_ == 2 && $_[1] eq "asm"){
						if($_[0] =~ /^[ab]$/){
							return "set_$_[2](_ASM<0?(sex_$_[0]>>(-(_ASM))):(sex_$_[0]<<_ASM));";
						};
						return "";
					}elsif($#_ >1){
						return "";
					};
					if ($_[0] =~ s/(\w+)([+-])0B$/\1/){
						$post="$1=rcp($1,$2 ar0);";
					};
					return "" if $_[0] =~ /0B$/;
					$_[0]=~s/^#//;
#					$_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
					$_[0]=~ s/DP\+(.*)/ram[(uint16_t)(sp+\1)]/;
					if($_[0]=~s/\*(.*)([+-])$/*\1/){
						$post="$1$2$2;";
					};
					if($_[0]=~s/\*(.*)([+-])0$/*\1/){
						$post="$1$2=ar0;";
					};
					$_[0]=~ s/^\*(.*)\((.*)\)/ram[(uint16_t)(\1+\2)]/;
					$_[0]=~s/^\*(.*)/ram[\1]/;
					if($_[1] =~ /^[ab]$/){
						my $mask="(int16_t)";
						if ($_[0] =~ /^[ab]$/){
							$mask="(int32_t)";
						};
						if (0){
						;
							}elsif($sxm{$laddr}==-1){
								"set_$_[1]($_[0]<<$shift);".$post;
							}else{
								if($shift>=0){
								return "if(_SXM){".
								($_[0] =~ /^[ab]$/ ?
								"set_$_[1]($_[0]<<$shift);"
								:
								"set_$_[1]((uint64_t)($mask($_[0])<<$shift));").
								"}else{".
								"set_$_[1]($_[0]<<$shift);".
								"};".$post;
								}else{
									$shift=-$shift;
								return "if(_SXM){".
								($_[0] =~ /^[ab]$/ ?
								"set_$_[1](((($_[0]&(1LL<<32))?0xffffff0000000000:0)|$_[0])>>$shift);"
								:
								"set_$_[1]((uint64_t)($mask($_[0])>>$shift));").
								"}else{".
								"set_$_[1]($_[0]>>$shift);".
								"};".$post;
								};
							};
					}else{
						"$_[1]=$_[0]<<$shift;$post"
					}
	},
	call  => sub {
					if($_[0]!~/^0x(....)$/){
						qq!die("invalid","call @_","$addr");!
					}else{
						fixaddr($_[0]);
						$_[0]=~s/^3//; return "ram[--sp]=".(2+hex $laddr).";sub_$_[0]();";
					}},
	calld  => sub {
					if($_[0]!~/^0x(....)$/){
						qq!die("invalid","call @_","$addr");!
					}else{
						fixaddr($_[0]);
						$_[0]=~s/^3//;
						unshift @{$post{hex($laddr)+3}},
							"sub_$_[0]();";
						return "/* calld */"."ram[--sp]=".(4+hex $laddr).";";
					}},
	ret   => "++sp;return;", #X#
	retd   => sub {
					unshift @{$post{hex($laddr)+2}},
						"/* retd */return;";
						"/* retd */ ++sp;";
	},
	mvdk  => sub {
					my $pre;
					if ($_[0] =~ /^\*([+-])(\w+)\((.*)\)/){
						$pre="$2 $1=$3;";
						$_[0] = "*$2";
					};
					fixop($_[0]);
					"$pre;ram[$_[1]]=$_[0];"
					},
	mvdd  => sub {
					return "" if $_[0] =~ /%/;
					fixop($_[0]);
					fixop($_[1]);
					"$_[1]=$_[0];"
					},
	stm   => sub {
					fixop($_[0]);
					fixop($_[1]);
					"$_[1]=$_[0];"
					},
	dst   => sub {
					my $post="";
					$_[1] =~ s/DP/sp/;
					$_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
					$_[1]=~ s/^\*(.*)/\1/;
#					$_[1]=~s/([+-])$/\1\1/;
					if($_[1]=~s/([+-])$//){
						$post= $_[1]."$1=2;"
					}elsif($_[1]=~s/([+-])0$//){
						$post= $_[1]."$1=ar0;"
					};
					"ram[$_[1] +1]=($_[0]&0xffff);".
					"ram[$_[1] ]=(($_[0]>>16)&0xffff);".
					$post
					},
	stl   => sub {
					my $shift=0;
					return "" if $_[1] =~ /^\*\+/;
					my ($bk,$bk0,$bkd);;
					if ($#_==2){
						$shift=$_[1];
						$_[1]=$_[2];
					};
					if($_[1]=~/([+-])0?%/){
						$bk=1;
						$bkd=$1;
						$bk0=($_[1]=~/0%/);
						$_[1]=~s/[+-]0?%//;
					};
					$_[1] =~ s/DP/sp/;
					$_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
					$_[1]=~ s/^\*(.*)/\1/;
					$_[1]=~s/([+-])$/\1\1/;
					if($bk){
						$bk="$_[1]=bk_fixup($_[1],$bkd".($bk0?"ar0":"1").");";
					}
					if($shift eq "asm"){
						return "ram[$_[1]]=((".
							"((_ASM<0)?($_[0]>>(-_ASM)):($_[0]<<_ASM))".
							")&0xffff);".$bk
					}elsif ($shift < 0){
						return "ram[$_[1]]=(($_[0]>>-($shift))&0xffff);".$bk
					}else{
						return "ram[$_[1]]=(($_[0]<<$shift)&0xffff);".$bk
					};
					},
	stlm   => sub {
					return "" if $_[1] =~/[ab]l/;
					"$_[1]=($_[0]&0xffff);"
					},
	ldm    => sub {
					fixop($_[0]);
					"set_$_[1]($_[0]);",
			},
	adds    => sub {
				return "" if $_[0]=~/%/;
				$_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
				$_[0]=~s/([+-])$/\1\1/;
				$_[0]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$_[0]=~ s/^\*(.*)/ram[\1]/;
				return "set_$_[1](tmp=($_[1]+$_[0]));".
					"if(tmp>0x100000000){SSBX_C;}else{RSBX_C;};";
			},
	add    => sub {
				my ($src,$shift,$s2,$dst);
				my ($shift2)=0;
				if($#_ == 1){
					if($_[1]=~/^\d+$/){
						$src=$_[0];
						$s2=$dst=$_[0];
						$shift=$_[1];
					}else{
						$src=$_[0];
						$s2=$dst=$_[1];
						$shift=0;
					};
				}elsif($#_==2 && $_[1]=~/^[ab]$/){
					$src=$_[0];
					$s2=$_[1];
					$dst=$_[2];
					$shift=0;
				}elsif($#_==2 && $_[1]=~/^-?\d+$/ && $_[0] =~ /^[ab]$/){
					$src=$_[2];
					$s2=$_[0];
					$dst=$_[2];
					$shift=$_[1];
				}elsif($#_==2 && $_[1]=~/^-?\d+$/){
					$src=$_[2];
					$s2=$_[0];
					$dst=$_[2];
					$shift=$_[1];
				}elsif($#_==2 && $_[1] eq "ts"){
					return "";
				}elsif($#_==2 ){
					$src=$_[0];
					$s2=$_[1];
					$dst=$_[2];
					$shift=16;
					$shift2=16;
				}elsif($#_==3 ){
					$src=$_[0];
					$s2=$_[2];
					$dst=$_[3];
					$shift2=$_[1];
					$shift=0;
				}else{
					return "";
				};
				$src=~s/^#//;
				$src=~ s/DP\+(.*)/ram[sp+\1]/;
				$src=~s/([+-])$/\1\1/;
				$src=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$src=~ s/^\*(.*)/ram[\1]/;
				$s2=~s/^#//;
				$s2=~ s/DP\+(.*)/ram[sp+\1]/;
				$s2=~s/([+-])$/\1\1/;
				$s2=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$s2=~ s/^\*(.*)/ram[\1]/;
				my($s2m,$srcm);
				if($s2 =~ /^[ab]$/){
					$s2m="sex_$s2";
				}else{
					$s2m="(int16_t)$s2";
				};
				if($src =~ /^[ab]$/){
					$srcm="sex_$src";
				}else{
					$srcm="(int16_t)$src";
				};
				if($shift<0){
					return "if(_SXM){".
					"set_$dst(tmp=(($srcm<<$shift2) + ($s2m>>-($shift))));".
					"}else{".
					"set_$dst(tmp=(($src <<$shift2) + ($s2 >>-($shift))));".
					"};".
					"if(tmp>0x100000000){SSBX_C;}else{RSBX_C;};";
				}else{
					if($shift2<0){
					return "if(_SXM){".
					"set_$dst(tmp=(($srcm>>-($shift2)) + ($s2m<<$shift)));".
					"}else{".
					"set_$dst(tmp=(($src >>-($shift2)) + ($s2 <<$shift)));".
					"};".
					"if(tmp>0x100000000){SSBX_C;}else{RSBX_C;};";
					}else{
					return "if(_SXM){".
					"set_$dst(tmp=(($srcm<<$shift2) + ($s2m<<$shift)));".
					"}else{".
					"set_$dst(tmp=(($src <<$shift2) + ($s2 <<$shift)));".
					"};".
					"if(tmp>0x100000000){SSBX_C;}else{RSBX_C;};";
					};
				};
				},
	subs    => sub {
				fixop($_[0]);
				"set_$_[1]($_[1]-$_[0]);";
				},
	sub    => sub {
				my $post;
				my ($src,$shift,$s2,$dst);
				return "" if $_[0] =~ /%/;
				if($#_ == 1){
					$src=$_[0];
					$s2=$dst=$_[1];
					$shift=0;
				}elsif($#_==0){ # Seems kinda pointless
					$src=$_[0];
					$s2=$_[0];
					$dst=$_[0];
					$shift=0;
#					return "set_$_[0](0);SSBX_C;";
				}elsif($#_==2){
					if ($_[1] =~ /^-?\d+$/){
						if ($_[0] =~ s/(\w+)([+-])0B$/\1/){
							$post="$1=rcp($1,$2 ar0);";
						};
						$src=$_[0];
						$s2=$dst=$_[2];
						$shift=$_[1];
					}elsif($_[0]=~/^#/){
						$src=$_[0];
						$s2=$_[1];
						$dst=$_[2];
						$shift=0;
					}else{
						return "";
					};
				}elsif($#_==3){
					$src=$_[0];
					$shift=$_[1];
					$s2=$_[2];
					$dst=$_[3];
				}else{
					return "";
				};
				$src=~s/^#//;
				$src=~ s/DP\+(.*)/ram[sp+\1]/;
				$src=~s/([+-])$/\1\1/;
				$src=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$src=~ s/^\*(.*)/ram[\1]/;
				my $cast;
				if($src !~ /^[ab]$/){
					$cast="(int16_t)";
				}else{
					$src="sex_$src";
				};
				if($shift<0){
					return "if(_SXM){".
				"set_$dst(tmp=($s2 - ($cast$src>>-($shift))) );if(tmp<0){RSBX_C;}else{SSBX_C;};$post".
						"}else{".
				"set_$dst(tmp=($s2 - ($src>>-($shift))) );if(tmp<0){RSBX_C;}else{SSBX_C;};$post".
						"};$post";
				}else{
					return "if(_SXM){".
				"set_$dst(tmp=($s2 - ($cast$src<<$shift)) );if(tmp<0){RSBX_C;}else{SSBX_C;};".
						"}else{".
				"set_$dst(tmp=($s2 - ($src<<$shift)) );if(tmp<0){RSBX_C;}else{SSBX_C;};".
						"};$post";
				};

				},
	pshm  => sub {
					$_[0] =~ s/^MMR\((.*)\)/ram[\1]/;
					"ram[--sp]=$_[0];"
				},
	popm  => sub {
					$_[0] =~ s/^MMR\((.*)\)/ram[\1]/;
					"$_[0]=ram[sp++];",
				},
	ssbx  => sub { uc "SSBX_$_[1];" },
	rsbx  => sub { uc "RSBX_$_[1];" },
	addm    => sub {
				fixop($_[0]);
				fixop($_[1]);
				"$_[1]+=$_[0];";
				},
	rc    => sub {
				"if(".getcond($_[0])."){++sp;return;};";
			},
	sfta    => sub {
				my $s;
				if ($_[1] <0){
					$s=">> ".-$_[1];
				}else{
					$s="<< ".$_[1];
				};
				"set_$_[0]( ( (int64_t)($_[0]| (($_[0]&(1LL<<39))?0xffffff0000000000L:0) )) $s);",
				},
	bc    => sub {
					fixaddr($_[0]);
					"if(".getcond($_[1])."){goto L$_[0];};";
					},
	bcd    => sub {
				fixaddr($_[0]);
				unshift @{$post{hex($laddr)+3}},
				"/* DELAY */ if(doit){goto L$_[0];};\n";
				return "if(".getcond($_[1])."){doit=1;}else{doit=0;};";
				},
	and    => sub {
				my $dst=$_[1];
				$dst=$_[2] if ($#_==2);
				return "" if($#_==2 && $_[1]=~ /^\d+$/);
				fixop($_[0]);
				"set_$dst($_[1] & (uint16_t)$_[0]);";
				},
	andm    => sub {
				fixop($_[0]);
				fixop($_[1]);
				"$_[1] &= $_[0];";
				},
	rpt    => sub {
				my $delay=1;
				if($lines{hex($laddr)+1}[0] eq ""){
					$delay=2;
				};
				$_[0]=~s/^#//;
				$_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
				$_[0]=~ s/^\*(.*)/ram[\1]/;
				unshift @{$post{hex($laddr)+$delay}}," /* rpt */}; ";
				return "rc=$_[0];while(rc-->=0){";
				},
	mas    => sub {
				my $post;
				if($#_==2){
					$_[0]=~s/^#//;
					$_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
					if($_[0]=~/(\w+)([+-])0$/){
						$post="$1$2=ar0;";
						$_[0]=~s/[+-]0$//;
					};
					if($_[0]=~/(\w+)([+-])$/){
						$post="$1$2$2;";
						$_[0]=~s/[+-]$//;
					};
					$_[0]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
					$_[0]=~ s/^\*(.*)/ram[\1]/;

					$_[1]=~s/^#//;
					$_[1]=~ s/DP\+(.*)/ram[sp+\1]/;
					$_[1]=~s/([+-])$/\1\1/;
					$_[1]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
					$_[1]=~ s/^\*(.*)/ram[\1]/;
					return "if(_SXM){".
						"set_$_[2]( $_[2] - ((int16_t)$_[0] * (int16_t)$_[1] <<_FRCT));".
					"}else{".
						"set_$_[2]( $_[2] - ($_[0] * $_[1]<<_FRCT));".
					"};t=$_[0];$post";
				};
				$_[0]=~s/^#//;
				$_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
				if($_[0]=~/(\w+)([+-])0$/){
					$post="$1$2=ar0;";
					$_[0]=~s/[+-]0$//;
				};
				$_[0]=~s/([+-])$/\1\1/;
				$_[0]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				$_[0]=~ s/^\*(.*)/ram[\1]/;
				return "if(_SXM){".
					"set_$_[1]( $_[1] - ((int16_t)$_[0] * (int16_t)t <<_FRCT));$post".
				"}else{".
					"set_$_[1]( $_[1] - ($_[0] * t <<_FRCT));$post".
				"};";

				},
	rptbd    => sub {
				unshift @{$post{hex($_[0])}}," /* rptb */ }\nwhile(brc-->0);";
				unshift @{$post{hex($laddr)+3}},"do {";
				return "/* rptbd */";
				},
	rptb    => sub {
				unshift @{$post{hex($_[0])}}," /* rptb */ }\nwhile(brc-->0);";
				return "do {";
				},
	mvmd    => sub {
				return "ram[$_[1]]=$_[0];";
				},
	mvdm    => sub {
				return "$_[1]=ram[$_[0]];";
				},
	mvmm    => sub {
				return "$_[1]=$_[0];";
				},
	mvkd    => sub {
				fixop($_[1]);
				return "$_[1]=ram[$_[0]];";
				},
	exp    => sub {
				return "if ($_[0]==0){t=0;}else if(($_[0])&0x8000000000){t=__builtin_clz($_[0]^0xffffffff);}else{t=__builtin_clz((int32_t)$_[0])-1;};";
				},
	xor    => sub {
				fixop($_[0]);
				return "set_$_[1]($_[1] ^ $_[0]);";
				},
	orm    => sub {
				fixop($_[0]);
				fixop($_[1]);
				return "$_[1]=($_[1] | $_[0]);";
				},
	bd       => sub {
				fixaddr($_[0]);
				unshift @{$post{hex($laddr)+3}},"goto L$_[0];";
				"/* bd */";
				},
	b       => sub {
				fixaddr($_[0]);
				return "goto L$_[0];";
				},
	banz       => sub {
				my $post="";
				if ($_[1] =~ s/^\*\+(\w+)\((.*)\)/*$1/){
					$post="$1+=$2;";
				};
				fixaddr($_[0]);
				$_[1]=~s/([+-])$/\1\1/;
				$_[1]=~ s/^\*(.*)\((.*)\)/((int16_t)\1+(int16_t)\2)/;
				$_[1]=~ s/^\*(.*)/\1/;
				return "$post;if($_[1] !=0){goto L$_[0];}";
				},
	banzd      => sub {
				my $post="";
				if ($_[1] =~ s/^\*\+(\w+)\((.*)\)/*$1/){
					$post="$1+=$2;";
				};
				fixaddr($_[0]);
				$_[1]=~s/([+-])$/\1\1/;
				$_[1]=~ s/^\*(.*)\((.*)\)/(\1+\2)/;
				$_[1]=~ s/^\*(.*)/\1/;

				unshift @{$post{hex($laddr)+3}},"if(doit){goto L$_[0];}";
				"/* banzd */ $post;if($_[1]!=0){doit=1;}else{doit=0;};";
				},
	bitf       => sub {
#				$_[1]=~s/([+-])$/\1\1/;
				fixop($_[0]);
				fixop($_[1]);
				return "if($_[0] & $_[1]){SSBX_TC;}else{RSBX_TC;};";
				},
	sth       => sub {
					my ($bk,$bk0,$bkd);
					my $post;
					my $shift=0;
					if($#_>1){
						$shift=$_[1];
						$_[1]=$_[2];
						if($shift eq "asm"){
							$shift="(_ASM)";
						};
					};
					if($_[1]=~/([+-])0?%/){
						$bk=1;
						$bkd=$1;
						$bk0=($_[1]=~/0%/);
						$_[1]=~s/[+-]0?%//;
					};
					if($_[1]=~/(\w+)([+-])0$/){
						$post="$1$2= ar0;";
						$_[1]=~s/[+-]0$//;
					};
					$_[1] =~ s/DP/sp/;
					$_[1]=~ s/^\*(.*)\((.*)\)/\1+\2/;
					$_[1]=~ s/^\*(.*)/\1/;
					$_[1]=~s/([+-])$/\1\1/;
					if($bk){
						$bk="$_[1]=bk_fixup($_[1],$bkd".($bk0?"ar0":"1").");";
					}
					"ram[$_[1]]=(($_[0]>>(16-($shift)))&0xffff);".$bk.$post
			
				},
	dadd       => sub {
					my $dst=$_[1];
					if($#_==2){
						$dst=$_[2];
					};
					if ($_[0] =~ /DP(.*)/){
						return "set_$dst( $_[1] + (ram[sp $1]<<16|ram[sp $1 +1]));";
					}elsif($_[0] =~ /\*(.*)([+-])$/){
						return "set_$dst( $_[1] + (ram[$1]<<16|ram[$1 +1]));$1$2$2;";
					}elsif($_[0] =~ /\*(.*)/){
						return "set_$dst( $_[1] + (ram[$1]<<16|ram[$1 +1]));";
					}else{
						return "";
					};
				},
	dsub       => sub {
					if ($_[0] =~ /DP(.*)/){
						return "set_$_[1]( $_[1] - (ram[sp $1]<<16|ram[sp $1 +1]));";
					}elsif($_[0] =~ /\*(.*)([+-])$/){
						return "set_$_[1]( $_[1] - (ram[$1]<<16|ram[$1 +1]));$1$2$2;";
					}elsif($_[0] =~ /\*(.*)/){
						return "set_$_[1]( $_[1] - (ram[$1]<<16|ram[$1 +1]));";
					}else{
						return "";
					};
				},
	abs       => sub {
					return "" if($#_>0);
					return "set_$_[0](abs($_[0]));if($_[0]==0){SSBX_C;};";
				},
	neg       => sub {
					my $dst=$_[0];
					$dst=$_[1] if ($#_==1);
					return "set_$dst(-$_[0]);if($_[0]==0){SSBX_C;}else{RSBX_C;};";
				},
	dld       => sub {
					if ($_[0] =~ /DP(.*)/){
						return "set_$_[1]( ram[sp $1]<<16|ram[sp $1 +1]);";
					}elsif($_[0] =~ /\*(.*)([+])$/){
						return "set_$_[1]( ram[$1]<<16|ram[$1 +1]);$1$2=2;";
					}elsif($_[0] =~ /\*(.*)/){
						return "set_$_[1]( ram[$1]<<16|ram[$1 +1]);";
					}else{
						return "";
					};
				},
	subc       => sub {
					$_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
					$_[0]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
					$_[0]=~ s/^\*(.*)/ram[\1]/;
					return "tmp=$_[1]-(($_[0])<<15);if(tmp>=0){set_$_[1]((tmp<<1)+1);}else{set_$_[1]($_[1]<<1);};";
				},
	cmpr       => sub {
					my $cond;
					if ($_[0] eq "eq"){
						$cond="$_[1] == ar0";
					}elsif ($_[0] eq "lt"){
						$cond="$_[1] < ar0";
					}elsif ($_[0] eq "gt"){
						$cond="$_[1] > ar0";
					}elsif ($_[0] eq "neq"){
						$cond="$_[1] != ar0";
					}else{
						return "";
					};
					"if(".$cond."){SSBX_TC;}else{RSBX_TC;};";
				},
	cmpm       => sub {
					fixop($_[0]);
					fixop($_[1]);
					"if( $_[0] == $_[1] ){SSBX_TC;}else{RSBX_TC;};";
				},
	mar       => sub {
					return "" if($#_>0);
					if($_[0]=~ /^\*(.*)([+-])0$/){
						return "$1=$1$2ar0;";
					};
					return "" if($_[0]=~/[+-]0$/);
					return "" if($_[0]=~/[+-]0?%$/);
#					return "" if($_[0]=~/[+-]0B$/);
					if ($_[0] =~ s/(\w+)([+-])0B$/\1/){
						return "$1=rcp($1,$2 ar0);";
					};
#					$_[0]=~ s/^\*(.*)\((.*)\)/\1/;
					if($_[0]=~ /^\*\+(.*)\((.*)\)/){
						return "$1=$1+$2;";
					};
					$_[0]=~ s/^\*(.*)/\1/;
					$_[0]=~s/([+-])$/\1\1/;
					return "$_[0];";
				},
	macsu       => sub {
					my $post;
					if( $_[0]=~s/([+-])$//){
						my $ss=$1;
						my $x=$_[0];
						$x=~s/^\*//;
						$post.="$x$ss$ss;";
					};
					if( $_[1]=~s/([+-])$//){
						my $x=$_[1];
						$x=~s/^\*//;
						$post.="$x++;";
					};
					fixop($_[0]);
					fixop($_[1]);
					return "set_$_[2]($_[2]+(uint32_t)($_[0]*$_[1]<<_FRCT));t=$_[0];$post";
				},
	mac       => sub {
					if($#_==2){
					my ($bbk,$bbkr,$bbk0,$bbkd);
					my $post;
					if( $_[0]=~s/([+-])$//){
						my $ss=$1;
						my $x=$_[0];
						$x=~s/^\*//;
						$post.="$x$ss$ss;";
					};
					if($_[0]=~/(\w+)([+-])0?%/){
						$bbk=1;
						$bbkr=$1;
						$bbkd=$2;
						$bbk0=($_[0]=~/0%/);
						$_[0]=~s/[+-]0?%//;
					};
					fixop($_[0]);

					my ($bk,$bkr,$bk0,$bkd);
					if($_[1]=~/(\w+)([+-])0?%/){
						$bk=1;
						$bkr=$1;
						$bkd=$2;
						$bk0=($_[1]=~/0%/);
						$_[1]=~s/[+-]0?%//;
					};
					fixop($_[1]);
					if($bbk){
						$post.="$bbkr=bk_fixup($bbkr,$bbkd".($bbk0?"ar0":"1").");";
					}
					if($bk){
						$post.="$bkr=bk_fixup($bkr,$bkd".($bk0?"ar0":"1").");";
					}
						return "if(_SXM){".
						"set_$_[2](((int16_t)$_[0]*(int16_t)$_[1]<<_FRCT)+$_[2]);".
						"}else{".
						"set_$_[2](($_[0]*$_[1]<<_FRCT)+$_[2]);".
						"};t=$_[0];$post";
					};
					return "" if($#_>1);
					fixop($_[0]);
					"if(_SXM){".
					"set_$_[1]((((int16_t)$_[0]*(int16_t)t)<<_FRCT)+$_[1]);".
						"}else{".
					"set_$_[1]((($_[0]*t)<<_FRCT)+$_[1]);".
					"};";
				},
	sftl       => sub {
					my $dst;
					if ($#_ == 2){
						$dst=$_[2] ;
					}else{
						$dst=$_[0] ;
					};
					if($_[1] >0){
						"if($_[0] << ($_[1]-1)& 0x80000000){SSBX_C;}else{RSBX_C;}; set_$dst(0x00ffffffff & ($_[0]<<$_[1]));";
					}elsif($_[1]==0){
						"RSBX_C; set_$dst(0x00ffffffff & ($_[0]));";
					}else{
						"if($_[0] & (1<< (-($_[1])-1))){SSBX_C;}else{RSBX_C;}; set_$dst(0x00ffffffff & ($_[0]>> -($_[1])));";
					};
				},
	addc       => sub {
					fixop($_[0]);
					"set_$_[1](tmp=($_[1]+$_[0]+_C));if(tmp<0x100000000){RSBX_C;}else{SSBX_C;};";
				},
	bit       => sub {
					fixop($_[0]);
					"if($_[0]&(1<<(15-$_[1]))){SSBX_TC;}else{RSBX_TC;};";
				},
	rol       => sub {
					"tmp=$_[0]&0x80000000;set_$_[0]((($_[0]<<1)|_C)&0xffffffff);if(tmp){SSBX_C;}else{RSBX_C;};";
				},
	ror       => sub {
					"tmp=$_[0]&0x1;set_$_[0]((($_[0]>>1)|(_C<<31))&0xffffffff);if(tmp){SSBX_C;}else{RSBX_C;};";
				},
	norm       => sub {
					my $dst=$_[0];
					$dst=$_[1] if ($#_>0);
					if ($sxm{$laddr}==1){
						return "if(t&0x20){set_$dst(sex_$_[0]>>(32-(t&0x1f)));}else{set_$dst($_[0]<<(t&0x1f));};";
					}else{
						return "if(t&0x20){set_$dst(sex_$_[0]>>(32-(t&0x1f)));}else{set_$dst($_[0]<<(t&0x1f));};";
					};
				},
	xc       => sub {
					unshift @{$post{hex($laddr)+$_[0]}}," /* xc */}; ";
					return "if(".getcond($_[1])."){";
				},
	cmpl       => sub {
					return "set_$_[0]($_[0]^0xffffffffff);";
				},
	max       => sub {
					return "if(sex_a>sex_b){set_$_[0](a);RSBX_C;}else{set_$_[0](b);SSBX_C;};";
				},
	min       => sub {
					return "if(sex_a<sex_b){set_$_[0](a);RSBX_C;}else{set_$_[0](b);SSBX_C;};";
				},
	maca       => sub {
					if ($_[1] eq "b"){
						fixop($_[0]);
						return "set_b((int16_t)((a>>16)&0xffff)*(int16_t)$_[0]+b);t=$_[0];";
					}else{
						return "";
					};

				},
	mpya       => sub {
				   if ($_[0] =~ /^[ab]$/){
					   return "set_$_[0](((a>>16)&0xffff)*t<<_FRCT);";
				   }else{
					   fixop($_[0]);
					   if ($sxm{$laddr}!=-1){
					   return "set_b(((int16_t)((a>>16)&0xffff)*(int16_t)(t=$_[0]))<<_FRCT);";
					   }else{
					   return "set_b((((a>>16)&0xffff)*(t=$_[0]))<<_FRCT);";
					   };
				   };
				},
	mpyu       => sub {
					fixop($_[0]);
					return "set_$_[1]((uint32_t)(t*$_[0]));";
				},
	squr       => sub {
					my $post;
				   if($_[0]=~s/\*(\w+)([+-])$/*\1/){
							$post="$1$2$2;";
					};
					fixop($_[0]);
				   return "t=$_[0];set_$_[1](((int16_t)$_[0]*(int16_t)$_[0])<<_FRCT);$post";
				},
	squra       => sub {
					my $post;
				   $_[0]=~ s/DP\+(.*)/ram[sp+\1]/;
				   if($_[0]=~s/\*(\w+)([+-])$/*\1/){
							$post="$1$2$2;";
					};
				   $_[0]=~ s/^\*(.*)\((.*)\)/ram[\1+\2]/;
				   $_[0]=~ s/^\*(.*)/ram[\1]/;
				   return "t=$_[0];set_$_[1]($_[1]+(((int16_t)$_[0]*(int16_t)$_[0])<<_FRCT));$post";
				},
	mpy       => sub {
				   if($#_==2 && $_[1]=~/^#/){
				   		fixop($_[0]); # XXX: Correct postop!
				   		fixop($_[1]);
					   return "set_$_[2](($_[0]*$_[1])<<_FRCT);t=$_[0];";
				   }elsif($#_==2 ){
					   my $post="";
					   if($_[0]=~s/(\w+)([+-])$/\1/){
						   $post="$1$2$2;";
					   };
					   return "" if $_[0]=~/%/;
					   if ($_[1]=~/\*(\w+)\+0%/){
							$post.="$1=bk_fixup($1,ar0);";
					   		$_[1]=~s/\+0%//;
					   };
					   return "" if $_[1]=~/%/;
					   fixop($_[0]);
					   fixop($_[1]);
					   if ($sxm{$laddr}==1){
					   return "set_$_[2](((int16_t)$_[0]*(int16_t)$_[1])<<_FRCT);t=$_[0];$post";
					   }elsif($sxm{$laddr}==-1){
					   return "set_$_[2](($_[0]*$_[1])<<_FRCT);t=$_[0];$post";
					   }else{
						return "if(_SXM){".
						   "set_$_[2](((int16_t)$_[0]*(int16_t)$_[1])<<_FRCT);t=$_[0];".
						"}else{".
						   "set_$_[2](($_[0]*$_[1])<<_FRCT);t=$_[0];".
						"};$post";
					   };
				   }elsif($#_==1){
					   return "" if $_[0] =~ /%/;
					   fixop($_[0]);
					   if($sxm{$laddr}!=-1){
						   return "set_$_[1](((int16_t)t*(int16_t)$_[0])<<_FRCT);";
					   }else{
						   return "set_$_[1]((t*$_[0])<<_FRCT);";
					   };
				   };
				},
);

my $oldlabel;
my %labels=map {$_ => 1} values %func;
print "/* ",scalar(keys %labels)," subroutines */ \n";
for (sort keys %labels){
	print "void $_(void);\n";
};
print "\n";

sub invert{
	my $in=$_[0];
	my %out;
	for (sort keys %{$in}){
		push @{$out{$in->{$_}}},$_;
	};
	return %out;
};

my %inv=invert \%func;
for my $label (sort keys %inv){
	print "void $label(){\n";
	my $oldaddr;
	for my $addr (@{$inv{$label}}){
		printf qq!die("unreach","","0x%04x");\n!,$addr if($oldaddr && $oldaddr!=$addr-1);
	    $oldaddr=$addr;

		$cmd=$lines{$addr}[0];
		@arg=@{$lines{$addr}[1] // [] };
		$laddr=sprintf "0x%04x",$addr;
		printf "/* %-10s %-27s sxm=%2d */ ",$func{hex($laddr)},"$cmd @arg",$sxm{$laddr};

		if ($label{$laddr}){
			printf "L%04x: ",$addr ;
		}else{
			printf "%-6s ","";
		};

		if ($cmd ne ""){
			$cmds++;
			my $out="";
			if (defined $cmds{$cmd}){
				$out=$cmds{$cmd};
				if (ref $out eq "CODE"){
					$out=&$out(@arg);
				}else{
					for my $no (0..$#arg){
						$out =~ s/%$no/$arg[$no]/g;
					};
				};
			};
			printf qq!d(0x%x);!,hex $laddr;
			if ($out eq ""){
				print qq!die("missing","$cmd","$laddr");!;
				$broken++;
				$broken{$cmd}++;
			}else{
				$cmdsok++;
				if ($patch{$addr}){
					printf "/* PATCH(%04x) */",$addr;
					$out=~s/goto \w+;/$patch{$addr}/;
				};
				print $out;
			};
		};

		if ($post{$addr}){
			for (@{$post{$addr}}){
				if ($patch{$addr}){
					printf "/* PATCH(%04x) */",$addr;
					$_=~s/goto \w+;/$patch{$addr}/;
				};
				print "$_";
			};
		};
		print "\n";

	};
	print "/* endsub */};\n";
};

printf STDERR "%d/%d lines translated (%4.1f%%)\n",$cmdsok,$cmds,($cmdsok/$cmds)*100;
printf STDERR "(%d lines/%d ops still to translate)\n",$broken,scalar keys %broken;
#for (keys %broken){ print STDERR "- $_\n"; };

