#!/usr/bin/perl
#
# vim:set ts=4 sw=4:

use strict;
use warnings;
use Cwd;
use File::Basename;

my $cpus=4;

my $pwd=cwd();
my $pdir="../iridium";

if ($pdir =~ m!^/!){
	# absolute;
}else{
	$pdir="../".$pdir;
};

my ($one,$two,$three);
my $auto=1;
if ($#ARGV >=0){
	if ($ARGV[0] =~ /^-/){
		$one= 1 if $ARGV[0]=~/1/;
		$two= 1 if $ARGV[0]=~/2/;
		$three= 1 if $ARGV[0]=~/3/;
		$auto=0;
		shift;
	};
};

my $foff=0;
if ($#ARGV >=0){
	if ($ARGV[0] =~ /^\+/){
		($foff=$ARGV[0])=~s/^\+//;
		shift;
	};
};

sub do_stage1{
	my $file=shift;
	my $dir;
	($dir=$file)=~s/\.raw$//;
	system(qq(cd "$dir";$pdir/detector-fft.py ../$file));
	if($? != 0){
		if($! !~ /Not a directory/){
			warn "system exit: $?: $!";
		};
	};
};

sub do_stage2{
	my $arg=shift;
	my $dir=dirname($arg);
	my $file=basename($arg);
	system(qq(cd "$dir";$pdir/cut-and-downmix-2.py $file $foff| tee -a cut-output |grep ^File));
	if($? != 0){
		if($! !~ /Not a directory/){
			die "system exit: $?: $!";
		};
	};
};
sub do_stage3{
	my $arg=shift;
	my $dir=dirname($arg);
	my $file=basename($arg);
	system(qq(cd $dir;$pdir/demod.py $file | tee -a demod-output |grep ^RAW));
	if($? != 0){
		if($! !~ /Not a directory/){
			die "system exit: $?: $!";
		};
	};
};
sub do_stage23{
	my $arg=shift;
	my $dir=dirname($arg);
	my $file=basename($arg);
	system(qq(
		cd $dir;
		file=`$pdir/cut-and-downmix-2.py $file $foff| tee .${file}.cut |grep ^output=|cut -d= -f2|cut -c 2-`;
		echo stage2=\$file;
		$pdir/demod.py \$file |tee .\$file.demod | grep RAW;true
	));
	if($? != 0){
		if($! !~ /Not a directory/){
			die "system exit: $?: $!";
		};
	};
};

sub auto_stage23{
	my $file=shift;
	my $out;
	($out=$file)=~s/\.det//;
	my @out=<$out-f*.cut>;
	if ($#out==0){
		print "auto: skipping -2 $file\n";
		my $s3;
		($s3=$out[0])=~s/\.cut$/.samples/;
		if ( -f $s3){
			print "auto: skipping -3 $out[0]\n";
		}else{
			process("do_stage3",$out[0]);
		};
	}else{
		process("do_stage23",$file);
	};
};

my @processes;
sub process{
	push @processes,[@_];
};

our %run;
sub startone{
	if ($#processes >-1){
		my @task=@{shift @processes};
		my ($func,$arg)=($task[0],$task[1]);
#		shift(@task); shift(@task);
		{ no strict 'refs';
			my $pid=fork();
			if($pid==0){
				no strict 'refs';
				$func->($arg);
				exit(0);
			};
			print "run: $func $arg ($pid)\n";
			$run{$pid}=1;
		};
	};
};

sub sigchld {
	my $pid=wait();
#	print "pid:$pid\n";
	if ($run{$pid}){
		print "One down, ",scalar(@processes)," to go...\n";
		delete $run{$pid};
		startone();
	};
};
$SIG{CHLD}='sigchld';

for my $file (@ARGV){
	if($file =~ /\d+/ && ! -f $file && ! -d $file){
		my @guess=glob("*/*-${file}.det");
		if($#guess==0){
			$file=$guess[0];
		}elsif($#guess==-1){
			print STDERR "$file matches nothing here\n";
		}else{
			print STDERR "$file matches @guess\n";
		};
	};
	if ($auto){
		my $dir;
		if ($file =~ /\.raw$/){
			($dir=$file)=~s/\.raw$//;
			if ( ! -d $dir){
				mkdir($dir);
				do_stage1(basename($file));
			}else{
				print "auto: skipping 1 $file\n";
			};
			$file=$dir;
		};
		if ( -d $file ) {
			for my $sub (<$file/*.det>){
				auto_stage23($sub);
			};
		}elsif( -f "$file" ) {
			if ($file =~ /\.det$/){
				process("do_stage23",$file);
			}elsif($file =~ /\.cut$/){
				process("do_stage3",$file);
			}else{
				print STDERR "auto: no idea what to do with file: $file\n";
			};
		}else{
			print STDERR "auto: no idea what to do with $file\n";
		};
	}else{ # no auto
		if($one){
			if ($file =~ /\.raw$/){
				my $dir;
				($dir=$file)=~s/\.raw$//;
				if ( ! -d $dir){
					mkdir($dir);
				};
				do_stage1(basename($file));
				$file=$dir;
			}else{
				print STDERR "-1 set, but no idea what $file is\n";
			};
		};
		if($two && $three){
			if( -f $file){
				process("do_stage23",$file);
			}elsif( -d $file){
				for my $sub (<$file/*.det>){
					process("do_stage23",$sub);
				};
			}else{
				print STDERR "-23 set, but no idea what $file is\n";
			};
		}elsif($two){
			if( -f $file){
				process("do_stage2",$file);
			}elsif( -d $file){
				for my $sub (<$file/*.det>){
					process("do_stage2",$sub);
				};
			}else{
				print STDERR "-2 set, but no idea what $file is\n";
			};
		}elsif($three){
			if( -f $file){
				process("do_stage3",$file);
			}elsif( -d $file){
				for my $sub (<$file/*.cut>){
					process("do_stage3",$sub);
				};
			}else{
				print STDERR "-3 set, but no idea what $file is\n";
			};
		};
	};
};

for(1..$cpus){
	startone();
};

while($#processes >-1){
	sleep(1);
};

print "waiting for: ",(keys %run),"\n";

while(scalar keys%run >0){
	sleep(1);
};
