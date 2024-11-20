use strict;
use warnings;

my $version = 1.10;
my $version_date = "17/09/2024";

my @current = (); 
my @next =();
my @rules=();
my @hist=();

sub apply($$$);
sub filter($$);
sub print_conf(@);
sub read_system($);
sub rhs_escape($);
sub escape($);
sub unescape($);

my $configName = "gcrsim.cfg";

# important parameters
#
# 1. remember strings that were already considered
our $history = 1;
#
# 2. skip RE and skip len for printing
our $print_skip = "@";  # no skip
our $print_len = 16;

# 3. skip RE and skip len for adding to next configuration
our $add_skip = "@";  # no skip
our $add_skip_len = 16;

# 4. print detailed rule application
our $show_detailed_application = 0;


#my $input_file;

# Adding the current directory to the include path
push @INC, ".";


my ($input_file, $run_steps) = @ARGV;
my $interactive = 1;

# Retrieving the input file name (either as argv[0] or from the user input)
if (not defined $input_file) {
  print "Enter input file name: ";
  $input_file = <>;
  chomp $input_file;
}

# Retrieving the number of steps to run
if (defined $run_steps) {
  $interactive = 0;
  $run_steps = int($run_steps);
  die "Bad number of steps: $run_steps !\n" if $run_steps < 0;
}


die "Bad input filename: $input_file !\n" unless  -e $input_file;

# Reading the system from the input file
read_system($input_file);

# If the configuration file is given, we read it (as a perl script)
if (-e "$configName") {require $configName;}
else {$configName="Bad config file ($configName). Using default.";}

# checking if a user filter function (called filter_next) is given
my $str_defined_filter = "yes";
unless (defined(&filter_next)) {
  eval "sub filter_next(\$\$){ return 1;}";
  $str_defined_filter="no";
}


# Starting the main program

# Autoflush on
$|=1;

my $str_hist = "no";
$str_hist="yes" if $history; 

print "\n\n========================================\n";
print "gcrsim simulator v.$version ($version_date)\n";
print "Program configuration:\n";
print "Input file: $input_file\n";
print "Configuration file: $configName\n";
print "Print_skip = \"$print_skip\"; Print_len=$print_len;\n";
print "Add_skip=\"$add_skip\"; Add_skip_len=$add_skip_len\n";
print "Filter function used: $str_defined_filter, History: $str_hist\n";
print "========================================\n";
print "The initial configuration (at STEP 0):\n\n";

print_conf(@current);

if ($interactive) {
  print "Press any key for next or q for quit\n";
  my $a  = <STDIN>;
  chomp $a;
  exit if $a eq "q";
}

# Main loop

my $step=1;

exit if $run_steps == 0;

do{

  print "\n\n============\n";
  print "STEP $step\n";
  print "============\n\n";

  $step++;

  # Apply all rules to all strings
  for (my $i=0; $i<@current; $i++) {
    foreach my $s (@{$current[$i]}) {
      foreach my $r (@{$rules[$i]}) {
         push @ {$next[@{$r}[2]]}, apply $s, @{$r}[0], @{$r}[1];
      }
    }
  }

  # Filter out strings according to filter rules
  for (my $i=0; $i<@current; $i++) {
   @{$current[$i]} = filter $next[$i],$i;
   $next[$i] = ();
  }

  print_conf @current;

  if ($interactive) {
     print "Press any key for next or q for quit\n";
     my $a  = <STDIN>;
     chomp $a;
     exit if $a eq "q";
  } else {
     exit if $run_steps < $step;
  }
} while (1);


sub apply($$$){
  my ($s, $from, $to) = @_;
  my @res = ();
  # We may have several matches, so we loop
#  while ($s =~m/($from)/g)
#  {
#    push @res, "$`$to$'";
#  } 

# new version with substitution
  my $dst = 'push @res,$`."'.$to.'".$\'';

  my $xs = $s;
  $s =~ s/$from/$dst/gee;
  if ($show_detailed_application) {
     print "$xs => @res\n" if $xs ne $s;
  }
  return @res;
}


# Filters strings for the next step
# uses: duplicata, length, RE and custom function
sub filter($$){
  # Arguments : next step strings, next component
  my ($n,$c)=@_;
  my %h=();
  my $seen = \%h;
  if($history) {
    %{$hist[$c]} = () unless defined $hist[$c];
    $seen = $hist[$c];
  };
  my @u=();
  @u = grep { ! $$seen{$_} ++ &&  # Duplicata
                length($_)<=$add_skip_len && # length
				!/$add_skip/ && # RE
				filter_next($_,$c) # Custom function
			} @{$n};
  return @u;
}


sub print_conf(@){
  my (@conf) = @_;
  my $m=1;
  for(my $m=0; $m<@conf; $m++) {
    print "\nComponent ",$m+1,":\n";
    # for debug
    #	print $#{$conf[$m]}+1,"\n" if defined @{$conf[$m]};
    foreach my $s (@{$conf[$m]}) {
	  # print $s unless it fits RE or size limit
	  #unquote
	 # $s=~ s/\\(.)/$1/g;
      print  "$s\n" unless $s=~/$print_skip/ || length($s)>$print_len;
	}  
  }
}

sub read_system($){
  my ($f) = @_;
  open F,$f;

  my $ri =0;
  my $max=0;
  my $readr = 0;
  while (<F>){
    chomp ;
    s/\s//g;
	# Disabled in 1.8
	# Consider # as comment only if preceded by space
    #s/[ ]#.*$//;
	# // is also a comment
    s/\/\/.*$//;
    next if /^$/;
	# Consider # as a comment at the beginning of the line
    next if /^#/;
    next if /^\/\//;
    next if /^Axioms/i;
	if (/^ConfigFile(.*)/i){
	  $configName = $1;
	  next;
	}
    if (/^Rules/i) {
      $readr = 1;
	  next;
    }
    if (!$readr) {
      if (/\[(.*)\]/) {
  	    s/\[|\]//g;
        @{$current[$ri++]} = split /,/ ;
	  }	
    } else {
	   # Disabled in 1.7
       #s/@//;
	   # match a rule
       my ($from,$lhs,$rhs,$to) = 
                 / (?:(\d*),)?                       # eventual component number
			       ([^-]*)                           # lhs: string
				  ->
                   ([^,]*)                           # rhs: string
				   (?:,(\d*))?                       # eventual component number
				  /x;                

		# get component number
		$to = 1 if !defined $to or $to eq "";
        $from = 1 if !defined $from or $from eq "";
        $to--; $from--;

        # Add rule

        # precompile pattern
        my $patt = escape $lhs;
        push @{$rules[$from]}, [qr/$patt/, rhs_escape $rhs, $to]; 	
#print $lhs."->".$rhs."\n";		
		
       # find the maximal component
       $max = $to if $to > $max; 
	   $max = $from if $from > $max; 
    }
  }
 
  for (my $i=$ri; $i<=$max; $i++) { @{$current[$i]} = (); }
  if ($history) {
    for (my $i=0; $i<=$max; $i++) {
	  foreach my $s (@{$current[$i]}) {$hist[$i]{$s}=1;}  
	}; 
  }	
  @next = ();
  close F;
}

sub rhs_escape($){
 ($a) = @_;
 $a =~ s/\$(?!\$\d|\d)/\\\$/g;   #single unescaped $ is escaped
 $a =~ s/\$\$(?=\d)/\$/g;          #double $ followed by num is transformed to 1 $
 #print $a."\n";
 return $a;
}

sub escape($){
($a) = @_;
#  $a=~s/\\/\\\\/g;
  $a=~s/\$/\\\$/g;
  $a=~s/\@/\\\@/g;
  $a=~s/\%/\\\%/g;
  $a=~s/\#/\\\#/g;
  $a=~s/\'/\\\'/g;
 # $a=~s/\-/\\\-/g;
  return $a;
}

sub unescape($){
($a) = @_;
  $a=~s/\\\$/\$/g;
  $a=~s/\\\@/\@/g;
  $a=~s/\\\%/\%/g;
  $a=~s/\\\#/\#/g;
  $a=~s/\\\'/\'/g;
#  $a=~s/\\\-/\-/g;
  $a=~s/\\\\/\\/g;
  return $a;
}

#######################
#   History of changes
#	1.10 (28/08/2024):
#		 - Cleaning up the code
#		 - Moving the code to GitHub
#
#   1.9 (29/03/2023):
#		 - Added $show_detailed_application to simplify the track of applications
#
#   1.8.2 (25/12/2019):
#        - Added push @INC,"." for WSL execution.
#
#   1.8.1 (08/01/2017):
#        - Small bug fixes.
#
#   1.8 (06/01/2017):
#
#        - New matching procedure allowing some regexp substitutions (e.g. (.) -> _$$1_ ). The support for {} from 1.7 is dropped.
#          $ is automatically quoted and $$ is transformed to $.
#        - # is comment only at the beginning of the line
#
#   1.7 (21/12/2016):
#        - Added support for symbol lists in rules (ex: 2,x{a,b}y->z{c,d}t,1 expands to 4 rules). 
#          Limitations: only one substitution per side (lhs rhs) is performed.
#          The empty list at rhs implies the use of the matched symbol from the other side
#          Attention, use only one rule per line.
#        - Removed the alias of @ to \lambda 
#		 - Redefining the role of # as comment: now it should be either at the beginning of the line or be preceded by space
#
#   1.6 (17/12/2016):
#        - Bug fixes for special symbols support
#
#   1.5 (15/12/2016):
#        - Added support for some special symbols in rules
#          
#   1.4 (21/12/2009):
#        - Can indicate the config file to use in the input file (Keyword: ConfigFile) 
#          
#    1.3 (14/12/2009): 
#          - Added tracking of strings: a string that appeared before 
#             is not filtered any more
#          - Custom filter function now the second argument which is the number of the component
#
#    1.2 (06/12/2009): 
#           - Did use strict compatibility
#           - Added the possibility to have a custom filter function