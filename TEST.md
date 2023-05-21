# TEST

## Load data from Snapshot
* The simulator will load data from lnd_describegraph_regtest.json

    ![Alt text](./figs/snapshot.png?raw=true "Load from Snapshot")

## Load data from a LND node

* The simulator can load data from a node by specifying a macaroon and cert dir or name of a node

    * Macaroon and cert dir
    
        ![Alt text](./figs/lnd_path.png?raw=true "Macaroon and cert dir")

    * Name of a node
    
        ![Alt text](./figs/lnd_node.png?raw=true "Macaroon and cert dir")

## Type of test

* There are two types of test on the simulator: the first one is manual test in which the user specifies the parameter values for the query route, the second one executes query routes with data from a test file

    * Manual test
    
        ![Alt text](./figs/manual_test.png?raw=true "Manual test")
      
    * Automatic test

        ![Alt text](./figs/automatic_test.png?raw=true "Automatic test")
    
        * Result from automatic test
    
          ![Alt text](./figs/result_test_file.png?raw=true "Result test file")

## Checking accuracy of the simulator

* Once the simulation is finished, it checks that the balance of the channels is even
    ![Alt text](./figs/result_test.png?raw=true "Channels balance checked")