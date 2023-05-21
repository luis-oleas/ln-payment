## Libraries

To get a proper execution of the simulator, it is required to set python version 3.5+. Additionally, it is recommended to create a virtual environment to install the needed libraries to execute the program as follows:

```sh
$ python -m pip install virtualenv  
$ virtualenv venv 
$ source venv/bin/activate 
$ python -m pip install --upgrade pip 
$ python -m pip install grpcio 
```

Therefore, the simulator requires the following libraries with its corresponding versions as well as additional code modules:

| Name             | Version    | Description                                                                                                                                                                                                         |
|------------------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| grpcio           | `1.29`     | library with gRPC tools which include the protocol buffer compiler protoc and the special plugin for generating server and client code from .proto service definitions which are used with rpc_pb2 and rpc_pb2_grpc |
| grpcio-tools     | '1.51.1'   | library that works with grpcio                                                                                                                                                                                      |
| jsonpickle       | `3.0.1`	   | library used to serialize and deserialize complex Python object to and from JSON, which in this case allows to create output files with the test results                                                            |
| numpy            | `1.24.1`   | handles the assignation of random balance with any of the following distributions: beta, exponential, normal, uniform                                                                                               |
| networkx         | `3.0`      | library to create and manipulate the structure of dynamic and complex networks                                                                                                                                      |
| typing-extension | `3.7.4.3`  | library to declare variables of type List                                                                                                                                                                           |
| pylightning      | `0.0.7.3`	 | handles the c-lightning client stub that allows to connect with the node through JSON-RPC protocol                                                                                                                  |
| requests         | `2.10.4`   | library that allows to create HTTPS connections                                                                                                                                                                     |

## Proto buffer modules

The following modules results from the compilation of the proto files **rpc** and **router** which are used as wrappers for connect to lnd modules  

| Name          | Version                                                                                                                                                                                                                                                                                                                                                   |
|---------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| rpc_pb2       | Handles the parameters (channel, pub keys, amounts, etc) used to perform the execution of the methods such as GetChanInfo, QueryRoutes, Describe Graph, among others                                                                                                                                                                                      |
| rpc_pb2_grpc	 | Handles the lnd lightning client stub which is responsible for conversion (marshalling) of parameters (request structure given by rpc_pb2 and metadata-macaroon) used for the node's connection and reconversion of its results passed from the node after execution of any of its methods such as GetChanInfo, QueryRoutes, Describe Graph, among others |

In case the above modules are corrupted or damaged, it is necessary to rebuild the protocol buffer files **rpc.proto** and **router.proto** 


```sh
$ git clone <https://github.com/googleapis/googleapis.git  
$ curl -o rpc.proto -s https://raw.githubusercontent.com/lightningnetwork/lnd/master/lnrpc/rpc.proto 
$ curl -o router.proto -s https://raw.githubusercontent.com/lightningnetwork/lnd/3190437188a5f78bc2730bd0d437f9c42a6b8477/lnrpc/routerrpc/router.proto 
$ cd googleapis 
$ python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. rpc.proto 
$ python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. router.proto
```
>**NOTE:**
>After this process four files **rpc_pb2.py**, **rpc_pb2_grpc.py**, **router_pb2.py** and **router_pb2_grpc.py** will be generated. Copy those four files on the folder ..\LNModel\ln-payment\ln

## Additional modules

| Package | Subpackage |        Module         | Description                                                                                        |
|:-------:|:----------:|:---------------------:|----------------------------------------------------------------------------------------------------|
|   ln    |    ---     |          ---          | root in the structure of the program files                                                         |
|    .    |    -->     |    ln-payment       | module that invokes the functionality of the simulation, i.e. it is the main module in the program |
|    .    |    -->     |         utils         | module that provides with generic methods, functions and classes used along the whole program      |
|    .    |    -->     |    route_payment	     | module with the required structure to create te routes with their hops and the payments            |
|   -->   | connector  |          ---          | sub-path in the structure of the program files                                                     |
|    .    |    -->     |      	lnd_client      | 	module that interacts with lnd nodes                                                              |
|    .    |    -->     |  	clightning_client   | module that interacts c-lightning nodes                                                            |
|    .    |    -->     |    	eclair_client     | module that interacts with eclair nodes                                                            |

## Support files

1. parameters.json
   
|     Key      |   Sub-key   | Description                                                                                                               |
|:------------:|:-----------:|---------------------------------------------------------------------------------------------------------------------------|
|     file     |     ---     | These items contain the name of the snapshots of the different kinds of networks (mainnet, testnet and regtest)           |
|     -->      |   regtest   | file that contains the structure of describe graph of the `regtest` network. File located on folder `data` of the project |
|     -->      |   mainnet   | file that contains the structure of describe graph of the `mainnet` network. File located on folder `data` of the project |
|     -->      |   testnet   | file that contains the structure of describe graph of the `testnet` network. File located on folder `data` of the project |
|  connector   |     ---     | These items contain the required parameters to connect to a specific network (lnd, eclair and c-lightning)                |
|     -->      |     lnd     | parameters to connect to a specific `lnd` node. This is used to test routes through a given node alias                    |
|     -->      |   eclair    | parameters to connect to a specific `eclair` node. This is used to test routes through a given node alias                 |
|     -->      | c-lightning | parameters to connect to a specific `eclightning` node. This is used to test routes through a given node alias            |
|     loop     |     ---     | number of repetitions executed of query route implementation over the same couple of nodes                                |
|    num_k     |     ---     | number of routes to gather by means of the Yen's algorithm                                                                |
|    sleep     |     ---     | seconds that the simulator halts previous to continue with a payment                                                      |                                                      
|    update    |     ---     | parameter considered for a future implementation                                                                          |                                                    
|  num_routes  |     ---     | number of routes to simulate query routes that will be considered at the time to create a test.json file                  |    
|  max_amount  |     ---     | max payment amount to send to a destiny node                                                                              |   
| step_diff_ns |     ---     | increment in nanoseconds at the moment to calculate a timeout. Default 0.5 seconds                                        |                   
| min_diff_ns  |     ---     | nanoseconds specifying at which position to start. Default 1 second                                                       |                  
| max_diff_ns  |     ---     | nanoseconds specifying at which position to start. Default 2.5 seconds                                                    |                 
|  test_file   |     ---     | name of the json file that contains the test set                                                                          |                
| results_file |     ---     | name of the json file that contains the results of the tests. `Deprecated`                                                |               
|  polar_path  |     ---     | Parameter that helps to configure the connection to a node LND                                                            |              

1. test.json

| Key                      | Sub-key | Parameters                                                                 |
|--------------------------|---------|----------------------------------------------------------------------------|
| lnd, eclair, c-lightning | ---     | Parameters to test both Yen's algorithm, and the LN implementations        |
| -->                      | flag    | flag that specifies whether the simulator test that implementation or not  |
| -->                      | node    | name of the node over which the simulator will connect to perform the test |
| -->                      | routes  | pub key origin node, pub key destiny node, payment amount                  |
