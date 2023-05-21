# ln-payment
ln-payment is a simulator that works over the lightning network with the aim to provide a global understanding about its functionality as a network and possible improvement to its technology.
The simulator works with LN implementations to validate the route handling.
Once the routes are found, we proceeded to implement the functions of blocking and making payment as final step in the simulation. However, we include a timeout control to cancel the payment in case of an exceeding the time to send a payment


Additional functionality such as describe a graph, query routes, get info, send payment were used from each implementation.
Finally, the simulator takes on account two considerations: one is that the simulations can be performed one at a time (manual 
test), and the other is that simulator can run a set of test (automatic test) from a test file:

Previous to execute the simulator, the reader must fulfill the following [Prerequisites](PREREQUISITES.md) to be able to execute the software properly.

* The section [Libraries](./PREREQUISITES.md#libraries) specifies the several libraries that must be installed beforehand the execution of the simulator
* The section [Proto buffer modules](./PREREQUISITES.md#proto-buffer-modules) describes the wrapper modules required to connect to an LND modules. In case that any module shows up any error, it is advisable to recompile the proto buffer files specified on the **note** of this section
* The section [Additional modules](./PREREQUISITES.md#additional-modules) makes reference to all the modules involved in the simulator and describe its functionality
* The section [Support files](./PREREQUISITES.md#support-files) explains the essential parameters for the proper execution of the simulator. The user must put attention to specific parameters, such us:
    * polar_path on `parameters.json` (partial path to a node on the POLAR app given by /home/**USER**/.polar/networks/**INDEX_POLAR_NETWORK**/volumes/. The highlighted sections on the previous path must be modified according to the unix environment on which the user is testing the simulator, for instance, /home/deic/.polar/networks/1/volumes/)
    * routes on `test.json` (array of routes to perform a query route and their corresponding block and make payment)
    
In addition, to the prerequisites, the user must deploy a network in the POLAR app. The network is necessary since the simulator can connect to the LN implementations (lnd, eclair and c-lightning), to compare the results of their query routes against the implementation of Yen's algorithm. As an example, in the root of the project, we can find the file LN_polar.zip that contains an LN network in which the three implementations are included.

To sum up, the reader must perform the following steps previously to execute the simulator:

1. Download the [ln-payment](https://github.com/StvanLeo/ln-payment.git) GitHub repository
2. Create a python virtual environment on the same folder as the one that contains the GitHub repository
3. Install the required libraries with their corresponding versions
4. Set the values of the configuration parameters, especially **polar_path** and **port** (on: connector/lnd) on `parameters.json`
5. Set the values of the test parameters, especially **routes** and **port** (in lnd/node) on `test.json`
6. Deploy an LN network on Polar
7. Set the LN network with the different scenarios (full connectivity among nodes, partial disconnection of nodes and partial disconnection of channels)
8. Recreate, if necessary, the snapshot file (lnd_describegraph_regtest.json) through the following commands (that connect to a node on Polar) on a terminal:
```sh
  deic@deic:~$ sudo docker exec -it polar-n1-alice /bin/bash
  root@alice:/# su lnd
  $ lncli --network=regtest describegraph
```
* n1 on polar-n1-alice correspond to the index of the Polar network, for example, if it is the fifth network on Polar, the command would include polar-n5-alice

## Test

The following sequence diagram shows the flow of the simulator, but, for a better visualization of the simulation, please refer to [Test](TEST.md) 

>**CAUTION:**
>The following message indicates that the simulator is trying to connect to an LND node to determine its grpc port, it is only a warning message, not an error message  
![#f03c15](https://via.placeholder.com/15/f03c15/000000?text=+) [E0204 20:56:38.633000000  1816 src/core/tsi/ssl_transport_security.cc:1458] Handshake failed with fatal error SSL_ERROR_SSL: error:1000007d:SSL routines:OPENSSL_internal:CERTIFICATE_VERIFY_FAILED.

<!---![Test](http://www.plantuml.com/plantuml/png/XLJ1Sfmm3Btp5RfrSsdlxA59RvrfPZ9DBvtPYu85k34ojKKs_7rbGnZSakaUTW2_z_Ia9xYDWa6cmLLLlgegsyBfcqS31WMX3Nw02pyoZh7tyla6f2U6qqpnfWAetORqhUBO6ugVcXwPoSKBPph2h-WPMkled3WT2HXgSN828mOSI2X4g21f87JsXHXKIT4gGd1YdsebOr6fh8ICp9WtG-WiPajQ8A6-FW0Q4oX6nQvgs-7eW-mVBsLe66LE4iJ6jjNoh_Z2vSPATkwH9tJmWwByDHY0Qs-TYdwdtvCU9xTqXGUS1s85sxY3Pb-F9F22Ji6vkS5FhAm8Lt9E9wjNFjZECY3hn5NIyfojn7CfyZHlq_L14Q9izPQnshcppRmqj2CUcWr-4Zgm2h24SJTQK7oOLsGvWV9NDvwP6W7nQt3dVp7qIeqAWMEp5owHsqgyp_z9_242kiu7A_rGyfTO2rv7ibI2g-AXzsCiEUiIvEmWIfWQcOBwscdc2PQ-wY_EDyzll5rAz_XCvUDIe6onreYRO9y8KeeoZtdxXUBAhGEXoVSVY_TiI_MElJ83s65qb6gYMCzBiFHgTNUhVQmZXTQ78Il2gNNOtRn5gvsJWezppVOkN5OvY7frLMnOOQJGNzqSxqEPuF7PSNRvBRem6WCscrVzwOZzT9pX-wcNuHKRTy1ORrVzU3YBUlZFlYnjuWijCuYfdq1nSiL6hD-pfYTjgF4XQ6oyVXzJT1gS3q86ke1ZVwwY-B6gRfKs3UuF)--->
![Test](http://www.plantuml.com/plantuml/png/ZLInRjmm3Dtz5TnwMThTDpJfLg01WgPBWIoCJP_Lo9GhqRduxqjPP-C8d85gI0BvlSSdyZ7tIJ3ADFYgMlwgAjV1uKV05beKX2w60LxucN5CVP2lTo0zCHncIdSLGEqtPEWKnw6bzANfaPbyUk65Zl0d1OREUJfcpea4MkfmyW8ZHXn8A2Qe86iWdDmxCQYIebM4uC0Xryh6ab9P2GMPCQiXz0wp9JrrHdr_0cpRI2bbR57RFeuXolLrAKF3A7EM86vTLvMVYZSkDrQsyuWyeOTVbCGsHi-vTrv5VzBVIJzdjtI69vm7OWMxj47BgPz9u1szWfV73M5YPIKua_VQMTJhw4wE0LaxhfAEvyLAEbgHrtdhReYA46MhjmMhB_UkcSk3LkAUsHWc8MDrFMKO3wC3nSTvHPeEs5CtWPaQ0Gc0L-Cm6FgWHeN0StijR95R9FRvlua_9K1_qev9FrX-6QlXdKXA9JWh7lem9iif8IYpWoHnQcIAgw-YMJfeVDNVV6ZULjxLb1xnZUor5J1FBBc_x5_fyNMPkdFSvbkuT3YKaEhDTJgAP1cDQKAja2QwLreOCe-qi2d9SQlUH48XG0QS90mehbaGUQLlZRqkX1AZ1VdP_0UmGpHkbDZUP5pQyy11oqLmm-Wfzq_D12uXfG-Nf2YkpaUANOX3SNleF9xkLhyI9rBmJaOLesjZgvZOchqnssAC6FtLpMwsRHhjj_qS0dAhPh5jmItcLN-wnNwzaSSR2GRZVnrMX_ghNDgPxL4lbvToQNT6uWOAqnPjMqTFFTXrMS_-OjYESRkISs_iIA_bx8gOPng8IKx93N93tbhylnxL2T-fJ3jbTv7Iv4tsYqRTzAIZQqACr0XJsdPStnEYK0kdY6D_h9A4iQhkbJOD_Xy0)
```puml
@startuml

start

if (Load data from \nSnapshot?) then (yes)
  :load data of \nnodes/channels\nfrom a json file;
  :get default parameters 
  of a given node;
else (no)
  if (set name of a node) then (alias)
    :set IP address of node;
    :set port of node;
  else (empty)
  endif
endif
:set parameters of node;
if (Manual Test) then (yes)
    while (Request a new Payment) is (yes)
        :Set values of amount as well \nas origin and destiny nodes;
        :Set by default or not \nthe node policy params;
        while (Request a new route) is (yes)
            if (Api query route) then (yes)
                :connect to a node;
                :execute lnd query route;
            else (no)
                :execute Yen's algorithm;
            endif
            :get route with hops;
            :set payment structure;
        endwhile (no)
        :Block payment;
        :Make payment;
    endwhile (no)
else (no)
    if (snapshot) then (no)
      :find the connectors of the nodes;
    else (yes)
    endif
    :describe the type of test;
    if (create an automatic test file) then (yes)
      :create a new test.json file;
    else (no)
    endif
    :read test.json file;
    while (Another implementation) is (exist)
        if (perform test (flag)) then (true)
            :connect to the \nimplementation node;
            while (new route) is (exist)
                :perform query route;
                :get route;
                :set payment structure and \nadd it to queue;
                :block payment;
            endwhile (no exist)
        else (false)
        endif
    endwhile (no exist)
    while (payments) is (exist)
        if (timeout) then (false)
          :make payment;
          if (snapshot) then (no)
            :send payment to implementation;
          else (yes)
          endif
        else (true)
          :cancel payment;
        endif
    endwhile (no exist)
    :save routes to result.json file;
endif
:check correctness of the imported graph;
stop

@enduml
```
