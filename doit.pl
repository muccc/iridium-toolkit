#!/usr/bin/perl
#
# vim:set ts=4 sw=4:

use strict;
use warnings;
use Cwd;
use File::Basename;

my $cpus=6;
my $center;
my $rate;

$|=1;

my $pwd=cwd();
my $pdir="../iridium";
my $verbose;

if ($pdir =~ m!^/!){
	# absolute;
}else{
	$pdir="../".$pdir;
};

my ($gone,$gtwo,$gthree,$gfour);
my $gauto=1;
if ($#ARGV >=0){
	while ($ARGV[0] =~ /^-/){
		if($ARGV[0] eq "-n"){
			shift;
			$cpus=shift;
		}elsif($ARGV[0] eq "-v"){
			shift;
			$verbose=1;
		}else{
			$gone= 1   if $ARGV[0]=~/1/;
			$gtwo= 1   if $ARGV[0]=~/2/;
			$gthree= 1 if $ARGV[0]=~/3/;
			$gfour= 1  if $ARGV[0]=~/4/;
			$gauto=0;
			shift;
		}
	};
};

my $foff=0;
if ($#ARGV >=0){
	if ($ARGV[0] =~ /^\+/){
		($foff=$ARGV[0])=~s/^\+//;
		shift;
	};
};

sub checkrate {
	my $file=shift;
	if($file=~/-([vs])\d+(?:\.|\/|-|$)/){
		if($1 eq "v"){
			$center=1626270833;
			$rate=2000000;
		}elsif($1 eq "s"){
			$center=1626440000;
			$rate=250000;
		}else{
			warn "No idea what center/rate type $1 unknown\n";
		};
	}else{
		warn "No idea what center/rate for $file\n";
	};
};

sub do_stage1{
	my $file=shift;
	checkrate($file);
	my $dir;
	($dir=$file)=~s/\.raw$//;
	system(qq(cd "$dir";$pdir/detector-fft.py -r $rate ../$file));
	if($? != 0){
		warn "system exit: $?: $!";
	};
}

sub do_stage2{
	my $arg=shift;
	checkrate($arg);
	my $dir=dirname($arg);
	my $file=basename($arg);
	my $base=$file;
	$base=~s!\..*?$!!;
	exec(qq(cd "$dir";$pdir/cut-and-downmix-2.py -r $rate -c $center $file $foff| tee ${base}.out |grep ^File));
	die "system exit: $?: $!";
}

sub do_stage3{
	my $arg=shift;
	checkrate($arg);
	my $dir=dirname($arg);
	my $file=basename($arg);
	my $base=$file;
	$base=~s!\..*?$!!;
	exec(qq(cd $dir;$pdir/demod.py -r $rate $file | tee ${base}.demod |grep ^RAW|cut -c 1-77));
	die "system exit: $?: $!";
}

sub do_stage23{
	my $arg=shift;
	checkrate($arg);
	my $dir=dirname($arg);
	my $file=basename($arg);
	my $base=$file;
	$base=~s!\..*?$!!;
	exec(qq(
		cd $dir;
		file=`$pdir/cut-and-downmix-2.py -r $rate -c $center $file $foff| tee ${base}.out |sed -n 's/^output= *//p'`;
		$pdir/demod.py -r $rate \$file |tee \${file%.cut}.demod |grep ^RAW|cut -c 1-77;true
	));
	die "system exit: $?: $!";
};

sub do_stage4{
	my $dir=shift;
	exec(qq(echo -n "A:OK Signals:";grep -h ^RAW $dir/*.demod | grep A:OK |tee $dir.bits |wc -l));
	die "system exit: $?: $!";
}

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
			$run{$pid}=1;
			$arg=~s!.*/!!;
			print "[",scalar keys @processes,"] run: $func $arg ($pid)\n";
		};
	}else{
		print "run: no more tasks to do\n";
	};
};

my @gather;

for my $file (@ARGV){
	my($auto,$one,$two,$three)=($gauto,$gone,$gtwo,$gthree);

	# It's just a single stage2/3 by time id
	if($file =~ /\d+/ && ! -f $file && ! -d $file){
		if($auto){
			print STDERR "auto mode not possible: doing -3\n";
			$three=1;
		};
		if($one){
			print STDERR "-1 not possible here\n";
		};
		my @guess=glob("*/*-${file}.det");
		if($#guess==0){
			$file=$guess[0];
		}elsif($#guess==-1){
			print STDERR "$file matches nothing here\n";
			next;
		}else{
			print STDERR "$file matches (@guess)\n";
			next;
		};
		if($two && $three){
				do_stage23($file);
		}elsif($two){
				do_stage2($file);
		}elsif($three){
				do_stage3($file);
		};
		next;
	};

	# It's ok to use the raw filename or the directory.
	my ($dir);
	if (-f $file && $file =~ /\.raw$/){
		($dir=$file)=~s/\.raw$//;
	}elsif(-d $file or -f "$file.raw"){
		$dir=$file;
		$file.=".raw";
	}else{
		print STDERR "Canonify: no idea about $file\n";
		next;
	};
	if($auto && ! -d $dir ){
			$one=1;
			$auto=0;$two=1;$three=1;
	};
	checkrate($file);
	print "$file uses center=$center, rate=$rate\n";
	if($one){
		if (! -d $dir){
			mkdir($dir);
		};
		do_stage1(basename($file));
	};
	if($auto){ # Make missing s2/s3 files
		my($s1,@s2,$s3);
		for my $sub (glob("$dir/*.det")){
			($s1=$sub)=~s/\..*?$//;
			@s2=glob("$s1-f*.cut");
			if (defined($s2[0])){ #s2 already done
				print "auto: skipping -2: ",basename($sub),"\n" if ($verbose);
				($s3=$s2[0])=~s/\..*?$//;
				if (-f "$s3.data"){				 # s3 also done
					print "auto: skipping -3: ",basename($s2[0]),"\n" if($verbose);
				}else{
					process("do_stage3",$s2[0])
				};
			}else{
				process("do_stage23",$sub);
			};
		};
		push @gather,$dir;
	}elsif($two && $three){
		for my $sub (glob("$dir/*.det")){
			process("do_stage23",$sub);
		}
		push @gather,$dir;
	}elsif($two){
		for my $sub (glob("$dir/*.det")){
			process("do_stage2",$sub);
		};
	}elsif($three){
		for my $sub (glob("$dir/*.cut")){
			process("do_stage3",$sub);
		}
		push @gather,$dir;
	}elsif($gfour){
		push @gather,$dir;
	}
}

for(1..$cpus){
	startone();
}

while($#processes >-1){
	my $pid=wait();

	if ($run{$pid}){
		print "One down, ",scalar(@processes)," to go...\n" if ($verbose);
		delete $run{$pid};
		startone();
	}else{
		print "Unknown child $pid\n";
	};
};

if(scalar keys %run >0){
	print "waiting for: ",join(" ",(keys %run)),"\n";
	while(scalar keys%run >0){
		my $pid=wait();
		if ($run{$pid}){
			delete $run{$pid};
			print "One down, waiting for ",scalar keys %run," more...\n"
				if scalar keys %run;
		}else{
			print "Unknown child $pid\n";
		};
	};
};

if($gfour || $gauto){
	for my $sub (@gather){
		do_stage4($sub);
	};
};
