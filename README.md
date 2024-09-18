# gcrsim

Graph Controlled string Rewriting SIMulator. It can be used to simulate the derivation of most common types of regulated rewriting. It was primary developed and heavily used for the simulation of insertion-deletion systems.

## Usage

```
perl gcrsim.pl input_file [steps]
```

This will run the simulator on the input file for the specified number of steps. If the number of steps is not specified, the interactive mode is started.

The result of the simulation is sent to the standard output.