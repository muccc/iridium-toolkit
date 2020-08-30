#!/usr/bin/env -S perl -n

/^(class|def) / && do {
	do {
		print;
		$_=<>;
	} while (defined($_) && $_ =~ /^(\s|#|$)/ );
	redo;
};

/^[a-z][a-z0-9_]*\s*=/i && do {print};
/^(import|from|#!|$)/ && do {print};
