# Front Matter

_Source: PDF pages 1-12; extracted PDF pages 1-12._

---

<a id="page-1"></a>

<!-- Page 1 of 888 -->

CONTENTS
PREFACE xix
## 1 Introduction 1
### 1.1 USES OF COMPUTER NETWORKS, 3
#### 1.1.1 Business Applications, 3
#### 1.1.2 Home Applications, 6
#### 1.1.3 Mobile Users, 10
#### 1.1.4 Social Issues, 14
### 1.2 NETWORK HARDWARE, 17
#### 1.2.1 Personal Area Networks, 18
#### 1.2.2 Local Area Networks, 19
#### 1.2.3 Metropolitan Area Networks, 23
#### 1.2.4 Wide Area Networks, 23
#### 1.2.5 Internetworks, 28
### 1.3 NETWORK SOFTWARE, 29
#### 1.3.1 Protocol Hierarchies, 29
#### 1.3.2 Design Issues for the Layers, 33
#### 1.3.3 Connection-Oriented Versus Connectionless Service, 35
#### 1.3.4 Service Primitives, 38
#### 1.3.5 The Relationship of Services to Protocols, 40
### 1.4 REFERENCE MODELS, 41
#### 1.4.1 The OSI Reference Model, 41
#### 1.4.2 The TCP/IP Reference Model, 45
#### 1.4.3 The Model Used in This Book, 48



---

<a id="page-2"></a>

<!-- Page 2 of 888 -->

viii CONTENTS
#### 1.4.4 A Comparison of the OSI and TCP/IP Reference Models*, 49
#### 1.4.5 A Critique of the OSI Model and Protocols*, 51
#### 1.4.6 A Critique of the TCP/IP Reference Model*, 53
### 1.5 EXAMPLE NETWORKS, 54
#### 1.5.1 The Internet, 54
#### 1.5.2 Third-Generation Mobile Phone Networks*, 65
#### 1.5.3 Wireless LANs: 802.11*, 70
#### 1.5.4 RFID and Sensor Networks*, 73
### 1.6 NETWORK STANDARDIZATION*, 75
#### 1.6.1 Who's Who in the Telecommunications World, 77
#### 1.6.2 Who's Who in the International Standards World, 78
#### 1.6.3 Who's Who in the Internet Standards World, 80
### 1.7 METRIC UNITS, 82
### 1.8 OUTLINE OF THE REST OF THE BOOK, 83
### 1.9 SUMMARY, 84
## 2 The Physical Layer 89
### 2.1 THE THEORETICAL BASIS FOR DATA COMMUNICATION, 90
#### 2.1.1 Fourier Analysis, 90
#### 2.1.2 Bandwidth-Limited Signals, 90
#### 2.1.3 The Maximum Data Rate of a Channel, 94
### 2.2 GUIDED TRANSMISSION MEDIA, 95
#### 2.2.1 Magnetic Media, 95
#### 2.2.2 Twisted Pairs, 96
#### 2.2.3 Coaxial Cable, 97
#### 2.2.4 Power Lines, 98
#### 2.2.5 Fiber Optics, 99
### 2.3 WIRELESS TRANSMISSION, 105
#### 2.3.1 The Electromagnetic Spectrum, 105
#### 2.3.2 Radio Transmission, 109
#### 2.3.3 Microwave Transmission, 110
#### 2.3.4 Infrared Transmission, 114
#### 2.3.5 Light Transmission, 114


---

<a id="page-3"></a>

<!-- Page 3 of 888 -->

CONTENTS ix
### 2.4 COMMUNICATION SATELLITES*, 116
#### 2.4.1 Geostationary Satellites, 117
#### 2.4.2 Medium-Earth Orbit Satellites, 121
#### 2.4.3 Low-Earth Orbit Satellites, 121
#### 2.4.4 Satellites Versus Fiber, 123
### 2.5 DIGITAL MODULATION AND MULTIPLEXING, 125
#### 2.5.1 Baseband Transmission, 125
#### 2.5.2 Passband Transmission, 130
#### 2.5.3 Frequency Division Multiplexing, 132
#### 2.5.4 Time Division Multiplexing, 135
#### 2.5.5 Code Division Multiplexing, 135
### 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK, 138
#### 2.6.1 Structure of the Telephone System, 139
#### 2.6.2 The Politics of Telephones, 142
#### 2.6.3 The Local Loop: Modems, ADSL, and Fiber, 144
#### 2.6.4 Trunks and Multiplexing, 152
#### 2.6.5 Switching, 161
### 2.7 THE MOBILE TELEPHONE SYSTEM*, 164
#### 2.7.1 First-Generation (coco1G) Mobile Phones: Analog Voice, 166
#### 2.7.2 Second-Generation (2G) Mobile Phones: Digital Voice, 170
#### 2.7.3 Third-Generation (3G) Mobile Phones: Digital Voice and Data, 174
### 2.8 CABLE TELEVISION*, 179
#### 2.8.1 Community Antenna Television, 179
#### 2.8.2 Internet over Cable, 180
#### 2.8.3 Spectrum Allocation, 182
#### 2.8.4 Cable Modems, 183
#### 2.8.5 ADSL Versus Cable, 185
### 2.9 SUMMARY, 186
## 3 The Data Link Layer 193
### 3.1 DATA LINK LAYER DESIGN ISSUES, 194
#### 3.1.1 Services Provided to the Network Layer, 194
#### 3.1.2 Framing, 197
#### 3.1.3 Error Control, 200
#### 3.1.4 Flow Control, 201


---

<a id="page-4"></a>

<!-- Page 4 of 888 -->

x CONTENTS
### 3.2 ERROR DETECTION AND CORRECTION, 202
#### 3.2.1 Error-Correcting Codes, 204
#### 3.2.2 Error-Detecting Codes, 209
### 3.3 ELEMENTARY DATA LINK PROTOCOLS, 215
#### 3.3.1 A Utopian Simplex Protocol, 220
#### 3.3.2 A Simplex Stop-and-Wait Protocol for an Error-Free Channel, 221
#### 3.3.3 A Simplex Stop-and-Wait Protocol for a Noisy Channel, 222
### 3.4 SLIDING WINDOW PROTOCOLS, 226
#### 3.4.1 A One-Bit Sliding Window Protocol, 229
#### 3.4.2 A Protocol Using Go-Back-N, 232
#### 3.4.3 A Protocol Using Selective Repeat, 239
### 3.5 EXAMPLE DATA LINK PROTOCOLS, 244
#### 3.5.1 Packet over SONET, 245
#### 3.5.2 ADSL (Asymmetric Digital Subscriber Loop), 248
### 3.6 SUMMARY, 251
## 4 The Medium Access Control Sublayer 257
### 4.1 THE CHANNEL ALLOCATION PROBLEM, 258
#### 4.1.1 Static Channel Allocation, 258
#### 4.1.2 Assumptions for Dynamic Channel Allocation, 260
### 4.2 MULTIPLE ACCESS PROTOCOLS, 261
#### 4.2.1 ALOHA, 262
#### 4.2.2 Carrier Sense Multiple Access Protocols, 266
#### 4.2.3 Collision-Free Protocols, 269
#### 4.2.4 Limited-Contention Protocols, 274
#### 4.2.5 Wireless LAN Protocols, 277
### 4.3 ETHERNET, 280
#### 4.3.1 Classic Ethernet Physical Layer, 281
#### 4.3.2 Classic Ethernet MAC Sublayer Protocol, 282
#### 4.3.3 Ethernet Performance, 286
#### 4.3.4 Switched Ethernet, 288


---

<a id="page-5"></a>

<!-- Page 5 of 888 -->

CONTENTS xi
#### 4.3.5 Fast Ethernet, 290
#### 4.3.6 Gigabit Ethernet, 293
#### 4.3.7 10-Gigabit Ethernet, 296
#### 4.3.8 Retrospective on Ethernet, 298
### 4.4 WIRELESS LANS, 299
#### 4.4.1 The 802.11 Architecture and Protocol Stack, 299
#### 4.4.2 The 802.11 Physical Layer, 301
#### 4.4.3 The 802.11 MAC Sublayer Protocol, 303
#### 4.4.4 The 802.11 Frame Structure, 309
#### 4.4.5 Services, 311
### 4.5 BROADBAND WIRELESS*, 312
#### 4.5.1 Comparison of 802.16 with 802.11 and 3G, 313
#### 4.5.2 The 802.16 Architecture and Protocol Stack, 314
#### 4.5.3 The 802.16 Physical Layer, 316
#### 4.5.4 The 802.16 MAC Sublayer Protocol, 317
#### 4.5.5 The 802.16 Frame Structure, 319
### 4.6 BLUETOOTH*, 320
#### 4.6.1 Bluetooth Architecture, 320
#### 4.6.2 Bluetooth Applications, 321
#### 4.6.3 The Bluetooth Protocol Stack, 322
#### 4.6.4 The Bluetooth Radio Layer, 324
#### 4.6.5 The Bluetooth Link Layers, 324
#### 4.6.6 The Bluetooth Frame Structure, 325
### 4.7 RFID*, 327
#### 4.7.1 EPC Gen 2 Architecture, 327
#### 4.7.2 EPC Gen 2 Physical Layer, 328
#### 4.7.3 EPC Gen 2 Tag Identification Layer, 329
#### 4.7.4 Tag Identification Message Formats, 331
### 4.8 DATA LINK LAYER SWITCHING, 332
#### 4.8.1 Uses of Bridges, 332
#### 4.8.2 Learning Bridges, 334
#### 4.8.3 Spanning Tree Bridges, 337
#### 4.8.4 Repeaters, Hubs, Bridges, Switches, Routers, and Gateways, 340
#### 4.8.5 Virtual LANs, 342
### 4.9 SUMMARY, 349


---

<a id="page-6"></a>

<!-- Page 6 of 888 -->

xii CONTENTS
## 5 The Network Layer 355
### 5.1 NETWORK LAYER DESIGN ISSUES, 355
#### 5.1.1 Store-and-Forward Packet Switching, 356
#### 5.1.2 Services Provided to the Transport Layer, 356
#### 5.1.3 Implementation of Connectionless Service, 358
#### 5.1.4 Implementation of Connection-Oriented Service, 359
#### 5.1.5 Comparison of Virtual-Circuit and Datagram Networks, 361
### 5.2 ROUTING ALGORITHMS, 362
#### 5.2.1 The Optimality Principle, 364
#### 5.2.2 Shortest Path Algorithm, 366
#### 5.2.3 Flooding, 368
#### 5.2.4 Distance Vector Routing, 370
#### 5.2.5 Link State Routing, 373
#### 5.2.6 Hierarchical Routing, 378
#### 5.2.7 Broadcast Routing, 380
#### 5.2.8 Multicast Routing, 382
#### 5.2.9 Anycast Routing, 385
#### 5.2.10 Routing for Mobile Hosts, 386
#### 5.2.11 Routing in Ad Hoc Networks, 389
### 5.3 CONGESTION CONTROL ALGORITHMS, 392
#### 5.3.1 Approaches to Congestion Control, 394
#### 5.3.2 Traffic-Aware Routing, 395
#### 5.3.3 Admission Control, 397
#### 5.3.4 Traffic Throttling, 398
#### 5.3.5 Load Shedding, 401
### 5.4 QUALITY OF SERVICE, 404
#### 5.4.1 Application Requirements, 405
#### 5.4.2 Traffic Shaping, 407
#### 5.4.3 Packet Scheduling, 411
#### 5.4.4 Admission Control, 415
#### 5.4.5 Integrated Services, 418
#### 5.4.6 Differentiated Services, 421
### 5.5 INTERNETWORKING, 424
#### 5.5.1 How Networks Differ, 425
#### 5.5.2 How Networks Can Be Connected, 426
#### 5.5.3 Tunneling, 429


---

<a id="page-7"></a>

<!-- Page 7 of 888 -->

CONTENTS xiii
#### 5.5.4 Internetwork Routing, 431
#### 5.5.5 Packet Fragmentation, 432
### 5.6 THE NETWORK LAYER IN THE INTERNET, 436
#### 5.6.1 The IP Version 4 Protocol, 439
#### 5.6.2 IP Addresses, 442
#### 5.6.3 IP Version 6, 455
#### 5.6.4 Internet Control Protocols, 465
#### 5.6.5 Label Switching and MPLS, 470
#### 5.6.6 OSPF-An Interior Gateway Routing Protocol, 474
#### 5.6.7 BGP-The Exterior Gateway Routing Protocol, 479
#### 5.6.8 Internet Multicasting, 484
#### 5.6.9 Mobile IP, 485
### 5.7 SUMMARY, 488
## 6 The Transport Layer 495
### 6.1 THE TRANSPORT SERVICE, 495
#### 6.1.1 Services Provided to the Upper Layers, 496
#### 6.1.2 Transport Service Primitives, 498
#### 6.1.3 Berkeley Sockets, 500
#### 6.1.4 An Example of Socket Programming: An Internet File Server, 503
### 6.2 ELEMENTS OF TRANSPORT PROTOCOLS, 507
#### 6.2.1 Addressing, 509
#### 6.2.2 Connection Establishment, 512
#### 6.2.3 Connection Release, 517
#### 6.2.4 Error Control and Flow Control, 522
#### 6.2.5 Multiplexing, 527
#### 6.2.6 Crash Recovery, 527
### 6.3 CONGESTION CONTROL, 530
#### 6.3.1 Desirable Bandwidth Allocation, 531
#### 6.3.2 Regulating the Sending Rate, 535
#### 6.3.3 Wireless Issues, 539
### 6.4 THE INTERNET TRANSPORT PROTOCOLS: UDP, 541
#### 6.4.1 Introduction to UDP, 541
#### 6.4.2 Remote Procedure Call, 543
#### 6.4.3 Real-Time Transport Protocols, 546


---

<a id="page-8"></a>

<!-- Page 8 of 888 -->

xiv CONTENTS
### 6.5 THE INTERNET TRANSPORT PROTOCOLS: TCP, 552
#### 6.5.1 Introduction to TCP, 552
#### 6.5.2 The TCP Service Model, 553
#### 6.5.3 The TCP Protocol, 556
#### 6.5.4 The TCP Segment Header, 557
#### 6.5.5 TCP Connection Establishment, 560
#### 6.5.6 TCP Connection Release, 562
#### 6.5.7 TCP Connection Management Modeling, 562
#### 6.5.8 TCP Sliding Window, 565
#### 6.5.9 TCP Timer Management, 568
#### 6.5.10 TCP Congestion Control, 571
#### 6.5.11 The Future of TCP, 581
### 6.6 PERFORMANCE ISSUES*, 582
#### 6.6.1 Performance Problems in Computer Networks, 583
#### 6.6.2 Network Performance Measurement, 584
#### 6.6.3 Host Design for Fast Networks, 586
#### 6.6.4 Fast Segment Processing, 590
#### 6.6.5 Header Compression, 593
#### 6.6.6 Protocols for Long Fat Networks, 595
### 6.7 DELAY-TOLERANT NETWORKING*, 599
#### 6.7.1 DTN Architecture, 600
#### 6.7.2 The Bundle Protocol, 603
### 6.8 SUMMARY, 605
## 7 The Application Layer 611
### 7.1 DNS-THE DOMAIN NAME SYSTEM, 611
#### 7.1.1 The DNS Name Space, 612
#### 7.1.2 Domain Resource Records, 616
#### 7.1.3 Name Servers, 619
### 7.2 ELECTRONIC MAIL*, 623
#### 7.2.1 Architecture and Services, 624
#### 7.2.2 The User Agent, 626
#### 7.2.3 Message Formats, 630
#### 7.2.4 Message Transfer, 637
#### 7.2.5 Final Delivery, 643


---

<a id="page-9"></a>

<!-- Page 9 of 888 -->

CONTENTS xv
### 7.3 THE WORLD WIDE WEB, 646
#### 7.3.1 Architectural Overview, 647
#### 7.3.2 Static Web Pages, 662
#### 7.3.3 Dynamic Web Pages and Web Applications, 672
#### 7.3.4 HTTP-The HyperText Transfer Protocol, 683
#### 7.3.5 The Mobile Web, 693
#### 7.3.6 Web Search, 695
### 7.4 STREAMING AUDIO AND VIDEO, 697
#### 7.4.1 Digital Audio, 699
#### 7.4.2 Digital Video, 704
#### 7.4.3 Streaming Stored Media, 713
#### 7.4.4 Streaming Live Media, 721
#### 7.4.5 Real-Time Conferencing, 724
### 7.5 CONTENT DELIVERY, 734
#### 7.5.1 Content and Internet Traffic, 736
#### 7.5.2 Server Farms and Web Proxies, 738
#### 7.5.3 Content Delivery Networks, 743
#### 7.5.4 Peer-to-Peer Networks, 748
### 7.6 SUMMARY, 757
## 8 Network Security 763
### 8.1 CRYPTOGRAPHY, 766
#### 8.1.1 Introduction to Cryptography, 767
#### 8.1.2 Substitution Ciphers, 769
#### 8.1.3 Transposition Ciphers, 771
#### 8.1.4 One-Time Pads, 772
#### 8.1.5 Two Fundamental Cryptographic Principles, 776
### 8.2 SYMMETRIC-KEY ALGORITHMS, 778
#### 8.2.1 DES-The Data Encryption Standard, 780
#### 8.2.2 AES-The Advanced Encryption Standard, 783
#### 8.2.3 Cipher Modes, 787
#### 8.2.4 Other Ciphers, 792
#### 8.2.5 Cryptanalysis, 792


---

<a id="page-10"></a>

<!-- Page 10 of 888 -->

xvi CONTENTS
### 8.3 PUBLIC-KEY ALGORITHMS, 793
#### 8.3.1 RSA, 794
#### 8.3.2 Other Public-Key Algorithms, 796
### 8.4 DIGITAL SIGNATURES, 797
#### 8.4.1 Symmetric-Key Signatures, 798
#### 8.4.2 Public-Key Signatures, 799
#### 8.4.3 Message Digests, 800
#### 8.4.4 The Birthday Attack, 804
### 8.5 MANAGEMENT OF PUBLIC KEYS, 806
#### 8.5.1 Certificates, 807
#### 8.5.2 X.509, 809
#### 8.5.3 Public Key Infrastructures, 810
### 8.6 COMMUNICATION SECURITY, 813
#### 8.6.1 IPsec, 814
#### 8.6.2 Firewalls, 818
#### 8.6.3 Virtual Private Networks, 821
#### 8.6.4 Wireless Security, 822
### 8.7 AUTHENTICATION PROTOCOLS, 827
#### 8.7.1 Authentication Based on a Shared Secret Key, 828
#### 8.7.2 Establishing a Shared Key: The Diffie-Hellman Key Exchange, 833
#### 8.7.3 Authentication Using a Key Distribution Center, 835
#### 8.7.4 Authentication Using Kerberos, 838
#### 8.7.5 Authentication Using Public-Key Cryptography, 840
### 8.8 EMAIL SECURITY*, 841
#### 8.8.1 PGP-Pretty Good Privacy, 842
#### 8.8.2 S/MIME, 846
### 8.9 WEB SECURITY, 846
#### 8.9.1 Threats, 847
#### 8.9.2 Secure Naming, 848
#### 8.9.3 SSL-The Secure Sockets Layer, 853
#### 8.9.4 Mobile Code Security, 857
### 8.10 SOCIAL ISSUES, 860
#### 8.10.1 Privacy, 860
#### 8.10.2 Freedom of Speech, 863
#### 8.10.3 Copyright, 867
### 8.11 SUMMARY, 869


---

<a id="page-11"></a>

<!-- Page 11 of 888 -->

CONTENTS xvii
## 9 Reading List And Bibliography 877
### 9.1 SUGGESTIONS FOR FURTHER READING*, 877
#### 9.1.1 Introduction and General Works, 878
#### 9.1.2 The Physical Layer, 879
#### 9.1.3 The Data Link Layer, 880
#### 9.1.4 The Medium Access Control Sublayer, 880
#### 9.1.5 The Network Layer, 881
#### 9.1.6 The Transport Layer, 882
#### 9.1.7 The Application Layer, 882
#### 9.1.8 Network Security, 883
### 9.2 ALPHABETICAL BIBLIOGRAPHY*, 884
## Index 905


---

<a id="page-12"></a>

<!-- Page 12 of 888 -->

This page intentionally left blank
