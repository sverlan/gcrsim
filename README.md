# gcrsim

Graph Controlled string Rewriting SIMulator. It can be used to simulate the derivation of most common types of regulated rewriting. It was primary developed and heavily used for the simulation of insertion-deletion systems.

## Usage

```
perl gcrsim.pl input_file [steps]
```

This will run the simulator on the input file for the specified number of steps. If the number of steps is not specified, the interactive mode is started.

The result of the simulation is sent to the standard output.

## Input file syntax

The input file has two sections: Axioms and Rules. It can optionally have a configuration section. Here is an example:
```
# Comments are lines starting with # symbol
# Keywords (section titles) should start at the beginning of the line

# The below section is optional
ConfigFile anbn.cfg

# The axioms section
Axioms

# The list of axioms is in square brackets
#[S,xSy]
[S]

# The rules section
Rules

# Each rule has the form: 
# component,u->v,component

1,S->aS,2

2,S->Sb,1

# lambda is represented by an empty string
1,S->,1

# If component number is not given, it defaults to 1. Hence, the above rule is equivalent to:
# 1,S->
# S->,1
# S->
```

## The output 

The output is a step by step simulation of the corresponding graph-controlled grammar. For the above example (and 3 steps) the result is:

```
========================================
gcrsim simulator v.1.2 (17/09/2024)
Program configuration:
Input file: examples\an_bn_2comp.txt
Configuration file: gcrsim.cfg
Print_skip = "@"; Print_len=16;
Add_skip="@"; Add_skip_len=16
Filter function used: no, History: yes
========================================
The initial configuration (at STEP 0):


Component 1:
S

Component 2:


============
STEP 1
============


Component 1:


Component 2:
aS


============
STEP 2
============


Component 1:
aSb

Component 2:


============
STEP 3
============


Component 1:
ab

Component 2:
aaSb
```

## Configuration file

This file contains the parameters that can affect the simulation behavior. If not given, default values are used. Here is an example of a configuration file:

```
# This file contains parameters for gcrsim
# It uses a Perl format and it is included and evaluated 
# by the main program.
# It contains parameters allowing to tune the simulation

# Tells to use or not the history of seen strings. If turned on,
# strings that were already considered are further ignored.
# There is no reason to turn it off, except for memory consumption reasons.
$history = 1;

# Print the details of rules' application for each step
$show_detailed_application = 1;

# Next two parameters define strings that are not printed to the 
# output. However, these strings are considered by the simulator.

# Do not print strings longer than the below size.
$print_len = 16;

# Do not print strings that match the below regular expression
$print_skip = "\@";  # no skip
#$print_skip = "([a-z]).*\\1";  # skip printing strings with same letter repeated

# Next three parameters define strings that are removed from the next configuration.

# Ignore strings longer than the below size.
$add_skip_len = 16;

# Skip strings that match the below regular expression
$add_skip = "\@";  # no skip
# $add_skip = "(D.*){2}"; # Skip strings having D? repeated two times 

# Next function permits to have a fine-tuning on the strings
# that have to be in the next configuration. It is called on every
# string and if the result is 0, then this string is eliminated. 

# Arguments : string, component
sub filter_next($$){
  my ($s, $c) = @_;

# incrementing the component, as by default it starts from 0
  $c++;

  # If the string match RE below, they are ignored
  # return 0 if /(p.).*\1.*\1/;

  # it is possible to add messages, e.g., when the string
  # is terminal or has the needed form.
  # The below example outputs the string if it is in component 1 and matches the corresponding RE
  print "Terminal string: $s\n" if /^[ab]+$/ and $c==1;

  return 1;
}
```

Then the output is a bit different:

```
========================================
gcrsim simulator v.1.2 (17/09/2024)
Program configuration:
Input file: examples\an_bn_2comp.txt
Configuration file: gcrsim.cfg
Print_skip = "@"; Print_len=16;
Add_skip="@"; Add_skip_len=16
Filter function used: yes, History: yes
========================================
The initial configuration (at STEP 0):


Component 1:
S

Component 2:


============
STEP 1
============

S => aS
S =>

Component 1:


Component 2:
aS


============
STEP 2
============

aS => aSb

Component 1:
aSb

Component 2:


============
STEP 3
============

aSb => aaSb
aSb => ab
Terminal string: ab

Component 1:
ab

Component 2:
aaSb
```