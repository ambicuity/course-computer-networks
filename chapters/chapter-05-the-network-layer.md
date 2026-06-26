# Chapter 5: The Network Layer

_Source: printed pages 355-494; extracted PDF pages 367-506._

---

<a id="page-367"></a>

<!-- Page 367 of 888 -->

## The Network Layer
The network layer is concerned with getting packets from the source all the
way to the destination. Getting to the destination may require making many hops
at intermediate routers along the way. This function clearly contrasts with that of
the data link layer, which has the more modest goal of just moving frames from
one end of a wire to the other. Thus, the network layer is the lowest layer that
deals with end-to-end transmission.
To achieve its goals, the network layer must know about the topology of the
network (i.e., the set of all routers and links) and choose appropriate paths through
it, even for large networks. It must also take care when choosing routes to avoid
overloading some of the communication lines and routers while leaving others
idle. Finally, when the source and destination are in different networks, new
problems occur. It is up to the network layer to deal with them. In this chapter
we will study all these issues and illustrate them, primarily using the Internet and
its network layer protocol, IP.
### 5.1 NETWORK LAYER DESIGN ISSUES
In the following sections, we will give an introduction to some of the issues
that the designers of the network layer must grapple with. These issues include
the service provided to the transport layer and the internal design of the network.



---

<a id="page-368"></a>

<!-- Page 368 of 888 -->

356 THE NETWORK LAYER CHAP. 5
#### 5.1.1 Store-and-Forward Packet Switching
Before starting to explain the details of the network layer, it is worth restating
the context in which the network layer protocols operate. This context can be
seen in Fig. 5-1. The major components of the network are the ISP's equipment
(routers connected by transmission lines), shown inside the shaded oval, and the
customers' equipment, shown outside the oval. Host H1 is directly connected to
one of the ISP's routers, A, perhaps as a home computer that is plugged into a
DSL modem. In contrast, H2 is on a LAN, which might be an office Ethernet,
with a router, F, owned and operated by the customer. This router has a leased
line to the ISP's equipment. We have shown F as being outside the oval because
it does not belong to the ISP. For the purposes of this chapter, however, routers
on customer premises are considered part of the ISP network because they run the
same algorithms as the ISP's routers (and our main concern here is algorithms).
Router ISP's equipment
Process P1 P2
B

A E F
Host H1 LAN H2

Packet
Figure 5-1. The environment of the network layer protocols.
This equipment is used as follows. A host with a packet to send transmits it to
the nearest router, either on its own LAN or over a point-to-point link to the ISP.
The packet is stored there until it has fully arrived and the link has finished its
processing by verifying the checksum. Then it is forwarded to the next router
along the path until it reaches the destination host, where it is delivered. This
mechanism is store-and-forward packet switching, as we have seen in previous
chapters.
#### 5.1.2 Services Provided to the Transport Layer
The network layer provides services to the transport layer at the network
layer/transport layer interface. An important question is precisely what kind of
services the network layer provides to the transport layer. The services need to be
carefully designed with the following goals in mind:


---

<a id="page-369"></a>

<!-- Page 369 of 888 -->

SEC. 5.1 NETWORK LAYER DESIGN ISSUES 357
1. The services should be independent of the router technology.
2. The transport layer should be shielded from the number, type, and
topology of the routers present.
3. The network addresses made available to the transport layer should
use a uniform numbering plan, even across LANs and WANs.
Given these goals, the designers of the network layer have a lot of freedom in
writing detailed specifications of the services to be offered to the transport layer.
This freedom often degenerates into a raging battle between two warring factions.
The discussion centers on whether the network layer should provide connection-
oriented service or connectionless service.
One camp (represented by the Internet community) argues that the routers'
job is moving packets around and nothing else. In this view (based on 40 years of
experience with a real computer network), the network is inherently unreliable, no
matter how it is designed. Therefore, the hosts should accept this fact and do
error control (i.e., error detection and correction) and flow control themselves.
This viewpoint leads to the conclusion that the network service should be con-
nectionless, with primitives SEND PACKET and RECEIVE PACKET and little else.
In particular, no packet ordering and flow control should be done, because the
hosts are going to do that anyway and there is usually little to be gained by doing
it twice. This reasoning is an example of the end-to-end argument, a design
principle that has been very influential in shaping the Internet (Saltzer et al.,
1984). Furthermore, each packet must carry the full destination address, because
each packet sent is carried independently of its predecessors, if any.
The other camp (represented by the telephone companies) argues that the net-
work should provide a reliable, connection-oriented service. They claim that 100
years of successful experience with the worldwide telephone system is an excel-
lent guide. In this view, quality of service is the dominant factor, and without
connections in the network, quality of service is very difficult to achieve, espe-
cially for real-time traffic such as voice and video.
Even after several decades, this controversy is still very much alive. Early,
widely used data networks, such as X.25 in the 1970s and its successor Frame
Relay in the 1980s, were connection-oriented. However, since the days of the
ARPANET and the early Internet, connectionless network layers have grown
tremendously in popularity. The IP protocol is now an ever-present symbol of suc-
cess. It was undeterred by a connection-oriented technology called ATM that was
developed to overthrow it in the 1980s; instead, it is ATM that is now found in
niche uses and IP that is taking over telephone networks. Under the covers, how-
ever, the Internet is evolving connection-oriented features as quality of service be-
comes more important. Two examples of connection-oriented technologies are
MPLS (MultiProtocol Label Switching), which we will describe in this chapter,
and VLANs, which we saw in Chap. 4. Both technologies are widely used.


---

<a id="page-370"></a>

<!-- Page 370 of 888 -->

358 THE NETWORK LAYER CHAP. 5
#### 5.1.3 Implementation of Connectionless Service
Having looked at the two classes of service the network layer can provide to
its users, it is time to see how this layer works inside. Two different organizations
are possible, depending on the type of service offered. If connectionless service is
offered, packets are injected into the network individually and routed indepen-
dently of each other. No advance setup is needed. In this context, the packets are
frequently called datagrams (in analogy with telegrams) and the network is call-
ed a datagram network. If connection-oriented service is used, a path from the
source router all the way to the destination router must be established before any
data packets can be sent. This connection is called a VC (virtual circuit), in an-
alogy with the physical circuits set up by the telephone system, and the network is
called a virtual-circuit network. In this section, we will examine datagram net-
works; in the next one, we will examine virtual-circuit networks.
Let us now see how a datagram network works. Suppose that the process P1
in Fig. 5-2 has a long message for P2. It hands the message to the transport layer,
with instructions to deliver it to process P2 on host H2. The transport layer code
runs on H1, typically within the operating system. It prepends a transport header
to the front of the message and hands the result to the network layer, probably just
another procedure within the operating system.
Router ISP's equipment
Process P1 P2
B

A E F
3 2
Host H1 LAN H2

Packet
A's table (initially) A's table (later) C's table E's table
## A - A - A A A C
## B B B B B A B D
## C C C C C - C C
## D B D B D E D D
## E C E B E E E -
## F C F B F E F F
Dest. Line
Figure 5-2. Routing within a datagram network.
Let us assume for this example that the message is four times longer than the
maximum packet size, so the network layer has to break it into four packets, 1, 2,


---

<a id="page-371"></a>

<!-- Page 371 of 888 -->

SEC. 5.1 NETWORK LAYER DESIGN ISSUES 359
3, and 4, and send each of them in turn to router A using some point-to-point pro-
tocol, for example, PPP. At this point the ISP takes over. Every router has an in-
ternal table telling it where to send packets for each of the possible destinations.
Each table entry is a pair consisting of a destination and the outgoing line to use
for that destination. Only directly connected lines can be used. For example, in
Fig. 5-2, A has only two outgoing lines-to B and to C-so every incoming packet
must be sent to one of these routers, even if the ultimate destination is to some
other router. A's initial routing table is shown in the figure under the label ''ini-
tially.''
At A, packets 1, 2, and 3 are stored briefly, having arrived on the incoming
link and had their checksums verified. Then each packet is forwarded according
to A's table, onto the outgoing link to C within a new frame. Packet 1 is then for-
warded to E and then to F. When it gets to F, it is sent within a frame over the
LAN to H2. Packets 2 and 3 follow the same route.
However, something different happens to packet 4. When it gets to A it is
sent to router B, even though it is also destined for F. For some reason, A decided
to send packet 4 via a different route than that of the first three packets. Perhaps it
has learned of a traffic jam somewhere along the ACE path and updated its rout-
ing table, as shown under the label ''later.'' The algorithm that manages the tables
and makes the routing decisions is called the routing algorithm. Routing algo-
rithms are one of the main topics we will study in this chapter. There are several
different kinds of them, as we will see.
IP (Internet Protocol), which is the basis for the entire Internet, is the dom-
inant example of a connectionless network service. Each packet carries a destina-
tion IP address that routers use to individually forward each packet. The addresses
are 32 bits in IPv4 packets and 128 bits in IPv6 packets. We will describe IP in
much detail later in this chapter.
#### 5.1.4 Implementation of Connection-Oriented Service
For connection-oriented service, we need a virtual-circuit network. Let us see
how that works. The idea behind virtual circuits is to avoid having to choose a
new route for every packet sent, as in Fig. 5-2. Instead, when a connection is es-
tablished, a route from the source machine to the destination machine is chosen as
part of the connection setup and stored in tables inside the routers. That route is
used for all traffic flowing over the connection, exactly the same way that the
telephone system works. When the connection is released, the virtual circuit is
also terminated. With connection-oriented service, each packet carries an identi-
fier telling which virtual circuit it belongs to.
As an example, consider the situation shown in Fig. 5-3. Here, host H1 has
established connection 1 with host H2. This connection is remembered as the first
entry in each of the routing tables. The first line of A's table says that if a packet


---

<a id="page-372"></a>

<!-- Page 372 of 888 -->

360 THE NETWORK LAYER CHAP. 5
bearing connection identifier 1 comes in from H1, it is to be sent to router C and
given connection identifier 1. Similarly, the first entry at C routes the packet to E,
also with connection identifier 1.
P3
Router ISP's equipment
P2
B
H3 D

Process P1
A 4 E F

## 3 Lan H2

Packet
Host H1
A's table C's table E's table
## H1 1 C 1 A 1 E 1 C 1 F 1
## H3 1 C 2 A 2 E 2 C 2 F 2
In Out
Figure 5-3. Routing within a virtual-circuit network.
Now let us consider what happens if H3 also wants to establish a connection
to H2. It chooses connection identifier 1 (because it is initiating the connection
and this is its only connection) and tells the network to establish the virtual circuit.
This leads to the second row in the tables. Note that we have a conflict here be-
cause although A can easily distinguish connection 1 packets from H1 from con-
nection 1 packets from H3, C cannot do this. For this reason, A assigns a different
connection identifier to the outgoing traffic for the second connection. Avoiding
conflicts of this kind is why routers need the ability to replace connection identi-
fiers in outgoing packets.
In some contexts, this process is called label switching. An example of a
connection-oriented network service is MPLS (MultiProtocol Label Switching).
It is used within ISP networks in the Internet, with IP packets wrapped in an
MPLS header having a 20-bit connection identifier or label. MPLS is often hid-
den from customers, with the ISP establishing long-term connections for large
amounts of traffic, but it is increasingly being used to help when quality of service
is important but also with other ISP traffic management tasks. We will have more
to say about MPLS later in this chapter.


---

<a id="page-373"></a>

<!-- Page 373 of 888 -->

SEC. 5.1 NETWORK LAYER DESIGN ISSUES 361
#### 5.1.5 Comparison of Virtual-Circuit and Datagram Networks
Both virtual circuits and datagrams have their supporters and their detractors.
We will now attempt to summarize both sets of arguments. The major issues are
listed in Fig. 5-4, although purists could probably find a counterexample for
everything in the figure.
Issue Datagram network Virtual-circuit network
Circuit setup Not needed Required
Addressing Each packet contains the full Each packet contains a
source and destination address short VC number
State information Routers do not hold state Each VC requires router
information about connections table space per connection
Routing Each packet is routed Route chosen when VC is
independently set up; all packets follow it
Effect of router failures None, except for packets All VCs that passed
lost during the crash through the failed
router are terminated
Quality of service Difficult Easy if enough resources
can be allocated in
advance for each VC
Congestion control Difficult Easy if enough resources
can be allocated in
advance for each VC
Figure 5-4. Comparison of datagram and virtual-circuit networks.
Inside the network, several trade-offs exist between virtual circuits and data-
grams. One trade-off is setup time versus address parsing time. Using virtual cir-
cuits requires a setup phase, which takes time and consumes resources. However,
once this price is paid, figuring out what to do with a data packet in a virtual-cir-
cuit network is easy: the router just uses the circuit number to index into a table to
find out where the packet goes. In a datagram network, no setup is needed but a
more complicated lookup procedure is required to locate the entry for the destina-
tion.
A related issue is that the destination addresses used in datagram networks are
longer than circuit numbers used in virtual-circuit networks because they have a
global meaning. If the packets tend to be fairly short, including a full destination
address in every packet may represent a significant amount of overhead, and
hence a waste of bandwidth.
Yet another issue is the amount of table space required in router memory. A
datagram network needs to have an entry for every possible destination, whereas a
virtual-circuit network just needs an entry for each virtual circuit. However, this


---

<a id="page-374"></a>

<!-- Page 374 of 888 -->

362 THE NETWORK LAYER CHAP. 5
advantage is somewhat illusory since connection setup packets have to be routed
too, and they use destination addresses, the same as datagrams do.
Virtual circuits have some advantages in guaranteeing quality of service and
avoiding congestion within the network because resources (e.g., buffers, band-
width, and CPU cycles) can be reserved in advance, when the connection is estab-
lished. Once the packets start arriving, the necessary bandwidth and router capac-
ity will be there. With a datagram network, congestion avoidance is more diffi-
cult.
For transaction processing systems (e.g., stores calling up to verify credit card
purchases), the overhead required to set up and clear a virtual circuit may easily
dwarf the use of the circuit. If the majority of the traffic is expected to be of this
kind, the use of virtual circuits inside the network makes little sense. On the other
hand, for long-running uses such as VPN traffic between two corporate offices,
permanent virtual circuits (that are set up manually and last for months or years)
may be useful.
Virtual circuits also have a vulnerability problem. If a router crashes and
loses its memory, even if it comes back up a second later, all the virtual circuits
passing through it will have to be aborted. In contrast, if a datagram router goes
down, only those users whose packets were queued in the router at the time need
suffer (and probably not even then since the sender is likely to retransmit them
shortly). The loss of a communication line is fatal to virtual circuits using it, but
can easily be compensated for if datagrams are used. Datagrams also allow the
routers to balance the traffic throughout the network, since routes can be changed
partway through a long sequence of packet transmissions.
### 5.2 ROUTING ALGORITHMS
The main function of the network layer is routing packets from the source ma-
chine to the destination machine. In most networks, packets will require multiple
hops to make the journey. The only notable exception is for broadcast networks,
but even here routing is an issue if the source and destination are not on the same
network segment. The algorithms that choose the routes and the data structures
that they use are a major area of network layer design.
The routing algorithm is that part of the network layer software responsible
for deciding which output line an incoming packet should be transmitted on. If
the network uses datagrams internally, this decision must be made anew for every
arriving data packet since the best route may have changed since last time. If the
network uses virtual circuits internally, routing decisions are made only when a
new virtual circuit is being set up. Thereafter, data packets just follow the already
established route. The latter case is sometimes called session routing because a
route remains in force for an entire session (e.g., while logged in over a VPN).


---

<a id="page-375"></a>

<!-- Page 375 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 363
It is sometimes useful to make a distinction between routing, which is making
the decision which routes to use, and forwarding, which is what happens when a
packet arrives. One can think of a router as having two processes inside it. One
of them handles each packet as it arrives, looking up the outgoing line to use for it
in the routing tables. This process is forwarding. The other process is responsi-
ble for filling in and updating the routing tables. That is where the routing algo-
rithm comes into play.
Regardless of whether routes are chosen independently for each packet sent or
only when new connections are established, certain properties are desirable in a
routing algorithm: correctness, simplicity, robustness, stability, fairness, and effi-
ciency. Correctness and simplicity hardly require comment, but the need for
robustness may be less obvious at first. Once a major network comes on the air, it
may be expected to run continuously for years without system-wide failures. Dur-
ing that period there will be hardware and software failures of all kinds. Hosts,
routers, and lines will fail repeatedly, and the topology will change many times.
The routing algorithm should be able to cope with changes in the topology and
traffic without requiring all jobs in all hosts to be aborted. Imagine the havoc if
the network needed to be rebooted every time some router crashed!
Stability is also an important goal for the routing algorithm. There exist rout-
ing algorithms that never converge to a fixed set of paths, no matter how long they
run. A stable algorithm reaches equilibrium and stays there. It should converge
quickly too, since communication may be disrupted until the routing algorithm
has reached equilibrium.
Fairness and efficiency may sound obvious-surely no reasonable person
would oppose them-but as it turns out, they are often contradictory goals. As a
simple example of this conflict, look at Fig. 5-5. Suppose that there is enough
traffic between A and A′, between B and B′, and between C and C′ to saturate the
horizontal links. To maximize the total flow, the X to X′ traffic should be shut off
altogether. Unfortunately, X and X′ may not see it that way. Evidently, some
compromise between global efficiency and fairness to individual connections is
needed.
Before we can even attempt to find trade-offs between fairness and efficiency,
we must decide what it is we seek to optimize. Minimizing the mean packet delay
is an obvious candidate to send traffic through the network effectively, but so is
maximizing total network throughput. Furthermore, these two goals are also in
conflict, since operating any queueing system near capacity implies a long queue-
ing delay. As a compromise, many networks attempt to minimize the distance a
packet must travel, or simply reduce the number of hops a packet must make. Ei-
ther choice tends to improve the delay and also reduce the amount of bandwidth
consumed per packet, which tends to improve the overall network throughput as
well.
Routing algorithms can be grouped into two major classes: nonadaptive and
adaptive. Nonadaptive algorithms do not base their routing decisions on any


---

<a id="page-376"></a>

<!-- Page 376 of 888 -->

364 THE NETWORK LAYER CHAP. 5
A B C
X X′
A' B' C'
Figure 5-5. Network with a conflict between fairness and efficiency.
measurements or estimates of the current topology and traffic. Instead, the choice
of the route to use to get from I to J (for all I and J) is computed in advance, off-
line, and downloaded to the routers when the network is booted. This procedure
is sometimes called static routing. Because it does not respond to failures, static
routing is mostly useful for situations in which the routing choice is clear. For ex-
ample, router F in Fig. 5-3 should send packets headed into the network to router
E regardless of the ultimate destination.
Adaptive algorithms, in contrast, change their routing decisions to reflect
changes in the topology, and sometimes changes in the traffic as well. These
dynamic routing algorithms differ in where they get their information (e.g.,
locally, from adjacent routers, or from all routers), when they change the routes
(e.g., when the topology changes, or every ∆T seconds as the load changes), and
what metric is used for optimization (e.g., distance, number of hops, or estimated
transit time).
In the following sections, we will discuss a variety of routing algorithms. The
algorithms cover delivery models besides sending a packet from a source to a
destination. Sometimes the goal is to send the packet to multiple, all, or one of a
set of destinations. All of the routing algorithms we describe here make decisions
based on the topology; we defer the possibility of decisions based on the traffic
levels to Sec 5.3.
#### 5.2.1 The Optimality Principle
Before we get into specific algorithms, it may be helpful to note that one can
make a general statement about optimal routes without regard to network topo-
logy or traffic. This statement is known as the optimality principle (Bellman,
1957). It states that if router J is on the optimal path from router I to router K,


---

<a id="page-377"></a>

<!-- Page 377 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 365
then the optimal path from J to K also falls along the same route. To see this, call
the part of the route from I to J r and the rest of the route r . If a route better
1 2
than r existed from J to K, it could be concatenated with r to improve the route
2 1
from I to K, contradicting our statement that r r is optimal.
1 2
As a direct consequence of the optimality principle, we can see that the set of
optimal routes from all sources to a given destination form a tree rooted at the
destination. Such a tree is called a sink tree and is illustrated in Fig. 5-6(b),
where the distance metric is the number of hops. The goal of all routing algo-
rithms is to discover and use the sink trees for all routers.
B B
A A C

D E D E
G J G J
F F
I I
H N H N
L L
K K
M O M O
(a) (b)
Figure 5-6. (a) A network. (b) A sink tree for router B.
Note that a sink tree is not necessarily unique; other trees with the same path
lengths may exist. If we allow all of the possible paths to be chosen, the tree be-
comes a more general structure called a DAG (Directed Acyclic Graph). DAGs
have no loops. We will use sink trees as a convenient shorthand for both cases.
Both cases also depend on the technical assumption that the paths do not interfere
with each other so, for example, a traffic jam on one path will not cause another
path to divert.
Since a sink tree is indeed a tree, it does not contain any loops, so each packet
will be delivered within a finite and bounded number of hops. In practice, life is
not quite this easy. Links and routers can go down and come back up during oper-
ation, so different routers may have different ideas about the current topology.
Also, we have quietly finessed the issue of whether each router has to individually
acquire the information on which to base its sink tree computation or whether this
information is collected by some other means. We will come back to these issues
shortly. Nevertheless, the optimality principle and the sink tree provide a bench-
mark against which other routing algorithms can be measured.


---

<a id="page-378"></a>

<!-- Page 378 of 888 -->

366 THE NETWORK LAYER CHAP. 5
#### 5.2.2 Shortest Path Algorithm
Let us begin our study of routing algorithms with a simple technique for com-
puting optimal paths given a complete picture of the network. These paths are the
ones that we want a distributed routing algorithm to find, even though not all rout-
ers may know all of the details of the network.
The idea is to build a graph of the network, with each node of the graph
representing a router and each edge of the graph representing a communication
line, or link. To choose a route between a given pair of routers, the algorithm just
finds the shortest path between them on the graph.
The concept of a shortest path deserves some explanation. One way of
measuring path length is the number of hops. Using this metric, the paths ABC
and ABE in Fig. 5-7 are equally long. Another metric is the geographic distance
in kilometers, in which case ABC is clearly much longer than ABE (assuming the
figure is drawn to scale).
B 7 C B (2, A) C (∞,− )
2 22 3 3
E 2 F EE (∞,− )
AA D A F (∞,− ) D (∞,− )
11 2
66 2

GG H GG (6, A) HH (∞,− )
(a) (b)
## B (2, A) C (9, B) B (2, A) C (9, B)
## E (4, B) E (4, B)
AA F (∞,− ) D (∞,−) AA F (6, E) D (∞,1)
G (6, A) H (∞,− ) G (5, E) H (∞,− )
(c) (d)
## B (2, A) C (9, B) B (2, A) C (9, B)
## E (4, B) E (4, B)
AA F (6, E) D (∞,−) AA F (6,E) D (∞,−)
## G (5, E) H (9, G) G (5, E) H (8, F)
(e) (f)
Figure 5-7. The first six steps used in computing the shortest path from A to D.
The arrows indicate the working node.


---

<a id="page-379"></a>

<!-- Page 379 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 367
However, many other metrics besides hops and physical distance are also pos-
sible. For example, each edge could be labeled with the mean delay of a standard
test packet, as measured by hourly runs. With this graph labeling, the shortest
path is the fastest path rather than the path with the fewest edges or kilometers.
In the general case, the labels on the edges could be computed as a function of
the distance, bandwidth, average traffic, communication cost, measured delay,
and other factors. By changing the weighting function, the algorithm would then
compute the ''shortest'' path measured according to any one of a number of cri-
teria or to a combination of criteria.
Several algorithms for computing the shortest path between two nodes of a
graph are known. This one is due to Dijkstra (1959) and finds the shortest paths
between a source and all destinations in the network. Each node is labeled (in
parentheses) with its distance from the source node along the best known path.
The distances must be non-negative, as they will be if they are based on real quan-
tities like bandwidth and delay. Initially, no paths are known, so all nodes are
labeled with infinity. As the algorithm proceeds and paths are found, the labels
may change, reflecting better paths. A label may be either tentative or permanent.
Initially, all labels are tentative. When it is discovered that a label represents the
shortest possible path from the source to that node, it is made permanent and
never changed thereafter.
To illustrate how the labeling algorithm works, look at the weighted,
undirected graph of Fig. 5-7(a), where the weights represent, for example, dis-
tance. We want to find the shortest path from A to D. We start out by marking
node A as permanent, indicated by a filled-in circle. Then we examine, in turn,
each of the nodes adjacent to A (the working node), relabeling each one with the
distance to A. Whenever a node is relabeled, we also label it with the node from
which the probe was made so that we can reconstruct the final path later. If the
network had more than one shortest path from A to D and we wanted to find all of
them, we would need to remember all of the probe nodes that could reach a node
with the same distance.
Having examined each of the nodes adjacent to A, we examine all the tenta-
tively labeled nodes in the whole graph and make the one with the smallest label
permanent, as shown in Fig. 5-7(b). This one becomes the new working node.
We now start at B and examine all nodes adjacent to it. If the sum of the label
on B and the distance from B to the node being considered is less than the label on
that node, we have a shorter path, so the node is relabeled.
After all the nodes adjacent to the working node have been inspected and the
tentative labels changed if possible, the entire graph is searched for the tentatively
labeled node with the smallest value. This node is made permanent and becomes
the working node for the next round. Figure 5-7 shows the first six steps of the al-
gorithm.
To see why the algorithm works, look at Fig. 5-7(c). At this point we have
just made E permanent. Suppose that there were a shorter path than ABE, say


---

<a id="page-380"></a>

<!-- Page 380 of 888 -->

368 THE NETWORK LAYER CHAP. 5
AXYZE (for some X and Y). There are two possibilities: either node Z has already
been made permanent, or it has not been. If it has, then E has already been probed
(on the round following the one when Z was made permanent), so the AXYZE path
has not escaped our attention and thus cannot be a shorter path.
Now consider the case where Z is still tentatively labeled. If the label at Z is
greater than or equal to that at E, then AXYZE cannot be a shorter path than ABE.
If the label is less than that of E, then Z and not E will become permanent first, al-
lowing E to be probed from Z.
This algorithm is given in Fig. 5-8. The global variables n and dist describe
the graph and are initialized before shortest path is called. The only difference
between the program and the algorithm described above is that in Fig. 5-8, we
compute the shortest path starting at the terminal node, t, rather than at the source
node, s.
Since the shortest paths from t to s in an undirected graph are the same as the
shortest paths from s to t, it does not matter at which end we begin. The reason
for searching backward is that each node is labeled with its predecessor rather
than its successor. When the final path is copied into the output variable, path,
the path is thus reversed. The two reversal effects cancel, and the answer is pro-
duced in the correct order.
#### 5.2.3 Flooding
When a routing algorithm is implemented, each router must make decisions
based on local knowledge, not the complete picture of the network. A simple
local technique is flooding, in which every incoming packet is sent out on every
outgoing line except the one it arrived on.
Flooding obviously generates vast numbers of duplicate packets, in fact, an
infinite number unless some measures are taken to damp the process. One such
measure is to have a hop counter contained in the header of each packet that is
decremented at each hop, with the packet being discarded when the counter
reaches zero. Ideally, the hop counter should be initialized to the length of the
path from source to destination. If the sender does not know how long the path is,
it can initialize the counter to the worst case, namely, the full diameter of the net-
work.
Flooding with a hop count can produce an exponential number of duplicate
packets as the hop count grows and routers duplicate packets they have seen be-
fore. A better technique for damming the flood is to have routers keep track of
which packets have been flooded, to avoid sending them out a second time. One
way to achieve this goal is to have the source router put a sequence number in
each packet it receives from its hosts. Each router then needs a list per source
router telling which sequence numbers originating at that source have already
been seen. If an incoming packet is on the list, it is not flooded.


---

<a id="page-381"></a>

<!-- Page 381 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 369
#define MAX NODES 1024 /* maximum number of nodes */
#define INFINITY 1000000000 /* a number larger than every maximum path */
int n, dist[MAX NODES][MAX NODES]; /* dist[i][j] is the distance from i to j */
void shortest path(int s, int t, int path[])
{ struct state { /* the path being worked on */
int predecessor; /* previous node */
int length; /* length from source to this node */
enum {permanent, tentative} label; /* label state */
} state[MAX NODES];
int i, k, min;
struct state *p;
for (p = &state[0]; p < &state[n]; p++) { /* initialize state */
p->predecessor = −1;
p->length = INFINITY;
p->label = tentative;
}
state[t].length = 0; state[t].label = permanent;
k = t; /* k is the initial working node */
do { /* Is there a better path from k? */
for (i = 0; i < n; i++) /* this graph has n nodes */
if (dist[k][i] != 0 && state[i].label == tentative) {
if (state[k].length + dist[k][i] < state[i].length) {
state[i].predecessor = k;
state[i].length = state[k].length + dist[k][i];
}
}
/* Find the tentatively labeled node with the smallest label. */
k = 0; min = INFINITY;
for (i = 0; i < n; i++)
if (state[i].label == tentative && state[i].length < min) {
min = state[i].length;
k = i;
}
state[k].label = permanent;
} while (k != s);
/* Copy the path into the output array. */
i = 0; k = s;
do {path[i++] = k; k = state[k].predecessor; } while (k >= 0);
}
Figure 5-8. Dijkstra's algorithm to compute the shortest path through a graph.
To prevent the list from growing without bound, each list should be aug-
mented by a counter, k, meaning that all sequence numbers through k have been
seen. When a packet comes in, it is easy to check if the packet has already been


---

<a id="page-382"></a>

<!-- Page 382 of 888 -->

370 THE NETWORK LAYER CHAP. 5
flooded (by comparing its sequence number to k; if so, it is discarded. Further-
more, the full list below k is not needed, since k effectively summarizes it.
Flooding is not practical for sending most packets, but it does have some im-
portant uses. First, it ensures that a packet is delivered to every node in the net-
work. This may be wasteful if there is a single destination that needs the packet,
but it is effective for broadcasting information. In wireless networks, all mes-
sages transmitted by a station can be received by all other stations within its radio
range, which is, in fact, flooding, and some algorithms utilize this property.
Second, flooding is tremendously robust. Even if large numbers of routers are
blown to bits (e.g., in a military network located in a war zone), flooding will find
a path if one exists, to get a packet to its destination. Flooding also requires little
in the way of setup. The routers only need to know their neighbors. This means
that flooding can be used as a building block for other routing algorithms that are
more efficient but need more in the way of setup. Flooding can also be used as a
metric against which other routing algorithms can be compared. Flooding always
chooses the shortest path because it chooses every possible path in parallel. Con-
sequently, no other algorithm can produce a shorter delay (if we ignore the over-
head generated by the flooding process itself).
#### 5.2.4 Distance Vector Routing
Computer networks generally use dynamic routing algorithms that are more
complex than flooding, but more efficient because they find shortest paths for the
current topology. Two dynamic algorithms in particular, distance vector routing
and link state routing, are the most popular. In this section, we will look at the
former algorithm. In the following section, we will study the latter algorithm.
A distance vector routing algorithm operates by having each router maintain
a table (i.e., a vector) giving the best known distance to each destination and
which link to use to get there. These tables are updated by exchanging infor-
mation with the neighbors. Eventually, every router knows the best link to reach
each destination.
The distance vector routing algorithm is sometimes called by other names,
most commonly the distributed Bellman-Ford routing algorithm, after the re-
searchers who developed it (Bellman, 1957; and Ford and Fulkerson, 1962). It
was the original ARPANET routing algorithm and was also used in the Internet
under the name RIP.
In distance vector routing, each router maintains a routing table indexed by,
and containing one entry for each router in the network. This entry has two parts:
the preferred outgoing line to use for that destination and an estimate of the dis-
tance to that destination. The distance might be measured as the number of hops
or using another metric, as we discussed for computing shortest paths.
The router is assumed to know the ''distance'' to each of its neighbors. If the
metric is hops, the distance is just one hop. If the metric is propagation delay, the


---

<a id="page-383"></a>

<!-- Page 383 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 371
router can measure it directly with special ECHO packets that the receiver just
timestamps and sends back as fast as it can.
As an example, assume that delay is used as a metric and that the router
knows the delay to each of its neighbors. Once every T msec, each router sends to
each neighbor a list of its estimated delays to each destination. It also receives a
similar list from each neighbor. Imagine that one of these tables has just come in
from neighbor X, with X being X's estimate of how long it takes to get to router i.

If the router knows that the delay to X is m msec, it also knows that it can reach
router i via X in X + m msec. By performing this calculation for each neighbor, a

router can find out which estimate seems the best and use that estimate and the
corresponding link in its new routing table. Note that the old routing table is not
used in the calculation.
This updating process is illustrated in Fig. 5-9. Part (a) shows a network. The
first four columns of part (b) show the delay vectors received from the neighbors
of router J. A claims to have a 12-msec delay to B, a 25-msec delay to C, a 40-
msec delay to D, etc. Suppose that J has measured or estimated its delay to its
neighbors, A, I, H, and K, as 8, 10, 12, and 6 msec, respectively.
Router
A B C D
0 24 20 21 8
12 36 31 28 20
25 18 19 36 28
## F G 40 27 8 24 20 E H
14 7 30 22 17
23 20 19 40 30
18 31 6 31 18
17 20 0 19 12
I J K L
21 0 14 22 10
9 11 7 10 0
24 22 22 0 6
29 33 9 9 15
(a)
AA
H
HH
−

New estimated
delay from J
To A I H K Line
A
B

E
F
G
H

J
K K
L K
## Ja Ji Jh Jk
delay delay delay delay New
is is is is routing
8 10 12 6 table
for J
Vectors received from
J's four neighbors
(b)
Figure 5-9. (a) A network. (b) Input from A, I, H, K, and the new routing table for J.
Consider how J computes its new route to router G. It knows that it can get to
A in 8 msec, and furthermore A claims to be able to get to G in 18 msec, so J
knows it can count on a delay of 26 msec to G if it forwards packets bound for G


---

<a id="page-384"></a>

<!-- Page 384 of 888 -->

372 THE NETWORK LAYER CHAP. 5
to A. Similarly, it computes the delay to G via I, H, and K as 41 (31 + 10), 18
(6 + 12), and 37 (31 + 6) msec, respectively. The best of these values is 18, so it
makes an entry in its routing table that the delay to G is 18 msec and that the route
to use is via H. The same calculation is performed for all the other destinations,
with the new routing table shown in the last column of the figure.
The Count-to-Infinity Problem
The settling of routes to best paths across the network is called convergence.
Distance vector routing is useful as a simple technique by which routers can col-
lectively compute shortest paths, but it has a serious drawback in practice: al-
though it converges to the correct answer, it may do so slowly. In particular, it
reacts rapidly to good news, but leisurely to bad news. Consider a router whose
best route to destination X is long. If, on the next exchange, neighbor A suddenly
reports a short delay to X, the router just switches over to using the line to A to
send traffic to X. In one vector exchange, the good news is processed.
To see how fast good news propagates, consider the five-node (linear) net-
work of Fig. 5-10, where the delay metric is the number of hops. Suppose A is
down initially and all the other routers know this. In other words, they have all
recorded the delay to A as infinity.
## A B C D E A B C D E
• • • • Initially 1 2 3 4 Initially
1 • • • After 1 exchange 3 2 3 4 After 1 exchange
1 2 • • After 2 exchanges 3 4 3 4 After 2 exchanges
1 2 3 • After 3 exchanges 5 4 5 4 After 3 exchanges
1 2 3 4 After 4 exchanges 5 6 5 6 After 4 exchanges
7 6 7 6 After 5 exchanges
7 8 7 8 After 6 exchanges
.
.
.
• • • •
(a) (b)
Figure 5-10. The count-to-infinity problem.
When A comes up, the other routers learn about it via the vector exchanges.
For simplicity, we will assume that there is a gigantic gong somewhere that is
struck periodically to initiate a vector exchange at all routers simultaneously. At
the time of the first exchange, B learns that its left-hand neighbor has zero delay
to A. B now makes an entry in its routing table indicating that A is one hop away
to the left. All the other routers still think that A is down. At this point, the rout-
ing table entries for A are as shown in the second row of Fig. 5-10(a). On the next


---

<a id="page-385"></a>

<!-- Page 385 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 373
exchange, C learns that B has a path of length 1 to A, so it updates its routing table
to indicate a path of length 2, but D and E do not hear the good news until later.
Clearly, the good news is spreading at the rate of one hop per exchange. In a net-
work whose longest path is of length N hops, within N exchanges everyone will
know about newly revived links and routers.
Now let us consider the situation of Fig. 5-10(b), in which all the links and
routers are initially up. Routers B, C, D, and E have distances to A of 1, 2, 3, and
4 hops, respectively. Suddenly, either A goes down or the link between A and B is
cut (which is effectively the same thing from B's point of view).
At the first packet exchange, B does not hear anything from A. Fortunately, C
says ''Do not worry; I have a path to A of length 2.'' Little does B suspect that C's
path runs through B itself. For all B knows, C might have ten links all with sepa-
rate paths to A of length 2. As a result, B thinks it can reach A via C, with a path
length of 3. D and E do not update their entries for A on the first exchange.
On the second exchange, C notices that each of its neighbors claims to have a
path to A of length 3. It picks one of them at random and makes its new distance
to A 4, as shown in the third row of Fig. 5-10(b). Subsequent exchanges produce
the history shown in the rest of Fig. 5-10(b).
From this figure, it should be clear why bad news travels slowly: no router
ever has a value more than one higher than the minimum of all its neighbors.
Gradually, all routers work their way up to infinity, but the number of exchanges
required depends on the numerical value used for infinity. For this reason, it is
wise to set infinity to the longest path plus 1.
Not entirely surprisingly, this problem is known as the count-to-infinity prob-
lem. There have been many attempts to solve it, for example, preventing routers
from advertising their best paths back to the neighbors from which they heard
them with the split horizon with poisoned reverse rule discussed in RFC 1058.
However, none of these heuristics work well in practice despite the colorful
names. The core of the problem is that when X tells Y that it has a path some-
where, Y has no way of knowing whether it itself is on the path.
#### 5.2.5 Link State Routing
Distance vector routing was used in the ARPANET until 1979, when it was
replaced by link state routing. The primary problem that caused its demise was
that the algorithm often took too long to converge after the network topology
changed (due to the count-to-infinity problem). Consequently, it was replaced by
an entirely new algorithm, now called link state routing. Variants of link state
routing called IS-IS and OSPF are the routing algorithms that are most widely
used inside large networks and the Internet today.
The idea behind link state routing is fairly simple and can be stated as five
parts. Each router must do the following things to make it work:


---

<a id="page-386"></a>

<!-- Page 386 of 888 -->

374 THE NETWORK LAYER CHAP. 5
1. Discover its neighbors and learn their network addresses.
2. Set the distance or cost metric to each of its neighbors.
3. Construct a packet telling all it has just learned.
4. Send this packet to and receive packets from all other routers.
5. Compute the shortest path to every other router.
In effect, the complete topology is distributed to every router. Then Dijkstra's al-
gorithm can be run at each router to find the shortest path to every other router.
Below we will consider each of these five steps in more detail.
Learning about the Neighbors
When a router is booted, its first task is to learn who its neighbors are. It
accomplishes this goal by sending a special HELLO packet on each point-to-point
line. The router on the other end is expected to send back a reply giving its name.
These names must be globally unique because when a distant router later hears
that three routers are all connected to F, it is essential that it can determine wheth-
er all three mean the same F.
When two or more routers are connected by a broadcast link (e.g., a switch,
ring, or classic Ethernet), the situation is slightly more complicated. Fig. 5-11(a)
illustrates a broadcast LAN to which three routers, A, C, and F, are directly con-
nected. Each of these routers is connected to one or more additional routers, as
shown.
H Router
B D E
## D E G I G H
B
A C F C
A
F I
LAN N
(a) (b)
Figure 5-11. (a) Nine routers and a broadcast LAN. (b) A graph model of (a).
The broadcast LAN provides connectivity between each pair of attached rout-
ers. However, modeling the LAN as many point-to-point links increases the size


---

<a id="page-387"></a>

<!-- Page 387 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 375
of the topology and leads to wasteful messages. A better way to model the LAN
is to consider it as a node itself, as shown in Fig. 5-11(b). Here, we have intro-
duced a new, artificial node, N, to which A, C, and F are connected. One desig-
nated router on the LAN is selected to play the role of N in the routing protocol.
The fact that it is possible to go from A to C on the LAN is represented by the
path ANC here.
Setting Link Costs
The link state routing algorithm requires each link to have a distance or cost
metric for finding shortest paths. The cost to reach neighbors can be set automat-
ically, or configured by the network operator. A common choice is to make the
cost inversely proportional to the bandwidth of the link. For example, 1-Gbps
Ethernet may have a cost of 1 and 100-Mbps Ethernet a cost of 10. This makes
higher-capacity paths better choices.
If the network is geographically spread out, the delay of the links may be fac-
tored into the cost so that paths over shorter links are better choices. The most
direct way to determine this delay is to send over the line a special ECHO packet
that the other side is required to send back immediately. By measuring the
round-trip time and dividing it by two, the sending router can get a reasonable
estimate of the delay.
Building Link State Packets
Once the information needed for the exchange has been collected, the next
step is for each router to build a packet containing all the data. The packet starts
with the identity of the sender, followed by a sequence number and age (to be de-
scribed later) and a list of neighbors. The cost to each neighbor is also given. An
example network is presented in Fig. 5-12(a) with costs shown as labels on the
lines. The corresponding link state packets for all six routers are shown in Fig. 5-
12(b).
Link State Packets
B 2 C
## A B C D E F
4 3
Seq. Seq. Seq. Seq. Seq. Seq.
A D Age Age Age Age Age Age
1 6 B 4 A 4 B 2 C 3 A 5 B 6
5 7
## E 5 C 2 D 3 F 7 C 1 D 7
## E 8 F F 6 E 1 F 8 E 8
(a) (b)
Figure 5-12. (a) A network. (b) The link state packets for this network.


---

<a id="page-388"></a>

<!-- Page 388 of 888 -->

376 THE NETWORK LAYER CHAP. 5
Building the link state packets is easy. The hard part is determining when to
build them. One possibility is to build them periodically, that is, at regular inter-
vals. Another possibility is to build them when some significant event occurs,
such as a line or neighbor going down or coming back up again or changing its
properties appreciably.
Distributing the Link State Packets
The trickiest part of the algorithm is distributing the link state packets. All of
the routers must get all of the link state packets quickly and reliably. If different
routers are using different versions of the topology, the routes they compute can
have inconsistencies such as loops, unreachable machines, and other problems.
First, we will describe the basic distribution algorithm. After that we will
give some refinements. The fundamental idea is to use flooding to distribute the
link state packets to all routers. To keep the flood in check, each packet contains
a sequence number that is incremented for each new packet sent. Routers keep
track of all the (source router, sequence) pairs they see. When a new link state
packet comes in, it is checked against the list of packets already seen. If it is new,
it is forwarded on all lines except the one it arrived on. If it is a duplicate, it is
discarded. If a packet with a sequence number lower than the highest one seen so
far ever arrives, it is rejected as being obsolete as the router has more recent data.
This algorithm has a few problems, but they are manageable. First, if the se-
quence numbers wrap around, confusion will reign. The solution here is to use a
32-bit sequence number. With one link state packet per second, it would take 137
years to wrap around, so this possibility can be ignored.
Second, if a router ever crashes, it will lose track of its sequence number. If it
starts again at 0, the next packet it sends will be rejected as a duplicate.
Third, if a sequence number is ever corrupted and 65,540 is received instead
of 4 (a 1-bit error), packets 5 through 65,540 will be rejected as obsolete, since the
current sequence number will be thought to be 65,540.
The solution to all these problems is to include the age of each packet after
the sequence number and decrement it once per second. When the age hits zero,
the information from that router is discarded. Normally, a new packet comes in,
say, every 10 sec, so router information only times out when a router is down (or
six consecutive packets have been lost, an unlikely event). The Age field is also
decremented by each router during the initial flooding process, to make sure no
packet can get lost and live for an indefinite period of time (a packet whose age is
zero is discarded).
Some refinements to this algorithm make it more robust. When a link state
packet comes in to a router for flooding, it is not queued for transmission im-
mediately. Instead, it is put in a holding area to wait a short while in case more
links are coming up or going down. If another link state packet from the same
source comes in before the first packet is transmitted, their sequence numbers are


---

<a id="page-389"></a>

<!-- Page 389 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 377
compared. If they are equal, the duplicate is discarded. If they are different, the
older one is thrown out. To guard against errors on the links, all link state packets
are acknowledged.
The data structure used by router B for the network shown in Fig. 5-12(a) is
depicted in Fig. 5-13. Each row here corresponds to a recently arrived, but as yet
not fully processed, link state packet. The table records where the packet ori-
ginated, its sequence number and age, and the data. In addition, there are send
and acknowledgement flags for each of B's three links (to A, C, and F, re-
spectively). The send flags mean that the packet must be sent on the indicated
link. The acknowledgement flags mean that it must be acknowledged there.
Send flags ACK flags
Source Seq. Age A C F A C F Data
## A 21 60 0 1 1 1 0 0
## F 21 60 1 1 0 0 0 1
## E 21 59 0 1 0 1 0 1
## C 20 60 1 0 1 0 1 0
## D 21 59 1 0 0 0 1 1
Figure 5-13. The packet buffer for router B in Fig. 5-12(a).
In Fig. 5-13, the link state packet from A arrives directly, so it must be sent to
C and F and acknowledged to A, as indicated by the flag bits. Similarly, the pack-
et from F has to be forwarded to A and C and acknowledged to F.
However, the situation with the third packet, from E, is different. It arrives
twice, once via EAB and once via EFB. Consequently, it has to be sent only to C
but must be acknowledged to both A and F, as indicated by the bits.
If a duplicate arrives while the original is still in the buffer, bits have to be
changed. For example, if a copy of C's state arrives from F before the fourth
entry in the table has been forwarded, the six bits will be changed to 100011 to in-
dicate that the packet must be acknowledged to F but not sent there.
Computing the New Routes
Once a router has accumulated a full set of link state packets, it can construct
the entire network graph because every link is represented. Every link is, in fact,
represented twice, once for each direction. The different directions may even
have different costs. The shortest-path computations may then find different paths
from router A to B than from router B to A.
Now Dijkstra's algorithm can be run locally to construct the shortest paths to
all possible destinations. The results of this algorithm tell the router which link to


---

<a id="page-390"></a>

<!-- Page 390 of 888 -->

378 THE NETWORK LAYER CHAP. 5
use to reach each destination. This information is installed in the routing tables,
and normal operation is resumed.
Compared to distance vector routing, link state routing requires more memory
and computation. For a network with n routers, each of which has k neighbors,
the memory required to store the input data is proportional to kn, which is at least
as large as a routing table listing all the destinations. Also, the computation time
grows faster than kn, even with the most efficient data structures, an issue in large
networks. Nevertheless, in many practical situations, link state routing works
well because it does not suffer from slow convergence problems.
Link state routing is widely used in actual networks, so a few words about
some example protocols are in order. Many ISPs use the IS-IS (Intermediate
System-Intermediate System) link state protocol (Oran, 1990). It was designed
for an early network called DECnet, later adopted by ISO for use with the OSI
protocols and then modified to handle other protocols as well, most notably, IP.
OSPF (Open Shortest Path First) is the other main link state protocol. It was
designed by IETF several years after IS-IS and adopted many of the innovations
designed for IS-IS. These innovations include a self-stabilizing method of flood-
ing link state updates, the concept of a designated router on a LAN, and the meth-
od of computing and supporting path splitting and multiple metrics. As a conse-
quence, there is very little difference between IS-IS and OSPF. The most impor-
tant difference is that IS-IS can carry information about multiple network layer
protocols at the same time (e.g., IP, IPX, and AppleTalk). OSPF does not have
this feature, and it is an advantage in large multiprotocol environments. We will
go over OSPF in Sec. 5.6.6.
A general comment on routing algorithms is also in order. Link state, dis-
tance vector, and other algorithms rely on processing at all the routers to compute
routes. Problems with the hardware or software at even a small number of routers
can wreak havoc across the network. For example, if a router claims to have a
link it does not have or forgets a link it does have, the network graph will be
incorrect. If a router fails to forward packets or corrupts them while forwarding
them, the route will not work as expected. Finally, if it runs out of memory or
does the routing calculation wrong, bad things will happen. As the network grows
into the range of tens or hundreds of thousands of nodes, the probability of some
router failing occasionally becomes nonnegligible. The trick is to try to arrange to
limit the damage when the inevitable happens. Perlman (1988) discusses these
problems and their possible solutions in detail.
#### 5.2.6 Hierarchical Routing
As networks grow in size, the router routing tables grow proportionally. Not
only is router memory consumed by ever-increasing tables, but more CPU time is
needed to scan them and more bandwidth is needed to send status reports about
them. At a certain point, the network may grow to the point where it is no longer


---

<a id="page-391"></a>

<!-- Page 391 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 379
feasible for every router to have an entry for every other router, so the routing will
have to be done hierarchically, as it is in the telephone network.
When hierarchical routing is used, the routers are divided into what we will
call regions. Each router knows all the details about how to route packets to dest-
inations within its own region but knows nothing about the internal structure of
other regions. When different networks are interconnected, it is natural to regard
each one as a separate region to free the routers in one network from having to
know the topological structure of the other ones.
For huge networks, a two-level hierarchy may be insufficient; it may be nec-
essary to group the regions into clusters, the clusters into zones, the zones into
groups, and so on, until we run out of names for aggregations. As an example of a
multilevel hierarchy, consider how a packet might be routed from Berkeley, Cali-
fornia, to Malindi, Kenya. The Berkeley router would know the detailed topology
within California but would send all out-of-state traffic to the Los Angeles router.
The Los Angeles router would be able to route traffic directly to other domestic
routers but would send all foreign traffic to New York. The New York router
would be programmed to direct all traffic to the router in the destination country
responsible for handling foreign traffic, say, in Nairobi. Finally, the packet would
work its way down the tree in Kenya until it got to Malindi.
Figure 5-14 gives a quantitative example of routing in a two-level hierarchy
with five regions. The full routing table for router 1A has 17 entries, as shown in
Fig. 5-14(b). When routing is done hierarchically, as in Fig. 5-14(c), there are en-
tries for all the local routers, as before, but all other regions are condensed into a
single router, so all traffic for region 2 goes via the 1B-2A line, but the rest of the
remote traffic goes via the 1C-3B line. Hierarchical routing has reduced the table
from 17 to 7 entries. As the ratio of the number of regions to the number of rout-
ers per region grows, the savings in table space increase.
Unfortunately, these gains in space are not free. There is a penalty to be paid:
increased path length. For example, the best route from 1A to 5C is via region 2,
but with hierarchical routing all traffic to region 5 goes via region 3, because that
is better for most destinations in region 5.
When a single network becomes very large, an interesting question is ''how
many levels should the hierarchy have?'' For example, consider a network with
720 routers. If there is no hierarchy, each router needs 720 routing table entries.
If the network is partitioned into 24 regions of 30 routers each, each router needs
30 local entries plus 23 remote entries for a total of 53 entries. If a three-level
hierarchy is chosen, with 8 clusters each containing 9 regions of 10 routers, each
router needs 10 entries for local routers, 8 entries for routing to other regions
within its own cluster, and 7 entries for distant clusters, for a total of 25 entries.
Kamoun and Kleinrock (1979) discovered that the optimal number of levels for an
N router network is ln N, requiring a total of e ln N entries per router. They have
also shown that the increase in effective mean path length caused by hierarchical
routing is sufficiently small that it is usually acceptable.


---

<a id="page-392"></a>

<!-- Page 392 of 888 -->

380 THE NETWORK LAYER CHAP. 5
Full table for 1A Hierarchical table for 1A
Dest. Line Hops Dest. Line Hops
Region 1 Region 2 1A - - 1A - -
1B 2A 2B 1B 1B 1 1B 1B 1
1C 1C 1 1C 1C 1
1A
2A 1B 2 2 1B 2
1C 2C 2D
2B 1B 3 3 1C 2
2C 1B 3 4 1C 3
2D 1B 4 5 1C 4
3A 4A 5B 5C 3A 1C 3
5A 3B 1C 2
4B
3B 4C 5D 4A 1C 3
5E
4B 1C 4
Region 3 Region 4 Region 5
4C 1C 4
5A 1C 4
5B 1C 5
5C 1B 5
5D 1C 6
5E 1C 5
(a) (b) (c)
Figure 5-14. Hierarchical routing.
#### 5.2.7 Broadcast Routing
In some applications, hosts need to send messages to many or all other hosts.
For example, a service distributing weather reports, stock market updates, or live
radio programs might work best by sending to all machines and letting those that
are interested read the data. Sending a packet to all destinations simultaneously is
called broadcasting. Various methods have been proposed for doing it.
One broadcasting method that requires no special features from the network is
for the source to simply send a distinct packet to each destination. Not only is the
method wasteful of bandwidth and slow, but it also requires the source to have a
complete list of all destinations. This method is not desirable in practice, even
though it is widely applicable.
An improvement is multidestination routing, in which each packet contains
either a list of destinations or a bit map indicating the desired destinations. When
a packet arrives at a router, the router checks all the destinations to determine the
set of output lines that will be needed. (An output line is needed if it is the best
route to at least one of the destinations.) The router generates a new copy of the
packet for each output line to be used and includes in each packet only those dest-
inations that are to use the line. In effect, the destination set is partitioned among


---

<a id="page-393"></a>

<!-- Page 393 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 381
the output lines. After a sufficient number of hops, each packet will carry only
one destination like a normal packet. Multidestination routing is like using sepa-
rately addressed packets, except that when several packets must follow the same
route, one of them pays full fare and the rest ride free. The network bandwidth is
therefore used more efficiently. However, this scheme still requires the source to
know all the destinations, plus it is as much work for a router to determine where
to send one multidestination packet as it is for multiple distinct packets.
We have already seen a better broadcast routing technique: flooding. When
implemented with a sequence number per source, flooding uses links efficiently
with a decision rule at routers that is relatively simple. Although flooding is ill-
suited for ordinary point-to-point communication, it rates serious consideration for
broadcasting. However, it turns out that we can do better still once the shortest
path routes for regular packets have been computed.
The idea for reverse path forwarding is elegant and remarkably simple once
it has been pointed out (Dalal and Metcalfe, 1978). When a broadcast packet ar-
rives at a router, the router checks to see if the packet arrived on the link that is
normally used for sending packets toward the source of the broadcast. If so, there
is an excellent chance that the broadcast packet itself followed the best route from
the router and is therefore the first copy to arrive at the router. This being the
case, the router forwards copies of it onto all links except the one it arrived on. If,
however, the broadcast packet arrived on a link other than the preferred one for
reaching the source, the packet is discarded as a likely duplicate.
## B C B C I
A D A D
## F E F F H J N
E
I G I G
## A D E K G O M O
J
## H N H L J
## L N E C G D N K
O O
K K
H B L H

L B
(a) (b) (c)
Figure 5-15. Reverse path forwarding. (a) A network. (b) A sink tree. (c) The
tree built by reverse path forwarding.
An example of reverse path forwarding is shown in Fig. 5-15. Part (a) shows
a network, part (b) shows a sink tree for router I of that network, and part (c)
shows how the reverse path algorithm works. On the first hop, I sends packets to
F, H, J, and N, as indicated by the second row of the tree. Each of these packets
arrives on the preferred path to I (assuming that the preferred path falls along the
sink tree) and is so indicated by a circle around the letter. On the second hop,


---

<a id="page-394"></a>

<!-- Page 394 of 888 -->

382 THE NETWORK LAYER CHAP. 5
eight packets are generated, two by each of the routers that received a packet on
the first hop. As it turns out, all eight of these arrive at previously unvisited rout-
ers, and five of these arrive along the preferred line. Of the six packets generated
on the third hop, only three arrive on the preferred path (at C, E, and K); the oth-
ers are duplicates. After five hops and 24 packets, the broadcasting terminates,
compared with four hops and 14 packets had the sink tree been followed exactly.
The principal advantage of reverse path forwarding is that it is efficient while
being easy to implement. It sends the broadcast packet over each link only once
in each direction, just as in flooding, yet it requires only that routers know how to
reach all destinations, without needing to remember sequence numbers (or use
other mechanisms to stop the flood) or list all destinations in the packet.
Our last broadcast algorithm improves on the behavior of reverse path for-
warding. It makes explicit use of the sink tree-or any other convenient spanning
tree-for the router initiating the broadcast. A spanning tree is a subset of the
network that includes all the routers but contains no loops. Sink trees are spanning
trees. If each router knows which of its lines belong to the spanning tree, it can
copy an incoming broadcast packet onto all the spanning tree lines except the one
it arrived on. This method makes excellent use of bandwidth, generating the
absolute minimum number of packets necessary to do the job. In Fig. 5-15, for
example, when the sink tree of part (b) is used as the spanning tree, the broadcast
packet is sent with the minimum 14 packets. The only problem is that each router
must have knowledge of some spanning tree for the method to be applicable.
Sometimes this information is available (e.g., with link state routing, all routers
know the complete topology, so they can compute a spanning tree) but sometimes
it is not (e.g., with distance vector routing).
#### 5.2.8 Multicast Routing
Some applications, such as a multiplayer game or live video of a sports event
streamed to many viewing locations, send packets to multiple receivers. Unless
the group is very small, sending a distinct packet to each receiver is expensive.
On the other hand, broadcasting a packet is wasteful if the group consists of, say,
1000 machines on a million-node network, so that most receivers are not inter-
ested in the message (or worse yet, they are definitely interested but are not sup-
posed to see it). Thus, we need a way to send messages to well-defined groups
that are numerically large in size but small compared to the network as a whole.
Sending a message to such a group is called multicasting, and the routing al-
gorithm used is called multicast routing. All multicasting schemes require some
way to create and destroy groups and to identify which routers are members of a
group. How these tasks are accomplished is not of concern to the routing algo-
rithm. For now, we will assume that each group is identified by a multicast ad-
dress and that routers know the groups to which they belong. We will revisit
group membership when we describe the network layer of the Internet in Sec. 5.6.


---

<a id="page-395"></a>

<!-- Page 395 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 383
Multicast routing schemes build on the broadcast routing schemes we have al-
ready studied, sending packets along spanning trees to deliver the packets to the
members of the group while making efficient use of bandwidth. However, the
best spanning tree to use depends on whether the group is dense, with receivers
scattered over most of the network, or sparse, with much of the network not be-
longing to the group. In this section we will consider both cases.
If the group is dense, broadcast is a good start because it efficiently gets the
packet to all parts of the network. But broadcast will reach some routers that are
not members of the group, which is wasteful. The solution explored by Deering
and Cheriton (1990) is to prune the broadcast spanning tree by removing links that
do not lead to members. The result is an efficient multicast spanning tree.
As an example, consider the two groups, 1 and 2, in the network shown in
Fig. 5-16(a). Some routers are attached to hosts that belong to one or both of
these groups, as indicated in the figure. A spanning tree for the leftmost router is
shown in Fig. 5-16(b). This tree can be used for broadcast but is overkill for mu-
lticast, as can be seen from the two pruned versions that are shown next. In
Fig. 5-16(c), all the links that do not lead to hosts that are members of group 1
have been removed. The result is the multicast spanning tree for the leftmost
router to send to group 1. Packets are forwarded only along this spanning tree,
which is more efficient than the broadcast tree because there are 7 links instead of
10. Fig. 5-16(d) shows the multicast spanning tree after pruning for group 2. It is
efficient too, with only five links this time. It also shows that different multicast
groups have different spanning trees.
Various ways of pruning the spanning tree are possible. The simplest one can
be used if link state routing is used and each router is aware of the complete topo-
logy, including which hosts belong to which groups. Each router can then con-
struct its own pruned spanning tree for each sender to the group in question by
constructing a sink tree for the sender as usual and then removing all links that do
not connect group members to the sink node. MOSPF (Multicast OSPF) is an
example of a link state protocol that works in this way (Moy, 1994).
With distance vector routing, a different pruning strategy can be followed.
The basic algorithm is reverse path forwarding. However, whenever a router with
no hosts interested in a particular group and no connections to other routers re-
ceives a multicast message for that group, it responds with a PRUNE message, tel-
ling the neighbor that sent the message not to send it any more multicasts from the
sender for that group. When a router with no group members among its own hosts
has received such messages on all the lines to which it sends the multicast, it, too,
can respond with a PRUNE message. In this way, the spanning tree is recursively
pruned. DVMRP (Distance Vector Multicast Routing Protocol) is an example
of a multicast routing protocol that works this way (Waitzman et al., 1988).
Pruning results in efficient spanning trees that use only the links that are actu-
ally needed to reach members of the group. One potential disadvantage is that it
is lots of work for routers, especially for large networks. Suppose that a network


---

<a id="page-396"></a>

<!-- Page 396 of 888 -->

384 THE NETWORK LAYER CHAP. 5
2 1 2 1
1, 2
1, 2
1, 2
1, 2

2 2 2

(a) (b)

1 2
1 2 2 2

(c) (d)
Figure 5-16. (a) A network. (b) A spanning tree for the leftmost router. (c) A
multicast tree for group 1. (d) A multicast tree for group 2.
has n groups, each with an average of m nodes. At each router and for each
group, m pruned spanning trees must be stored, for a total of mn trees. For exam-
ple, Fig. 5-16(c) gives the spanning tree for the leftmost router to send to group 1.
The spanning tree for the rightmost router to send to group 1 (not shown) will
look quite different, as packets will head directly for group members rather than
via the left side of the graph. This in turn means that routers must forward pack-
ets destined to group 1 in different directions depending on which node is sending
to the group. When many large groups with many senders exist, considerable
storage is needed to store all the trees.
An alternative design uses core-based trees to compute a single spanning tree
for the group (Ballardie et al., 1993). All of the routers agree on a root (called the
core or rendezvous point) and build the tree by sending a packet from each
member to the root. The tree is the union of the paths traced by these packets.
Fig. 5-17(a) shows a core-based tree for group 1. To send to this group, a sender
sends a packet to the core. When the packet reaches the core, it is forwarded down
the tree. This is shown in Fig. 5-17(b) for the sender on the righthand side of the
network. As a performance optimization, packets destined for the group do not
need to reach the core before they are multicast. As soon as a packet reaches the


---

<a id="page-397"></a>

<!-- Page 397 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 385
tree, it can be forwarded up toward the root, as well as down all the other
branches. This is the case for the sender at the top of Fig. 5-17(b).
1 1
Sender
1 1
Sender
1 1
Core
Core
1 1
1 1
(a) (b)
Figure 5-17. (a) Core-based tree for group 1. (b) Sending to group 1.
Having a shared tree is not optimal for all sources. For example, in Fig. 5-
17(b), the packet from the sender on the righthand side reaches the top-right group
member via the core in three hops, instead of directly. The inefficiency depends
on where the core and senders are located, but often it is reasonable when the core
is in the middle of the senders. When there is only a single sender, as in a video
that is streamed to a group, using the sender as the core is optimal.
Also of note is that shared trees can be a major savings in storage costs, mes-
sages sent, and computation. Each router has to keep only one tree per group, in-
stead of m trees. Further, routers that are not part of the tree do no work at all to
support the group. For this reason, shared tree approaches like core-based trees
are used for multicasting to sparse groups in the Internet as part of popular proto-
cols such as PIM (Protocol Independent Multicast) (Fenner et al., 2006).
#### 5.2.9 Anycast Routing
So far, we have covered delivery models in which a source sends to a single
destination (called unicast), to all destinations (called broadcast), and to a group
of destinations (called multicast). Another delivery model, called anycast is
sometimes also useful. In anycast, a packet is delivered to the nearest member of
a group (Partridge et al., 1993). Schemes that find these paths are called anycast
routing.
Why would we want anycast? Sometimes nodes provide a service, such as
time of day or content distribution for which it is getting the right information all
that matters, not the node that is contacted; any node will do. For example, any-
cast is used in the Internet as part of DNS, as we will see in Chap. 7.
Luckily, we will not have to devise new routing schemes for anycast because
regular distance vector and link state routing can produce anycast routes. Suppose


---

<a id="page-398"></a>

<!-- Page 398 of 888 -->

386 THE NETWORK LAYER CHAP. 5
we want to anycast to the members of group 1. They will all be given the address
''1,'' instead of different addresses. Distance vector routing will distribute vectors
as usual, and nodes will choose the shortest path to destination 1. This will result
in nodes sending to the nearest instance of destination 1. The routes are shown in
Fig. 5-18(a). This procedure works because the routing protocol does not realize
that there are multiple instances of destination 1. That is, it believes that all the
instances of node 1 are the same node, as in the topology shown in Fig. 5-18(b).

1 1

(a) (b)
Figure 5-18. (a) Anycast routes to group 1. (b) Topology seen by the routing protocol.
This procedure works for link state routing as well, although there is the
added consideration that the routing protocol must not find seemingly short paths
that pass through node 1. This would result in jumps through hyperspace, since
the instances of node 1 are really nodes located in different parts of the network.
However, link state protocols already make this distinction between routers and
hosts. We glossed over this fact earlier because it was not needed for our dis-
cussion.
#### 5.2.10 Routing for Mobile Hosts
Millions of people use computers while on the go, from truly mobile situa-
tions with wireless devices in moving cars, to nomadic situations in which laptop
computers are used in a series of different locations. We will use the term mobile
hosts to mean either category, as distinct from stationary hosts that never move.
Increasingly, people want to stay connected wherever in the world they may be, as
easily as if they were at home. These mobile hosts introduce a new complication:
to route a packet to a mobile host, the network first has to find it.
The model of the world that we will consider is one in which all hosts are as-
sumed to have a permanent home location that never changes. Each hosts also
has a permanent home address that can be used to determine its home location,
analogous to the way the telephone number 1-212-5551212 indicates the United
States (country code 1) and Manhattan (212). The routing goal in systems with


---

<a id="page-399"></a>

<!-- Page 399 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 387
mobile hosts is to make it possible to send packets to mobile hosts using their
fixed home addresses and have the packets efficiently reach them wherever they
may be. The trick, of course, is to find them.
Some discussion of this model is in order. A different model would be to
recompute routes as the mobile host moves and the topology changes. We could
then simply use the routing schemes described earlier in this section. However,
with a growing number of mobile hosts, this model would soon lead to the entire
network endlessly computing new routes. Using the home addresses greatly re-
duces this burden.
Another alternative would be to provide mobility above the network layer,
which is what typically happens with laptops today. When they are moved to new
Internet locations, laptops acquire new network addresses. There is no association
between the old and new addresses; the network does not know that they belonged
to the same laptop. In this model, a laptop can be used to browse the Web, but
other hosts cannot send packets to it (for example, for an incoming call), without
building a higher layer location service, for example, signing into Skype again
after moving. Moreover, connections cannot be maintained while the host is mov-
ing; new connections must be started up instead. Network-layer mobility is useful
to fix these problems.
The basic idea used for mobile routing in the Internet and cellular networks is
for the mobile host to tell a host at the home location where it is now. This host,
which acts on behalf of the mobile host, is called the home agent. Once it knows
where the mobile host is currently located, it can forward packets so that they are
delivered.
Fig. 5-19 shows mobile routing in action. A sender in the northwest city of
Seattle wants to send a packet to a host normally located across the United States
in New York. The case of interest to us is when the mobile host is not at home.
Instead, it is temporarily in San Diego.
The mobile host in San Diego must acquire a local network address before it
can use the network. This happens in the normal way that hosts obtain network
addresses; we will cover how this works for the Internet later in this chapter. The
local address is called a care of address. Once the mobile host has this address,
it can tell its home agent where it is now. It does this by sending a registration
message to the home agent (step 1) with the care of address. The message is
shown with a dashed line in Fig. 5-19 to indicate that it is a control message, not a
data message.
Next, the sender sends a data packet to the mobile host using its permanent
address (step 2). This packet is routed by the network to the host's home location
because that is where the home address belongs. In New York, the home agent
intercepts this packet because the mobile host is away from home. It then wraps
or encapsulates the packet with a new header and sends this bundle to the care of
address (step 3). This mechanism is called tunneling. It is very important in the
Internet so we will look at it in more detail later.


---

<a id="page-400"></a>

<!-- Page 400 of 888 -->

388 THE NETWORK LAYER CHAP. 5
Sender
2:Sendtohomeaddress
4: Reply
to sender
5: Tunnel
to ad c d a r r e e s o s f 1: 3 R : e T g u i n s n te e r l c to ar c e a o re fa o d f d a r d e d s r s ess H h o o m m e e a a d g d e r n e t s a s t
Mobile host at
care of address
Figure 5-19. Packet routing for mobile hosts.
When the encapsulated packet arrives at the care of address, the mobile host
unwraps it and retrieves the packet from the sender. The mobile host then sends
its reply packet directly to the sender (step 4). The overall route is called triangle
routing because it may be circuitous if the remote location is far from the home
location. As part of step 4, the sender may learn the current care of address. Sub-
sequent packets can be routed directly to the mobile host by tunneling them to the
care of address (step 5), bypassing the home location entirely. If connectivity is
lost for any reason as the mobile moves, the home address can always be used to
reach the mobile.
An important aspect that we have omitted from this description is security. In
general, when a host or router gets a message of the form ''Starting right now,
please send all of Stephany's mail to me,'' it might have a couple of questions
about whom it is talking to and whether this is a good idea. Security information
is included in the messages so that their validity can be checked with crypto-
graphic protocols that we will study in Chap. 8.
There are many variations on mobile routing. The scheme above is modeled
on IPv6 mobility, the form of mobility used in the Internet (Johnson et al., 2004)
and as part of IP-based cellular networks such as UMTS. We showed the sender
to be a stationary node for simplicity, but the designs let both nodes be mobile
hosts. Alternatively, the host may be part of a mobile network, for example a
computer in a plane. Extensions of the basic scheme support mobile networks
with no work on the part of the hosts (Devarapalli et al., 2005).
Some schemes make use of a foreign (i.e., remote) agent, similar to the home
agent but at the foreign location, or analogous to the VLR (Visitor Location Reg-
ister) in cellular networks. However, in more recent schemes, the foreign agent is
not needed; mobile hosts act as their own foreign agents. In either case, know-
ledge of the temporary location of the mobile host is limited to a small number of


---

<a id="page-401"></a>

<!-- Page 401 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 389
hosts (e.g., the mobile, home agent, and senders) so that the many routers in a
large network do not need to recompute routes.
For more information about mobile routing, see also Perkins (1998, 2002) and
Snoeren and Balakrishnan (2000).
#### 5.2.11 Routing in Ad Hoc Networks
We have now seen how to do routing when the hosts are mobile but the rout-
ers are fixed. An even more extreme case is one in which the routers themselves
are mobile. Among the possibilities are emergency workers at an earthquake site,
military vehicles on a battlefield, a fleet of ships at sea, or a gathering of people
with laptop computers in an area lacking 802.11.
In all these cases, and others, each node communicates wirelessly and acts as
both a host and a router. Networks of nodes that just happen to be near each other
are called ad hoc networks or MANETs (Mobile Ad hoc NETworks). Let us
now examine them briefly. More information can be found in Perkins (2001).
What makes ad hoc networks different from wired networks is that the topo-
logy is suddenly tossed out the window. Nodes can come and go or appear in new
places at the drop of a bit. With a wired network, if a router has a valid path to
some destination, that path continues to be valid barring failures, which are hope-
fully rare. With an ad hoc network, the topology may be changing all the time, so
the desirability and even the validity of paths can change spontaneously without
warning. Needless to say, these circumstances make routing in ad hoc networks
more challenging than routing in their fixed counterparts.
Many, many routing algorithms for ad hoc networks have been proposed.
However, since ad hoc networks have been little used in practice compared to
mobile networks, it is unclear which of these protocols are most useful. As an ex-
ample, we will look at one of the most popular routing algorithms, AODV (Ad
hoc On-demand Distance Vector) (Perkins and Royer, 1999). It is a relative of
the distance vector algorithm that has been adapted to work in a mobile environ-
ment, in which nodes often have limited bandwidth and battery lifetimes. Let us
now see how it discovers and maintains routes.
Route Discovery
In AODV, routes to a destination are discovered on demand, that is, only
when a somebody wants to send a packet to that destination. This saves much
work that would otherwise be wasted when the topology changes before the route
is used. At any instant, the topology of an ad hoc network can be described by a
graph of connected nodes. Two nodes are connected (i.e., have an arc between
them in the graph) if they can communicate directly using their radios. A basic
but adequate model that is sufficient for our purposes is that each node can com-
municate with all other nodes that lie within its coverage circle. Real networks are


---

<a id="page-402"></a>

<!-- Page 402 of 888 -->

390 THE NETWORK LAYER CHAP. 5
more complicated, with buildings, hills, and other obstacles that block communi-
cation, and nodes for which A is connected to B but B is not connected to A be-
cause A has a more powerful transmitter than B. However, for simplicity, we will
assume all connections are symmetric.
To describe the algorithm, consider the newly formed ad hoc network of
Fig. 5-20. Suppose that a process at node A wants to send a packet to node I. The
AODV algorithm maintains a distance vector table at each node, keyed by desti-
nation, giving information about that destination, including the neighbor to which
to send packets to reach the destination. First, A looks in its table and does not
find an entry for I. It now has to discover a route to I. This property of discover-
ing routes only when they are needed is what makes this algorithm ''on demand.''
Range of
A's broadcast
## A B A B A B A B
C C C C
D D D D
E E E E
F F F F
G G G G
## H I H I H I H I
(a) (b) (c) (d)
Figure 5-20. (a) Range of A's broadcast. (b) After B and D receive it. (c) After
C, F, and G receive it. (d) After E, H, and I receive it. The shaded nodes are
new recipients. The dashed lines show possible reverse routes. The solid lines
show the discovered route.
To locate I, A constructs a ROUTE REQUEST packet and broadcasts it using
flooding, as described in Sec. 5.2.3. The transmission from A reaches B and D, as
illustrated in Fig. 5-20(a). Each node rebroadcasts the request, which continues to
reach nodes F, G, and C in Fig. 5-20(c) and nodes H, E, and I in Fig. 5-20(d). A
sequence number set at the source is used to weed out duplicates during the flood.
For example, D discards the transmission from B in Fig. 5-20(c) because it has al-
ready forwarded the request.
Eventually, the request reaches node I, which constructs a ROUTE REPLY
packet. This packet is unicast to the sender along the reverse of the path followed
by the request. For this to work, each intermediate node must remember the node
that sent it the request. The arrows in Fig. 5-20(b)-(d) show the reverse route
information that is stored. Each intermediate node also increments a hop count as
it forwards the reply. This tells the nodes how far they are from the destination.
The replies tell each intermediate node which neighbor to use to reach the destina-
tion: it is the node that sent them the reply. Intermediate nodes G and D put the


---

<a id="page-403"></a>

<!-- Page 403 of 888 -->

SEC. 5.2 ROUTING ALGORITHMS 391
best route they hear into their routing tables as they process the reply. When the
reply reaches A, a new route, ADGI, has been created.
In a large network, the algorithm generates many broadcasts, even for destina-
tions that are close by. To reduce overhead, the scope of the broadcasts is limited
using the IP packet's Time to live field. This field is initialized by the sender and
decremented on each hop. If it hits 0, the packet is discarded instead of being
broadcast. The route discovery process is then modified as follows. To locate a
destination, the sender broadcasts a ROUTE REQUEST packet with Time to live set
to 1. If no response comes back within a reasonable time, another one is sent, this
time with Time to live set to 2. Subsequent attempts use 3, 4, 5, etc. In this way,
the search is first attempted locally, then in increasingly wider rings.
Route Maintenance
Because nodes can move or be switched off, the topology can change spon-
taneously. For example, in Fig. 5-20, if G is switched off, A will not realize that
the route it was using to I (ADGI) is no longer valid. The algorithm needs to be
able to deal with this. Periodically, each node broadcasts a Hello message. Each
of its neighbors is expected to respond to it. If no response is forthcoming, the
broadcaster knows that that neighbor has moved out of range or failed and is no
longer connected to it. Similarly, if it tries to send a packet to a neighbor that
does not respond, it learns that the neighbor is no longer available.
This information is used to purge routes that no longer work. For each pos-
sible destination, each node, N, keeps track of its active neighbors that have fed it
a packet for that destination during the last ∆T seconds. When any of N's neigh-
bors becomes unreachable, it checks its routing table to see which destinations
have routes using the now-gone neighbor. For each of these routes, the active
neighbors are informed that their route via N is now invalid and must be purged
from their routing tables. In our example, D purges its entries for G and I from its
routing table and notifies A, which purges its entry for I. In the general case, the
active neighbors tell their active neighbors, and so on, recursively, until all routes
depending on the now-gone node are purged from all routing tables.
At this stage, the invalid routes have been purged from the network, and send-
ers can find new, valid routes by using the discovery mechanism that we de-
scribed. However, there is a complication. Recall that distance vector protocols
can suffer from slow convergence or count-to-infinity problems after a topology
change in which they confuse old, invalid routes with new, valid routes.
To ensure rapid convergence, routes include a sequence number that is con-
trolled by the destination. The destination sequence number is like a logical
clock. The destination increments it every time that it sends a fresh ROUTE
REPLY. Senders ask for a fresh route by including in the ROUTE REQUEST the
destination sequence number of the last route they used, which will either be the
sequence number of the route that was just purged, or 0 as an initial value. The


---

<a id="page-404"></a>

<!-- Page 404 of 888 -->

392 THE NETWORK LAYER CHAP. 5
request will be broadcast until a route with a higher sequence number is found.
Intermediate nodes store the routes that have a higher sequence number, or the
fewest hops for the current sequence number.
In the spirit of an on demand protocol, intermediate nodes only store the
routes that are in use. Other route information learned during broadcasts is timed
out after a short delay. Discovering and storing only the routes that are used helps
to save bandwidth and battery life compared to a standard distance vector protocol
that periodically broadcasts updates.
So far, we have considered only a single route, from A to I. To further save
resources, route discovery and maintenance are shared when routes overlap. For
instance, if B also wants to send packets to I, it will perform route discovery.
However, in this case the request will first reach D, which already has a route to I.
Node D can then generate a reply to tell B the route without any additional work
being required.
There are many other ad hoc routing schemes. Another well-known on de-
mand scheme is DSR (Dynamic Source Routing) (Johnson et al., 2001). A dif-
ferent strategy based on geography is explored by GPSR (Greedy Perimeter State-
less Routing) (Karp and Kung, 2000). If all nodes know their geographic posi-
tions, forwarding to a destination can proceed without route computation by sim-
ply heading in the right direction and circling back to escape any dead ends.
Which protocols win out will depend on the kinds of ad hoc networks that prove
useful in practice.
### 5.3 CONGESTION CONTROL ALGORITHMS
Too many packets present in (a part of) the network causes packet delay and
loss that degrades performance. This situation is called congestion. The network
and transport layers share the responsibility for handling congestion. Since con-
gestion occurs within the network, it is the network layer that directly experiences
it and must ultimately determine what to do with the excess packets. However,
the most effective way to control congestion is to reduce the load that the tran-
sport layer is placing on the network. This requires the network and transport lay-
ers to work together. In this chapter we will look at the network aspects of con-
gestion. In Chap. 6, we will complete the topic by covering the transport aspects
of congestion.
Figure 5-21 depicts the onset of congestion. When the number of packets
hosts send into the network is well within its carrying capacity, the number deliv-
ered is proportional to the number sent. If twice as many are sent, twice as many
are delivered. However, as the offered load approaches the carrying capacity,
bursts of traffic occasionally fill up the buffers inside routers and some packets
are lost. These lost packets consume some of the capacity, so the number of de-
livered packets falls below the ideal curve. The network is now congested.


---

<a id="page-405"></a>

<!-- Page 405 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 393
Ideal
)ces/stekcap(tupdooG
Capacity of
the network
Desirable
response
Congestion
Onset of
collapse
congestion
Offered load (packet/sec)
Figure 5-21. With too much traffic, performance drops sharply.
Unless the network is well designed, it may experience a congestion collapse,
in which performance plummets as the offered load increases beyond the capaci-
ty. This can happen because packets can be sufficiently delayed inside the net-
work that they are no longer useful when they leave the network. For example, in
the early Internet, the time a packet spent waiting for a backlog of packets ahead
of it to be sent over a slow 56-kbps link could reach the maximum time it was al-
lowed to remain in the network. It then had to be thrown away. A different failure
mode occurs when senders retransmit packets that are greatly delayed, thinking
that they have been lost. In this case, copies of the same packet will be delivered
by the network, again wasting its capacity. To capture these factors, the y-axis of
Fig. 5-21 is given as goodput, which is the rate at which useful packets are deliv-
ered by the network.
We would like to design networks that avoid congestion where possible and
do not suffer from congestion collapse if they do become congested. Unfortunate-
ly, congestion cannot wholly be avoided. If all of a sudden, streams of packets
begin arriving on three or four input lines and all need the same output line, a
queue will build up. If there is insufficient memory to hold all of them, packets
will be lost. Adding more memory may help up to a point, but Nagle (1987) real-
ized that if routers have an infinite amount of memory, congestion gets worse, not
better. This is because by the time packets get to the front of the queue, they have
already timed out (repeatedly) and duplicates have been sent. This makes matters
worse, not better-it leads to congestion collapse.
Low-bandwidth links or routers that process packets more slowly than the line
rate can also become congested. In this case, the situation can be improved by
directing some of the traffic away from the bottleneck to other parts of the net-
work. Eventually, however, all regions of the network will be congested. In this
situation, there is no alternative but to shed load or build a faster network.
It is worth pointing out the difference between congestion control and flow
control, as the relationship is a very subtle one. Congestion control has to do with


---

<a id="page-406"></a>

<!-- Page 406 of 888 -->

394 THE NETWORK LAYER CHAP. 5
making sure the network is able to carry the offered traffic. It is a global issue, in-
volving the behavior of all the hosts and routers. Flow control, in contrast, relates
to the traffic between a particular sender and a particular receiver. Its job is to
make sure that a fast sender cannot continually transmit data faster than the re-
ceiver is able to absorb it.
To see the difference between these two concepts, consider a network made
up of 100-Gbps fiber optic links on which a supercomputer is trying to force feed
a large file to a personal computer that is capable of handling only 1 Gbps. Al-
though there is no congestion (the network itself is not in trouble), flow control is
needed to force the supercomputer to stop frequently to give the personal com-
puter a chance to breathe.
At the other extreme, consider a network with 1-Mbps lines and 1000 large
computers, half of which are trying to transfer files at 100 kbps to the other half.
Here, the problem is not that of fast senders overpowering slow receivers, but that
the total offered traffic exceeds what the network can handle.
The reason congestion control and flow control are often confused is that the
best way to handle both problems is to get the host to slow down. Thus, a host
can get a ''slow down'' message either because the receiver cannot handle the
load or because the network cannot handle it. We will come back to this point in
Chap. 6.
We will start our study of congestion control by looking at the approaches that
can be used at different time scales. Then we will look at approaches to pre-
venting congestion from occurring in the first place, followed by approaches for
coping with it once it has set in.
#### 5.3.1 Approaches to Congestion Control
The presence of congestion means that the load is (temporarily) greater than
the resources (in a part of the network) can handle. Two solutions come to mind:
increase the resources or decrease the load. As shown in Fig. 5-22, these solu-
tions are usually applied on different time scales to either prevent congestion or
react to it once it has occurred.
Network Traffic-aware Admission Traffic Load
provisioning routing control throttling shedding
Slower Faster
(Preventative) (Reactive)
Figure 5-22. Timescales of approaches to congestion control.
The most basic way to avoid congestion is to build a network that is well
matched to the traffic that it carries. If there is a low-bandwidth link on the path
along which most traffic is directed, congestion is likely. Sometimes resources


---

<a id="page-407"></a>

<!-- Page 407 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 395
can be added dynamically when there is serious congestion, for example, turning
on spare routers or enabling lines that are normally used only as backups (to make
the system fault tolerant) or purchasing bandwidth on the open market. More
often, links and routers that are regularly heavily utilized are upgraded at the earli-
est opportunity. This is called provisioning and happens on a time scale of
months, driven by long-term traffic trends.
To make the most of the existing network capacity, routes can be tailored to
traffic patterns that change during the day as network users wake and sleep in dif-
ferent time zones. For example, routes may be changed to shift traffic away from
heavily used paths by changing the shortest path weights. Some local radio sta-
tions have helicopters flying around their cities to report on road congestion to
make it possible for their mobile listeners to route their packets (cars) around
hotspots. This is called traffic-aware routing. Splitting traffic across multiple
paths is also helpful.
However, sometimes it is not possible to increase capacity. The only way
then to beat back the congestion is to decrease the load. In a virtual-circuit net-
work, new connections can be refused if they would cause the network to become
congested. This is called admission control.
At a finer granularity, when congestion is imminent the network can deliver
feedback to the sources whose traffic flows are responsible for the problem. The
network can request these sources to throttle their traffic, or it can slow down the
traffic itself.
Two difficulties with this approach are how to identify the onset of conges-
tion, and how to inform the source that needs to slow down. To tackle the first
issue, routers can monitor the average load, queueing delay, or packet loss. In all
cases, rising numbers indicate growing congestion.
To tackle the second issue, routers must participate in a feedback loop with
the sources. For a scheme to work correctly, the time scale must be adjusted care-
fully. If every time two packets arrive in a row, a router yells STOP and every
time a router is idle for 20 µsec, it yells GO, the system will oscillate wildly and
never converge. On the other hand, if it waits 30 minutes to make sure before
saying anything, the congestion-control mechanism will react too sluggishly to be
of any use. Delivering timely feedback is a nontrivial matter. An added concern
is having routers send more messages when the network is already congested.
Finally, when all else fails, the network is forced to discard packets that it
cannot deliver. The general name for this is load shedding. A good policy for
choosing which packets to discard can help to prevent congestion collapse.
#### 5.3.2 Traffic-Aware Routing
The first approach we will examine is traffic-aware routing. The routing
schemes we looked at in Sec 5.2 used fixed link weights. These schemes adapted
to changes in topology, but not to changes in load. The goal in taking load into


---

<a id="page-408"></a>

<!-- Page 408 of 888 -->

396 THE NETWORK LAYER CHAP. 5
account when computing routes is to shift traffic away from hotspots that will be
the first places in the network to experience congestion.
The most direct way to do this is to set the link weight to be a function of the
(fixed) link bandwidth and propagation delay plus the (variable) measured load or
average queuing delay. Least-weight paths will then favor paths that are more
lightly loaded, all else being equal.
Traffic-aware routing was used in the early Internet according to this model
(Khanna and Zinky, 1989). However, there is a peril. Consider the network of
Fig. 5-23, which is divided into two parts, East and West, connected by two links,
CF and EI. Suppose that most of the traffic between East and West is using link
CF, and, as a result, this link is heavily loaded with long delays. Including queue-
ing delay in the weight used for the shortest path calculation will make EI more
attractive. After the new routing tables have been installed, most of the East-West
traffic will now go over EI, loading this link. Consequently, in the next update,
CF will appear to be the shortest path. As a result, the routing tables may oscil-
late wildly, leading to erratic routing and many potential problems.
West East
G
B C F
H
A
E

D J
Figure 5-23. A network in which the East and West parts are connected by two links.
If load is ignored and only bandwidth and propagation delay are considered,
this problem does not occur. Attempts to include load but change weights within
a narrow range only slow down routing oscillations. Two techniques can contri-
bute to a successful solution. The first is multipath routing, in which there can be
multiple paths from a source to a destination. In our example this means that the
traffic can be spread across both of the East to West links. The second one is for
the routing scheme to shift traffic across routes slowly enough that it is able to
converge, as in the scheme of Gallagher (1977).
Given these difficulties, in the Internet routing protocols do not generally ad-
just their routes depending on the load. Instead, adjustments are made outside the
routing protocol by slowly changing its inputs. This is called traffic engineering.


---

<a id="page-409"></a>

<!-- Page 409 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 397
#### 5.3.3 Admission Control
One technique that is widely used in virtual-circuit networks to keep conges-
tion at bay is admission control. The idea is simple: do not set up a new virtual
circuit unless the network can carry the added traffic without becoming congest-
ed. Thus, attempts to set up a virtual circuit may fail. This is better than the alter-
native, as letting more people in when the network is busy just makes matters
worse. By analogy, in the telephone system, when a switch gets overloaded it
practices admission control by not giving dial tones.
The trick with this approach is working out when a new virtual circuit will
lead to congestion. The task is straightforward in the telephone network because
of the fixed bandwidth of calls (64 kbps for uncompressed audio). However, vir-
tual circuits in computer networks come in all shapes and sizes. Thus, the circuit
must come with some characterization of its traffic if we are to apply admission
control.
Traffic is often described in terms of its rate and shape. The problem of how
to describe it in a simple yet meaningful way is difficult because traffic is typi-
cally bursty-the average rate is only half the story. For example, traffic that
varies while browsing the Web is more difficult to handle than a streaming movie
with the same long-term throughput because the bursts of Web traffic are more
likely to congest routers in the network. A commonly used descriptor that cap-
tures this effect is the leaky bucket or token bucket. A leaky bucket has two pa-
rameters that bound the average rate and the instantaneous burst size of traffic.
Since leaky buckets are widely used for quality of service, we will go over them
in detail in Sec. 5.4.
Armed with traffic descriptions, the network can decide whether to admit the
new virtual circuit. One possibility is for the network to reserve enough capacity
along the paths of each of its virtual circuits that congestion will not occur. In this
case, the traffic description is a service agreement for what the network will guar-
antee its users. We have prevented congestion but veered into the related topic of
quality of service a little too early; we will return to it in the next section.
Even without making guarantees, the network can use traffic descriptions for
admission control. The task is then to estimate how many circuits will fit within
the carrying capacity of the network without congestion. Suppose that virtual cir-
cuits that may blast traffic at rates up to 10 Mbps all pass through the same 100-
Mbps physical link. How many circuits should be admitted? Clearly, 10 circuits
can be admitted without risking congestion, but this is wasteful in the normal case
since it may rarely happen that all 10 are transmitting full blast at the same time.
In real networks, measurements of past behavior that capture the statistics of
transmissions can be used to estimate the number of circuits to admit, to trade bet-
ter performance for acceptable risk.
Admission control can also be combined with traffic-aware routing by consid-
ering routes around traffic hotspots as part of the setup procedure. For example,


---

<a id="page-410"></a>

<!-- Page 410 of 888 -->

398 THE NETWORK LAYER CHAP. 5
consider the network illustrated in Fig. 5-24(a), in which two routers are congest-
ed, as indicated.
A Congestion A
B
B
Virtual
circuit
Congestion
(a) (b)
Figure 5-24. (a) A congested network. (b) The portion of the network that is not
congested. A virtual circuit from A to B is also shown.
Suppose that a host attached to router A wants to set up a connection to a host
attached to router B. Normally, this connection would pass through one of the
congested routers. To avoid this situation, we can redraw the network as shown in
Fig. 5-24(b), omitting the congested routers and all of their lines. The dashed line
shows a possible route for the virtual circuit that avoids the congested routers.
Shaikh et al. (1999) give a design for this kind of load-sensitive routing.
#### 5.3.4 Traffic Throttling
In the Internet and many other computer networks, senders adjust their trans-
missions to send as much traffic as the network can readily deliver. In this setting,
the network aims to operate just before the onset of congestion. When congestion
is imminent, it must tell the senders to throttle back their transmissions and slow
down. This feedback is business as usual rather than an exceptional situation. The
term congestion avoidance is sometimes used to contrast this operating point
with the one in which the network has become (overly) congested.
Let us now look at some approaches to throttling traffic that can be used in
both datagram networks and virtual-circuit networks. Each approach must solve
two problems. First, routers must determine when congestion is approaching,
ideally before it has arrived. To do so, each router can continuously monitor the
resources it is using. Three possibilities are the utilization of the output links, the
buffering of queued packets inside the router, and the number of packets that are
lost due to insufficient buffering. Of these possibilities, the second one is the
most useful. Averages of utilization do not directly account for the burstiness of


---

<a id="page-411"></a>

<!-- Page 411 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 399
most traffic-a utilization of 50% may be low for smooth traffic and too high for
highly variable traffic. Counts of packet losses come too late. Congestion has al-
ready set in by the time that packets are lost.
The queueing delay inside routers directly captures any congestion experi-
enced by packets. It should be low most of time, but will jump when there is a
burst of traffic that generates a backlog. To maintain a good estimate of the
queueing delay, d, a sample of the instantaneous queue length, s, can be made per-
iodically and d updated according to
d =α d + (1 − α)s
new old
where the constant α determines how fast the router forgets recent history. This is
called an EWMA (Exponentially Weighted Moving Average). It smoothes out
fluctuations and is equivalent to a low-pass filter. Whenever d moves above the
threshold, the router notes the onset of congestion.
The second problem is that routers must deliver timely feedback to the send-
ers that are causing the congestion. Congestion is experienced in the network, but
relieving congestion requires action on behalf of the senders that are using the net-
work. To deliver feedback, the router must identify the appropriate senders. It
must then warn them carefully, without sending many more packets into the al-
ready congested network. Different schemes use different feedback mechanisms,
as we will now describe.
Choke Packets
The most direct way to notify a sender of congestion is to tell it directly. In
this approach, the router selects a congested packet and sends a choke packet
back to the source host, giving it the destination found in the packet. The original
packet may be tagged (a header bit is turned on) so that it will not generate any
more choke packets farther along the path and then forwarded in the usual way.
To avoid increasing load on the network during a time of congestion, the router
may only send choke packets at a low rate.
When the source host gets the choke packet, it is required to reduce the traffic
sent to the specified destination, for example, by 50%. In a datagram network,
simply picking packets at random when there is congestion is likely to cause
choke packets to be sent to fast senders, because they will have the most packets
in the queue. The feedback implicit in this protocol can help prevent congestion
yet not throttle any sender unless it causes trouble. For the same reason, it is like-
ly that multiple choke packets will be sent to a given host and destination. The
host should ignore these additional chokes for the fixed time interval until its
reduction in traffic takes effect. After that period, further choke packets indicate
that the network is still congested.
An example of a choke packet used in the early Internet is the SOURCE-
QUENCH message (Postel, 1981). It never caught on, though, partly because the


---

<a id="page-412"></a>

<!-- Page 412 of 888 -->

400 THE NETWORK LAYER CHAP. 5
circumstances in which it was generated and the effect it had were not clearly
specified. The modern Internet uses an alternative notification design that we will
describe next.
Explicit Congestion Notification
Instead of generating additional packets to warn of congestion, a router can
tag any packet it forwards (by setting a bit in the packet's header) to signal that it
is experiencing congestion. When the network delivers the packet, the destination
can note that there is congestion and inform the sender when it sends a reply pack-
et. The sender can then throttle its transmissions as before.
This design is called ECN (Explicit Congestion Notification) and is used in
the Internet (Ramakrishnan et al., 2001). It is a refinement of early congestion
signaling protocols, notably the binary feedback scheme of Ramakrishnan and
Jain (1988) that was used in the DECNET architecture. Two bits in the IP packet
header are used to record whether the packet has experienced congestion. Packets
are unmarked when they are sent, as illustrated in Fig. 5-25. If any of the routers
they pass through is congested, that router will then mark the packet as having
experienced congestion as it is forwarded. The destination will then echo any
marks back to the sender as an explicit congestion signal in its next reply packet.
This is shown with a dashed line in the figure to indicate that it happens above the
IP level (e.g., in TCP). The sender must then throttle its transmissions, as in the
case of choke packets.
Packet Congested Marked
router packet
Host Host
Congestion signal
Figure 5-25. Explicit congestion notification
Hop-by-Hop Backpressure
At high speeds or over long distances, many new packets may be transmitted
after congestion has been signaled because of the delay before the signal takes ef-
fect. Consider, for example, a host in San Francisco (router A in Fig. 5-26) that is
sending traffic to a host in New York (router D in Fig. 5-26) at the OC-3 speed of
155 Mbps. If the New York host begins to run out of buffers, it will take about 40
msec for a choke packet to get back to San Francisco to tell it to slow down. An
ECN indication will take even longer because it is delivered via the destination.
Choke packet propagation is illustrated as the second, third, and fourth steps in


---

<a id="page-413"></a>

<!-- Page 413 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 401
Fig. 5-26(a). In those 40 msec, another 6.2 megabits will have been sent. Even if
the host in San Francisco completely shuts down immediately, the 6.2 megabits in
the pipe will continue to pour in and have to be dealt with. Only in the seventh
diagram in Fig. 5-26(a) will the New York router notice a slower flow.
An alternative approach is to have the choke packet take effect at every hop it
passes through, as shown in the sequence of Fig. 5-26(b). Here, as soon as the
choke packet reaches F, F is required to reduce the flow to D. Doing so will re-
quire F to devote more buffers to the connection, since the source is still sending
away at full blast, but it gives D immediate relief, like a headache remedy in a
television commercial. In the next step, the choke packet reaches E, which tells E
to reduce the flow to F. This action puts a greater demand on E's buffers but
gives F immediate relief. Finally, the choke packet reaches A and the flow
genuinely slows down.
The net effect of this hop-by-hop scheme is to provide quick relief at the point
of congestion, at the price of using up more buffers upstream. In this way, con-
gestion can be nipped in the bud without losing any packets. The idea is dis-
cussed in detail by Mishra et al. (1996).
#### 5.3.5 Load Shedding
When none of the above methods make the congestion disappear, routers can
bring out the heavy artillery: load shedding. Load shedding is a fancy way of
saying that when routers are being inundated by packets that they cannot handle,
they just throw them away. The term comes from the world of electrical power
generation, where it refers to the practice of utilities intentionally blacking out
certain areas to save the entire grid from collapsing on hot summer days when the
demand for electricity greatly exceeds the supply.
The key question for a router drowning in packets is which packets to drop.
The preferred choice may depend on the type of applications that use the network.
For a file transfer, an old packet is worth more than a new one. This is because
dropping packet 6 and keeping packets 7 through 10, for example, will only force
the receiver to do more work to buffer data that it cannot yet use. In contrast, for
real-time media, a new packet is worth more than an old one. This is because
packets become useless if they are delayed and miss the time at which they must
be played out to the user.
The former policy (old is better than new) is often called wine and the latter
(new is better than old) is often called milk because most people would rather
drink new milk and old wine than the alternative.
More intelligent load shedding requires cooperation from the senders. An ex-
ample is packets that carry routing information. These packets are more important
than regular data packets because they establish routes; if they are lost, the net-
work may lose connectivity. Another example is that algorithms for compressing
video, like MPEG, periodically transmit an entire frame and then send subsequent


---

<a id="page-414"></a>

<!-- Page 414 of 888 -->

402 THE NETWORK LAYER CHAP. 5
B C B C
A D A D
Heavy flow
E F E F
e e
k k
o o
h h
C C
Choke Choke
Reduced
flow
C C
h h
o o
k k
e e
Reduced
flow
Flow is still
at maximum rate
Flow is
reduced
(a) (b)
Figure 5-26. (a) A choke packet that affects only the source. (b) A choke pack-
et that affects each hop it passes through.


---

<a id="page-415"></a>

<!-- Page 415 of 888 -->

SEC. 5.3 CONGESTION CONTROL ALGORITHMS 403
frames as differences from the last full frame. In this case, dropping a packet that
is part of a difference is preferable to dropping one that is part of a full frame be-
cause future packets depend on the full frame.
To implement an intelligent discard policy, applications must mark their pack-
ets to indicate to the network how important they are. Then, when packets have to
be discarded, routers can first drop packets from the least important class, then the
next most important class, and so on.
Of course, unless there is some significant incentive to avoid marking every
packet as VERY IMPORTANT-NEVER, EVER DISCARD, nobody will do it.
Often accounting and money are used to discourage frivolous marking. For ex-
ample, the network might let senders send faster than the service they purchased
allows if they mark excess packets as low priority. Such a strategy is actually not
a bad idea because it makes more efficient use of idle resources, allowing hosts to
use them as long as nobody else is interested, but without establishing a right to
them when times get tough.
Random Early Detection
Dealing with congestion when it first starts is more effective than letting it
gum up the works and then trying to deal with it. This observation leads to an in-
teresting twist on load shedding, which is to discard packets before all the buffer
space is really exhausted.
The motivation for this idea is that most Internet hosts do not yet get conges-
tion signals from routers in the form of ECN. Instead, the only reliable indication
of congestion that hosts get from the network is packet loss. After all, it is diffi-
cult to build a router that does not drop packets when it is overloaded. Transport
protocols such as TCP are thus hardwired to react to loss as congestion, slowing
down the source in response. The reasoning behind this logic is that TCP was de-
signed for wired networks and wired networks are very reliable, so lost packets
are mostly due to buffer overruns rather than transmission errors. Wireless links
must recover transmission errors at the link layer (so they are not seen at the net-
work layer) to work well with TCP.
This situation can be exploited to help reduce congestion. By having routers
drop packets early, before the situation has become hopeless, there is time for the
source to take action before it is too late. A popular algorithm for doing this is
called RED (Random Early Detection) (Floyd and Jacobson, 1993). To deter-
mine when to start discarding, routers maintain a running average of their queue
lengths. When the average queue length on some link exceeds a threshold, the
link is said to be congested and a small fraction of the packets are dropped at ran-
dom. Picking packets at random makes it more likely that the fastest senders will
see a packet drop; this is the best option since the router cannot tell which source
is causing the most trouble in a datagram network. The affected sender will
notice the loss when there is no acknowledgement, and then the transport protocol


---

<a id="page-416"></a>

<!-- Page 416 of 888 -->

404 THE NETWORK LAYER CHAP. 5
will slow down. The lost packet is thus delivering the same message as a choke
packet, but implicitly, without the router sending any explicit signal.
RED routers improve performance compared to routers that drop packets only
when their buffers are full, though they may require tuning to work well. For ex-
ample, the ideal number of packets to drop depends on how many senders need to
be notified of congestion. However, ECN is the preferred option if it is available.
It works in exactly the same manner, but delivers a congestion signal explicitly
rather than as a loss; RED is used when hosts cannot receive explicit signals.
### 5.4 QUALITY OF SERVICE
The techniques we looked at in the previous sections are designed to reduce
congestion and improve network performance. However, there are applications
(and customers) that demand stronger performance guarantees from the network
than ''the best that could be done under the circumstances.'' Multimedia applica-
tions in particular, often need a minimum throughput and maximum latency to
work. In this section, we will continue our study of network performance, but
now with a sharper focus on ways to provide quality of service that is matched to
application needs. This is an area in which the Internet is undergoing a long-term
upgrade.
An easy solution to provide good quality of service is to build a network with
enough capacity for whatever traffic will be thrown at it. The name for this solu-
tion is overprovisioning. The resulting network will carry application traffic
without significant loss and, assuming a decent routing scheme, will deliver pack-
ets with low latency. Performance doesn't get any better than this. To some
extent, the telephone system is overprovisioned because it is rare to pick up a tele-
phone and not get a dial tone instantly. There is simply so much capacity avail-
able that demand can almost always be met.
The trouble with this solution is that it is expensive. It is basically solving a
problem by throwing money at it. Quality of service mechanisms let a network
with less capacity meet application requirements just as well at a lower cost.
Moreover, overprovisioning is based on expected traffic. All bets are off if the
traffic pattern changes too much. With quality of service mechanisms, the net-
work can honor the performance guarantees that it makes even when traffic
spikes, at the cost of turning down some requests.
Four issues must be addressed to ensure quality of service:
1. What applications need from the network.
2. How to regulate the traffic that enters the network.
3. How to reserve resources at routers to guarantee performance.
4. Whether the network can safely accept more traffic.


---

<a id="page-417"></a>

<!-- Page 417 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 405
No single technique deals efficiently with all these issues. Instead, a variety of
techniques have been developed for use at the network (and transport) layer.
Practical quality-of-service solutions combine multiple techniques. To this end,
we will describe two versions of quality of service for the Internet called
Integrated Services and Differentiated Services.
#### 5.4.1 Application Requirements
A stream of packets from a source to a destination is called a flow (Clark,
1988). A flow might be all the packets of a connection in a connection-oriented
network, or all the packets sent from one process to another process in a con-
nectionless network. The needs of each flow can be characterized by four pri-
mary parameters: bandwidth, delay, jitter, and loss. Together, these determine the
QoS (Quality of Service) the flow requires.
Several common applications and the stringency of their network re-
quirements are listed in Fig. 5-27. Note that network requirements are less de-
manding than application requirements in those cases that the application can im-
prove on the service provided by the network. In particular, networks do not need
to be lossless for reliable file transfer, and they do not need to deliver packets with
identical delays for audio and video playout. Some amount of loss can be repaired
with retransmissions, and some amount of jitter can be smoothed by buffering
packets at the receiver. However, there is nothing applications can do to remedy
the situation if the network provides too little bandwidth or too much delay.
Application Bandwidth Delay Jitter Loss
Email Low Low Low Medium
File sharing High Low Low Medium
Web access Medium Medium Low Medium
Remote login Low Medium Medium Medium
Audio on demand Low Low High Low
Video on demand High Low High Low
Telephony Low High High Low
Videoconferencing High High High Low
Figure 5-27. Stringency of applications' quality-of-service requirements.
The applications differ in their bandwidth needs, with email, audio in all
forms, and remote login not needing much, but file sharing and video in all forms
needing a great deal.
More interesting are the delay requirements. File transfer applications, in-
cluding email and video, are not delay sensitive. If all packets are delayed uni-
formly by a few seconds, no harm is done. Interactive applications, such as Web


---

<a id="page-418"></a>

<!-- Page 418 of 888 -->

406 THE NETWORK LAYER CHAP. 5
surfing and remote login, are more delay sensitive. Real-time applications, such
as telephony and videoconferencing, have strict delay requirements. If all the
words in a telephone call are each delayed by too long, the users will find the con-
nection unacceptable. On the other hand, playing audio or video files from a ser-
ver does not require low delay.
The variation (i.e., standard deviation) in the delay or packet arrival times is
called jitter. The first three applications in Fig. 5-27 are not sensitive to the pack-
ets arriving with irregular time intervals between them. Remote login is some-
what sensitive to that, since updates on the screen will appear in little bursts if the
connection suffers much jitter. Video and especially audio are extremely sensi-
tive to jitter. If a user is watching a video over the network and the frames are all
delayed by exactly 2.000 seconds, no harm is done. But if the transmission time
varies randomly between 1 and 2 seconds, the result will be terrible unless the ap-
plication hides the jitter. For audio, a jitter of even a few milliseconds is clearly
audible.
The first four applications have more stringent requirements on loss than aud-
io and video because all bits must be delivered correctly. This goal is usually a-
chieved with retransmissions of packets that are lost in the network by the tran-
sport layer. This is wasted work; it would be better if the network refused packets
it was likely to lose in the first place. Audio and video applications can tolerate
some lost packets without retransmission because people do not notice short
pauses or occasional skipped frames.
To accommodate a variety of applications, networks may support different
categories of QoS. An influential example comes from ATM networks, which
were once part of a grand vision for networking but have since become a niche
technology. They support:
1. Constant bit rate (e.g., telephony).
2. Real-time variable bit rate (e.g., compressed videoconferencing).
3. Non-real-time variable bit rate (e.g., watching a movie on demand).
4. Available bit rate (e.g., file transfer).
These categories are also useful for other purposes and other networks. Constant
bit rate is an attempt to simulate a wire by providing a uniform bandwidth and a
uniform delay. Variable bit rate occurs when video is compressed, with some
frames compressing more than others. Sending a frame with a lot of detail in it
may require sending many bits, whereas a shot of a white wall may compress ex-
tremely well. Movies on demand are not actually real time because a few seconds
of video can easily be buffered at the receiver before playback starts, so jitter on
the network merely causes the amount of stored-but-not-played video to vary.
Available bit rate is for applications such as email that are not sensitive to delay
or jitter and will take what bandwidth they can get.


---

<a id="page-419"></a>

<!-- Page 419 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 407
#### 5.4.2 Traffic Shaping
Before the network can make QoS guarantees, it must know what traffic is
being guaranteed. In the telephone network, this characterization is simple. For
example, a voice call (in uncompressed format) needs 64 kbps and consists of one
8-bit sample every 125 µsec. However, traffic in data networks is bursty. It typi-
cally arrives at nonuniform rates as the traffic rate varies (e.g., videoconferencing
with compression), users interact with applications (e.g., browsing a new Web
page), and computers switch between tasks. Bursts of traffic are more difficult to
handle than constant-rate traffic because they can fill buffers and cause packets to
be lost.
Traffic shaping is a technique for regulating the average rate and burstiness
of a flow of data that enters the network. The goal is to allow applications to
transmit a wide variety of traffic that suits their needs, including some bursts, yet
have a simple and useful way to describe the possible traffic patterns to the net-
work. When a flow is set up, the user and the network (i.e., the customer and the
provider) agree on a certain traffic pattern (i.e., shape) for that flow. In effect, the
customer says to the provider ''My transmission pattern will look like this; can
you handle it?''
Sometimes this agreement is called an SLA (Service Level Agreement), es-
pecially when it is made over aggregate flows and long periods of time, such as
all of the traffic for a given customer. As long as the customer fulfills her part of
the bargain and only sends packets according to the agreed-on contract, the pro-
vider promises to deliver them all in a timely fashion.
Traffic shaping reduces congestion and thus helps the network live up to its
promise. However, to make it work, there is also the issue of how the provider
can tell if the customer is following the agreement and what to do if the customer
is not. Packets in excess of the agreed pattern might be dropped by the network, or
they might be marked as having lower priority. Monitoring a traffic flow is called
traffic policing.
Shaping and policing are not so important for peer-to-peer and other transfers
that will consume any and all available bandwidth, but they are of great impor-
tance for real-time data, such as audio and video connections, which have
stringent quality-of-service requirements.
Leaky and Token Buckets
We have already seen one way to limit the amount of data an application
sends: the sliding window, which uses one parameter to limit how much data is in
transit at any given time, which indirectly limits the rate. Now we will look at a
more general way to characterize traffic, with the leaky bucket and token bucket
algorithms. The formulations are slightly different but give an equivalent result.


---

<a id="page-420"></a>

<!-- Page 420 of 888 -->

408 THE NETWORK LAYER CHAP. 5
Try to imagine a bucket with a small hole in the bottom, as illustrated in
Fig. 5-28(b). No matter the rate at which water enters the bucket, the outflow is at
a constant rate, R, when there is any water in the bucket and zero when the bucket
is empty. Also, once the bucket is full to capacity B, any additional water enter-
ing it spills over the sides and is lost.
Host
Rate
Packets Put in R
water
B
Check Take out
bucket water/tokens B
here
Rate
R
Network
(a) (b) (c)
Figure 5-28. (a) Shaping packets. (b) A leaky bucket. (c) A token bucket.
This bucket can be used to shape or police packets entering the network, as
shown in Fig. 5-28(a). Conceptually, each host is connected to the network by an
interface containing a leaky bucket. To send a packet into the network, it must be
possible to put more water into the bucket. If a packet arrives when the bucket is
full, the packet must either be queued until enough water leaks out to hold it or be
discarded. The former might happen at a host shaping its traffic for the network
as part of the operating system. The latter might happen in hardware at a provider
network interface that is policing traffic entering the network. This technique was
proposed by Turner (1986) and is called the leaky bucket algorithm.
A different but equivalent formulation is to imagine the network interface as a
bucket that is being filled, as shown in Fig. 5-28(c). The tap is running at rate R
and the bucket has a capacity of B, as before. Now, to send a packet we must be
able to take water, or tokens, as the contents are commonly called, out of the
bucket (rather than putting water into the bucket). No more than a fixed number
of tokens, B, can accumulate in the bucket, and if the bucket is empty, we must
wait until more tokens arrive before we can send another packet. This algorithm
is called the token bucket algorithm.
Leaky and token buckets limit the long-term rate of a flow but allow short-
term bursts up to a maximum regulated length to pass through unaltered and
without suffering any artificial delays. Large bursts will be smoothed by a leaky
bucket traffic shaper to reduce congestion in the network. As an example, imag-
ine that a computer can produce data at up to 1000 Mbps (125 million bytes/sec)
and that the first link of the network also runs at this speed. The pattern of traffic
the host generates is shown in Fig. 5-29(a). This pattern is bursty. The average


---

<a id="page-421"></a>

<!-- Page 421 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 409
rate over one second is 200 Mbps, even though the host sends a burst of 16,000
KB at the top speed of 1000 Mbps (for 1/8 of the second).
Rate (Mbps) Bucket (KB)
125 MB/s for
1000 125 msec 16000
25 MB/s for
250 msec
(a) (d)
With R = 25 MB/s,
B = 9600 KB 9600 Bucket empties,
traffic delayed
(b) (e)
With R = 25 MB/s, B = 0 Bucket always empty

Time (msec) 1000 Time (msec) 1000
(c) (f)
Figure 5-29. (a) Traffic from a host. Output shaped by a token bucket of rate
200 Mbps and capacity (b) 9600 KB and (c) 0 KB. Token bucket level for shap-
ing with rate 200 Mbps and capacity (d) 16,000 KB, (e) 9600 KB, and (f) 0 KB.
Now suppose that the routers can accept data at the top speed only for short
intervals, until their buffers fill up. The buffer size is 9600 KB, smaller than the
traffic burst. For long intervals, the routers work best at rates not exceeding 200
Mbps (say, because this is all the bandwidth given to the customer). The implica-
tion is that if traffic is sent in this pattern, some of it will be dropped in the net-
work because it does not fit into the buffers at routers.
To avoid this packet loss, we can shape the traffic at the host with a token
bucket. If we use a rate, R, of 200 Mbps and a capacity, B, of 9600 KB, the traffic
will fall within what the network can handle. The output of this token bucket is
shown in Fig. 5-29(b). The host can send full throttle at 1000 Mbps for a short
while until it has drained the bucket. Then it has to cut back to 200 Mbps until the
burst has been sent. The effect is to spread out the burst over time because it was
too large to handle all at once. The level of the token bucket is shown in Fig. 5-
29(e). It starts off full and is depleted by the initial burst. When it reaches zero,
new packets can be sent only at the rate at which the buffer is filling; there can be
no more bursts until the bucket has recovered. The bucket fills when no traffic is
being sent and stays flat when traffic is being sent at the fill rate.
We can also shape the traffic to be less bursty. Fig. 5-29(c) shows the output
of a token bucket with R = 200 Mbps and a capacity of 0. This is the extreme case


---

<a id="page-422"></a>

<!-- Page 422 of 888 -->

410 THE NETWORK LAYER CHAP. 5
in which the traffic has been completely smoothed. No bursts are allowed, and the
traffic enters the network at a steady rate. The corresponding bucket level, shown
in Fig. 5-29(f), is always empty. Traffic is being queued on the host for release
into the network and there is always a packet waiting to be sent when it is allow-
ed.
Finally, Fig. 5-29(d) shows the bucket level for a token bucket with R = 200
Mbps and a capacity of B = 16, 000 KB. This is the smallest token bucket through
which the traffic passes unaltered. It might be used at a router in the network to
police the traffic that the host sends. If the host is sending traffic that conforms to
the token bucket on which it has agreed with the network, the traffic will fit
through that same token bucket run at the router at the edge of the network. If the
host sends at a faster or burstier rate, the token bucket will run out of water. If this
happens, a traffic policer will know that the traffic is not as described. It will then
either drop the excess packets or lower their priority, depending on the design of
the network. In our example, the bucket empties only momentarily, at the end of
the initial burst, then recovers enough for the next burst.
Leaky and token buckets are easy to implement. We will now describe the
operation of a token bucket. Even though we have described water flowing con-
tinuously into and out of the bucket, real implementations must work with discrete
quantities. A token bucket is implemented with a counter for the level of the
bucket. The counter is advanced by R /∆T units at every clock tick of ∆T seconds.
This would be 200 Kbit every 1 msec in our example above. Every time a unit of
traffic is sent into the network, the counter is decremented, and traffic may be sent
until the counter reaches zero.
When the packets are all the same size, the bucket level can just be counted in
packets (e.g., 200 Mbit is 20 packets of 1250 bytes). However, often variable-
sized packets are being used. In this case, the bucket level is counted in bytes. If
the residual byte count is too low to send a large packet, the packet must wait until
the next tick (or even longer, if the fill rate is small).
Calculating the length of the maximum burst (until the bucket empties) is
slightly tricky. It is longer than just 9600 KB divided by 125 MB/sec because
while the burst is being output, more tokens arrive. If we call the burst length S
sec., the maximum output rate M bytes/sec, the token bucket capacity B bytes, and
the token arrival rate R bytes/sec, we can see that an output burst contains a maxi-
mum of B + RS bytes. We also know that the number of bytes in a maximum-
speed burst of length S seconds is MS. Hence, we have
B + RS = MS
We can solve this equation to get S = B /(M − R). For our parameters of B = 9600
KB, M = 125 MB/sec, and R = 25 MB/sec, we get a burst time of about 94 msec.
A potential problem with the token bucket algorithm is that it reduces large
bursts down to the long-term rate R. It is frequently desirable to reduce the peak
rate, but without going down to the long-term rate (and also without raising the


---

<a id="page-423"></a>

<!-- Page 423 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 411
long-term rate to allow more traffic into the network). One way to get smoother
traffic is to insert a second token bucket after the first one. The rate of the second
bucket should be much higher than the first one. Basically, the first bucket charac-
terizes the traffic, fixing its average rate but allowing some bursts. The second
bucket reduces the peak rate at which the bursts are sent into the network. For ex-
ample, if the rate of the second token bucket is set to be 500 Mbps and the capaci-
ty is set to 0, the initial burst will enter the network at a peak rate of 500 Mbps,
which is lower than the 1000 Mbps rate we had previously.
Using all of these buckets can be a bit tricky. When token buckets are used for
traffic shaping at hosts, packets are queued and delayed until the buckets permit
them to be sent. When token buckets are used for traffic policing at routers in the
network, the algorithm is simulated to make sure that no more packets are sent
than permitted. Nevertheless, these tools provide ways to shape the network traf-
fic into more manageable forms to assist in meeting quality-of-service re-
quirements.
#### 5.4.3 Packet Scheduling
Being able to regulate the shape of the offered traffic is a good start. Howev-
er, to provide a performance guarantee, we must reserve sufficient resources
along the route that the packets take through the network. To do this, we are as-
suming that the packets of a flow follow the same route. Spraying them over rout-
ers at random makes it hard to guarantee anything. As a consequence, something
similar to a virtual circuit has to be set up from the source to the destination, and
all the packets that belong to the flow must follow this route.
Algorithms that allocate router resources among the packets of a flow and be-
tween competing flows are called packet scheduling algorithms. Three different
kinds of resources can potentially be reserved for different flows:
1. Bandwidth.
2. Buffer space.
3. CPU cycles.
The first one, bandwidth, is the most obvious. If a flow requires 1 Mbps and the
outgoing line has a capacity of 2 Mbps, trying to direct three flows through that
line is not going to work. Thus, reserving bandwidth means not oversubscribing
any output line.
A second resource that is often in short supply is buffer space. When a packet
arrives, it is buffered inside the router until it can be transmitted on the chosen
outgoing line. The purpose of the buffer is to absorb small bursts of traffic as the
flows contend with each other. If no buffer is available, the packet has to be dis-
carded since there is no place to put it. For good quality of service, some buffers
might be reserved for a specific flow so that flow does not have to compete for


---

<a id="page-424"></a>

<!-- Page 424 of 888 -->

412 THE NETWORK LAYER CHAP. 5
buffers with other flows. Up to some maximum value, there will always be a
buffer available when the flow needs one.
Finally, CPU cycles may also be a scarce resource. It takes router CPU time
to process a packet, so a router can process only a certain number of packets per
second. While modern routers are able to process most packets quickly, some
kinds of packets require greater CPU processing, such as the ICMP packets we
will describe in Sec. 5.6. Making sure that the CPU is not overloaded is needed to
ensure timely processing of these packets.
Packet scheduling algorithms allocate bandwidth and other router resources
by determining which of the buffered packets to send on the output line next. We
already described the most straightforward scheduler when explaining how rout-
ers work. Each router buffers packets in a queue for each output line until they
can be sent, and they are sent in the same order that they arrived. This algorithm
is known as FIFO (First-In First-Out), or equivalently FCFS (First-Come
First-Serve).
FIFO routers usually drop newly arriving packets when the queue is full.
Since the newly arrived packet would have been placed at the end of the queue,
this behavior is called tail drop. It is intuitive, and you may be wondering what
alternatives exist. In fact, the RED algorithm we described in Sec. 5.3.5 chose a
newly arriving packet to drop at random when the average queue length grew
large. The other scheduling algorithms that we will describe also create other
opportunities for deciding which packet to drop when the buffers are full.
FIFO scheduling is simple to implement, but it is not suited to providing good
quality of service because when there are multiple flows, one flow can easily
affect the performance of the other flows. If the first flow is aggressive and sends
large bursts of packets, they will lodge in the queue. Processing packets in the
order of their arrival means that the aggressive sender can hog most of the capaci-
ty of the routers its packets traverse, starving the other flows and reducing their
quality of service. To add insult to injury, the packets of the other flows that do
get through are likely to be delayed because they had to sit in the queue behind
many packets from the aggressive sender.
Many packet scheduling algorithms have been devised that provide stronger
isolation between flows and thwart attempts at interference (Bhatti and Crowcroft,
2000). One of the first ones was the fair queueing algorithm devised by Nagle
(1987). The essence of this algorithm is that routers have separate queues, one for
each flow for a given output line. When the line becomes idle, the router scans
the queues round-robin, as shown in Fig. 5-30. It then takes the first packet on the
next queue. In this way, with n hosts competing for the output line, each host gets
to send one out of every n packets. It is fair in the sense that all flows get to send
packets at the same rate. Sending more packets will not improve this rate.
Although a start, the algorithm has a flaw: it gives more bandwidth to hosts
that use large packets than to hosts that use small packets. Demers et al. (1990)
suggested an improvement in which the round-robin is done in such a way as to


---

<a id="page-425"></a>

<!-- Page 425 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 413

2 Round-robin 3 2 1 3 2 1
service
Output line

Input queues
Figure 5-30. Round-robin fair queueing.
simulate a byte-by-byte round-robin, instead of a packet-by-packet round-robin.
The trick is to compute a virtual time that is the number of the round at which
each packet would finish being sent. Each round drains a byte from all of the
queues that have data to send. The packets are then sorted in order of their fin-
ishing times and sent in that order.
This algorithm and an example of finish times for packets arriving in three
flows are illustrated in Fig. 5-31. If a packet has length L, the round at which it
will finish is simply L rounds after the start time. The start time is either the fin-
ish time of the previous packet, or the arrival time of the packet, if the queue is
empty when it arrives.
Arrives Arrives after D
late but goes first Packet Arrival Length Finish Output
time time order
## F A A 0 8 8 1
## B 5 6 11 3
## C 5 10 10 2
Fair
## H D B D 8 9 20 7
queueing
## E 8 8 14 4
## F 10 6 16 5
G E C 2X
## G 11 10 19 6
Input queues Weight is 2 H 20 8 28 8
(a) (b)
Figure 5-31. (a) Weighted Fair Queueing. (b) Finishing times for the packets.
From the table in Fig. 5-32(b), and looking only at the first two packets in the
top two queues, packets arrive in the order A, B, D, and F. Packet A arrives at
round 0 and is 8 bytes long, so its finish time is round 8. Similarly the finish time
for packet B is 11. Packet D arrives while B is being sent. Its finish time is 9
byte-rounds after it starts when B finishes, or 20. Similarly, the finish time for F
is 16. In the absence of new arrivals, the relative sending order is A, B, F, D, even
though F arrived after D. It is possible that another small packet will arrive on the
top flow and obtain a finish time before D. It will only jump ahead of D if the


---

<a id="page-426"></a>

<!-- Page 426 of 888 -->

414 THE NETWORK LAYER CHAP. 5
transmission of that packet has not started. Fair queueing does not preempt pack-
ets that are currently being transmitted. Because packets are sent in their entirety,
fair queueing is only an approximation of the ideal byte-by-byte scheme. But it is
a very good approximation, staying within one packet transmission of the ideal
scheme at all times.
One shortcoming of this algorithm in practice is that it gives all hosts the
same priority. In many situations, it is desirable to give, for example, video ser-
vers more bandwidth than, say, file servers. This is easily possible by giving the
video server two or more bytes per round. This modified algorithm is called
WFQ (Weighted Fair Queueing). Letting the number of bytes per round be the
weight of a flow, W, we can now give the formula for computing the finish time:
F = max(A ,F )+L /W
i i i −1 i
where A is the arrival time, F is the finish time, and L is the length of packet i.
i i i
The bottom queue of Fig. 5-31(a) has a weight of 2, so its packets are sent more
quickly as you can see in the finish times given in Fig. 5-31(b).
Another practical consideration is implementation complexity. WFQ requires
that packets be inserted by their finish time into a sorted queue. With N flows, this
is at best an O(logN) operation per packet, which is difficult to achieve for many
flows in high-speed routers. Shreedhar and Varghese (1995) describe an approxi-
mation called deficit round robin that can be implemented very efficiently, with
only O(1) operations per packet. WFQ is widely used given this approximation.
Other kinds of scheduling algorithms exist, too. A simple example is priority
scheduling, in which each packet is marked with a priority. High-priority packets
are always sent before any low-priority packets that are buffered. Within a prior-
ity, packets are sent in FIFO order. However, priority scheduling has the disad-
vantage that a burst of high-priority packets can starve low-priority packets, which
may have to wait indefinitely. WFQ often provides a better alternative. By giving
the high-priority queue a large weight, say 3, high-priority packets will often go
through a short line (as relatively few packets should be high priority) yet some
fraction of low priority packets will continue to be sent even when there is high
priority traffic. A high and low priority system is essentially a two-queue WFQ
system in which the high priority has infinite weight.
As a final example of a scheduler, packets might carry timestamps and be sent
in timestamp order. Clark et al. (1992) describe a design in which the timestamp
records how far the packet is behind or ahead of schedule as it is sent through a
sequence of routers on the path. Packets that have been queued behind other
packets at a router will tend to be behind schedule, and the packets that have been
serviced first will tend to be ahead of schedule. Sending packets in order of their
timestamps has the beneficial effect of speeding up slow packets while at the
same time slowing down fast packets. The result is that all packets are delivered
by the network with a more consistent delay.


---

<a id="page-427"></a>

<!-- Page 427 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 415
#### 5.4.4 Admission Control
We have now seen all the necessary elements for QoS and it is time to put
them together to actually provide it. QoS guarantees are established through the
process of admission control. We first saw admission control used to control con-
gestion, which is a performance guarantee, albeit a weak one. The guarantees we
are considering now are stronger, but the model is the same. The user offers a
flow with an accompanying QoS requirement to the network. The network then
decides whether to accept or reject the flow based on its capacity and the commit-
ments it has made to other flows. If it accepts, the network reserves capacity in
advance at routers to guarantee QoS when traffic is sent on the new flow.
The reservations must be made at all of the routers along the route that the
packets take through the network. Any routers on the path without reservations
might become congested, and a single congested router can break the QoS guaran-
tee. Many routing algorithms find the single best path between each source and
each destination and send all traffic over the best path. This may cause some
flows to be rejected if there is not enough spare capacity along the best path. QoS
guarantees for new flows may still be accommodated by choosing a different
route for the flow that has excess capacity. This is called QoS routing. Chen and
Nahrstedt (1998) give an overview of these techniques. It is also possible to split
the traffic for each destination over multiple paths to more easily find excess ca-
pacity. A simple method is for routers to choose equal-cost paths and to divide
the traffic equally or in proportion to the capacity of the outgoing links. However,
more sophisticated algorithms are also available (Nelakuditi and Zhang, 2002).
Given a path, the decision to accept or reject a flow is not a simple matter of
comparing the resources (bandwidth, buffers, cycles) requested by the flow with
the router's excess capacity in those three dimensions. It is a little more compli-
cated than that. To start with, although some applications may know about their
bandwidth requirements, few know about buffers or CPU cycles, so at the mini-
mum, a different way is needed to describe flows and translate this description to
router resources. We will get to this shortly.
Next, some applications are far more tolerant of an occasional missed dead-
line than others. The applications must choose from the type of guarantees that
the network can make, whether hard guarantees or behavior that will hold most of
the time. All else being equal, everyone would like hard guarantees, but the diffi-
culty is that they are expensive because they constrain worst case behavior. Guar-
antees for most of the packets are often sufficient for applications, and more flows
with this guarantee can be supported for a fixed capacity.
Finally, some applications may be willing to haggle about the flow parameters
and others may not. For example, a movie viewer that normally runs at 30
frames/sec may be willing to drop back to 25 frames/sec if there is not enough
free bandwidth to support 30 frames/sec. Similarly, the number of pixels per
frame, audio bandwidth, and other properties may be adjustable.


---

<a id="page-428"></a>

<!-- Page 428 of 888 -->

416 THE NETWORK LAYER CHAP. 5
Because many parties may be involved in the flow negotiation (the sender, the
receiver, and all the routers along the path between them), flows must be de-
scribed accurately in terms of specific parameters that can be negotiated. A set of
such parameters is called a flow specification. Typically, the sender (e.g., the
video server) produces a flow specification proposing the parameters it would like
to use. As the specification propagates along the route, each router examines it
and modifies the parameters as need be. The modifications can only reduce the
flow, not increase it (e.g., a lower data rate, not a higher one). When it gets to the
other end, the parameters can be established.
As an example of what can be in a flow specification, consider the example of
Fig. 5-32. This is based on RFCs 2210 and 2211 for Integrated Services, a QoS
design we will cover in the next section. It has five parameters. The first two pa-
rameters, the token bucket rate and token bucket size, use a token bucket to give
the maximum sustained rate the sender may transmit, averaged over a long time
interval, and the largest burst it can send over a short time interval.
Parameter Unit
Token bucket rate Bytes/sec
Token bucket size Bytes
Peak data rate Bytes/sec
Minimum packet size Bytes
Maximum packet size Bytes
Figure 5-32. An example flow specification.
The third parameter, the peak data rate, is the maximum transmission rate
tolerated, even for brief time intervals. The sender must never exceed this rate
even for short bursts.
The last two parameters specify the minimum and maximum packet sizes, in-
cluding the transport and network layer headers (e.g., TCP and IP). The minimum
size is useful because processing each packet takes some fixed time, no matter
how short. A router may be prepared to handle 10,000 packets/sec of 1 KB each,
but not be prepared to handle 100,000 packets/sec of 50 bytes each, even though
this represents a lower data rate. The maximum packet size is important due to
internal network limitations that may not be exceeded. For example, if part of the
path goes over an Ethernet, the maximum packet size will be restricted to no more
than 1500 bytes no matter what the rest of the network can handle.
An interesting question is how a router turns a flow specification into a set of
specific resource reservations. At first glance, it might appear that if a router has
a link that runs at, say, 1 Gbps and the average packet is 1000 bits, it can process
1 million packets/sec. This observation is not the case, though, because there will
always be idle periods on the link due to statistical fluctuations in the load. If the


---

<a id="page-429"></a>

<!-- Page 429 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 417
link needs every bit of capacity to get its work done, idling for even a few bits
creates a backlog it can never get rid of.
Even with a load slightly below the theoretical capacity, queues can build up
and delays can occur. Consider a situation in which packets arrive at random with
a mean arrival rate of λ packets/sec. The packets have random lengths and can be
sent on the link with a mean service rate of µ packets/sec. Under the assumption
that both the arrival and service distributions are Poisson distributions (what is
called an M/M/1 queueing system, where ''M'' stands for Markov, i.e., Poisson),
it can be proven using queueing theory that the mean delay experienced by a
packet, T, is
1 1 1 1
T = × = ×
µ 1 − λ/µ µ 1 − ρ
where ρ=λ /µ is the CPU utilization. The first factor, 1/µ, is what the service
time would be in the absence of competition. The second factor is the slowdown
due to competition with other flows. For example, if λ= 950,000 packets/sec and
µ = 1,000,000 packets/sec, then ρ= 0.95 and the mean delay experienced by each
packet will be 20 µsec instead of 1 µsec. This time accounts for both the queue-
ing time and the service time, as can be seen when the load is very low (λ/µ ∼∼ 0).
If there are, say, 30 routers along the flow's route, queueing delay alone will ac-
count for 600 µsec of delay.
One method of relating flow specifications to router resources that correspond
to bandwidth and delay performance guarantees is given by Parekh and Gallagher
(1993, 1994). It is based on traffic sources shaped by (R, B) token buckets and
WFQ at routers. Each flow is given a WFQ weight W large enough to drain its
token bucket rate R as shown in Fig. 5-33. For example, if the flow has a rate of 1
Mbps and the router and output link have a capacity of 1 Gbps, the weight for the
flow must be greater than 1/1000th of the total of the weights for all of the flows
at that router for the output link. This guarantees the flow a minimum bandwidth.
If it cannot be given a large enough rate, the flow cannot be admitted.
W x C
R <
w weights

W
Capacity C
(R, B) w i
Traffic source Weighted
Router fair queue
Figure 5-33. Bandwidth and delay guarantees with token buckets and WFQ.
The largest queueing delay the flow will see is a function of the burst size of
the token bucket. Consider the two extreme cases. If the traffic is smooth, without


---

<a id="page-430"></a>

<!-- Page 430 of 888 -->

418 THE NETWORK LAYER CHAP. 5
any bursts, packets will be drained from the router just as quickly as they arrive.
There will be no queueing delay (ignoring packetization effects). On the other
hand, if the traffic is saved up in bursts, then a maximum-size burst, B, may arrive
at the router all at once. In this case the maximum queueing delay, D, will be the
time taken to drain this burst at the guaranteed bandwidth, or B/R (again, ignoring
packetization effects). If this delay is too large, the flow must request more band-
width from the network.
These guarantees are hard. The token buckets bound the burstiness of the
source, and fair queueing isolates the bandwidth given to different flows. This
means that the flow will meet its bandwidth and delay guarantees regardless of
how the other competing flows behave at the router. Those other flows cannot
break the guarantee even by saving up traffic and all sending at once.
Moreover, the result holds for a path through multiple routers in any network
topology. Each flow gets a minimum bandwidth because that bandwidth is guar-
anteed at each router. The reason each flow gets a maximum delay is more sub-
tle. In the worst case that a burst of traffic hits the first router and competes with
the traffic of other flows, it will be delayed up to the maximum delay of D. How-
ever, this delay will also smooth the burst. In turn, this means that the burst will
incur no further queueing delays at later routers. The overall queueing delay will
be at most D.
#### 5.4.5 Integrated Services
Between 1995 and 1997, IETF put a lot of effort into devising an architecture
for streaming multimedia. This work resulted in over two dozen RFCs, starting
with RFCs 2205-2212. The generic name for this work is integrated services. It
was aimed at both unicast and multicast applications. An example of the former
is a single user streaming a video clip from a news site. An example of the latter
is a collection of digital television stations broadcasting their programs as streams
of IP packets to many receivers at various locations. Below we will concentrate
on multicast, since unicast is a special case of multicast.
In many multicast applications, groups can change membership dynamically,
for example, as people enter a video conference and then get bored and switch to
a soap opera or the croquet channel. Under these conditions, the approach of hav-
ing the senders reserve bandwidth in advance does not work well, since it would
require each sender to track all entries and exits of its audience. For a system de-
signed to transmit television with millions of subscribers, it would not work at all.
RSVP-The Resource reSerVation Protocol
The main part of the integrated services architecture that is visible to the users
of the network is RSVP. It is described in RFCs 2205-2210. This protocol is
used for making the reservations; other protocols are used for sending the data.


---

<a id="page-431"></a>

<!-- Page 431 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 419
RSVP allows multiple senders to transmit to multiple groups of receivers, permits
individual receivers to switch channels freely, and optimizes bandwidth use while
at the same time eliminating congestion.
In its simplest form, the protocol uses multicast routing using spanning trees,
as discussed earlier. Each group is assigned a group address. To send to a group,
a sender puts the group's address in its packets. The standard multicast routing al-
gorithm then builds a spanning tree covering all group members. The routing al-
gorithm is not part of RSVP. The only difference from normal multicasting is a
little extra information that is multicast to the group periodically to tell the routers
along the tree to maintain certain data structures in their memories.
As an example, consider the network of Fig. 5-34(a). Hosts 1 and 2 are multi-
cast senders, and hosts 3, 4, and 5 are multicast receivers. In this example, the
senders and receivers are disjoint, but in general, the two sets may overlap. The
multicast trees for hosts 1 and 2 are shown in Fig. 5-34(b) and Fig. 5-34(c), re-
spectively.
Senders
1 2 1 2 1 2
B B B
## A C A C A C
## D F D F D F
E E E
H H H
## G I G I G I
K K K
## J L J L J L
3 4 5 3 4 5 3 4 5
Receivers
(a) (b) (c)
Figure 5-34. (a) A network. (b) The multicast spanning tree for host 1. (c) The
multicast spanning tree for host 2.
To get better reception and eliminate congestion, any of the receivers in a
group can send a reservation message up the tree to the sender. The message is
propagated using the reverse path forwarding algorithm discussed earlier. At each


---

<a id="page-432"></a>

<!-- Page 432 of 888 -->

420 THE NETWORK LAYER CHAP. 5
hop, the router notes the reservation and reserves the necessary bandwidth. We
saw in the previous section how a weighted fair queueing scheduler can be used to
make this reservation. If insufficient bandwidth is available, it reports back
failure. By the time the message gets back to the source, bandwidth has been re-
served all the way from the sender to the receiver making the reservation request
along the spanning tree.
An example of such a reservation is shown in Fig. 5-35(a). Here host 3 has
requested a channel to host 1. Once it has been established, packets can flow
from 1 to 3 without congestion. Now consider what happens if host 3 next
reserves a channel to the other sender, host 2, so the user can watch two television
programs at once. A second path is reserved, as illustrated in Fig. 5-35(b). Note
that two separate channels are needed from host 3 to router E because two inde-
pendent streams are being transmitted.
1 2 1 2 1 2
B B B
## A C A C A C
Bandwidth
reserved for
source 2
## D E F D E F D E F
Bandwidth reserved
for source 1
## G H I G H I G H I
K K K
## J L J L J L
3 4 5 3 4 5 3 4 5
(a) (b) (c)
Figure 5-35. (a) Host 3 requests a channel to host 1. (b) Host 3 then requests a
second channel, to host 2. (c) Host 5 requests a channel to host 1.
Finally, in Fig. 5-35(c), host 5 decides to watch the program being transmitted
by host 1 and also makes a reservation. First, dedicated bandwidth is reserved as
far as router H. However, this router sees that it already has a feed from host 1, so
if the necessary bandwidth has already been reserved, it does not have to reserve
any more. Note that hosts 3 and 5 might have asked for different amounts of
bandwidth (e.g., if host 3 is playing on a small screen and only wants the low-
resolution information), so the capacity reserved must be large enough to satisfy
the greediest receiver.
When making a reservation, a receiver can (optionally) specify one or more
sources that it wants to receive from. It can also specify whether these choices


---

<a id="page-433"></a>

<!-- Page 433 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 421
are fixed for the duration of the reservation or whether the receiver wants to keep
open the option of changing sources later. The routers use this information to op-
timize bandwidth planning. In particular, two receivers are only set up to share a
path if they both agree not to change sources later on.
The reason for this strategy in the fully dynamic case is that reserved band-
width is decoupled from the choice of source. Once a receiver has reserved band-
width, it can switch to another source and keep that portion of the existing path
that is valid for the new source. If host 2 is transmitting several video streams in
real time, for example a TV broadcaster with multiple channels, host 3 may
switch between them at will without changing its reservation: the routers do not
care what program the receiver is watching.
#### 5.4.6 Differentiated Services
Flow-based algorithms have the potential to offer good quality of service to
one or more flows because they reserve whatever resources are needed along the
route. However, they also have a downside. They require an advance setup to es-
tablish each flow, something that does not scale well when there are thousands or
millions of flows. Also, they maintain internal per-flow state in the routers, mak-
ing them vulnerable to router crashes. Finally, the changes required to the router
code are substantial and involve complex router-to-router exchanges for setting up
the flows. As a consequence, while work continues to advance integrated ser-
vices, few deployments of it or anything like it exist yet.
For these reasons, IETF has also devised a simpler approach to quality of ser-
vice, one that can be largely implemented locally in each router without advance
setup and without having the whole path involved. This approach is known as
class-based (as opposed to flow-based) quality of service. IETF has standardized
an architecture for it, called differentiated services, which is described in RFCs
2474, 2475, and numerous others. We will now describe it.
Differentiated services can be offered by a set of routers forming an adminis-
trative domain (e.g., an ISP or a telco). The administration defines a set of service
classes with corresponding forwarding rules. If a customer subscribes to dif-
ferentiated services, customer packets entering the domain are marked with the
class to which they belong. This information is carried in the Differentiated ser-
vices field of IPv4 and IPv6 packets (described in Sec. 5.6). The classes are de-
fined as per hop behaviors because they correspond to the treatment the packet
will receive at each router, not a guarantee across the network. Better service is
provided to packets with some per-hop behaviors (e.g., premium service) than to
others (e.g., regular service). Traffic within a class may be required to conform to
some specific shape, such as a leaky bucket with some specified drain rate. An
operator with a nose for business might charge extra for each premium packet
transported or might allow up to N premium packets per month for a fixed addi-
tional monthly fee. Note that this scheme requires no advance setup, no resource


---

<a id="page-434"></a>

<!-- Page 434 of 888 -->

422 THE NETWORK LAYER CHAP. 5
reservation, and no time-consuming end-to-end negotiation for each flow, as with
integrated services. This makes differentiated services relatively easy to imple-
ment.
Class-based service also occurs in other industries. For example, package de-
livery companies often offer overnight, two-day, and three-day service. Airlines
offer first class, business class, and cattle-class service. Long-distance trains
often have multiple service classes. Even the Paris subway has two different ser-
vice classes. For packets, the classes may differ in terms of delay, jitter, and
probability of being discarded in the event of congestion, among other possibili-
ties (but probably not roomier Ethernet frames).
To make the difference between flow-based quality of service and class-based
quality of service clearer, consider an example: Internet telephony. With a flow-
based scheme, each telephone call gets its own resources and guarantees. With a
class-based scheme, all the telephone calls together get the resources reserved for
the class telephony. These resources cannot be taken away by packets from the
Web browsing class or other classes, but no telephone call gets any private re-
sources reserved for it alone.
Expedited Forwarding
The choice of service classes is up to each operator, but since packets are
often forwarded between networks run by different operators, IETF has defined
some network-independent service classes. The simplest class is expedited for-
warding, so let us start with that one. It is described in RFC 3246.
The idea behind expedited forwarding is very simple. Two classes of service
are available: regular and expedited. The vast majority of the traffic is expected
to be regular, but a limited fraction of the packets are expedited. The expedited
packets should be able to transit the network as though no other packets were
present. In this way they will get low loss, low delay and low jitter service-just
what is needed for VoIP. A symbolic representation of this ''two-tube'' system is
given in Fig. 5-36. Note that there is still just one physical line. The two logical
pipes shown in the figure represent a way to reserve bandwidth for different
classes of service, not a second physical line.
One way to implement this strategy is as follows. Packets are classified as
expedited or regular and marked accordingly. This step might be done on the
sending host or in the ingress (first) router. The advantage of doing classification
on the sending host is that more information is available about which packets be-
long to which flows. This task may be performed by networking software or even
the operating system, to avoid having to change existing applications. For ex-
ample, it is becoming common for VoIP packets to be marked for expedited ser-
vice by hosts. If the packets pass through a corporate network or ISP that sup-
ports expedited service, they will receive preferential treatment. If the network
does not support expedited service, no harm is done.


---

<a id="page-435"></a>

<!-- Page 435 of 888 -->

SEC. 5.4 QUALITY OF SERVICE 423
Expedited packets
Regular packets
Figure 5-36. Expedited packets experience a traffic-free network.
Of course, if the marking is done by the host, the ingress router is likely to
police the traffic to make sure that customers are not sending more expedited traf-
fic than they have paid for. Within the network, the routers may have two output
queues for each outgoing line, one for expedited packets and one for regular pack-
ets. When a packet arrives, it is queued accordingly. The expedited queue is
given priority over the regular one, for example, by using a priority scheduler. In
this way, expedited packets see an unloaded network, even when there is, in fact,
a heavy load of regular traffic.
Assured Forwarding
A somewhat more elaborate scheme for managing the service classes is called
assured forwarding. It is described in RFC 2597. Assured forwarding specifies
that there shall be four priority classes, each class having its own resources. The
top three classes might be called gold, silver, and bronze. In addition, it defines
three discard classes for packets that are experiencing congestion: low, medium,
and high. Taken together, these two factors define 12 service classes.
Figure 5-37 shows one way packets might be processed under assured for-
warding. The first step is to classify the packets into one of the four priority
classes. As before, this step might be done on the sending host (as shown in the
figure) or in the ingress router, and the rate of higher-priority packets may be lim-
ited by the operator as part of the service offering.
The next step is to determine the discard class for each packet. This is done
by passing the packets of each priority class through a traffic policer such as a
token bucket. The policer lets all of the traffic through, but it identifies packets
that fit within small bursts as low discard, packets that exceed small bursts as
medium discard, and packets that exceed large bursts as high discard. The combi-
nation of priority and discard class is then encoded in each packet.
Finally, the packets are processed by routers in the network with a packet
scheduler that distinguishes the different classes. A common choice is to use


---

<a id="page-436"></a>

<!-- Page 436 of 888 -->

424 THE NETWORK LAYER CHAP. 5
Packets with
DiffServ mark
Gold
Silver
Classifier Policer
Bronze
Packet
source Four Twelve Weighted
priority priority/drop fair queues
classes classes Router
Figure 5-37. A possible implementation of assured forwarding.
weighted fair queueing for the four priority classes, with higher classes given
higher weights. In this way, the higher classes will get most of the bandwidth, but
the lower classes will not be starved of bandwidth entirely. For example, if the
weights double from one class to the next higher class, the higher class will get
twice the bandwidth. Within a priority class, packets with a higher discard class
can be preferentially dropped by running an algorithm such as RED (Random
Early Detection), which we saw in Sec. 5.3.5. RED will start to drop packets as
congestion builds but before the router has run out of buffer space. At this stage,
there is still buffer space with which to accept low discard packets while dropping
high discard packets.
### 5.5 INTERNETWORKING
Until now, we have implicitly assumed that there is a single homogeneous
network, with each machine using the same protocol in each layer. Unfortunately,
this assumption is wildly optimistic. Many different networks exist, including
PANs, LANs, MANs, and WANs. We have described Ethernet, Internet over
cable, the fixed and mobile telephone networks, 802.11, 802.16, and more. Num-
erous protocols are in widespread use across these networks in every layer. In the
following sections, we will take a careful look at the issues that arise when two or
more networks are connected to form an internetwork, or more simply an inter-
net.
It would be much simpler to join networks together if everyone used a single
networking technology, and it is often the case that there is a dominant kind of
network, such as Ethernet. Some pundits speculate that the multiplicity of technol-
ogies will go away as soon as everyone realizes how wonderful [fill in your favor-
ite network] is. Do not count on it. History shows this to be wishful thinking. Dif-
ferent kinds of networks grapple with different problems, so, for example, Ether-
net and satellite networks are always likely to differ. Reusing existing systems,
such as running data networks on top of cable, the telephone network, and power


---

<a id="page-437"></a>

<!-- Page 437 of 888 -->

SEC. 5.5 INTERNETWORKING 425
lines, adds constraints that cause the features of the networks to diverge. Hetero-
geneity is here to stay.
If there will always be different networks, it would be simpler if we did not
need to interconnect them. This also is unlikely. Bob Metcalfe postulated that the
value of a network with N nodes is the number of connections that may be made
between the nodes, or N 2 (Gilder, 1993). This means that large networks are
much more valuable than small networks because they allow many more con-
nections, so there always will be an incentive to combine smaller networks.
The Internet is the prime example of this interconnection. (We will write In-
ternet with a capital ''I'' to distinguish it from other internets, or connected net-
works.) The purpose of joining all these networks is to allow users on any of
them to communicate with users on all the other ones. When you pay an ISP for
Internet service, you may be charged depending on the bandwidth of your line, but
what you are really paying for is the ability to exchange packets with any other
host that is also connected to the Internet. After all, the Internet would not be very
popular if you could only send packets to other hosts in the same city.
Since networks often differ in important ways, getting packets from one net-
work to another is not always so easy. We must address problems of hetero-
geneity, and also problems of scale as the resulting internet grows very large. We
will begin by looking at how networks can differ to see what we are up against.
Then we shall see the approach used so successfully by IP (Internet Protocol), the
network layer protocol of the Internet, including techniques for tunneling through
networks, routing in internetworks, and packet fragmentation.
#### 5.5.1 How Networks Differ
Networks can differ in many ways. Some of the differences, such as different
modulation techniques or frame formats, are internal to the physical and data link
layers. These differences will not concern us here. Instead, in Fig. 5-38 we list
some of the differences that can be exposed to the network layer. It is papering
over these differences that makes internetworking more difficult than operating
within a single network.
When packets sent by a source on one network must transit one or more for-
eign networks before reaching the destination network, many problems can occur
at the interfaces between networks. To start with, the source needs to be able to
address the destination. What do we do if the source is on an Ethernet network
and the destination is on a WiMAX network? Assuming we can even specify a
WiMAX destination from an Ethernet network, packets would cross from a con-
nectionless network to a connection-oriented one. This may require that a new
connection be set up on short notice, which injects a delay, and much overhead if
the connection is not used for many more packets.
Many specific differences may have to be accommodated as well. How do
we multicast a packet to a group with some members on a network that does not


---

<a id="page-438"></a>

<!-- Page 438 of 888 -->

426 THE NETWORK LAYER CHAP. 5
Item Some Possibilities
Service offered Connectionless versus connection oriented
Addressing Different sizes, flat or hierarchical
Broadcasting Present or absent (also multicast)
Packet size Every network has its own maximum
Ordering Ordered and unordered delivery
Quality of service Present or absent; many different kinds
Reliability Different levels of loss
Security Privacy rules, encryption, etc.
Parameters Different timeouts, flow specifications, etc.
Accounting By connect time, packet, byte, or not at all
Figure 5-38. Some of the many ways networks can differ.
support multicast? The differing max packet sizes used by different networks can
be a major nuisance, too. How do you pass an 8000-byte packet through a net-
work whose maximum size is 1500 bytes? If packets on a connection-oriented
network transit a connectionless network, they may arrive in a different order than
they were sent. That is something the sender likely did not expect, and it might
come as an (unpleasant) surprise to the receiver as well.
These kinds of differences can be papered over, with some effort. For ex-
ample, a gateway joining two networks might generate separate packets for each
destination in lieu of better network support for multicasting. A large packet
might be broken up, sent in pieces, and then joined back together. Receivers
might buffer packets and deliver them in order.
Networks also can differ in large respects that are more difficult to reconcile.
The clearest example is quality of service. If one network has strong QoS and the
other offers best effort service, it will be impossible to make bandwidth and delay
guarantees for real-time traffic end to end. In fact, they can likely only be made
while the best-effort network is operated at a low utilization, or hardly used,
which is unlikely to be the goal of most ISPs. Security mechanisms are prob-
lematic, but at least encryption for confidentiality and data integrity can be lay-
ered on top of networks that do not already include it. Finally, differences in ac-
counting can lead to unwelcome bills when normal usage suddenly becomes ex-
pensive, as roaming mobile phone users with data plans have discovered.
#### 5.5.2 How Networks Can Be Connected
There are two basic choices for connecting different networks: we can build
devices that translate or convert packets from each kind of network into packets
for each other network, or, like good computer scientists, we can try to solve the


---

<a id="page-439"></a>

<!-- Page 439 of 888 -->

SEC. 5.5 INTERNETWORKING 427
problem by adding a layer of indirection and building a common layer on top of
the different networks. In either case, the devices are placed at the boundaries be-
tween networks.
Early on, Cerf and Kahn (1974) argued for a common layer to hide the dif-
ferences of existing networks. This approach has been tremendously successful,
and the layer they proposed was eventually separated into the TCP and IP proto-
cols. Almost four decades later, IP is the foundation of the modern Internet. For
this accomplishment, Cerf and Kahn were awarded the 2004 Turing Award, infor-
mally known as the Nobel Prize of computer science. IP provides a universal
packet format that all routers recognize and that can be passed through almost
every network. IP has extended its reach from computer networks to take over the
telephone network. It also runs on sensor networks and other tiny devices that
were once presumed too resource-constrained to support it.
We have discussed several different devices that connect networks, including
repeaters, hubs, switches, bridges, routers, and gateways. Repeaters and hubs just
move bits from one wire to another. They are mostly analog devices and do not
understand anything about higher layer protocols. Bridges and switches operate at
the link layer. They can be used to build networks, but only with minor protocol
translation in the process, for example, between 10, 100 and 1000 Mbps Ethernet
switches. Our focus in this section is interconnection devices that operate at the
network layer, namely the routers. We will leave gateways, which are higher-
layer interconnection devices, until later.
Let us first explore at a high level how interconnection with a common net-
work layer can be used to interconnect dissimilar networks. An internet
comprised of 802.11, MPLS, and Ethernet networks is shown in Fig. 5-39(a).
Suppose that the source machine on the 802.11 network wants to send a packet to
the destination machine on the Ethernet network. Since these technologies are dif-
ferent, and they are further separated by another kind of network (MPLS), some
added processing is needed at the boundaries between the networks.
Because different networks may, in general, have different forms of ad-
dressing, the packet carries a network layer address that can identify any host a-
cross the three networks. The first boundary the packet reaches is when it tran-
sitions from an 802.11 network to an MPLS network. 802.11 provides a con-
nectionless service, but MPLS provides a connection-oriented service. This means
that a virtual circuit must be set up to cross that network. Once the packet has
traveled along the virtual circuit, it will reach the Ethernet network. At this
boundary, the packet may be too large to be carried, since 802.11 can work with
larger frames than Ethernet. To handle this problem, the packet is divided into
fragments, and each fragment is sent separately. When the fragments reach the
destination, they are reassembled. Then the packet has completed its journey.
The protocol processing for this journey is shown in Fig. 5-39(b). The source
accepts data from the transport layer and generates a packet with the common net-
work layer header, which is IP in this example. The network header contains the


---

<a id="page-440"></a>

<!-- Page 440 of 888 -->

428 THE NETWORK LAYER CHAP. 5
Packet Virtual circuit
### 802.11 MPLS Ethernet
Source Router Router Destination
(a)
Data from
transport layer
## Ip Ip Ip Ip
### 802.11 IP 802.11 IP MPLSIP MPLSIP Eth IP Eth IP
Physical
(b)
Figure 5-39. (a) A packet crossing different networks. (b) Network and link
layer protocol processing.
ultimate destination address, which is used to determine that the packet should be
sent via the first router. So the packet is encapsulated in an 802.11 frame whose
destination is the first router and transmitted. At the router, the packet is removed
from the frame's data field and the 802.11 frame header is discarded. The router
now examines the IP address in the packet and looks up this address in its routing
table. Based on this address, it decides to send the packet to the second router
next. For this part of the path, an MPLS virtual circuit must be established to the
second router and the packet must be encapsulated with MPLS headers that travel
this circuit. At the far end, the MPLS header is discarded and the network address
is again consulted to find the next network layer hop. It is the destination itself.
Since the packet is too long to be sent over Ethernet, it is split into two portions.
Each of these portions is put into the data field of an Ethernet frame and sent to
the Ethernet address of the destination. At the destination, the Ethernet header is
stripped from each of the frames, and the contents are reassembled. The packet
has finally reached its destination.
Observe that there is an essential difference between the routed case and the
switched (or bridged) case. With a router, the packet is extracted from the frame
and the network address in the packet is used for deciding where to send it. With
a switch (or bridge), the entire frame is transported on the basis of its MAC ad-
dress. Switches do not have to understand the network layer protocol being used
to switch packets. Routers do.
Unfortunately, internetworking is not as easy as we have made it sound. In
fact, when bridges were introduced, it was intended that they would join different
types of networks, or at least different types of LANs. They were to do this by
translating frames from one LAN into frames from another LAN. However, this


---

<a id="page-441"></a>

<!-- Page 441 of 888 -->

SEC. 5.5 INTERNETWORKING 429
did not work well, for the same reason that internetworking is difficult: the dif-
ferences in the features of LANs, such as different maximum packet sizes and
LANs with and without priority classes, are hard to mask. Today, bridges are
predominantly used to connect the same kind of network at the link layer, and
routers connect different networks at the network layer.
Internetworking has been very successful at building large networks, but it
only works when there is a common network layer. There have, in fact, been
many network protocols over time. Getting everybody to agree on a single format
is difficult when companies perceive it to their commercial advantage to have a
proprietary format that they control. Examples besides IP, which is now the
near-universal network protocol, were IPX, SNA, and AppleTalk. None of these
protocols are still in widespread use, but there will always be other protocols. The
most relevant example now is probably IPv4 and IPv6. While these are both ver-
sions of IP, they are not compatible (or it would not have been necessary to create
IPv6).
A router that can handle multiple network protocols is called a multiprotocol
router. It must either translate the protocols, or leave connection for a higher
protocol layer. Neither approach is entirely satisfactory. Connection at a higher
layer, say, by using TCP, requires that all the networks implement TCP (which
may not be the case). Then, it limits usage across the networks to applications that
use TCP (which does not include many real-time applications).
The alternative is to translate packets between the networks. However, unless
the packet formats are close relatives with the same information fields, such
conversions will always be incomplete and often doomed to failure. For example,
IPv6 addresses are 128 bits long. They will not fit in a 32-bit IPv4 address field,
no matter how hard the router tries. Getting IPv4 and IPv6 to run in the same net-
work has proven to be a major obstacle to the deployment of IPv6. (To be fair, so
has getting customers to understand why they should want IPv6 in the first place.)
Greater problems can be expected when translating between fundamentally dif-
ferent protocols, such as connectionless and connection-oriented network proto-
cols. Given these difficulties, conversion is only rarely attempted. Arguably,
even IP has only worked so well by serving as a kind of lowest common denomi-
nator. It requires little of the networks on which it runs, but offers only best-effort
service as a result.
#### 5.5.3 Tunneling
Handling the general case of making two different networks interwork is
exceedingly difficult. However, there is a common special case that is man-
ageable even for different network protocols. This case is where the source and
destination hosts are on the same type of network, but there is a different network
in between. As an example, think of an international bank with an IPv6 network


---

<a id="page-442"></a>

<!-- Page 442 of 888 -->

430 THE NETWORK LAYER CHAP. 5
in Paris, an IPv6 network in London and connectivity between the offices via the
IPv4 Internet. This situation is shown in Fig. 5-40.
IPv6 IPv4 IPv6
Paris Router Router London
Tunnel
IPv6 packet IPv4 IPv6 packet IPv6 packet
Figure 5-40. Tunneling a packet from Paris to London.
The solution to this problem is a technique called tunneling. To send an IP
packet to a host in the London office, a host in the Paris office constructs the
packet containing an IPv6 address in London, and sends it to the multiprotocol
router that connects the Paris IPv6 network to the IPv4 Internet. When this router
gets the IPv6 packet, it encapsulates the packet with an IPv4 header addressed to
the IPv4 side of the multiprotocol router that connects to the London IPv6 net-
work. That is, the router puts a (IPv6) packet inside a (IPv4) packet. When this
wrapped packet arrives, the London router removes the original IPv6 packet and
sends it onward to the destination host.
The path through the IPv4 Internet can be seen as a big tunnel extending from
one multiprotocol router to the other. The IPv6 packet just travels from one end
of the tunnel to the other, snug in its nice box. It does not have to worry about
dealing with IPv4 at all. Neither do the hosts in Paris or London. Only the multi-
protocol routers have to understand both IPv4 and IPv6 packets. In effect, the en-
tire trip from one multiprotocol router to the other is like a hop over a single link.
An analogy may make tunneling clearer. Consider a person driving her car
from Paris to London. Within France, the car moves under its own power, but
when it hits the English Channel, it is loaded onto a high-speed train and tran-
sported to England through the Chunnel (cars are not permitted to drive through
the Chunnel). Effectively, the car is being carried as freight, as depicted in
Fig. 5-41. At the far end, the car is let loose on the English roads and once again
continues to move under its own power. Tunneling of packets through a foreign
network works the same way.
Tunneling is widely used to connect isolated hosts and networks using other
networks. The network that results is called an overlay since it has effectively
been overlaid on the base network. Deployment of a network protocol with a new
feature is a common reason, as our ''IPv6 over IPv4'' example shows. The disad-
vantage of tunneling is that none of the hosts on the network that is tunneled over
can be reached because the packets cannot escape in the middle of the tunnel.


---

<a id="page-443"></a>

<!-- Page 443 of 888 -->

SEC. 5.5 INTERNETWORKING 431
Car
English Channel
Paris London
Railroad carriage
Railroad track
Figure 5-41. Tunneling a car from France to England.
However, this limitation of tunnels is turned into an advantage with VPNs (Vir-
tual Private Networks). A VPN is simply an overlay that is used to provide a
measure of security. We will explore VPNs when we get to Chap. 8.
#### 5.5.4 Internetwork Routing
Routing through an internet poses the same basic problem as routing within a
single network, but with some added complications. To start, the networks may
internally use different routing algorithms. For example, one network may use
link state routing and another distance vector routing. Since link state algorithms
need to know the topology but distance vector algorithms do not, this difference
alone would make it unclear how to find the shortest paths across the internet.
Networks run by different operators lead to bigger problems. First, the opera-
tors may have different ideas about what is a good path through the network. One
operator may want the route with the least delay, while another may want the
most inexpensive route. This will lead the operators to use different quantities to
set the shortest-path costs (e.g., milliseconds of delay vs. monetary cost). The
weights will not be comparable across networks, so shortest paths on the internet
will not be well defined.
Worse yet, one operator may not want another operator to even know the de-
tails of the paths in its network, perhaps because the weights and paths may reflect
sensitive information (such as the monetary cost) that represents a competitive
business advantage.
Finally, the internet may be much larger than any of the networks that
comprise it. It may therefore require routing algorithms that scale well by using a
hierarchy, even if none of the individual networks need to use a hierarchy.
All of these considerations lead to a two-level routing algorithm. Within each
network, an intradomain or interior gateway protocol is used for routing.
(''Gateway'' is an older term for ''router.'') It might be a link state protocol of the
kind we have already described. Across the networks that make up the internet,
an interdomain or exterior gateway protocol is used. The networks may all use
different intradomain protocols, but they must use the same interdomain protocol.


---

<a id="page-444"></a>

<!-- Page 444 of 888 -->

432 THE NETWORK LAYER CHAP. 5
In the Internet, the interdomain routing protocol is called BGP (Border Gateway
Protocol). We will describe it in the next section.
There is one more important term to introduce. Since each network is oper-
ated independently of all the others, it is often referred to as an AS (Autonomous
System). A good mental model for an AS is an ISP network. In fact, an ISP net-
work may be comprised of more than one AS, if it is managed, or, has been ac-
quired, as multiple networks. But the difference is usually not significant.
The two levels are usually not strictly hierarchical, as highly suboptimal paths
might result if a large international network and a small regional network were
both abstracted to be a single network. However, relatively little information
about routes within the networks is exposed to find routes across the internetwork.
This helps to address all of the complications. It improves scaling and lets opera-
tors freely select routes within their own networks using a protocol of their choos-
ing. It also does not require weights to be compared across networks or expose
sensitive information outside of networks.
However, we have said little so far about how the routes across the networks
of the internet are determined. In the Internet, a large determining factor is the
business arrangements between ISPs. Each ISP may charge or receive money
from the other ISPs for carrying traffic. Another factor is that if internetwork
routing requires crossing international boundaries, various laws may suddenly
come into play, such as Sweden's strict privacy laws about exporting personal
data about Swedish citizens from Sweden. All of these nontechnical factors are
wrapped up in the concept of a routing policy that governs the way autonomous
networks select the routes that they use. We will return to routing policies when
we describe BGP.
#### 5.5.5 Packet Fragmentation
Each network or link imposes some maximum size on its packets. These lim-
its have various causes, among them
1. Hardware (e.g., the size of an Ethernet frame).
2. Operating system (e.g., all buffers are 512 bytes).
3. Protocols (e.g., the number of bits in the packet length field).
4. Compliance with some (inter)national standard.
5. Desire to reduce error-induced retransmissions to some level.
6. Desire to prevent one packet from occupying the channel too long.
The result of all these factors is that the network designers are not free to choose
any old maximum packet size they wish. Maximum payloads for some common


---

<a id="page-445"></a>

<!-- Page 445 of 888 -->

SEC. 5.5 INTERNETWORKING 433
technologies are 1500 bytes for Ethernet and 2272 bytes for 802.11. IP is more
generous, allows for packets as big as 65,515 bytes.
Hosts usually prefer to transmit large packets because this reduces packet
overheads such as bandwidth wasted on header bytes. An obvious internetwork-
ing problem appears when a large packet wants to travel through a network whose
maximum packet size is too small. This nuisance has been a persistent issue, and
solutions to it have evolved along with much experience gained on the Internet.
One solution is to make sure the problem does not occur in the first place.
However, this is easier said than done. A source does not usually know the path a
packet will take through the network to a destination, so it certainly does not
know how small packets must be to get there. This packet size is called the Path
MTU (Path Maximum Transmission Unit). Even if the source did know the
path MTU, packets are routed independently in a connectionless network such as
the Internet. This routing means that paths may suddenly change, which can
unexpectedly change the path MTU.
The alternative solution to the problem is to allow routers to break up packets
into fragments, sending each fragment as a separate network layer packet. How-
ever, as every parent of a small child knows, converting a large object into small
fragments is considerably easier than the reverse process. (Physicists have even
given this effect a name: the second law of thermodynamics.) Packet-switching
networks, too, have trouble putting the fragments back together again.
Two opposing strategies exist for recombining the fragments back into the
original packet. The first strategy is to make fragmentation caused by a ''small-
packet'' network transparent to any subsequent networks through which the pack-
et must pass on its way to the ultimate destination. This option is shown in Fig. 5-
42(a). In this approach, when an oversized packet arrives at G1, the router breaks
it up into fragments. Each fragment is addressed to the same exit router, G2,
where the pieces are recombined. In this way, passage through the small-packet
network is made transparent. Subsequent networks are not even aware that frag-
mentation has occurred.
Transparent fragmentation is straightforward but has some problems. For one
thing, the exit router must know when it has received all the pieces, so either a
count field or an ''end of packet'' bit must be provided. Also, because all packets
must exit via the same router so that they can be reassembled, the routes are con-
strained. By not allowing some fragments to follow one route to the ultimate dest-
ination and other fragments a disjoint route, some performance may be lost. More
significant is the amount of work that the router may have to do. It may need to
buffer the fragments as they arrive, and decide when to throw them away if not all
of the fragments arrive. Some of this work may be wasteful, too, as the packet
may pass through a series of small packet networks and need to be repeatedly
fragmented and reassembled.
The other fragmentation strategy is to refrain from recombining fragments at
any intermediate routers. Once a packet has been fragmented, each fragment is


---

<a id="page-446"></a>

<!-- Page 446 of 888 -->

434 THE NETWORK LAYER CHAP. 5
Network 1 Network 2
Packet
G G G G
1 2 3 4
G 2 G 4
G 1 fragments reassembles G 3 fragments reassembles
a large packet the fragments again again
(a)
Packet
G G G G
1 2 3 4
G fragments The fragments are not reassembled

a large packet until the final destination (a host) is reached
(b)
Figure 5-42. (a) Transparent fragmentation. (b) Nontransparent fragmentation.
treated as though it were an original packet. The routers pass the fragments, as
shown in Fig. 5-42(b), and reassembly is performed only at the destination host.
The main advantage of nontransparent fragmentation is that it requires routers
to do less work. IP works this way. A complete design requires that the fragments
be numbered in such a way that the original data stream can be reconstructed.
The design used by IP is to give every fragment a packet number (carried on all
packets), an absolute byte offset within the packet, and a flag indicating whether it
is the end of the packet. An example is shown in Fig. 5-43. While simple, this
design has some attractive properties. Fragments can be placed in a buffer at the
destination in the right place for reassembly, even if they arrive out of order.
Fragments can also be fragmented if they pass over a network with a yet smaller
MTU. This is shown in Fig. 5-43(c). Retransmissions of the packet (if all frag-
ments were not received) can be fragmented into different pieces. Finally, frag-
ments can be of arbitrary size, down to a single byte plus the packet header. In all
cases, the destination simply uses the packet number and fragment offset to place
the data in the right position, and the end-of-packet flag to determine when it has
the complete packet.
Unfortunately, this design still has problems. The overhead can be higher
than with transparent fragmentation because fragment headers are now carried
over some links where they may not be needed. But the real problem is the exist-
ence of fragments in the first place. Kent and Mogul (1987) argued that frag-
mentation is detrimental to performance because, as well as the header overheads,
a whole packet is lost if any of its fragments are lost, and because fragmentation is
more of a burden for hosts than was originally realized.


---

<a id="page-447"></a>

<!-- Page 447 of 888 -->

SEC. 5.5 INTERNETWORKING 435
Number of the first elementary fragment in this packet
Packet End of
number packet bit 1 byte
27 0 1 A B C D E F G H I J
Header
(a)
27 0 0 A B C D E F G H 27 8 1 I J
Header Header
(b)
27 0 0 A B C D E 27 5 0 F G H 27 8 1 I J
Header Header Header
(c)
Figure 5-43. Fragmentation when the elementary data size is 1 byte. (a) Origi-
nal packet, containing 10 data bytes. (b) Fragments after passing through a net-
work with maximum packet size of 8 payload bytes plus header. (c) Fragments
after passing through a size 5 gateway.
This leads us back to the original solution of getting rid of fragmentation in
the network, the strategy used in the modern Internet. The process is called path
MTU discovery (Mogul and Deering, 1990). It works as follows. Each IP packet
is sent with its header bits set to indicate that no fragmentation is allowed to be
performed. If a router receives a packet that is too large, it generates an error
packet, returns it to the source, and drops the packet. This is shown in Fig. 5-44.
When the source receives the error packet, it uses the information inside to refrag-
ment the packet into pieces that are small enough for the router to handle. If a
router further down the path has an even smaller MTU, the process is repeated.
Packet (with length)
1400 1200 900
Source Destination
"Try 1200" "Try 900"
Figure 5-44. Path MTU discovery.


---

<a id="page-448"></a>

<!-- Page 448 of 888 -->

436 THE NETWORK LAYER CHAP. 5
The advantage of path MTU discovery is that the source now knows what
length packet to send. If the routes and path MTU change, new error packets will
be triggered and the source will adapt to the new path. However, fragmentation is
still needed between the source and the destination unless the higher layers learn
the path MTU and pass the right amount of data to IP. TCP and IP are typically
implemented together (as ''TCP/IP'') to be able to pass this sort of information.
Even if this is not done for other protocols, fragmentation has still been moved out
of the network and into the hosts.
The disadvantage of path MTU discovery is that there may be added startup
delays simply to send a packet. More than one round-trip delay may be needed to
probe the path and find the MTU before any data is delivered to the destination.
This begs the question of whether there are better designs. The answer is proba-
bly ''Yes.'' Consider the design in which each router simply truncates packets that
exceed its MTU. This would ensure that the destination learns the MTU as rapidly
as possible (from the amount of data that was delivered) and receives some of the
data.
### 5.6 THE NETWORK LAYER IN THE INTERNET
It is now time to discuss the network layer of the Internet in detail. But before
getting into specifics, it is worth taking a look at the principles that drove its de-
sign in the past and made it the success that it is today. All too often, nowadays,
people seem to have forgotten them. These principles are enumerated and dis-
cussed in RFC 1958, which is well worth reading (and should be mandatory for all
protocol designers-with a final exam at the end). This RFC draws heavily on
ideas put forth by Clark (1988) and Saltzer et al. (1984). We will now summarize
what we consider to be the top 10 principles (from most important to least impor-
tant).
1. Make sure it works. Do not finalize the design or standard until
multiple prototypes have successfully communicated with each
other. All too often, designers first write a 1000-page standard, get it
approved, then discover it is deeply flawed and does not work. Then
they write version 1.1 of the standard. This is not the way to go.
2. Keep it simple. When in doubt, use the simplest solution. William
of Occam stated this principle (Occam's razor) in the 14th century.
Put in modern terms: fight features. If a feature is not absolutely es-
sential, leave it out, especially if the same effect can be achieved by
combining other features.
3. Make clear choices. If there are several ways of doing the same
thing, choose one. Having two or more ways to do the same thing is
looking for trouble. Standards often have multiple options or modes


---

<a id="page-449"></a>

<!-- Page 449 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 437
or parameters because several powerful parties insist that their way is
best. Designers should strongly resist this tendency. Just say no.
4. Exploit modularity. This principle leads directly to the idea of hav-
ing protocol stacks, each of whose layers is independent of all the
other ones. In this way, if circumstances require one module or layer
to be changed, the other ones will not be affected.
5. Expect heterogeneity. Different types of hardware, transmission
facilities, and applications will occur on any large network. To
handle them, the network design must be simple, general, and flexi-
ble.
6. Avoid static options and parameters. If parameters are unavoid-
able (e.g., maximum packet size), it is best to have the sender and re-
ceiver negotiate a value rather than defining fixed choices.
7. Look for a good design; it need not be perfect. Often, the de-
signers have a good design but it cannot handle some weird special
case. Rather than messing up the design, the designers should go
with the good design and put the burden of working around it on the
people with the strange requirements.
8. Be strict when sending and tolerant when receiving. In other
words, send only packets that rigorously comply with the standards,
but expect incoming packets that may not be fully conformant and
try to deal with them.
9. Think about scalability. If the system is to handle millions of hosts
and billions of users effectively, no centralized databases of any kind
are tolerable and load must be spread as evenly as possible over the
available resources.
10. Consider performance and cost. If a network has poor per-
formance or outrageous costs, nobody will use it.
Let us now leave the general principles and start looking at the details of the
Internet's network layer. In the network layer, the Internet can be viewed as a
collection of networks or ASes (Autonomous Systems) that are interconnected.
There is no real structure, but several major backbones exist. These are con-
structed from high-bandwidth lines and fast routers. The biggest of these back-
bones, to which everyone else connects to reach the rest of the Internet, are called
Tier 1 networks. Attached to the backbones are ISPs (Internet Service Pro-
viders) that provide Internet access to homes and businesses, data centers and
colocation facilities full of server machines, and regional (mid-level) networks.
The data centers serve much of the content that is sent over the Internet. Attached


---

<a id="page-450"></a>

<!-- Page 450 of 888 -->

438 THE NETWORK LAYER CHAP. 5
to the regional networks are more ISPs, LANs at many universities and com-
panies, and other edge networks. A sketch of this quasihierarchical organization
is given in Fig. 5-45.
Leased
Leased lines A U.S. backbone transatlantic A European backbone
to Asia lines
Mobile
network National
Regional
network
network
WiMAX
IP router Company
network
Cable
Home
network Ethernet
Figure 5-45. The Internet is an interconnected collection of many networks.
The glue that holds the whole Internet together is the network layer protocol,
IP (Internet Protocol). Unlike most older network layer protocols, IP was de-
signed from the beginning with internetworking in mind. A good way to think of
the network layer is this: its job is to provide a best-effort (i.e., not guaranteed)
way to transport packets from source to destination, without regard to whether
these machines are on the same network or whether there are other networks in
between them.
Communication in the Internet works as follows. The transport layer takes
data streams and breaks them up so that they may be sent as IP packets. In theory,
packets can be up to 64 KB each, but in practice they are usually not more than
1500 bytes (so they fit in one Ethernet frame). IP routers forward each packet
through the Internet, along a path from one router to the next, until the destination
is reached. At the destination, the network layer hands the data to the transport
layer, which gives it to the receiving process. When all the pieces finally get to
the destination machine, they are reassembled by the network layer into the origi-
nal datagram. This datagram is then handed to the transport layer.
In the example of Fig. 5-45, a packet originating at a host on the home net-
work has to traverse four networks and a large number of IP routers before even
getting to the company network on which the destination host is located. This is


---

<a id="page-451"></a>

<!-- Page 451 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 439
not unusual in practice, and there are many longer paths. There is also much
redundant connectivity in the Internet, with backbones and ISPs connecting to
each other in multiple locations. This means that there are many possible paths
between two hosts. It is the job of the IP routing protocols to decide which paths
to use.
#### 5.6.1 The IP Version 4 Protocol
An appropriate place to start our study of the network layer in the Internet is
with the format of the IP datagrams themselves. An IPv4 datagram consists of a
header part and a body or payload part. The header has a 20-byte fixed part and a
variable-length optional part. The header format is shown in Fig. 5-46. The bits
are transmitted from left to right and top to bottom, with the high-order bit of the
Version field going first. (This is a ''big-endian'' network byte order. On little-
endian machines, such as Intel x86 computers, a software conversion is required
on both transmission and reception.) In retrospect, little endian would have been
a better choice, but at the time IP was designed, no one knew it would come to
dominate computing.
32 Bits
Version IHL Differentiated services Total length
D M
Identification Fragment offset
F F
Time to live Protocol Header checksum
Source address
Destination address
Options (0 or more words)
Figure 5-46. The IPv4 (Internet Protocol) header.
The Version field keeps track of which version of the protocol the datagram
belongs to. Version 4 dominates the Internet today, and that is where we have
started our discussion. By including the version at the start of each datagram, it
becomes possible to have a transition between versions over a long period of time.
In fact, IPv6, the next version of IP, was defined more than a decade ago, yet is
only just beginning to be deployed. We will describe it later in this section. Its
use will eventually be forced when each of China's almost 231 people has a desk-
top PC, a laptop, and an IP phone. As an aside on numbering, IPv5 was an exper-
imental real-time stream protocol that was never widely used.


---

<a id="page-452"></a>

<!-- Page 452 of 888 -->

440 THE NETWORK LAYER CHAP. 5
Since the header length is not constant, a field in the header, IHL, is provided
to tell how long the header is, in 32-bit words. The minimum value is 5, which
applies when no options are present. The maximum value of this 4-bit field is 15,
which limits the header to 60 bytes, and thus the Options field to 40 bytes. For
some options, such as one that records the route a packet has taken, 40 bytes is far
too small, making those options useless.
The Differentiated services field is one of the few fields that has changed its
meaning (slightly) over the years. Originally, it was called the Type of service
field. It was and still is intended to distinguish between different classes of ser-
vice. Various combinations of reliability and speed are possible. For digitized
voice, fast delivery beats accurate delivery. For file transfer, error-free transmis-
sion is more important than fast transmission. The Type of service field provided
3 bits to signal priority and 3 bits to signal whether a host cared more about delay,
throughput, or reliability. However, no one really knew what to do with these bits
at routers, so they were left unused for many years. When differentiated services
were designed, IETF threw in the towel and reused this field. Now, the top 6 bits
are used to mark the packet with its service class; we described the expedited and
assured services earlier in this chapter. The bottom 2 bits are used to carry expli-
cit congestion notification information, such as whether the packet has experi-
enced congestion; we described explicit congestion notification as part of conges-
tion control earlier in this chapter.
The Total length includes everything in the datagram-both header and data.
The maximum length is 65,535 bytes. At present, this upper limit is tolerable, but
with future networks, larger datagrams may be needed.
The Identification field is needed to allow the destination host to determine
which packet a newly arrived fragment belongs to. All the fragments of a packet
contain the same Identification value.
Next comes an unused bit, which is surprising, as available real estate in the
IP header is extremely scarce. As an April Fool's joke, Bellovin (2003) proposed
using this bit to detect malicious traffic. This would greatly simplify security, as
packets with the ''evil'' bit set would be known to have been sent by attackers and
could just be discarded. Unfortunately, network security is not this simple.
Then come two 1-bit fields related to fragmentation. DF stands for Don't
Fragment. It is an order to the routers not to fragment the packet. Originally, it
was intended to support hosts incapable of putting the pieces back together again.
Now it is used as part of the process to discover the path MTU, which is the larg-
est packet that can travel along a path without being fragmented. By marking the
datagram with the DF bit, the sender knows it will either arrive in one piece, or an
error message will be returned to the sender.
MF stands for More Fragments. All fragments except the last one have this
bit set. It is needed to know when all fragments of a datagram have arrived.
The Fragment offset tells where in the current packet this fragment belongs.
All fragments except the last one in a datagram must be a multiple of 8 bytes, the


---

<a id="page-453"></a>

<!-- Page 453 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 441
elementary fragment unit. Since 13 bits are provided, there is a maximum of 8192
fragments per datagram, supporting a maximum packet length up to the limit of
the Total length field. Working together, the Identification, MF, and Fragment
offset fields are used to implement fragmentation as described in Sec. 5.5.5.
The TtL (Time to live) field is a counter used to limit packet lifetimes. It was
originally supposed to count time in seconds, allowing a maximum lifetime of 255
sec. It must be decremented on each hop and is supposed to be decremented mul-
tiple times when a packet is queued for a long time in a router. In practice, it just
counts hops. When it hits zero, the packet is discarded and a warning packet is
sent back to the source host. This feature prevents packets from wandering
around forever, something that otherwise might happen if the routing tables ever
become corrupted.
When the network layer has assembled a complete packet, it needs to know
what to do with it. The Protocol field tells it which transport process to give the
packet to. TCP is one possibility, but so are UDP and some others. The num-
bering of protocols is global across the entire Internet. Protocols and other assign-
ed numbers were formerly listed in RFC 1700, but nowadays they are contained in
an online database located at www.iana.org.
Since the header carries vital information such as addresses, it rates its own
checksum for protection, the Header checksum. The algorithm is to add up all the
16-bit halfwords of the header as they arrive, using one's complement arithmetic,
and then take the one's complement of the result. For purposes of this algorithm,
the Header checksum is assumed to be zero upon arrival. Such a checksum is
useful for detecting errors while the packet travels through the network. Note that
it must be recomputed at each hop because at least one field always changes (the
Time to live field), but tricks can be used to speed up the computation.
The Source address and Destination address indicate the IP address of the
source and destination network interfaces. We will discuss Internet addresses in
the next section.
The Options field was designed to provide an escape to allow subsequent ver-
sions of the protocol to include information not present in the original design, to
permit experimenters to try out new ideas, and to avoid allocating header bits to
information that is rarely needed. The options are of variable length. Each begins
with a 1-byte code identifying the option. Some options are followed by a 1-byte
option length field, and then one or more data bytes. The Options field is padded
out to a multiple of 4 bytes. Originally, the five options listed in Fig. 5-47 were
defined.
The Security option tells how secret the information is. In theory, a military
router might use this field to specify not to route packets through certain countries
the military considers to be ''bad guys.'' In practice, all routers ignore it, so its
only practical function is to help spies find the good stuff more easily.
The Strict source routing option gives the complete path from source to desti-
nation as a sequence of IP addresses. The datagram is required to follow that


---

<a id="page-454"></a>

<!-- Page 454 of 888 -->

442 THE NETWORK LAYER CHAP. 5
Option Description
Security Specifies how secret the datagram is
Strict source routing Gives the complete path to be followed
Loose source routing Gives a list of routers not to be missed
Record route Makes each router append its IP address
Timestamp Makes each router append its address and timestamp
Figure 5-47. Some of the IP options.
exact route. It is most useful for system managers who need to send emergency
packets when the routing tables have been corrupted, or for making timing meas-
urements.
The Loose source routing option requires the packet to traverse the list of
routers specified, in the order specified, but it is allowed to pass through other
routers on the way. Normally, this option will provide only a few routers, to force
a particular path. For example, to force a packet from London to Sydney to go
west instead of east, this option might specify routers in New York, Los Angeles,
and Honolulu. This option is most useful when political or economic consid-
erations dictate passing through or avoiding certain countries.
The Record route option tells each router along the path to append its IP ad-
dress to the Options field. This allows system managers to track down bugs in the
routing algorithms (''Why are packets from Houston to Dallas visiting Tokyo
first?''). When the ARPANET was first set up, no packet ever passed through
more than nine routers, so 40 bytes of options was plenty. As mentioned above,
now it is too small.
Finally, the Timestamp option is like the Record route option, except that in
addition to recording its 32-bit IP address, each router also records a 32-bit time-
stamp. This option, too, is mostly useful for network measurement.
Today, IP options have fallen out of favor. Many routers ignore them or do
not process them efficiently, shunting them to the side as an uncommon case. That
is, they are only partly supported and they are rarely used.
#### 5.6.2 IP Addresses
A defining feature of IPv4 is its 32-bit addresses. Every host and router on
the Internet has an IP address that can be used in the Source address and Destina-
tion address fields of IP packets. It is important to note that an IP address does
not actually refer to a host. It really refers to a network interface, so if a host is on
two networks, it must have two IP addresses. However, in practice, most hosts
are on one network and thus have one IP address. In contrast, routers have multi-
ple interfaces and thus multiple IP addresses.


---

<a id="page-455"></a>

<!-- Page 455 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 443
Prefixes
IP addresses are hierarchical, unlike Ethernet addresses. Each 32-bit address
is comprised of a variable-length network portion in the top bits and a host portion
in the bottom bits. The network portion has the same value for all hosts on a sin-
gle network, such as an Ethernet LAN. This means that a network corresponds to
a contiguous block of IP address space. This block is called a prefix.
IP addresses are written in dotted decimal notation. In this format, each of
the 4 bytes is written in decimal, from 0 to 255. For example, the 32-bit hexade-
cimal address 80D00297 is written as 128.208.2.151. Prefixes are written by giv-
ing the lowest IP address in the block and the size of the block. The size is deter-
mined by the number of bits in the network portion; the remaining bits in the host
portion can vary. This means that the size must be a power of two. By conven-
tion, it is written after the prefix IP address as a slash followed by the length in
bits of the network portion. In our example, if the prefix contains 28 addresses
and so leaves 24 bits for the network portion, it is written as 128.208.0.0/24.
Since the prefix length cannot be inferred from the IP address alone, routing
protocols must carry the prefixes to routers. Sometimes prefixes are simply de-
scribed by their length, as in a ''/16'' which is pronounced ''slash 16.'' The length
of the prefix corresponds to a binary mask of 1s in the network portion. When
written out this way, it is called a subnet mask. It can be ANDed with the IP ad-
dress to extract only the network portion. For our example, the subnet mask is
255.255.255.0. Fig. 5-48 shows a prefix and a subnet mask.
32 bits
Prefix length = L bits 32 - L bits
Network Host
Subnet
mask 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0
Figure 5-48. An IP prefix and a subnet mask.
Hierarchical addresses have significant advantages and disadvantages. The
key advantage of prefixes is that routers can forward packets based on only the
network portion of the address, as long as each of the networks has a unique ad-
dress block. The host portion does not matter to the routers because all hosts on
the same network will be sent in the same direction. It is only when the packets
reach the network for which they are destined that they are forwarded to the cor-
rect host. This makes the routing tables much smaller than they would otherwise
be. Consider that the number of hosts on the Internet is approaching one billion.
That would be a very large table for every router to keep. However, by using a
hierarchy, routers need to keep routes for only around 300,000 prefixes.


---

<a id="page-456"></a>

<!-- Page 456 of 888 -->

444 THE NETWORK LAYER CHAP. 5
While using a hierarchy lets Internet routing scale, it has two disadvantages.
First, the IP address of a host depends on where it is located in the network. An
Ethernet address can be used anywhere in the world, but every IP address belongs
to a specific network, and routers will only be able to deliver packets destined to
that address to the network. Designs such as mobile IP are needed to support hosts
that move between networks but want to keep the same IP addresses.
The second disadvantage is that the hierarchy is wasteful of addresses unless
it is carefully managed. If addresses are assigned to networks in (too) large
blocks, there will be (many) addresses that are allocated but not in use. This al-
location would not matter much if there were plenty of addresses to go around.
However, it was realized more than two decades ago that the tremendous growth
of the Internet was rapidly depleting the free address space. IPv6 is the solution to
this shortage, but until it is widely deployed there will be great pressure to allocate
IP addresses so that they are used very efficiently.
Subnets
Network numbers are managed by a nonprofit corporation called ICANN
(Internet Corporation for Assigned Names and Numbers), to avoid conflicts.
In turn, ICANN has delegated parts of the address space to various regional
authorities, which dole out IP addresses to ISPs and other companies. This is the
process by which a company is allocated a block of IP addresses.
However, this process is only the start of the story, as IP address assignment
is ongoing as companies grow. We have said that routing by prefix requires all the
hosts in a network to have the same network number. This property can cause
problems as networks grow. For example, consider a university that started out
with our example /16 prefix for use by the Computer Science Dept. for the com-
puters on its Ethernet. A year later, the Electrical Engineering Dept. wants to get
on the Internet. The Art Dept. soon follows suit. What IP addresses should these
departments use? Getting further blocks requires going outside the university and
may be expensive or inconvenient. Moreover, the /16 already allocated has
enough addresses for over 60,000 hosts. It might be intended to allow for signifi-
cant growth, but until that happens, it is wasteful to allocate further blocks of IP
addresses to the same university. A different organization is required.
The solution is to allow the block of addresses to be split into several parts for
internal use as multiple networks, while still acting like a single network to the
outside world. This is called subnetting and the networks (such as Ethernet
LANs) that result from dividing up a larger network are called subnets. As we
mentioned in Chap. 1, you should be aware that this new usage of the term con-
flicts with older usage of ''subnet'' to mean the set of all routers and communica-
tion lines in a network.
Fig. 5-49 shows how subnets can help with our example. The single /16 has
been split into pieces. This split does not need to be even, but each piece must be


---

<a id="page-457"></a>

<!-- Page 457 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 445
aligned so that any bits can be used in the lower host portion. In this case, half of
the block (a /17) is allocated to the Computer Science Dept, a quarter is allocated
to the Electrical Engineering Dept. (a /18), and one eighth (a /19) to the Art Dept.
The remaining eighth is unallocated. A different way to see how the block was di-
vided is to look at the resulting prefixes when written in binary notation:
Computer Science: 10000000 11010000 1|xxxxxxx xxxxxxxx
Electrical Eng.: 10000000 11010000 00|xxxxxx xxxxxxxx
Art: 10000000 11010000 011|xxxxx xxxxxxxx
Here, the vertical bar (|) shows the boundary between the subnet number and the
host portion.
EE
128.208.0.0/18
CS
128.208.0.0/16
128.208.128.0/17
(to Internet)
Art
128.208.96.0/19
Figure 5-49. Splitting an IP prefix into separate networks with subnetting.
When a packet comes into the main router, how does the router know which
subnet to give it to? This is where the details of our prefixes come in. One way
would be for each router to have a table with 65,536 entries telling it which out-
going line to use for each host on campus. But this would undermine the main
scaling benefit we get from using a hierarchy. Instead, the routers simply need to
know the subnet masks for the networks on campus.
When a packet arrives, the router looks at the destination address of the pack-
et and checks which subnet it belongs to. The router can do this by ANDing the
destination address with the mask for each subnet and checking to see if the result
is the corresponding prefix. For example, consider a packet destined for IP ad-
dress 128.208.2.151. To see if it is for the Computer Science Dept., we AND
with 255.255.128.0 to take the first 17 bits (which is 128.208.0.0) and see if they
match the prefix address (which is 128.208.128.0). They do not match. Checking
the first 18 bits for the Electrical Engineering Dept., we get 128.208.0.0 when
ANDing with the subnet mask. This does match the prefix address, so the packet
is forwarded onto the interface which leads to the Electrical Engineering network.


---

<a id="page-458"></a>

<!-- Page 458 of 888 -->

446 THE NETWORK LAYER CHAP. 5
The subnet divisions can be changed later if necessary, by updating all subnet
masks at routers inside the university. Outside the network, the subnetting is not
visible, so allocating a new subnet does not require contacting ICANN or chang-
ing any external databases.
CIDR-Classless InterDomain Routing
Even if blocks of IP addresses are allocated so that the addresses are used ef-
ficiently, there is still a problem that remains: routing table explosion.
Routers in organizations at the edge of a network, such as a university, need
to have an entry for each of their subnets, telling the router which line to use to
get to that network. For routes to destinations outside of the organization, they
can use the simple default rule of sending the packets on the line toward the ISP
that connects the organization to the rest of the Internet. The other destination ad-
dresses must all be out there somewhere.
Routers in ISPs and backbones in the middle of the Internet have no such lux-
ury. They must know which way to go to get to every network and no simple de-
fault will work. These core routers are said to be in the default-free zone of the
Internet. No one really knows how many networks are connected to the Internet
any more, but it is a large number, probably at least a million. This can make for
a very large table. It may not sound large by computer standards, but realize that
routers must perform a lookup in this table to forward every packet, and routers at
large ISPs may forward up to millions of packets per second. Specialized hard-
ware and fast memory are needed to process packets at these rates, not a general-
purpose computer.
In addition, routing algorithms require each router to exchange information
about the addresses it can reach with other routers. The larger the tables, the more
information needs to be communicated and processed. The processing grows at
least linearly with the table size. Greater communication increases the likelihood
that some parts will get lost, at least temporarily, possibly leading to routing insta-
bilities.
The routing table problem could have been solved by going to a deeper hier-
archy, like the telephone network. For example, having each IP address contain a
country, state/province, city, network, and host field might work. Then, each
router would only need to know how to get to each country, the states or pro-
vinces in its own country, the cities in its state or province, and the networks in its
city. Unfortunately, this solution would require considerably more than 32 bits
for IP addresses and would use addresses inefficiently (and Liechtenstein would
have as many bits in its addresses as the United States).
Fortunately, there is something we can do to reduce routing table sizes. We
can apply the same insight as subnetting: routers at different locations can know
about a given IP address as belonging to prefixes of different sizes. However, in-
stead of splitting an address block into subnets, here we combine multiple small


---

<a id="page-459"></a>

<!-- Page 459 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 447
prefixes into a single larger prefix. This process is called route aggregation. The
resulting larger prefix is sometimes called a supernet, to contrast with subnets as
the division of blocks of addresses.
With aggregation, IP addresses are contained in prefixes of varying sizes. The
same IP address that one router treats as part of a /22 (a block containing 210 ad-
dresses) may be treated by another router as part of a larger /20 (which contains
212 addresses). It is up to each router to have the corresponding prefix infor-
mation. This design works with subnetting and is called CIDR (Classless Inter-
Domain Routing), which is pronounced ''cider,'' as in the drink. The most recent
version of it is specified in RFC 4632 (Fuller and Li, 2006). The name highlights
the contrast with addresses that encode hierarchy with classes, which we will de-
scribe shortly.
To make CIDR easier to understand, let us consider an example in which a
block of 8192 IP addresses is available starting at 194.24.0.0. Suppose that Cam-
bridge University needs 2048 addresses and is assigned the addresses 194.24.0.0
through 194.24.7.255, along with mask 255.255.248.0. This is a /21 prefix. Next,
Oxford University asks for 4096 addresses. Since a block of 4096 addresses must
lie on a 4096-byte boundary, Oxford cannot be given addresses starting at
194.24.8.0. Instead, it gets 194.24.16.0 through 194.24.31.255, along with subnet
mask 255.255.240.0. Finally, the University of Edinburgh asks for 1024 ad-
dresses and is assigned addresses 194.24.8.0 through 194.24.11.255 and mask
255.255.252.0. These assignments are summarized in Fig. 5-50.
University First address Last address How many Prefix
Cambridge 194.24.0.0 194.24.7.255 2048 194.24.0.0/21
Edinburgh 194.24.8.0 194.24.11.255 1024 194.24.8.0/22
(Available) 194.24.12.0 194.24.15.255 1024 194.24.12.0/22
Oxford 194.24.16.0 194.24.31.255 4096 194.24.16.0/20
Figure 5-50. A set of IP address assignments.
All of the routers in the default-free zone are now told about the IP addresses
in the three networks. Routers close to the universities may need to send on a dif-
ferent outgoing line for each of the prefixes, so they need an entry for each of the
prefixes in their routing tables. An example is the router in London in Fig. 5-51.
Now let us look at these three universities from the point of view of a distant
router in New York. All of the IP addresses in the three prefixes should be sent
from New York (or the U.S. in general) to London. The routing process in London
notices this and combines the three prefixes into a single aggregate entry for the
prefix 194.24.0.0/19 that it passes to the New York router. This prefix contains 8K
addresses and covers the three universities and the otherwise unallocated 1024 ad-
dresses. By using aggregation, three prefixes have been reduced to one, reducing


---

<a id="page-460"></a>

<!-- Page 460 of 888 -->

448 THE NETWORK LAYER CHAP. 5
192.24.0.0/21
Cambridge
New York London
192.24.0.0/19 192.24.16.0/20
(1 aggregate prefix) (3 prefixes)
Oxford
192.24.8.0/22
Edinburgh
Figure 5-51. Aggregation of IP prefixes.
the prefixes that the New York router must be told about and the routing table en-
tries in the New York router.
When aggregation is turned on, it is an automatic process. It depends on
which prefixes are located where in the Internet not on the actions of an adminis-
trator assigning addresses to networks. Aggregation is heavily used throughout
the Internet and can reduce the size of router tables to around 200,000 prefixes.
As a further twist, prefixes are allowed to overlap. The rule is that packets are
sent in the direction of the most specific route, or the longest matching prefix
that has the fewest IP addresses. Longest matching prefix routing provides a use-
ful degree of flexibility, as seen in the behavior of the router at New York in
Fig. 5-52. This router still uses a single aggregate prefix to send traffic for the
three universities to London. However, the previously available block of ad-
dresses within this prefix has now been allocated to a network in San Francisco.
One possibility is for the New York router to keep four prefixes, sending packets
for three of them to London and packets for the fourth to San Francisco. Instead,
longest matching prefix routing can handle this forwarding with the two prefixes
that are shown. One overall prefix is used to direct traffic for the entire block to
London. One more specific prefix is also used to direct a portion of the larger
prefix to San Francisco. With the longest matching prefix rule, IP addresses with-
in the San Francisco network will be sent on the outgoing line to San Francisco,
and all other IP addresses in the larger prefix will be sent to London.
Conceptually, CIDR works as follows. When a packet comes in, the routing
table is scanned to determine if the destination lies within the prefix. It is possible
that multiple entries with different prefix lengths will match, in which case the
entry with the longest prefix is used. Thus, if there is a match for a /20 mask and
a /24 mask, the /24 entry is used to look up the outgoing line for the packet. How-
ever, this process would be tedious if the table were really scanned entry by entry.


---

<a id="page-461"></a>

<!-- Page 461 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 449
192.24.0.0/21
San Francisco New York London
192.24.16.0/20
192.24.12.0/22 192.24.0.0/19
192.24.12.0/22 192.24.8.0/22
Figure 5-52. Longest matching prefix routing at the New York router.
Instead, complex algorithms have been devised to speed up the address matching
process (Ruiz-Sanchez et al., 2001). Commercial routers use custom VLSI chips
with these algorithms embedded in hardware.
Classful and Special Addressing
To help you better appreciate why CIDR is so useful, we will briefly relate
the design that predated it. Before 1993, IP addresses were divided into the five
categories listed in Fig. 5-53. This allocation has come to be called classful
addressing.
32 Bits
Range of host
Class addresses
##### 1.0.0.0 to
A 0 Network Host 127.255.255.255
##### 128.0.0.0 to
B 10 Network Host
191.255.255.255
##### 192.0.0.0 to
C 110 Network Host
223.255.255.255
##### 224.0.0.0 to
D 1110 Multicast address 239.255.255.255
##### 240.0.0.0 to
E 1111 Reserved for future use
255.255.255.255
Figure 5-53. IP address formats.
The class A, B, and C formats allow for up to 128 networks with 16 million
hosts each, 16,384 networks with up to 65,536 hosts each, and 2 million networks
(e.g., LANs) with up to 256 hosts each (although a few of these are special). Also
supported is multicast (the class D format), in which a datagram is directed to
multiple hosts. Addresses beginning with 1111 are reserved for use in the future.
They would be valuable to use now given the depletion of the IPv4 address space.


---

<a id="page-462"></a>

<!-- Page 462 of 888 -->

450 THE NETWORK LAYER CHAP. 5
Unfortunately, many hosts will not accept these addresses as valid because they
have been off-limits for so long and it is hard to teach old hosts new tricks.
This is a hierarchical design, but unlike CIDR the sizes of the address blocks
are fixed. Over 2 billion addresses exist, but organizing the address space by
classes wastes millions of them. In particular, the real villain is the class B net-
work. For most organizations, a class A network, with 16 million addresses, is
too big, and a class C network, with 256 addresses is too small. A class B net-
work, with 65,536, is just right. In Internet folklore, this situation is known as the
three bears problem [as in Goldilocks and the Three Bears (Southey, 1848)].
In reality, though, a class B address is far too large for most organizations.
Studies have shown that more than half of all class B networks have fewer than 50
hosts. A class C network would have done the job, but no doubt every organiza-
tion that asked for a class B address thought that one day it would outgrow the 8-
bit host field. In retrospect, it might have been better to have had class C net-
works use 10 bits instead of 8 for the host number, allowing 1022 hosts per net-
work. Had this been the case, most organizations would probably have settled for
a class C network, and there would have been half a million of them (versus only
16,384 class B networks).
It is hard to fault the Internet's designers for not having provided more (and
smaller) class B addresses. At the time the decision was made to create the three
classes, the Internet was a research network connecting the major research univer-
sities in the U.S. (plus a very small number of companies and military sites doing
networking research). No one then perceived the Internet becoming a mass-
market communication system rivaling the telephone network. At the time, some-
one no doubt said: ''The U.S. has about 2000 colleges and universities. Even if
all of them connect to the Internet and many universities in other countries join,
too, we are never going to hit 16,000, since there are not that many universities in
the whole world. Furthermore, having the host number be an integral number of
bytes speeds up packet processing'' (which was then done entirely in software).
Perhaps some day people will look back and fault the folks who designed the tele-
phone number scheme and say: ''What idiots. Why didn't they include the planet
number in the phone number?'' But at the time, it did not seem necessary.
To handle these problems, subnets were introduced to flexibly assign blocks
of addresses within an organization. Later, CIDR was added to reduce the size of
the global routing table. Today, the bits that indicate whether an IP address be-
longs to class A, B, or C network are no longer used, though references to these
classes in the literature are still common.
To see how dropping the classes made forwarding more complicated, consider
how simple it was in the old classful system. When a packet arrived at a router, a
copy of the IP address was shifted right 28 bits to yield a 4-bit class number. A
16-way branch then sorted packets into A, B, C (and D and E) classes, with eight
of the cases for class A, four of the cases for class B, and two of the cases for
class C. The code for each class then masked off the 8-, 16-, or 24-bit network


---

<a id="page-463"></a>

<!-- Page 463 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 451
number and right aligned it in a 32-bit word. The network number was then
looked up in the A, B, or C table, usually by indexing for A and B networks and
hashing for C networks. Once the entry was found, the outgoing line could be
looked up and the packet forwarded. This is much simpler than the longest
matching prefix operation, which can no longer use a simple table lookup because
an IP address may have any length prefix.
Class D addresses continue to be used in the Internet for multicast. Actually,
it might be more accurate to say that they are starting to be used for multicast,
since Internet multicast has not been widely deployed in the past.
There are also several other addresses that have special meanings, as shown in
Fig. 5-54. The IP address 0.0.0.0, the lowest address, is used by hosts when they
are being booted. It means ''this network'' or ''this host.'' IP addresses with 0 as
the network number refer to the current network. These addresses allow machines
to refer to their own network without knowing its number (but they have to know
the network mask to know how many 0s to include). The address consisting of all
1s, or 255.255.255.255-the highest address-is used to mean all hosts on the in-
dicated network. It allows broadcasting on the local network, typically a LAN.
The addresses with a proper network number and all 1s in the host field allow ma-
chines to send broadcast packets to distant LANs anywhere in the Internet. How-
ever, many network administrators disable this feature as it is mostly a security
hazard. Finally, all addresses of the form 127.xx.yy.zz are reserved for loopback
testing. Packets sent to that address are not put out onto the wire; they are proc-
essed locally and treated as incoming packets. This allows packets to be sent to
the host without the sender knowing its number, which is useful for testing.
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 This host
0 0 . . . 0 0 Host A host on this network
Broadcast on the
1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
local network
Broadcast on a
Network 1 1 1 1 . . . 1 1 1 1
distant network
127 (Anything) Loopback
Figure 5-54. Special IP addresses.
NAT-Network Address Translation
IP addresses are scarce. An ISP might have a /16 address, giving it 65,534
usable host numbers. If it has more customers than that, it has a problem.


---

<a id="page-464"></a>

<!-- Page 464 of 888 -->

452 THE NETWORK LAYER CHAP. 5
This scarcity has led to techniques to use IP addresses sparingly. One ap-
proach is to dynamically assign an IP address to a computer when it is on and
using the network, and to take the IP address back when the host becomes inac-
tive. The IP address can then be assigned to another computer that becomes ac-
tive. In this way, a single /16 address can handle up to 65,534 active users.
This strategy works well in some cases, for example, for dialup networking
and mobile and other computers that may be temporarily absent or powered off.
However, it does not work very well for business customers. Many PCs in busi-
nesses are expected to be on continuously. Some are employee machines, backed
up at night, and some are servers that may have to serve a remote request at a
moment's notice. These businesses have an access line that always provides con-
nectivity to the rest of the Internet.
Increasingly, this situation also applies to home users subscribing to ADSL or
Internet over cable, since there is no connection charge (just a monthly flat rate
charge). Many of these users have two or more computers at home, often one for
each family member, and they all want to be online all the time. The solution is
to connect all the computers into a home network via a LAN and put a (wireless)
router on it. The router then connects to the ISP. From the ISP's point of view, the
family is now the same as a small business with a handful of computers. Wel-
come to Jones, Inc. With the techniques we have seen so far, each computer must
have its own IP address all day long. For an ISP with many thousands of custom-
ers, particularly business customers and families that are just like small busi-
nesses, the demand for IP addresses can quickly exceed the block that is available.
The problem of running out of IP addresses is not a theoretical one that might
occur at some point in the distant future. It is happening right here and right now.
The long-term solution is for the whole Internet to migrate to IPv6, which has
128-bit addresses. This transition is slowly occurring, but it will be years before
the process is complete. To get by in the meantime, a quick fix was needed. The
quick fix that is widely used today came in the form of NAT (Network Address
Translation), which is described in RFC 3022 and which we will summarize
below. For additional information, see Dutcher (2001).
The basic idea behind NAT is for the ISP to assign each home or business a
single IP address (or at most, a small number of them) for Internet traffic. Within
the customer network, every computer gets a unique IP address, which is used for
routing intramural traffic. However, just before a packet exits the customer net-
work and goes to the ISP, an address translation from the unique internal IP ad-
dress to the shared public IP address takes place. This translation makes use of
three ranges of IP addresses that have been declared as private. Networks may
use them internally as they wish. The only rule is that no packets containing these
addresses may appear on the Internet itself. The three reserved ranges are:
##### 10.0.0.0 - 10.255.255.255/8 (16,777,216 hosts)
##### 172.16.0.0 - 172.31.255.255/12 (1,048,576 hosts)
##### 192.168.0.0 - 192.168.255.255/16 (65,536 hosts)


---

<a id="page-465"></a>

<!-- Page 465 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 453
The first range provides for 16,777,216 addresses (except for all 0s and all 1s, as
usual) and is the usual choice, even if the network is not large.
The operation of NAT is shown in Fig. 5-55. Within the customer premises,
every machine has a unique address of the form 10.x.y.z. However, before a pack-
et leaves the customer premises, it passes through a NAT box that converts the in-
ternal IP source address, 10.0.0.1 in the figure, to the customer's true IP address,
##### 198.60.42.12 in this example. The NAT box is often combined in a single device
with a firewall, which provides security by carefully controlling what goes into
the customer network and what comes out of it. We will study firewalls in Chap.
8. It is also possible to integrate the NAT box into a router or ADSL modem.
Packet before Packet after
translation translation
IP = 10.0.0.1 IP = 198.60.42.12
port = 5544 port = 3344 (to Internet)
ISP
Customer router
NAT box/firewall
router
and LAN
Boundary of customer premises
Figure 5-55. Placement and operation of a NAT box.
So far, we have glossed over one tiny but crucial detail: when the reply comes
back (e.g., from a Web server), it is naturally addressed to 198.60.42.12, so how
does the NAT box know which internal address to replace it with? Herein lies the
problem with NAT. If there were a spare field in the IP header, that field could be
used to keep track of who the real sender was, but only 1 bit is still unused. In
principle, a new option could be created to hold the true source address, but doing
so would require changing the IP code on all the machines on the entire Internet to
handle the new option. This is not a promising alternative for a quick fix.
What actually happens is as follows. The NAT designers observed that most
IP packets carry either TCP or UDP payloads. When we study TCP and UDP in
Chap. 6, we will see that both of these have headers containing a source port and a
destination port. Below we will just discuss TCP ports, but exactly the same story
holds for UDP ports. The ports are 16-bit integers that indicate where the TCP
connection begins and ends. These ports provide the field needed to make NAT
work.
When a process wants to establish a TCP connection with a remote process, it
attaches itself to an unused TCP port on its own machine. This is called the
source port and tells the TCP code where to send incoming packets belonging to
this connection. The process also supplies a destination port to tell who to give


---

<a id="page-466"></a>

<!-- Page 466 of 888 -->

454 THE NETWORK LAYER CHAP. 5
the packets to on the remote side. Ports 0-1023 are reserved for well-known ser-
vices. For example, port 80 is the port used by Web servers, so remote clients can
locate them. Each outgoing TCP message contains both a source port and a desti-
nation port. Together, these ports serve to identify the processes using the con-
nection on both ends.
An analogy may make the use of ports clearer. Imagine a company with a
single main telephone number. When people call the main number, they reach an
operator who asks which extension they want and then puts them through to that
extension. The main number is analogous to the customer's IP address and the
extensions on both ends are analogous to the ports. Ports are effectively an extra
16 bits of addressing that identify which process gets which incoming packet.
Using the Source port field, we can solve our mapping problem. Whenever
an outgoing packet enters the NAT box, the 10.x.y.z source address is replaced by
the customer's true IP address. In addition, the TCP Source port field is replaced
by an index into the NAT box's 65,536-entry translation table. This table entry
contains the original IP address and the original source port. Finally, both the IP
and TCP header checksums are recomputed and inserted into the packet. It is
necessary to replace the Source port because connections from machines 10.0.0.1
and 10.0.0.2 may both happen to use port 5000, for example, so the Source port
alone is not enough to identify the sending process.
When a packet arrives at the NAT box from the ISP, the Source port in the
TCP header is extracted and used as an index into the NAT box's mapping table.
From the entry located, the internal IP address and original TCP Source port are
extracted and inserted into the packet. Then, both the IP and TCP checksums are
recomputed and inserted into the packet. The packet is then passed to the custo-
mer router for normal delivery using the 10.x.y.z address.
Although this scheme sort of solves the problem, networking purists in the IP
community have a tendency to regard it as an abomination-on-the-face-of-the-
earth. Briefly summarized, here are some of the objections. First, NAT violates
the architectural model of IP, which states that every IP address uniquely identi-
fies a single machine worldwide. The whole software structure of the Internet is
built on this fact. With NAT, thousands of machines may (and do) use address
10.0.0.1.
Second, NAT breaks the end-to-end connectivity model of the Internet, which
says that any host can send a packet to any other host at any time. Since the map-
ping in the NAT box is set up by outgoing packets, incoming packets cannot be
accepted until after outgoing ones. In practice, this means that a home user with
NAT can make TCP/IP connections to a remote Web server, but a remote user
cannot make connections to a game server on the home network. Special configu-
ration or NAT traversal techniques are needed to support this kind of situation.
Third, NAT changes the Internet from a connectionless network to a peculiar
kind of connection-oriented network. The problem is that the NAT box must
maintain information (i.e., the mapping) for each connection passing through it.


---

<a id="page-467"></a>

<!-- Page 467 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 455
Having the network maintain connection state is a property of connection-oriented
networks, not connectionless ones. If the NAT box crashes and its mapping table
is lost, all its TCP connections are destroyed. In the absence of NAT, a router can
crash and restart with no long-term effect on TCP connections. The sending proc-
ess just times out within a few seconds and retransmits all unacknowledged pack-
ets. With NAT, the Internet becomes as vulnerable as a circuit-switched network.
Fourth, NAT violates the most fundamental rule of protocol layering: layer k
may not make any assumptions about what layer k + 1 has put into the payload
field. This basic principle is there to keep the layers independent. If TCP is later
upgraded to TCP-2, with a different header layout (e.g., 32-bit ports), NAT will
fail. The whole idea of layered protocols is to ensure that changes in one layer do
not require changes in other layers. NAT destroys this independence.
Fifth, processes on the Internet are not required to use TCP or UDP. If a user
on machine A decides to use some new transport protocol to talk to a user on ma-
chine B (for example, for a multimedia application), introduction of a NAT box
will cause the application to fail because the NAT box will not be able to locate
the TCP Source port correctly.
A sixth and related problem is that some applications use multiple TCP/IP
connections or UDP ports in prescribed ways. For example, FTP, the standard
File Transfer Protocol, inserts IP addresses in the body of packet for the receiver
to extract and use. Since NAT knows nothing about these arrangements, it cannot
rewrite the IP addresses or otherwise account for them. This lack of under-
standing means that FTP and other applications such as the H.323 Internet tele-
phony protocol (which we will study in Chap. 7) will fail in the presence of NAT
unless special precautions are taken. It is often possible to patch NAT for these
cases, but having to patch the code in the NAT box every time a new application
comes along is not a good idea.
Finally, since the TCP Source port field is 16 bits, at most 65,536 machines
can be mapped onto an IP address. Actually, the number is slightly less because
the first 4096 ports are reserved for special uses. However, if multiple IP ad-
dresses are available, each one can handle up to 61,440 machines.
A view of these and other problems with NAT is given in RFC 2993. Despite
the issues, NAT is widely used in practice, especially for home and small business
networks, as the only expedient technique to deal with the IP address shortage. It
has become wrapped up with firewalls and privacy because it blocks unsolicited
incoming packets by default. For this reason, it is unlikely to go away even when
IPv6 is widely deployed.
#### 5.6.3 IP Version 6
IP has been in heavy use for decades. It has worked extremely well, as
demonstrated by the exponential growth of the Internet. Unfortunately, IP has be-
come a victim of its own popularity: it is close to running out of addresses. Even


---

<a id="page-468"></a>

<!-- Page 468 of 888 -->

456 THE NETWORK LAYER CHAP. 5
with CIDR and NAT using addresses more sparingly, the last IPv4 addresses are
expected to be assigned by ICANN before the end of 2012. This looming disaster
was recognized almost two decades ago, and it sparked a great deal of discussion
and controversy within the Internet community about what to do about it.
In this section, we will describe both the problem and several proposed solu-
tions. The only long-term solution is to move to larger addresses. IPv6 (IP ver-
sion 6) is a replacement design that does just that. It uses 128-bit addresses; a
shortage of these addresses is not likely any time in the foreseeable future. How-
ever, IPv6 has proved very difficult to deploy. It is a different network layer pro-
tocol that does not really interwork with IPv4, despite many similarities. Also,
companies and users are not really sure why they should want IPv6 in any case.
The result is that IPv6 is deployed and used on only a tiny fraction of the Internet
(estimates are 1%) despite having been an Internet Standard since 1998. The next
several years will be an interesting time, as the few remaining IPv4 addresses are
allocated. Will people start to auction off their IPv4 addresses on eBay? Will a
black market in them spring up? Who knows.
In addition to the address problems, other issues loom in the background. In
its early years, the Internet was largely used by universities, high-tech industries,
and the U.S. Government (especially the Dept. of Defense). With the explosion
of interest in the Internet starting in the mid-1990s, it began to be used by a dif-
ferent group of people, often with different requirements. For one thing, numer-
ous people with smart phones use it to keep in contact with their home bases. For
another, with the impending convergence of the computer, communication, and
entertainment industries, it may not be that long before every telephone and tele-
vision set in the world is an Internet node, resulting in a billion machines being
used for audio and video on demand. Under these circumstances, it became
apparent that IP had to evolve and become more flexible.
Seeing these problems on the horizon, in 1990 IETF started work on a new
version of IP, one that would never run out of addresses, would solve a variety of
other problems, and be more flexible and efficient as well. Its major goals were:
1. Support billions of hosts, even with inefficient address allocation.
2. Reduce the size of the routing tables.
3. Simplify the protocol, to allow routers to process packets faster.
4. Provide better security (authentication and privacy).
5. Pay more attention to the type of service, particularly for real-time data.
6. Aid multicasting by allowing scopes to be specified.
7. Make it possible for a host to roam without changing its address.
8. Allow the protocol to evolve in the future.
9. Permit the old and new protocols to coexist for years.


---

<a id="page-469"></a>

<!-- Page 469 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 457
The design of IPv6 presented a major opportunity to improve all of the fea-
tures in IPv4 that fall short of what is now wanted. To develop a protocol that met
all these requirements, IETF issued a call for proposals and discussion in RFC
1550. Twenty-one responses were initially received. By December 1992, seven
serious proposals were on the table. They ranged from making minor patches to
IP, to throwing it out altogether and replacing it with a completely different proto-
col.
One proposal was to run TCP over CLNP, the network layer protocol de-
signed for OSI. With its 160-bit addresses, CLNP would have provided enough
address space forever as it could give every molecule of water in the oceans
enough addresses (roughly 25) to set up a small network. This choice would also
have unified two major network layer protocols. However, many people felt that
this would have been an admission that something in the OSI world was actually
done right, a statement considered Politically Incorrect in Internet circles. CLNP
was patterned closely on IP, so the two are not really that different. In fact, the
protocol ultimately chosen differs from IP far more than CLNP does. Another
strike against CLNP was its poor support for service types, something required to
transmit multimedia efficiently.
Three of the better proposals were published in IEEE Network (Deering,
1993; Francis, 1993; and Katz and Ford, 1993). After much discussion, revision,
and jockeying for position, a modified combined version of the Deering and
Francis proposals, by now called SIPP (Simple Internet Protocol Plus) was se-
lected and given the designation IPv6.
IPv6 meets IETF's goals fairly well. It maintains the good features of IP, dis-
cards or deemphasizes the bad ones, and adds new ones where needed. In gener-
al, IPv6 is not compatible with IPv4, but it is compatible with the other auxiliary
Internet protocols, including TCP, UDP, ICMP, IGMP, OSPF, BGP, and DNS,
with small modifications being required to deal with longer addresses. The main
features of IPv6 are discussed below. More information about it can be found in
RFCs 2460 through 2466.
First and foremost, IPv6 has longer addresses than IPv4. They are 128 bits
long, which solves the problem that IPv6 set out to solve: providing an effectively
unlimited supply of Internet addresses. We will have more to say about addresses
shortly.
The second major improvement of IPv6 is the simplification of the header. It
contains only seven fields (versus 13 in IPv4). This change allows routers to
process packets faster and thus improves throughput and delay. We will discuss
the header shortly, too.
The third major improvement is better support for options. This change was
essential with the new header because fields that previously were required are
now optional (because they are not used so often). In addition, the way options
are represented is different, making it simple for routers to skip over options not
intended for them. This feature speeds up packet processing time.


---

<a id="page-470"></a>

<!-- Page 470 of 888 -->

458 THE NETWORK LAYER CHAP. 5
A fourth area in which IPv6 represents a big advance is in security. IETF had
its fill of newspaper stories about precocious 12-year-olds using their personal
computers to break into banks and military bases all over the Internet. There was
a strong feeling that something had to be done to improve security. Authentica-
tion and privacy are key features of the new IP. These were later retrofitted to
IPv4, however, so in the area of security the differences are not so great any more.
Finally, more attention has been paid to quality of service. Various half-
hearted efforts to improve QoS have been made in the past, but now, with the
growth of multimedia on the Internet, the sense of urgency is greater.
The Main IPv6 Header
The IPv6 header is shown in Fig. 5-56. The Version field is always 6 for IPv6
(and 4 for IPv4). During the transition period from IPv4, which has already taken
more than a decade, routers will be able to examine this field to tell what kind of
packet they have. As an aside, making this test wastes a few instructions in the
critical path, given that the data link header usually indicates the network protocol
for demultiplexing, so some routers may skip the check. For example, the Ether-
net Type field has different values to indicate an IPv4 or an IPv6 payload. The
discussions between the ''Do it right'' and ''Make it fast'' camps will no doubt be
lengthy and vigorous.
32 Bits
Version Diff. services Flow label
Payload length Next header Hop limit
Source address
(16 bytes)
Destination address
(16 bytes)
Figure 5-56. The IPv6 fixed header (required).
The Differentiated services field (originally called Traffic class) is used to
distinguish the class of service for packets with different real-time delivery


---

<a id="page-471"></a>

<!-- Page 471 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 459
requirements. It is used with the differentiated service architecture for quality of
service in the same manner as the field of the same name in the IPv4 packet. Also,
the low-order 2 bits are used to signal explicit congestion indications, again in the
same way as with IPv4.
The Flow label field provides a way for a source and destination to mark
groups of packets that have the same requirements and should be treated in the
same way by the network, forming a pseudoconnection. For example, a stream of
packets from one process on a certain source host to a process on a specific desti-
nation host might have stringent delay requirements and thus need reserved band-
width. The flow can be set up in advance and given an identifier. When a packet
with a nonzero Flow label shows up, all the routers can look it up in internal
tables to see what kind of special treatment it requires. In effect, flows are an at-
tempt to have it both ways: the flexibility of a datagram network and the guaran-
tees of a virtual-circuit network.
Each flow for quality of service purposes is designated by the source address,
destination address, and flow number. This design means that up to 220 flows
may be active at the same time between a given pair of IP addresses. It also
means that even if two flows coming from different hosts but with the same flow
label pass through the same router, the router will be able to tell them apart using
the source and destination addresses. It is expected that flow labels will be cho-
sen randomly, rather than assigned sequentially starting at 1, so routers are ex-
pected to hash them.
The Payload length field tells how many bytes follow the 40-byte header of
Fig. 5-56. The name was changed from the IPv4 Total length field because the
meaning was changed slightly: the 40 header bytes are no longer counted as part
of the length (as they used to be). This change means the payload can now be
65,535 bytes instead of a mere 65,515 bytes.
The Next header field lets the cat out of the bag. The reason the header could
be simplified is that there can be additional (optional) extension headers. This
field tells which of the (currently) six extension headers, if any, follow this one.
If this header is the last IP header, the Next header field tells which transport pro-
tocol handler (e.g., TCP, UDP) to pass the packet to.
The Hop limit field is used to keep packets from living forever. It is, in prac-
tice, the same as the Time to live field in IPv4, namely, a field that is decremented
on each hop. In theory, in IPv4 it was a time in seconds, but no router used it that
way, so the name was changed to reflect the way it is actually used.
Next come the Source address and Destination address fields. Deering's
original proposal, SIP, used 8-byte addresses, but during the review process many
people felt that with 8-byte addresses IPv6 would run out of addresses within a
few decades, whereas with 16-byte addresses it would never run out. Other peo-
ple argued that 16 bytes was overkill, whereas still others favored using 20-byte
addresses to be compatible with the OSI datagram protocol. Still another faction
wanted variable-sized addresses. After much debate and more than a few words


---

<a id="page-472"></a>

<!-- Page 472 of 888 -->

460 THE NETWORK LAYER CHAP. 5
unprintable in an academic textbook, it was decided that fixed-length 16-byte ad-
dresses were the best compromise.
A new notation has been devised for writing 16-byte addresses. They are
written as eight groups of four hexadecimal digits with colons between the groups,
like this:
8000:0000:0000:0000:0123:4567:89AB:CDEF
Since many addresses will have many zeros inside them, three optimizations have
been authorized. First, leading zeros within a group can be omitted, so 0123 can
be written as 123. Second, one or more groups of 16 zero bits can be replaced by
a pair of colons. Thus, the above address now becomes
8000::123:4567:89AB:CDEF
Finally, IPv4 addresses can be written as a pair of colons and an old dotted
decimal number, for example:
::192.31.20.46
Perhaps it is unnecessary to be so explicit about it, but there are a lot of 16-
byte addresses. Specifically, there are 2128 of them, which is approximately
3 × 1038. If the entire earth, land and water, were covered with computers, IPv6
would allow 7 × 1023 IP addresses per square meter. Students of chemistry will
notice that this number is larger than Avogadro's number. While it was not the
intention to give every molecule on the surface of the earth its own IP address, we
are not that far off.
In practice, the address space will not be used efficiently, just as the telephone
number address space is not (the area code for Manhattan, 212, is nearly full, but
that for Wyoming, 307, is nearly empty). In RFC 3194, Durand and Huitema cal-
culated that, using the allocation of telephone numbers as a guide, even in the
most pessimistic scenario there will still be well over 1000 IP addresses per
square meter of the entire earth's surface (land and water). In any likely scenario,
there will be trillions of them per square meter. In short, it seems unlikely that we
will run out in the foreseeable future.
It is instructive to compare the IPv4 header (Fig. 5-46) with the IPv6 header
(Fig. 5-56) to see what has been left out in IPv6. The IHL field is gone because
the IPv6 header has a fixed length. The Protocol field was taken out because the
Next header field tells what follows the last IP header (e.g., a UDP or TCP seg-
ment).
All the fields relating to fragmentation were removed because IPv6 takes a
different approach to fragmentation. To start with, all IPv6-conformant hosts are
expected to dynamically determine the packet size to use. They do this using the
path MTU discovery procedure we described in Sec. 5.5.5. In brief, when a host
sends an IPv6 packet that is too large, instead of fragmenting it, the router that is
unable to forward it drops the packet and sends an error message back to the


---

<a id="page-473"></a>

<!-- Page 473 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 461
sending host. This message tells the host to break up all future packets to that
destination. Having the host send packets that are the right size in the first place
is ultimately much more efficient than having the routers fragment them on the
fly. Also, the minimum-size packet that routers must be able to forward has been
raised from 576 to 1280 bytes to allow 1024 bytes of data and many headers.
Finally, the Checksum field is gone because calculating it greatly reduces per-
formance. With the reliable networks now used, combined with the fact that the
data link layer and transport layers normally have their own checksums, the value
of yet another checksum was deemed not worth the performance price it
extracted. Removing all these features has resulted in a lean and mean network
layer protocol. Thus, the goal of IPv6-a fast, yet flexible, protocol with plenty
of address space-is met by this design.
Extension Headers
Some of the missing IPv4 fields are occasionally still needed, so IPv6 intro-
duces the concept of (optional) extension headers. These headers can be sup-
plied to provide extra information, but encoded in an efficient way. Six kinds of
extension headers are defined at present, as listed in Fig. 5-57. Each one is op-
tional, but if more than one is present they must appear directly after the fixed
header, and preferably in the order listed.
Extension header Description
Hop-by-hop options Miscellaneous information for routers
Destination options Additional information for the destination
Routing Loose list of routers to visit
Fragmentation Management of datagram fragments
Authentication Verification of the sender's identity
Encrypted security payload Information about the encrypted contents
Figure 5-57. IPv6 extension headers.
Some of the headers have a fixed format; others contain a variable number of
variable-length options. For these, each item is encoded as a (Type, Length,
Value) tuple. The Type is a 1-byte field telling which option this is. The Type
values have been chosen so that the first 2 bits tell routers that do not know how
to process the option what to do. The choices are: skip the option; discard the
packet; discard the packet and send back an ICMP packet; and discard the packet
but do not send ICMP packets for multicast addresses (to prevent one bad multi-
cast packet from generating millions of ICMP reports).
The Length is also a 1-byte field. It tells how long the value is (0 to 255
bytes). The Value is any information required, up to 255 bytes.


---

<a id="page-474"></a>

<!-- Page 474 of 888 -->

462 THE NETWORK LAYER CHAP. 5
The hop-by-hop header is used for information that all routers along the path
must examine. So far, one option has been defined: support of datagrams exceed-
ing 64 KB. The format of this header is shown in Fig. 5-58. When it is used, the
Payload length field in the fixed header is set to 0.
Next header 0 194 4
Jumbo payload length
Figure 5-58. The hop-by-hop extension header for large datagrams (jumbograms).
As with all extension headers, this one starts with a byte telling what kind of
header comes next. This byte is followed by one telling how long the hop-by-hop
header is in bytes, excluding the first 8 bytes, which are mandatory. All exten-
sions begin this way.
The next 2 bytes indicate that this option defines the datagram size (code 194)
and that the size is a 4-byte number. The last 4 bytes give the size of the data-
gram. Sizes less than 65,536 bytes are not permitted and will result in the first
router discarding the packet and sending back an ICMP error message. Data-
grams using this header extension are called jumbograms. The use of jumbo-
grams is important for supercomputer applications that must transfer gigabytes of
data efficiently across the Internet.
The destination options header is intended for fields that need only be inter-
preted at the destination host. In the initial version of IPv6, the only options de-
fined are null options for padding this header out to a multiple of 8 bytes, so ini-
tially it will not be used. It was included to make sure that new routing and host
software can handle it, in case someone thinks of a destination option some day.
The routing header lists one or more routers that must be visited on the way to
the destination. It is very similar to the IPv4 loose source routing in that all ad-
dresses listed must be visited in order, but other routers not listed may be visited
in between. The format of the routing header is shown in Fig. 5-59.
Header extension
Next header Routing type Segments left
length
Type-specific data
Figure 5-59. The extension header for routing.


---

<a id="page-475"></a>

<!-- Page 475 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 463
The first 4 bytes of the routing extension header contain four 1-byte integers.
The Next header and Header extension length fields were described above. The
Routing type field gives the format of the rest of the header. Type 0 says that a re-
served 32-bit word follows the first word, followed by some number of IPv6 ad-
dresses. Other types may be invented in the future, as needed. Finally, the Seg-
ments left field keeps track of how many of the addresses in the list have not yet
been visited. It is decremented every time one is visited. When it hits 0, the
packet is on its own with no more guidance about what route to follow. Usually,
at this point it is so close to the destination that the best route is obvious.
The fragment header deals with fragmentation similarly to the way IPv4 does.
The header holds the datagram identifier, fragment number, and a bit telling
whether more fragments will follow. In IPv6, unlike in IPv4, only the source host
can fragment a packet. Routers along the way may not do this. This change is a
major philosophical break with the original IP, but in keeping with current prac-
tice for IPv4. Plus, it simplifies the routers' work and makes routing go faster. As
mentioned above, if a router is confronted with a packet that is too big, it discards
the packet and sends an ICMP error packet back to the source. This information
allows the source host to fragment the packet into smaller pieces using this header
and try again.
The authentication header provides a mechanism by which the receiver of a
packet can be sure of who sent it. The encrypted security payload makes it pos-
sible to encrypt the contents of a packet so that only the intended recipient can
read it. These headers use the cryptographic techniques that we will describe in
Chap. 8 to accomplish their missions.
Controversies
Given the open design process and the strongly held opinions of many of the
people involved, it should come as no surprise that many choices made for IPv6
were highly controversial, to say the least. We will summarize a few of these
briefly below. For all the gory details, see the RFCs.
We have already mentioned the argument about the address length. The result
was a compromise: 16-byte fixed-length addresses.
Another fight developed over the length of the Hop limit field. One camp felt
strongly that limiting the maximum number of hops to 255 (implicit in using an
8-bit field) was a gross mistake. After all, paths of 32 hops are common now, and
10 years from now much longer paths may be common. These people argued that
using a huge address size was farsighted but using a tiny hop count was short-
sighted. In their view, the greatest sin a computer scientist can commit is to pro-
vide too few bits somewhere.
The response was that arguments could be made to increase every field, lead-
ing to a bloated header. Also, the function of the Hop limit field is to keep pack-
ets from wandering around for too long a time and 65,535 hops is far, far too long.


---

<a id="page-476"></a>

<!-- Page 476 of 888 -->

464 THE NETWORK LAYER CHAP. 5
Finally, as the Internet grows, more and more long-distance links will be built,
making it possible to get from any country to any other country in half a dozen
hops at most. If it takes more than 125 hops to get from the source and the desti-
nation to their respective international gateways, something is wrong with the na-
tional backbones. The 8-bitters won this one.
Another hot potato was the maximum packet size. The supercomputer com-
munity wanted packets in excess of 64 KB. When a supercomputer gets started
transferring, it really means business and does not want to be interrupted every 64
KB. The argument against large packets is that if a 1-MB packet hits a 1.5-Mbps
T1 line, that packet will tie the line up for over 5 seconds, producing a very
noticeable delay for interactive users sharing the line. A compromise was reached
here: normal packets are limited to 64 KB, but the hop-by-hop extension header
can be used to permit jumbograms.
A third hot topic was removing the IPv4 checksum. Some people likened this
move to removing the brakes from a car. Doing so makes the car lighter so it can
go faster, but if an unexpected event happens, you have a problem.
The argument against checksums was that any application that really cares
about data integrity has to have a transport layer checksum anyway, so having an-
other one in IP (in addition to the data link layer checksum) is overkill. Fur-
thermore, experience showed that computing the IP checksum was a major
expense in IPv4. The antichecksum camp won this one, and IPv6 does not have a
checksum.
Mobile hosts were also a point of contention. If a portable computer flies
halfway around the world, can it continue operating there with the same IPv6 ad-
dress, or does it have to use a scheme with home agents? Some people wanted to
build explicit support for mobile hosts into IPv6. That effort failed when no con-
sensus could be found for any specific proposal.
Probably the biggest battle was about security. Everyone agreed it was essen-
tial. The war was about where to put it and how. First where. The argument for
putting it in the network layer is that it then becomes a standard service that all
applications can use without any advance planning. The argument against it is
that really secure applications generally want nothing less than end-to-end en-
cryption, where the source application does the encryption and the destination ap-
plication undoes it. With anything less, the user is at the mercy of potentially
buggy network layer implementations over which he has no control. The response
to this argument is that these applications can just refrain from using the IP securi-
ty features and do the job themselves. The rejoinder to that is that the people who
do not trust the network to do it right do not want to pay the price of slow, bulky
IP implementations that have this capability, even if it is disabled.
Another aspect of where to put security relates to the fact that many (but not
all) countries have very stringent export laws concerning cryptography. Some,
notably France and Iraq, also restrict its use domestically, so that people cannot
have secrets from the government. As a result, any IP implementation that used a


---

<a id="page-477"></a>

<!-- Page 477 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 465
cryptographic system strong enough to be of much value could not be exported
from the United States (and many other countries) to customers worldwide. Hav-
ing to maintain two sets of software, one for domestic use and one for export, is
something most computer vendors vigorously oppose.
One point on which there was no controversy is that no one expects the IPv4
Internet to be turned off on a Sunday evening and come back up as an IPv6 Inter-
net Monday morning. Instead, isolated ''islands'' of IPv6 will be converted, ini-
tially communicating via tunnels, as we showed in Sec. 5.5.3. As the IPv6 islands
grow, they will merge into bigger islands. Eventually, all the islands will merge,
and the Internet will be fully converted.
At least, that was the plan. Deployment has proved the Achilles heel of IPv6.
It remains little used, even though all major operating systems fully support it.
Most deployments are new situations in which a network operator-for example,
a mobile phone operator- needs a large number of IP addresses. Many strategies
have been defined to help ease the transition. Among them are ways to automat-
ically configure the tunnels that carry IPv6 over the IPv4 Internet, and ways for
hosts to automatically find the tunnel endpoints. Dual-stack hosts have an IPv4
and an IPv6 implementation so that they can select which protocol to use depend-
ing on the destination of the packet. These strategies will streamline the substan-
tial deployment that seems inevitable when IPv4 addresses are exhausted. For
more information about IPv6, see Davies (2008).
#### 5.6.4 Internet Control Protocols
In addition to IP, which is used for data transfer, the Internet has several com-
panion control protocols that are used in the network layer. They include ICMP,
ARP, and DHCP. In this section, we will look at each of these in turn, describing
the versions that correspond to IPv4 because they are the protocols that are in
common use. ICMP and DHCP have similar versions for IPv6; the equivalent of
ARP is called NDP (Neighbor Discovery Protocol) for IPv6.
IMCP-The Internet Control Message Protocol
The operation of the Internet is monitored closely by the routers. When some-
thing unexpected occurs during packet processing at a router, the event is reported
to the sender by the ICMP (Internet Control Message Protocol). ICMP is also
used to test the Internet. About a dozen types of ICMP messages are defined.
Each ICMP message type is carried encapsulated in an IP packet. The most im-
portant ones are listed in Fig. 5-60.
The DESTINATION UNREACHABLE message is used when the router cannot
locate the destination or when a packet with the DF bit cannot be delivered be-
cause a ''small-packet'' network stands in the way.


---

<a id="page-478"></a>

<!-- Page 478 of 888 -->

466 THE NETWORK LAYER CHAP. 5
Message type Description
Destination unreachable Packet could not be delivered
Time exceeded Time to live field hit 0
Parameter problem Invalid header field
Source quench Choke packet
Redirect Teach a router about geography
Echo and echo reply Check if a machine is alive
Timestamp request/reply Same as Echo, but with timestamp
Router advertisement/solicitation Find a nearby router
Figure 5-60. The principal ICMP message types.
The TIME EXCEEDED message is sent when a packet is dropped because its
TtL (Time to live) counter has reached zero. This event is a symptom that packets
are looping, or that the counter values are being set too low.
One clever use of this error message is the traceroute utility that was devel-
oped by Van Jacobson in 1987. Traceroute finds the routers along the path from
the host to a destination IP address. It finds this information without any kind of
privileged network support. The method is simply to send a sequence of packets
to the destination, first with a TtL of 1, then a TtL of 2, 3, and so on. The counters
on these packets will reach zero at successive routers along the path. These rout-
ers will each obediently send a TIME EXCEEDED message back to the host. From
those messages, the host can determine the IP addresses of the routers along the
path, as well as keep statistics and timings on parts of the path. It is not what the
TIME EXCEEDED message was intended for, but it is perhaps the most useful net-
work debugging tool of all time.
The PARAMETER PROBLEM message indicates that an illegal value has been
detected in a header field. This problem indicates a bug in the sending host's IP
software or possibly in the software of a router transited.
The SOURCE QUENCH message was long ago used to throttle hosts that were
sending too many packets. When a host received this message, it was expected to
slow down. It is rarely used anymore because when congestion occurs, these
packets tend to add more fuel to the fire and it is unclear how to respond to them.
Congestion control in the Internet is now done largely by taking action in the tran-
sport layer, using packet losses as a congestion signal; we will study it in detail in
Chap. 6.
The REDIRECT message is used when a router notices that a packet seems to
be routed incorrectly. It is used by the router to tell the sending host to update to a
better route.
The ECHO and ECHO REPLY messages are sent by hosts to see if a given
destination is reachable and currently alive. Upon receiving the ECHO message,


---

<a id="page-479"></a>

<!-- Page 479 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 467
the destination is expected to send back an ECHO REPLY message. These mes-
sages are used in the ping utility that checks if a host is up and on the Internet.
The TIMESTAMP REQUEST and TIMESTAMP REPLY messages are similar,
except that the arrival time of the message and the departure time of the reply are
recorded in the reply. This facility can be used to measure network performance.
The ROUTER ADVERTISEMENT and ROUTER SOLICITATION messages are
used to let hosts find nearby routers. A host needs to learn the IP address of at
least one router to be able to send packets off the local network.
In addition to these messages, others have been defined. The online list is
now kept at www.iana.org/assignments/icmp-parameters.
ARP-The Address Resolution Protocol
Although every machine on the Internet has one or more IP addresses, these
addresses are not sufficient for sending packets. Data link layer NICs (Network
Interface Cards) such as Ethernet cards do not understand Internet addresses. In
the case of Ethernet, every NIC ever manufactured comes equipped with a unique
48-bit Ethernet address. Manufacturers of Ethernet NICs request a block of
Ethernet addresses from IEEE to ensure that no two NICs have the same address
(to avoid conflicts should the two NICs ever appear on the same LAN). The NICs
send and receive frames based on 48-bit Ethernet addresses. They know nothing
at all about 32-bit IP addresses.
The question now arises, how do IP addresses get mapped onto data link layer
addresses, such as Ethernet? To explain how this works, let us use the example of
Fig. 5-61, in which a small university with two /24 networks is illustrated. One
network (CS) is a switched Ethernet in the Computer Science Dept. It has the
prefix 192.32.65.0/24. The other LAN (EE), also switched Ethernet, is in Electri-
cal Engineering and has the prefix 192.32.63.0/24. The two LANs are connected
by an IP router. Each machine on an Ethernet and each interface on the router has
a unique Ethernet address, labeled E1 through E6, and a unique IP address on the
CS or EE network.
Let us start out by seeing how a user on host 1 sends a packet to a user on host
2 on the CS network. Let us assume the sender knows the name of the intended
receiver, possibly something like eagle.cs.uni.edu. The first step is to find the IP
address for host 2. This lookup is performed by DNS, which we will study in
Chap. 7. For the moment, we will just assume that DNS returns the IP address for
host 2 (192.32.65.5).
The upper layer software on host 1 now builds a packet with 192.32.65.5 in
the Destination address field and gives it to the IP software to transmit. The IP
software can look at the address and see that the destination is on the CS network,
(i.e., its own network). However, it still needs some way to find the destination's
Ethernet address to send the frame. One solution is to have a configuration file
somewhere in the system that maps IP addresses onto Ethernet addresses. While


---

<a id="page-480"></a>

<!-- Page 480 of 888 -->

468 THE NETWORK LAYER CHAP. 5
IP1 = 192.32.65.7 IP3 = 192.32.63.3
E1 Ethernet E5
switch Router
Host 1 E3 E4 Host 3
Host 2 192.32.65.1 192.32.63.1 Host 4
CS Network EE Network
E2 192.32.65.0/24 192.32.63.0/24 E6
IP2 = 192.32.65.5 IP4 = 192.32.63.8
Source Source Destination Destination
Frame
IP Eth. IP Eth.
Host 1 to 2, on CS net IP1 E1 IP2 E2
Host 1 to 4, on CS net IP1 E1 IP4 E3
Host 1 to 4, on EE net IP1 E4 IP4 E6
Figure 5-61. Two switched Ethernet LANs joined by a router.
this solution is certainly possible, for organizations with thousands of machines
keeping all these files up to date is an error-prone, time-consuming job.
A better solution is for host 1 to output a broadcast packet onto the Ethernet
asking who owns IP address 192.32.65.5. The broadcast will arrive at every ma-
chine on the CS Ethernet, and each one will check its IP address. Host 2 alone
will respond with its Ethernet address (E2). In this way host 1 learns that IP ad-
dress 192.32.65.5 is on the host with Ethernet address E2. The protocol used for
asking this question and getting the reply is called ARP (Address Resolution
Protocol). Almost every machine on the Internet runs it. ARP is defined in RFC
826.
The advantage of using ARP over configuration files is the simplicity. The
system manager does not have to do much except assign each machine an IP ad-
dress and decide about subnet masks. ARP does the rest.
At this point, the IP software on host 1 builds an Ethernet frame addressed to
E2, puts the IP packet (addressed to 192.32.65.5) in the payload field, and dumps
it onto the Ethernet. The IP and Ethernet addresses of this packet are given in
Fig. 5-61. The Ethernet NIC of host 2 detects this frame, recognizes it as a frame
for itself, scoops it up, and causes an interrupt. The Ethernet driver extracts the IP
packet from the payload and passes it to the IP software, which sees that it is cor-
rectly addressed and processes it.
Various optimizations are possible to make ARP work more efficiently. To
start with, once a machine has run ARP, it caches the result in case it needs to
contact the same machine shortly. Next time it will find the mapping in its own
cache, thus eliminating the need for a second broadcast. In many cases, host 2


---

<a id="page-481"></a>

<!-- Page 481 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 469
will need to send back a reply, forcing it, too, to run ARP to determine the send-
er's Ethernet address. This ARP broadcast can be avoided by having host 1 in-
clude its IP-to-Ethernet mapping in the ARP packet. When the ARP broadcast ar-
rives at host 2, the pair (192.32.65.7, E1) is entered into host 2's ARP cache. In
fact, all machines on the Ethernet can enter this mapping into their ARP caches.
To allow mappings to change, for example, when a host is configured to use a
new IP address (but keeps its old Ethernet address), entries in the ARP cache
should time out after a few minutes. A clever way to help keep the cached infor-
mation current and to optimize performance is to have every machine broadcast
its mapping when it is configured. This broadcast is generally done in the form of
an ARP looking for its own IP address. There should not be a response, but a side
effect of the broadcast is to make or update an entry in everyone's ARP cache.
This is known as a gratuitous ARP. If a response does (unexpectedly) arrive,
two machines have been assigned the same IP address. The error must be resolv-
ed by the network manager before both machines can use the network.
Now let us look at Fig. 5-61 again, only this time assume that host 1 wants to
send a packet to host 4 (192.32.63.8) on the EE network. Host 1 will see that the
destination IP address is not on the CS network. It knows to send all such off-net-
work traffic to the router, which is also known as the default gateway. By con-
vention, the default gateway is the lowest address on the network (198.31.65.1).
To send a frame to the router, host 1 must still know the Ethernet address of the
router interface on the CS network. It discovers this by sending an ARP broadcast
for 198.31.65.1, from which it learns E3. It then sends the frame. The same
lookup mechanisms are used to send a packet from one router to the next over a
sequence of routers in an Internet path.
When the Ethernet NIC of the router gets this frame, it gives the packet to the
IP software. It knows from the network masks that the packet should be sent onto
the EE network where it will reach host 4. If the router does not know the Ether-
net address for host 4, then it will use ARP again. The table in Fig. 5-61 lists the
source and destination Ethernet and IP addresses that are present in the frames as
observed on the CS and EE networks. Observe that the Ethernet addresses change
with the frame on each network while the IP addresses remain constant (because
they indicate the endpoints across all of the interconnected networks).
It is also possible to send a packet from host 1 to host 4 without host 1 know-
ing that host 4 is on a different network. The solution is to have the router answer
ARPs on the CS network for host 4 and give its Ethernet address, E3, as the re-
sponse. It is not possible to have host 4 reply directly because it will not see the
ARP request (as routers do not forward Ethernet-level broadcasts). The router will
then receive frames sent to 192.32.63.8 and forward them onto the EE network.
This solution is called proxy ARP. It is used in special cases in which a host
wants to appear on a network even though it actually resides on another network.
A common situation, for example, is a mobile computer that wants some other
node to pick up packets for it when it is not on its home network.


---

<a id="page-482"></a>

<!-- Page 482 of 888 -->

470 THE NETWORK LAYER CHAP. 5
DHCP-The Dynamic Host Configuration Protocol
ARP (as well as other Internet protocols) makes the assumption that hosts are
configured with some basic information, such as their own IP addresses. How do
hosts get this information? It is possible to manually configure each computer,
but that is tedious and error-prone. There is a better way, and it is called DHCP
(Dynamic Host Configuration Protocol).
With DHCP, every network must have a DHCP server that is responsible for
configuration. When a computer is started, it has a built-in Ethernet or other link
layer address embedded in the NIC, but no IP address. Much like ARP, the com-
puter broadcasts a request for an IP address on its network. It does this by using a
DHCP DISCOVER packet. This packet must reach the DHCP server. If that server
is not directly attached to the network, the router will be configured to receive
DHCP broadcasts and relay them to the DHCP server, wherever it is located.
When the server receives the request, it allocates a free IP address and sends
it to the host in a DHCP OFFER packet (which again may be relayed via the
router). To be able to do this work even when hosts do not have IP addresses, the
server identifies a host using its Ethernet address (which is carried in the DHCP
DISCOVER packet)
An issue that arises with automatic assignment of IP addresses from a pool is
for how long an IP address should be allocated. If a host leaves the network and
does not return its IP address to the DHCP server, that address will be perma-
nently lost. After a period of time, many addresses may be lost. To prevent that
from happening, IP address assignment may be for a fixed period of time, a tech-
nique called leasing. Just before the lease expires, the host must ask for a DHCP
renewal. If it fails to make a request or the request is denied, the host may no
longer use the IP address it was given earlier.
DHCP is described in RFCs 2131 and 2132. It is widely used in the Internet
to configure all sorts of parameters in addition to providing hosts with IP ad-
dresses. As well as in business and home networks, DHCP is used by ISPs to set
the parameters of devices over the Internet access link, so that customers do not
need to phone their ISPs to get this information. Common examples of the infor-
mation that is configured include the network mask, the IP address of the default
gateway, and the IP addresses of DNS and time servers. DHCP has largely re-
placed earlier protocols (called RARP and BOOTP) with more limited func-
tionality.
#### 5.6.5 Label Switching and MPLS
So far, on our tour of the network layer of the Internet, we have focused
exclusively on packets as datagrams that are forwarded by IP routers. There is
also another kind of technology that is starting to be widely used, especially by
ISPs, in order to move Internet traffic across their networks. This technology is


---

<a id="page-483"></a>

<!-- Page 483 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 471
called MPLS (MultiProtocol Label Switching) and it is perilously close to cir-
cuit switching. Despite the fact that many people in the Internet community have
an intense dislike for connection-oriented networking, the idea seems to keep
coming back. As Yogi Berra once put it, it is like deja vu all over again. Howev-
er, there are essential differences between the way the Internet handles route con-
struction and the way connection-oriented networks do it, so the technique is cer-
tainly not traditional circuit switching.
MPLS adds a label in front of each packet, and forwarding is based on the
label rather than on the destination address. Making the label an index into an in-
ternal table makes finding the correct output line just a matter of table lookup.
Using this technique, forwarding can be done very quickly. This advantage was
the original motivation behind MPLS, which began as proprietary technology
known by various names including tag switching. Eventually, IETF began to
standardize the idea. It is described in RFC 3031 and many other RFCs. The
main benefits over time have come to be routing that is flexible and forwarding
that is suited to quality of service as well as fast.
The first question to ask is where does the label go? Since IP packets were
not designed for virtual circuits, there is no field available for virtual-circuit num-
bers within the IP header. For this reason, a new MPLS header had to be added in
front of the IP header. On a router-to-router line using PPP as the framing proto-
col, the frame format, including the PPP, MPLS, IP, and TCP headers, is as
shown in Fig. 5-62.
Headers
PPP MPLS IP TCP User data CRC
Bits 20 3 1 8
Label QoS S TtL
Figure 5-62. Transmitting a TCP segment using IP, MPLS, and PPP.
The generic MPLS header is 4 bytes long and has four fields. Most important
is the Label field, which holds the index. The QoS field indicates the class of ser-
vice. The S field relates to stacking multiple labels (which is discussed below).
The TtL field indicates how many more times the packet may be forwarded. It is
decremented at each router, and if it hits 0, the packet is discarded. This feature
prevents infinite looping in the case of routing instability.
MPLS falls between the IP network layer protocol and the PPP link layer pro-
tocol. It is not really a layer 3 protocol because it depends on IP or other network


---

<a id="page-484"></a>

<!-- Page 484 of 888 -->

472 THE NETWORK LAYER CHAP. 5
layer addresses to set up label paths. It is not really a layer 2 protocol either be-
cause it forwards packets across multiple hops, not a single link. For this reason,
MPLS is sometimes described as a layer 2.5 protocol. It is an illustration that real
protocols do not always fit neatly into our ideal layered protocol model.
On the brighter side, because the MPLS headers are not part of the network
layer packet or the data link layer frame, MPLS is to a large extent independent of
both layers. Among other things, this property means it is possible to build MPLS
switches that can forward both IP packets and non-IP packets, depending on what
shows up. This feature is where the ''multiprotocol'' in the name MPLS came
from. MPLS can also carry IP packets over non-IP networks.
When an MPLS-enhanced packet arrives at a LSR (Label Switched Router),
the label is used as an index into a table to determine the outgoing line to use and
also the new label to use. This label swapping is used in all virtual-circuit net-
works. Labels have only local significance and two different routers can feed un-
related packets with the same label into another router for transmission on the
same outgoing line. To be distinguishable at the other end, labels have to be
remapped at every hop. We saw this mechanism in action in Fig. 5-3. MPLS
uses the same technique.
As an aside, some people distinguish between forwarding and switching. For-
warding is the process of finding the best match for a destination address in a
table to decide where to send packets. An example is the longest matching prefix
algorithm used for IP forwarding. In contrast, switching uses a label taken from
the packet as an index into a forwarding table. It is simpler and faster. These defi-
nitions are far from universal, however.
Since most hosts and routers do not understand MPLS, we should also ask
when and how the labels are attached to packets. This happens when an IP packet
reaches the edge of an MPLS network. The LER (Label Edge Router) inspects
the destination IP address and other fields to see which MPLS path the packet
should follow, and puts the right label on the front of the packet. Within the
MPLS network, this label is used to forward the packet. At the other edge of the
MPLS network, the label has served its purpose and is removed, revealing the IP
packet again for the next network. This process is shown in Fig. 5-63. One dif-
ference from traditional virtual circuits is the level of aggregation. It is certainly
possible for each flow to have its own set of labels through the MPLS network.
However, it is more common for routers to group multiple flows that end at a par-
ticular router or LAN and use a single label for them. The flows that are grouped
together under a single label are said to belong to the same FEC (Forwarding
Equivalence Class). This class covers not only where the packets are going, but
also their service class (in the differentiated services sense) because all the pack-
ets are treated the same way for forwarding purposes.
With traditional virtual-circuit routing, it is not possible to group several dis-
tinct paths with different endpoints onto the same virtual-circuit identifier because
there would be no way to distinguish them at the final destination. With MPLS,


---

<a id="page-485"></a>

<!-- Page 485 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 473
Remove
Add label
IP label Switching on IP
label only
Label Label
Label IP (to next
network)
Label edge
router
Label switch
router
Figure 5-63. Forwarding an IP packet through an MPLS network.
the packets still contain their final destination address, in addition to the label. At
the end of the labeled route, the label header can be removed and forwarding can
continue the usual way, using the network layer destination address.
Actually, MPLS goes even further. It can operate at multiple levels at once by
adding more than one label to the front of a packet. For example, suppose that
there are many packets that already have different labels (because we want to
treat the packets differently somewhere in the network) that should follow a com-
mon path to some destination. Instead of setting up many label switching paths,
one for each of the different labels, we can set up a single path. When the al-
ready-labeled packets reach the start of this path, another label is added to the
front. This is called a stack of labels. The outermost label guides the packets
along the path. It is removed at the end of the path, and the labels revealed, if any,
are used to forward the packet further. The S bit in Fig. 5-62 allows a router
removing a label to know if there are any additional labels left. It is set to 1 for
the bottom label and 0 for all the other labels.
The final question we will ask is how the label forwarding tables are set up so
that packets follow them. This is one area of major difference between MPLS
and conventional virtual-circuit designs. In traditional virtual-circuit networks,
when a user wants to establish a connection, a setup packet is launched into the
network to create the path and make the forwarding table entries. MPLS does not
involve users in the setup phase. Requiring users to do anything other than send a
datagram would break too much existing Internet software.
Instead, the forwarding information is set up by protocols that are a combina-
tion of routing protocols and connection setup protocols. These control protocols
are cleanly separated from label forwarding, which allows multiple, different con-
trol protocols to be used. One of the variants works like this. When a router is
booted, it checks to see which routes it is the final destination for (e.g., which pre-
fixes belong to its interfaces). It then creates one or more FECs for them, allo-
cates a label for each one, and passes the labels to its neighbors. They, in turn,
enter the labels in their forwarding tables and send new labels to their neighbors,
until all the routers have acquired the path. Resources can also be reserved as the


---

<a id="page-486"></a>

<!-- Page 486 of 888 -->

474 THE NETWORK LAYER CHAP. 5
path is constructed to guarantee an appropriate quality of service. Other variants
can set up different paths, such as traffic engineering paths that take unused ca-
pacity into account, and create paths on-demand to support service offerings such
as quality of service.
Although the basic ideas behind MPLS are straightforward, the details are
complicated, with many variations and use cases that are being actively devel-
oped. For more information, see Davie and Farrel (2008) and Davie and Rekhter
(2000).
#### 5.6.6 OSPF-An Interior Gateway Routing Protocol
We have now finished our study of how packets are forwarded in the Internet.
It is time to move on to the next topic: routing in the Internet. As we mentioned
earlier, the Internet is made up of a large number of independent networks or
ASes (Autonomous Systems) that are operated by different organizations, usually
a company, university, or ISP. Inside of its own network, an organization can use
its own algorithm for internal routing, or intradomain routing, as it is more com-
monly known. Nevertheless, there are only a handful of standard protocols that
are popular. In this section, we will study the problem of intradomain routing and
look at the OSPF protocol that is widely used in practice. An intradomain routing
protocol is also called an interior gateway protocol. In the next section, we will
study the problem of routing between independently operated networks, or inter-
domain routing. For that case, all networks must use the same interdomain rout-
ing protocol or exterior gateway protocol. The protocol that is used in the Inter-
net is BGP (Border Gateway Protocol).
Early intradomain routing protocols used a distance vector design, based on
the distributed Bellman-Ford algorithm inherited from the ARPANET. RIP (Rout-
ing Information Protocol) is the main example that is used to this day. It works
well in small systems, but less well as networks get larger. It also suffers from the
count-to-infinity problem and generally slow convergence. The ARPANET
switched over to a link state protocol in May 1979 because of these problems, and
in 1988 IETF began work on a link state protocol for intradomain routing. That
protocol, called OSPF (Open Shortest Path First), became a standard in 1990.
It drew on a protocol called IS-IS (Intermediate-System to Intermediate-Sys-
tem), which became an ISO standard. Because of their shared heritage, the two
protocols are much more alike than different. For the complete story, see RFC
2328. They are the dominant intradomain routing protocols, and most router ven-
dors now support both of them. OSPF is more widely used in company networks,
and IS-IS is more widely used in ISP networks. Of the two, we will give a sketch
of how OSPF works.
Given the long experience with other routing protocols, the group designing
OSPF had a long list of requirements that had to be met. First, the algorithm had
to be published in the open literature, hence the ''O'' in OSPF. A proprietary


---

<a id="page-487"></a>

<!-- Page 487 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 475
solution owned by one company would not do. Second, the new protocol had to
support a variety of distance metrics, including physical distance, delay, and so
on. Third, it had to be a dynamic algorithm, one that adapted to changes in the
topology automatically and quickly.
Fourth, and new for OSPF, it had to support routing based on type of service.
The new protocol had to be able to route real-time traffic one way and other traf-
fic a different way. At the time, IP had a Type of service field, but no existing
routing protocol used it. This field was included in OSPF but still nobody used it,
and it was eventually removed. Perhaps this requirement was ahead of its time, as
it preceded IETF's work on differentiated services, which has rejuvenated classes
of service.
Fifth, and related to the above, OSPF had to do load balancing, splitting the
load over multiple lines. Most previous protocols sent all packets over a single
best route, even if there were two routes that were equally good. The other route
was not used at all. In many cases, splitting the load over multiple routes gives
better performance.
Sixth, support for hierarchical systems was needed. By 1988, some networks
had grown so large that no router could be expected to know the entire topology.
OSPF had to be designed so that no router would have to.
Seventh, some modicum of security was required to prevent fun-loving stu-
dents from spoofing routers by sending them false routing information. Finally,
provision was needed for dealing with routers that were connected to the Internet
via a tunnel. Previous protocols did not handle this well.
OSPF supports both point-to-point links (e.g., SONET) and broadcast net-
works (e.g., most LANs). Actually, it is able to support networks with multiple
routers, each of which can communicate directly with the others (called multiac-
cess networks) even if they do not have broadcast capability. Earlier protocols
did not handle this case well.
An example of an autonomous system network is given in Fig. 5-64(a). Hosts
are omitted because they do not generally play a role in OSPF, while routers and
networks (which may contain hosts) do. Most of the routers in Fig. 5-64(a) are
connected to other routers by point-to-point links, and to networks to reach the
hosts on those networks. However, routers R3, R4, and R5 are connected by a
broadcast LAN such as switched Ethernet.
OSPF operates by abstracting the collection of actual networks, routers, and
links into a directed graph in which each arc is assigned a weight (distance, delay,
etc.). A point-to-point connection between two routers is represented by a pair of
arcs, one in each direction. Their weights may be different. A broadcast network
is represented by a node for the network itself, plus a node for each router. The
arcs from that network node to the routers have weight 0. They are important
nonetheless, as without them there is no path through the network. Other net-
works, which have only hosts, have only an arc reaching them and not one re-
turning. This structure gives routes to hosts, but not through them.


---

<a id="page-488"></a>

<!-- Page 488 of 888 -->

476 THE NETWORK LAYER CHAP. 5
R1 R3 R5
LAN 1
LAN 4
LAN 3
LAN 2
R2 R4
(a)

## Lan 1 R1 R3 3 R5 Lan 4
5 0
1 5

4 4 7 LAN 1

8 0

R4
LAN 2 R2
(b)
Figure 5-64. (a) An autonomous system. (b) A graph representation of (a).
Figure 5-64(b) shows the graph representation of the network of Fig. 5-64(a).
What OSPF fundamentally does is represent the actual network as a graph like
this and then use the link state method to have every router compute the shortest
path from itself to all other nodes. Multiple paths may be found that are equally
short. In this case, OSPF remembers the set of shortest paths and during packet
forwarding, traffic is split across them. This helps to balance load. It is called
ECMP (Equal Cost MultiPath).
Many of the ASes in the Internet are themselves large and nontrivial to man-
age. To work at this scale, OSPF allows an AS to be divided into numbered
areas, where an area is a network or a set of contiguous networks. Areas do not
overlap but need not be exhaustive, that is, some routers may belong to no area.
Routers that lie wholly within an area are called internal routers. An area is a
generalization of an individual network. Outside an area, its destinations are visi-
ble but not its topology. This characteristic helps routing to scale.
Every AS has a backbone area, called area 0. The routers in this area are
called backbone routers. All areas are connected to the backbone, possibly by
tunnels, so it is possible to go from any area in the AS to any other area in the AS
via the backbone. A tunnel is represented in the graph as just another arc with a
cost. As with other areas, the topology of the backbone is not visible outside the
backbone.
Each router that is connected to two or more areas is called an area border
router. It must also be part of the backbone. The job of an area border router is
to summarize the destinations in one area and to inject this summary into the other


---

<a id="page-489"></a>

<!-- Page 489 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 477
areas to which it is connected. This summary includes cost information but not all
the details of the topology within an area. Passing cost information allows hosts in
other areas to find the best area border router to use to enter an area. Not passing
topology information reduces traffic and simplifies the shortest-path computations
of routers in other areas. However, if there is only one border router out of an
area, even the summary does not need to be passed. Routes to destinations out of
the area always start with the instruction ''Go to the border router.'' This kind of
area is called a stub area.
The last kind of router is the AS boundary router. It injects routes to exter-
nal destinations on other ASes into the area. The external routes then appear as
destinations that can be reached via the AS boundary router with some cost. An
external route can be injected at one or more AS boundary routers. The relation-
ship between ASes, areas, and the various kinds of routers is shown in Fig. 5-65.
One router may play multiple roles, for example, a border router is also a back-
bone router.
Area border Backbone AS boundary Internal
router router router router
One
autonomous
system
Area 2 (stub) Area 0 (backbone) Area 1
Figure 5-65. The relation between ASes, backbones, and areas in OSPF.
During normal operation, each router within an area has the same link state
database and runs the same shortest path algorithm. Its main job is to calculate
the shortest path from itself to every other router and network in the entire AS.
An area border router needs the databases for all the areas to which it is connected
and must run the shortest path algorithm for each area separately.
For a source and destination in the same area, the best intra-area route (that
lies wholly within the area) is chosen. For a source and destination in different
areas, the inter-area route must go from the source to the backbone, across the
backbone to the destination area, and then to the destination. This algorithm
forces a star configuration on OSPF, with the backbone being the hub and the
other areas being spokes. Because the route with the lowest cost is chosen, rout-
ers in different parts of the network may use different area border routers to enter
the backbone and destination area. Packets are routed from source to destination
''as is.'' They are not encapsulated or tunneled (unless going to an area whose


---

<a id="page-490"></a>

<!-- Page 490 of 888 -->

478 THE NETWORK LAYER CHAP. 5
only connection to the backbone is a tunnel). Also, routes to external destinations
may include the external cost from the AS boundary router over the external path,
if desired, or just the cost internal to the AS.
When a router boots, it sends HELLO messages on all of its point-to-point
lines and multicasts them on LANs to the group consisting of all the other routers.
From the responses, each router learns who its neighbors are. Routers on the
same LAN are all neighbors.
OSPF works by exchanging information between adjacent routers, which is
not the same as between neighboring routers. In particular, it is inefficient to have
every router on a LAN talk to every other router on the LAN. To avoid this situa-
tion, one router is elected as the designated router. It is said to be adjacent to
all the other routers on its LAN, and exchanges information with them. In effect,
it is acting as the single node that represents the LAN. Neighboring routers that
are not adjacent do not exchange information with each other. A backup de-
signated router is always kept up to date to ease the transition should the primary
designated router crash and need to be replaced immediately.
During normal operation, each router periodically floods LINK STATE
UPDATE messages to each of its adjacent routers. These messages gives its state
and provide the costs used in the topological database. The flooding messages are
acknowledged, to make them reliable. Each message has a sequence number, so a
router can see whether an incoming LINK STATE UPDATE is older or newer than
what it currently has. Routers also send these messages when a link goes up or
down or its cost changes.
DATABASE DESCRIPTION messages give the sequence numbers of all the
link state entries currently held by the sender. By comparing its own values with
those of the sender, the receiver can determine who has the most recent values.
These messages are used when a link is brought up.
Either partner can request link state information from the other one by using
LINK STATE REQUEST messages. The result of this algorithm is that each pair of
adjacent routers checks to see who has the most recent data, and new information
is spread throughout the area this way. All these messages are sent directly in IP
packets. The five kinds of messages are summarized in Fig. 5-66.
Message type Description
Hello Used to discover who the neighbors are
Link state update Provides the sender's costs to its neighbors
Link state ack Acknowledges link state update
Database description Announces which updates the sender has
Link state request Requests information from the partner
Figure 5-66. The five types of OSPF messages.


---

<a id="page-491"></a>

<!-- Page 491 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 479
Finally, we can put all the pieces together. Using flooding, each router
informs all the other routers in its area of its links to other routers and networks
and the cost of these links. This information allows each router to construct the
graph for its area(s) and compute the shortest paths. The backbone area does this
work, too. In addition, the backbone routers accept information from the area
border routers in order to compute the best route from each backbone router to
every other router. This information is propagated back to the area border routers,
which advertise it within their areas. Using this information, internal routers can
select the best route to a destination outside their area, including the best exit
router to the backbone.
#### 5.6.7 BGP-The Exterior Gateway Routing Protocol
Within a single AS, OSPF and IS-IS are the protocols that are commonly
used. Between ASes, a different protocol, called BGP (Border Gateway Proto-
col), is used. A different protocol is needed because the goals of an intradomain
protocol and an interdomain protocol are not the same. All an intradomain proto-
col has to do is move packets as efficiently as possible from the source to the dest-
ination. It does not have to worry about politics.
In contrast, interdomain routing protocols have to worry about politics a great
deal (Metz, 2001). For example, a corporate AS might want the ability to send
packets to any Internet site and receive packets from any Internet site. However,
it might be unwilling to carry transit packets originating in a foreign AS and end-
ing in a different foreign AS, even if its own AS is on the shortest path between
the two foreign ASes (''That's their problem, not ours''). On the other hand, it
might be willing to carry transit traffic for its neighbors, or even for specific other
ASes that paid it for this service. Telephone companies, for example, might be
happy to act as carriers for their customers, but not for others. Exterior gateway
protocols in general, and BGP in particular, have been designed to allow many
kinds of routing policies to be enforced in the interAS traffic.
Typical policies involve political, security, or economic considerations. A
few examples of possible routing constraints are:
1. Do not carry commercial traffic on the educational network.
2. Never send traffic from the Pentagon on a route through Iraq.
3. Use TeliaSonera instead of Verizon because it is cheaper.
4. Don't use AT&T in Australia because performance is poor.
5. Traffic starting or ending at Apple should not transit Google.
As you might imagine from this list, routing policies can be highly individual.
They are often proprietary because they contain sensitive business information.


---

<a id="page-492"></a>

<!-- Page 492 of 888 -->

480 THE NETWORK LAYER CHAP. 5
However, we can describe some patterns that capture the reasoning of the com-
pany above and that are often used as a starting point.
A routing policy is implemented by deciding what traffic can flow over which
of the links between ASes. One common policy is that a customer ISP pays anoth-
er provider ISP to deliver packets to any other destination on the Internet and re-
ceive packets sent from any other destination. The customer ISP is said to buy
transit service from the provider ISP. This is just like a customer at home buying
Internet access service from an ISP. To make it work, the provider should adver-
tise routes to all destinations on the Internet to the customer over the link that con-
nects them. In this way, the customer will have a route to use to send packets
anywhere. Conversely, the customer should advertise routes only to the destina-
tions on its network to the provider. This will let the provider send traffic to the
customer only for those addresses; the customer does not want to handle traffic in-
tended for other destinations.
We can see an example of transit service in Fig. 5-67. There are four ASes
that are connected. The connection is often made with a link at IXPs (Internet
eXchange Points), facilities to which many ISPs have a link for the purpose of
connecting with other ISPs. AS2, AS3, and AS4 are customers of AS1. They buy
transit service from it. Thus, when source A sends to destination C, the packets
travel from AS2 to AS1 and finally to AS4. The routing advertisements travel in
the opposite direction to the packets. AS4 advertises C as a destination to its tran-
sit provider, AS1, to let sources reach C via AS1. Later, AS1 advertises a route to
C to its other customers, including AS2, to let the customers know that they can
send traffic to C via AS1.
AS1 Routing policy:
TR = Transit
Path of BGP routing CU = Customer
advertisements (dash) PE = Peer
TR
CU
## Tr Cu Tr Cu
AS4
AS2 AS3
Path of IP
packets (solid) PE PE
A B C
Figure 5-67. Routing policies between four autonomous systems.
In Fig. 5-67, all of the other ASes buy transit service from AS1. This provides
them with connectivity so they can interact with any host on the Internet. Howev-
er, they have to pay for this privilege. Suppose that AS2 and AS3 exchange a lot
of traffic. Given that their networks are connected already, if they want to, they


---

<a id="page-493"></a>

<!-- Page 493 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 481
can use a different policy-they can send traffic directly to each other for free.
This will reduce the amount of traffic they must have AS1 deliver on their behalf,
and hopefully it will reduce their bills. This policy is called peering.
To implement peering, two ASes send routing advertisements to each other
for the addresses that reside in their networks. Doing so makes it possible for AS2
to send AS3 packets from A destined to B and vice versa. However, note that
peering is not transitive. In Fig. 5-67, AS3 and AS4 also peer with each other. This
peering allows traffic from C destined for B to be sent directly to AS4. What hap-
pens if C sends a packet to A? AS3 is only advertising a route to B to AS4. It is
not advertising a route to A. The consequence is that traffic will not pass from
AS4 to AS3 to AS2, even though a physical path exists. This restriction is exactly
what AS3 wants. It peers with AS4 to exchange traffic, but does not want to carry
traffic from AS4 to other parts of the Internet since it is not being paid to so do. In-
stead, AS4 gets transit service from AS1. Thus, it is AS1 who will carry the packet
from C to A.
Now that we know about transit and peering, we can also see that A, B, and C
have transit arrangements. For example, A must buy Internet access from AS2. A
might be a single home computer or a company network with many LANs. How-
ever, it does not need to run BGP because it is a stub network that is connected
to the rest of the Internet by only one link. So the only place for it to send packets
destined outside of the network is over the link to AS2. There is nowhere else to
go. This path can be arranged simply by setting up a default route. For this rea-
son, we have not shown A, B, and C as ASes that participate in interdomain rout-
ing.
On the other hand, some company networks are connected to multiple ISPs.
This technique is used to improve reliability, since if the path through one ISP
fails, the company can use the path via the other ISP. This technique is called
multihoming. In this case, the company network is likely to run an interdomain
routing protocol (e.g., BGP) to tell other ASes which addresses should be reached
via which ISP links.
Many variations on these transit and peering policies are possible, but they al-
ready illustrate how business relationships and control over where route advertise-
ments go can implement different kinds of policies. Now we will consider in
more detail how routers running BGP advertise routes to each other and select
paths over which to forward packets.
BGP is a form of distance vector protocol, but it is quite unlike intradomain
distance vector protocols such as RIP. We have already seen that policy, instead
of minimum distance, is used to pick which routes to use. Another large dif-
ference is that instead of maintaining just the cost of the route to each destination,
each BGP router keeps track of the path used. This approach is called a path vec-
tor protocol. The path consists of the next hop router (which may be on the other
side of the ISP, not adjacent) and the sequence of ASes, or AS path, that the route
has followed (given in reverse order). Finally, pairs of BGP routers communicate


---

<a id="page-494"></a>

<!-- Page 494 of 888 -->

482 THE NETWORK LAYER CHAP. 5
with each other by establishing TCP connections. Operating this way provides re-
liable communication and also hides all the details of the network being passed
through.
An example of how BGP routes are advertised is shown in Fig. 5-68. There
are three ASes and the middle one is providing transit to the left and right ISPs. A
route advertisement to prefix C starts in AS3. When it is propagated across the
link to R2c at the top of the figure, it has the AS path of simply AS3 and the next
hop router of R3a. At the bottom, it has the same AS path but a different next hop
because it came across a different link. This advertisement continues to propagate
and crosses the boundary into AS1. At router R1a, at the top of the figure, the AS
path is AS2, AS3 and the next hop is R2a.
AS path
Prefix Next hop
C, AS2, AS3, R1a C, AS2, AS3, R2a C, AS3, R3a
A C
R1a R2a R2c R3a
Path of
C, AS2, AS3, R1b C, AS2, AS3, R2b C, AS3, R3b
packets
B
R1b R2b R2d R3b
## As1 As2 As3
Figure 5-68. Propagation of BGP route advertisements.
Carrying the complete path with the route makes it easy for the receiving
router to detect and break routing loops. The rule is that each router that sends a
route outside of the AS prepends its own AS number to the route. (This is why the
list is in reverse order.) When a router receives a route, it checks to see if its own
AS number is already in the AS path. If it is, a loop has been detected and the
advertisement is discarded. However, and somewhat ironically, it was realized in
the late 1990s that despite this precaution BGP suffers from a version of the
count-to-infinity problem (Labovitz et al., 2001). There are no long-lived loops,
but routes can sometimes be slow to converge and have transient loops.
Giving a list of ASes is a very coarse way to specify a path. An AS might be
a small company, or an international backbone network. There is no way of telling
from the route. BGP does not even try because different ASes may use different
intradomain protocols whose costs cannot be compared. Even if they could be
compared, an AS may not want to reveal its internal metrics. This is one of the
ways that interdomain routing protocols differ from intradomain protocols.


---

<a id="page-495"></a>

<!-- Page 495 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 483
So far we have seen how a route advertisement is sent across the link between
two ISPs. We still need some way to propagate BGP routes from one side of the
ISP to the other, so they can be sent on to the next ISP. This task could be handled
by the intradomain protocol, but because BGP is very good at scaling to large net-
works, a variant of BGP is often used. It is called iBGP (internal BGP) to distin-
guish it from the regular use of BGP as eBGP (external BGP).
The rule for propagating routes inside an ISP is that every router at the bound-
ary of the ISP learns of all the routes seen by all the other boundary routers, for
consistency. If one boundary router on the ISP learns of a prefix to IP
128.208.0.0/16, all the other routers will learn of this prefix. The prefix will then
be reachable from all parts of the ISP, no matter how packets enter the ISP from
other ASes.
We have not shown this propagation in Fig. 5-68 to avoid clutter, but, for ex-
ample, router R2b will know that it can reach C via either router R2c at top or
router R2d at bottom. The next hop is updated as the route crosses within the ISP
so that routers on the far side of the ISP know which router to use to exit the ISP
on the other side. This can be seen in the leftmost routes in which the next hop
points to a router in the same ISP and not a router in the next ISP.
We can now describe the key missing piece, which is how BGP routers
choose which route to use for each destination. Each BGP router may learn a
route for a given destination from the router it is connected to in the next ISP and
from all of the other boundary routers (which have heard different routes from the
routers they are connected to in other ISPs). Each router must decide which route
in this set of routes is the best one to use. Ultimately the answer is that it is up to
the ISP to write some policy to pick the preferred route. However, this explana-
tion is very general and not at all satisfying, so we can at least describe some
common strategies.
The first strategy is that routes via peered networks are chosen in preference
to routes via transit providers. The former are free; the latter cost money. A simi-
lar strategy is that customer routes are given the highest preference. It is only
good business to send traffic directly to the paying customers.
A different kind of strategy is the default rule that shorter AS paths are better.
This is debatable given that an AS could be a network of any size, so a path
through three small ASes could actually be shorter than a path through one big
AS. However, shorter tends to be better on average, and this rule is a common
tiebreaker.
The final strategy is to prefer the route that has the lowest cost within the ISP.
This is the strategy implemented in Fig. 5-68. Packets sent from A to C exit AS1
at the top router, R1a. Packets sent from B exit via the bottom router, R1b. The
reason is that both A and B are taking the lowest-cost path or quickest route out of
AS1. Because they are located in different parts of the ISP, the quickest exit for
each one is different. The same thing happens as the packets pass through AS2.
On the last leg, AS3 has to carry the packet from B through its own network.


---

<a id="page-496"></a>

<!-- Page 496 of 888 -->

484 THE NETWORK LAYER CHAP. 5
This strategy is known as early exit or hot-potato routing. It has the curious
side effect of tending to make routes asymmetric. For example, consider the path
taken when C sends a packet back to B. The packet will exit AS3 quickly, at the
top router, to avoid wasting its resources. Similarly, it will stay at the top when
AS2 passes it to AS1 as quickly as possible. Then the packet will have a longer
journey in AS1. This is a mirror image of the path taken from B to C.
The above discussion should make clear that each BGP router chooses its own
best route from the known possibilities. It is not the case, as might naively be ex-
pected, that BGP chooses a path to follow at the AS level and OSPF chooses
paths within each of the ASes. BGP and the interior gateway protocol are
integrated much more deeply. This means that, for example, BGP can find the
best exit point from one ISP to the next and this point will vary across the ISP, as
in the case of the hot-potato policy. It also means that BGP routers in different
parts of one AS may choose different AS paths to reach the same destination.
Care must be exercised by the ISP to configure all of the BGP routers to make
compatible choices given all of this freedom, but this can be done in practice.
Amazingly, we have only scratched the surface of BGP. For more infor-
mation, see the BGP version 4 specification in RFC 4271 and related RFCs.
However, realize that much of its complexity lies with policies, which are not de-
scribed in the specification of the BGP protocol.
#### 5.6.8 Internet Multicasting
Normal IP communication is between one sender and one receiver. However,
for some applications, it is useful for a process to be able to send to a large num-
ber of receivers simultaneously. Examples are streaming a live sports event to
many viewers, delivering program updates to a pool of replicated servers, and
handling digital conference (i.e., multiparty) telephone calls.
IP supports one-to-many communication, or multicasting, using class D IP ad-
dresses. Each class D address identifies a group of hosts. Twenty-eight bits are
available for identifying groups, so over 250 million groups can exist at the same
time. When a process sends a packet to a class D address, a best-effort attempt is
made to deliver it to all the members of the group addressed, but no guarantees
are given. Some members may not get the packet.
The range of IP addresses 224.0.0.0/24 is reserved for multicast on the local
network. In this case, no routing protocol is needed. The packets are multicast by
simply broadcasting them on the LAN with a multicast address. All hosts on the
LAN receive the broadcasts, and hosts that are members of the group process the
packet. Routers do not forward the packet off the LAN. Some examples of local
multicast addresses are:
##### 224.0.0.1 All systems on a LAN
##### 224.0.0.2 All routers on a LAN
##### 224.0.0.5 All OSPF routers on a LAN
##### 224.0.0.251 All DNS servers on a LAN


---

<a id="page-497"></a>

<!-- Page 497 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 485
Other multicast addresses may have members on different networks. In this
case, a routing protocol is needed. But first the multicast routers need to know
which hosts are members of a group. A process asks its host to join in a specific
group. It can also ask its host to leave the group. Each host keeps track of which
groups its processes currently belong to. When the last process on a host leaves a
group, the host is no longer a member of that group. About once a minute, each
multicast router sends a query packet to all the hosts on its LAN (using the local
multicast address of 224.0.0.1, of course) asking them to report back on the
groups to which they currently belong. The multicast routers may or may not be
colocated with the standard routers. Each host sends back responses for all the
class D addresses it is interested in. These query and response packets use a pro-
tocol called IGMP (Internet Group Management Protocol). It is described in
RFC 3376.
Any of several multicast routing protocols may be used to build multicast
spanning trees that give paths from senders to all of the members of the group.
The algorithms that are used are the ones we described in Sec. 5.2.8. Within an
AS, the main protocol used is PIM (Protocol Independent Multicast). PIM
comes in several flavors. In Dense Mode PIM, a pruned reverse path forwarding
tree is created. This is suited to situations in which members are everywhere in
the network, such as distributing files to many servers within a data center net-
work. In Sparse Mode PIM, spanning trees that are built are similar to core-based
trees. This is suited to situations such as a content provider multicasting TV to
subscribers on its IP network. A variant of this design, called Source-Specific
Multicast PIM, is optimized for the case that there is only one sender to the group.
Finally, multicast extensions to BGP or tunnels need to be used to create multicast
routes when the group members are in more than one AS.
#### 5.6.9 Mobile IP
Many users of the Internet have mobile computers and want to stay connected
when they are away from home and even on the road in between. Unfortunately,
the IP addressing system makes working far from home easier said than done, as
we will describe shortly. When people began demanding the ability anyway,
IETF set up a Working Group to find a solution. The Working Group quickly for-
mulated a number of goals considered desirable in any solution. The major ones
were:
1. Each mobile host must be able to use its home IP address anywhere.
2. Software changes to the fixed hosts were not permitted.
3. Changes to the router software and tables were not permitted.
4. Most packets for mobile hosts should not make detours on the way.
5. No overhead should be incurred when a mobile host is at home.


---

<a id="page-498"></a>

<!-- Page 498 of 888 -->

486 THE NETWORK LAYER CHAP. 5
The solution chosen was the one described in Sec. 5.2.10. In brief, every site
that wants to allow its users to roam has to create a helper at the site called a
home agent. When a mobile host shows up at a foreign site, it obtains a new IP
address (called a care-of address) at the foreign site. The mobile then tells the
home agent where it is now by giving it the care-of address. When a packet for
the mobile arrives at the home site and the mobile is elsewhere, the home agent
grabs the packet and tunnels it to the mobile at the current care-of address. The
mobile can send reply packets directly to whoever it is communicating with, but
still using its home address as the source address. This solution meets all the re-
quirements stated above except that packets for mobile hosts do make detours.
Now that we have covered the network layer of the Internet, we can go into
the solution in more detail. The need for mobility support in the first place comes
from the IP addressing scheme itself. Every IP address contains a network num-
ber and a host number. For example, consider the machine with IP address
160.80.40.20/16. The 160.80 gives the network number; the 40.20 is the host
number. Routers all over the world have routing tables telling which link to use to
get to network 160.80. Whenever a packet comes in with a destination IP address
of the form 160.80.xxx.yyy, it goes out on that line. If all of a sudden, the ma-
chine with that address is carted off to some distant site, the packets for it will
continue to be routed to its home LAN (or router).
At this stage, there are two options-both unattractive. The first is that we
could create a route to a more specific prefix. That is, if the distant site advertises
a route to 160.80.40.20/32, packets sent to the destination will start arriving in the
right place again. This option depends on the longest matching prefix algorithm
that is used at routers. However, we have added a route to an IP prefix with a sin-
gle IP address in it. All ISPs in the world will learn about this prefix. If everyone
changes global IP routes in this way when they move their computer, each router
would have millions of table entries, at astronomical cost to the Internet. This
option is not workable.
The second option is to change the IP address of the mobile. True, packets
sent to the home IP address will no longer be delivered until all the relevant peo-
ple, programs, and databases are informed of the change. But the mobile can still
use the Internet at the new location to browse the Web and run other applications.
This option handles mobility at a higher layer. It is what typically happens when a
user takes a laptop to a coffee store and uses the Internet via the local wireless
network. The disadvantage is that it breaks some applications, and it does not
keep connectivity as the mobile moves around.
As an aside, mobility can also be handled at a lower layer, the link layer. This
is what happens when using a laptop on a single 802.11 wireless network. The IP
address of the mobile does not change and the network path remains the same. It
is the wireless link that is providing mobility. However, the degree of mobility is
limited. If the laptop moves too far, it will have to connect to the Internet via an-
other network with a different IP address.


---

<a id="page-499"></a>

<!-- Page 499 of 888 -->

SEC. 5.6 THE NETWORK LAYER IN THE INTERNET 487
The mobile IP solution for IPv4 is given in RFC 3344. It works with the
existing Internet routing and allows hosts to stay connected with their own IP ad-
dresses as they move about. For it to work, the mobile must be able to discover
when it has moved. This is accomplished with ICMP router advertisement and
solicitation messages. Mobiles listen for periodic router advertisements or send a
solicitation to discover the nearest router. If this router is not the usual address of
the router when the mobile is at home, it must be on a foreign network. If this
router has changed since last time, the mobile has moved to another foreign net-
work. This same mechanism lets mobile hosts find their home agents.
To get a care-of IP address on the foreign network, a mobile can simply use
DHCP. Alternatively, if IPv4 addresses are in short supply, the mobile can send
and receive packets via a foreign agent that already has an IP address on the net-
work. The mobile host finds a foreign agent using the same ICMP mechanism
used to find the home agent. After the mobile obtains an IP address or finds a for-
eign agent, it is able to use the network to send a message to its home agent,
informing the home agent of its current location.
The home agent needs a way to intercept packets sent to the mobile only
when the mobile is not at home. ARP provides a convenient mechanism. To send
a packet over an Ethernet to an IP host, the router needs to know the Ethernet ad-
dress of the host. The usual mechanism is for the router to send an ARP query to
ask, for example, what is the Ethernet address of 160.80.40.20. When the mobile
is at home, it answers ARP queries for its IP address with its own Ethernet ad-
dress. When the mobile is away, the home agent responds to this query by giving
its Ethernet address. The router then sends packets for 160.80.40.20 to the home
agent. Recall that this is called a proxy ARP.
To quickly update ARP mappings back and forth when the mobile leaves
home or arrives back home, another ARP technique called a gratuitous ARP can
be used. Basically, the mobile or home agent send themselves an ARP query for
the mobile IP address that supplies the right answer so that the router notices and
updates its mapping.
Tunneling to send a packet between the home agent and the mobile host at the
care-of address is done by encapsulating the packet with another IP header des-
tined for the care-of address. When the encapsulated packet arrives at the care-of
address, the outer IP header is removed to reveal the packet.
As with many Internet protocols, the devil is in the details, and most often the
details of compatibility with other protocols that are deployed. There are two
complications. First, NAT boxes depend on peeking past the IP header to look at
the TCP or UDP header. The original form of tunneling for mobile IP did not use
these headers, so it did not work with NAT boxes. The solution was to change the
encapsulation to include a UDP header.
The second complication is that some ISPs check the source IP addresses of
packets to see that they match where the routing protocol believes the source
should be located. This technique is called ingress filtering, and it is a security


---

<a id="page-500"></a>

<!-- Page 500 of 888 -->

488 THE NETWORK LAYER CHAP. 5
measure intended to discard traffic with seemingly incorrect addresses that may
be malicious. However, packets sent from the mobile to other Internet hosts when
it is on a foreign network will have a source IP address that is out of place, so they
will be discarded. To get around this problem, the mobile can use the care-of ad-
dress as a source to tunnel the packets back to the home agent. From here, they
are sent into the Internet from what appears to be the right location. The cost is
that the route is more roundabout.
Another issue we have not discussed is security. When a home agent gets a
message asking it to please forward all of Roberta's packets to some IP address, it
had better not comply unless it is convinced that Roberta is the source of this re-
quest, and not somebody trying to impersonate her. Cryptographic authentication
protocols are used for this purpose. We will study such protocols in Chap. 8.
Mobility protocols for IPv6 build on the IPv4 foundation. The scheme above
suffers from the triangle routing problem in which packets sent to the mobile take
a dogleg through a distant home agent. In IPv6, route optimization is used to fol-
low a direct path between the mobile and other IP addresses after the initial pack-
ets have followed the long route. Mobile IPv6 is defined in RFC 3775.
There is another kind of mobility that is also being defined for the Internet.
Some airplanes have built-in wireless networking that passengers can use to con-
nect their laptops to the Internet. The plane has a router that connects to the rest
of the Internet via a wireless link. (Did you expect a wired link?) So now we
have a flying router, which means that the whole network is mobile. Network
mobility designs support this situation without the laptops realizing that the plane
is mobile. As far as they are concerned, it is just another network. Of course,
some of the laptops may be using mobile IP to keep their home addresses while
they are on the plane, so we have two levels of mobility. Network mobility is de-
fined for IPv6 in RFC 3963.
### 5.7 SUMMARY
The network layer provides services to the transport layer. It can be based on
either datagrams or virtual circuits. In both cases, its main job is routing packets
from the source to the destination. In datagram networks, a routing decision is
made on every packet. In virtual-circuit networks, it is made when the virtual cir-
cuit is set up.
Many routing algorithms are used in computer networks. Flooding is a simple
algorithm to send a packet along all paths. Most algorithms find the shortest path
and adapt to changes in the network topology. The main algorithms are distance
vector routing and link state routing. Most actual networks use one of these.
Other important routing topics are the use of hierarchy in large networks, routing
for mobile hosts, and broadcast, multicast, and anycast routing.


---

<a id="page-501"></a>

<!-- Page 501 of 888 -->

SEC. 5.7 SUMMARY 489
Networks can easily become congested, leading to increased delay and lost
packets. Network designers attempt to avoid congestion by designing the network
to have enough capacity, choosing uncongested routes, refusing to accept more
traffic, signaling sources to slow down, and shedding load.
The next step beyond just dealing with congestion is to actually try to achieve
a promised quality of service. Some applications care more about throughput
whereas others care more about delay and jitter. The methods that can be used to
provide different qualities of service include a combination of traffic shaping,
reserving resources at routers, and admission control. Approaches that have been
designed for good quality of service include IETF integrated services (including
RSVP) and differentiated services.
Networks differ in various ways, so when multiple networks are intercon-
nected, problems can occur. When different networks have different maximum
packet sizes, fragmentation may be needed. Different networks may run different
routing protocols internally but need to run a common protocol externally. Some-
times the problems can be finessed by tunneling a packet through a hostile net-
work, but if the source and destination networks are different, this approach fails.
The Internet has a rich variety of protocols related to the network layer.
These include the datagram protocol, IP, and associated control protocols such as
ICMP, ARP, and DHCP. A connection-oriented protocol called MPLS carries IP
packets across some networks. One of the main routing protocols used within net-
works is OSPF, and the routing protocol used across networks is BGP. The Inter-
net is rapidly running out of IP addresses, so a new version of IP, IPv6, has been
developed and is ever-so-slowly being deployed.
PROBLEMS
1. Give two example computer applications for which connection-oriented service is ap-
propriate. Now give two examples for which connectionless service is best.
2. Datagram networks route each packet as a separate unit, independent of all others.
Virtual-circuit networks do not have to do this, since each data packet follows a prede-
termined route. Does this observation mean that virtual-circuit networks do not need
the capability to route isolated packets from an arbitrary source to an arbitrary destina-
tion? Explain your answer.
3. Give three examples of protocol parameters that might be negotiated when a con-
nection is set up.
4. Assuming that all routers and hosts are working properly and that all software in both
is free of all errors, is there any chance, however small, that a packet will be delivered
to the wrong destination?


---

<a id="page-502"></a>

<!-- Page 502 of 888 -->

490 THE NETWORK LAYER CHAP. 5
5. Give a simple heuristic for finding two paths through a network from a given source to
a given destination that can survive the loss of any communication line (assuming two
such paths exist). The routers are considered reliable enough, so it is not necessary to
worry about the possibility of router crashes.
6. Consider the network of Fig. 5-12(a). Distance vector routing is used, and the follow-
ing vectors have just come in to router C: from B: (5, 0, 8, 12, 6, 2); from D: (16, 12,
6, 0, 9, 10); and from E: (7, 6, 3, 9, 0, 4). The cost of the links from C to B, D, and E,
are 6, 3, and 5, respectively. What is C's new routing table? Give both the outgoing
line to use and the cost.
7. If costs are recorded as 8-bit numbers in a 50-router network, and distance vectors are
exchanged twice a second, how much bandwidth per (full-duplex) line is chewed up
by the distributed routing algorithm? Assume that each router has three lines to other
routers.
8. In Fig. 5-13 the Boolean OR of the two sets of ACF bits are 111 in every row. Is this
just an accident here, or does it hold for all networks under all circumstances?
9. For hierarchical routing with 4800 routers, what region and cluster sizes should be
chosen to minimize the size of the routing table for a three-layer hierarchy? A good
starting place is the hypothesis that a solution with k clusters of k regions of k routers
is close to optimal, which means that k is about the cube root of 4800 (around 16).
Use trial and error to check out combinations where all three parameters are in the
general vicinity of 16.
10. In the text it was stated that when a mobile host is not at home, packets sent to its
home LAN are intercepted by its home agent on that LAN. For an IP network on an
### 802.3 LAN, how does the home agent accomplish this interception?
11. Looking at the network of Fig. 5-6, how many packets are generated by a broadcast
from B, using
(a) reverse path forwarding?
(b) the sink tree?
12. Consider the network of Fig. 5-15(a). Imagine that one new line is added, between F
and G, but the sink tree of Fig. 5-15(b) remains unchanged. What changes occur to
Fig. 5-15(c)?
13. Compute a multicast spanning tree for router C in the following network for a group
with members at routers A, B, C, D, E, F, I, and K.

B
F

A
E
K
G J
H



---

<a id="page-503"></a>

<!-- Page 503 of 888 -->

CHAP. 5 PROBLEMS 491
14. Suppose that node B in Fig. 5-20 has just rebooted and has no routing information in
its tables. It suddenly needs a route to H. It sends out broadcasts with TtL set to 1, 2,
3, and so on. How many rounds does it take to find a route?
15. As a possible congestion control mechanism in a network using virtual circuits inter-
nally, a router could refrain from acknowledging a received packet until (1) it knows
its last transmission along the virtual circuit was received successfully and (2) it has a
free buffer. For simplicity, assume that the routers use a stop-and-wait protocol and
that each virtual circuit has one buffer dedicated to it for each direction of traffic. If it
takes T sec to transmit a packet (data or acknowledgement) and there are n routers on
the path, what is the rate at which packets are delivered to the destination host? As-
sume that transmission errors are rare and that the host-router connection is infinitely
fast.
16. A datagram network allows routers to drop packets whenever they need to. The
probability of a router discarding a packet is p. Consider the case of a source host
connected to the source router, which is connected to the destination router, and then
to the destination host. If either of the routers discards a packet, the source host even-
tually times out and tries again. If both host-router and router-router lines are counted
as hops, what is the mean number of
(a) hops a packet makes per transmission?
(b) transmissions a packet makes?
(c) hops required per received packet?
17. Describe two major differences between the ECN method and the RED method of
congestion avoidance.
18. A token bucket scheme is used for traffic shaping. A new token is put into the bucket
every 5 µsec. Each token is good for one short packet, which contains 48 bytes of
data. What is the maximum sustainable data rate?
19. A computer on a 6-Mbps network is regulated by a token bucket. The token bucket is
filled at a rate of 1 Mbps. It is initially filled to capacity with 8 megabits. How long
can the computer transmit at the full 6 Mbps?
20. The network of Fig. 5-34 uses RSVP with multicast trees for hosts 1 and 2 as shown.
Suppose that host 3 requests a channel of bandwidth 2 MB/sec for a flow from host 1
and another channel of bandwidth 1 MB/sec for a flow from host 2. At the same time,
host 4 requests a channel of bandwidth 2 MB/sec for a flow from host 1 and host 5 re-
quests a channel of bandwidth 1 MB/sec for a flow from host 2. How much total
bandwidth will be reserved for these requests at routers A, B, C, E, H, J, K, and L?
21. A router can process 2 million packets/sec. The load offered to it is 1.5 million pack-
ets/sec on average. If a route from source to destination contains 10 routers, how
much time is spent being queued and serviced by the router?
22. Consider the user of differentiated services with expedited forwarding. Is there a
guarantee that expedited packets experience a shorter delay than regular packets?
Why or why not?


---

<a id="page-504"></a>

<!-- Page 504 of 888 -->

492 THE NETWORK LAYER CHAP. 5
23. Suppose that host A is connected to a router R 1, R 1 is connected to another router,
R 2, and R 2 is connected to host B. Suppose that a TCP message that contains 900
bytes of data and 20 bytes of TCP header is passed to the IP code at host A for deliv-
ery to B. Show the Total length, Identification, DF, MF, and Fragment offset fields of
the IP header in each packet transmitted over the three links. Assume that link A-R1
can support a maximum frame size of 1024 bytes including a 14-byte frame header,
link R1-R2 can support a maximum frame size of 512 bytes, including an 8-byte frame
header, and link R2-B can support a maximum frame size of 512 bytes including a
12-byte frame header.
24. A router is blasting out IP packets whose total length (data plus header) is 1024 bytes.
Assuming that packets live for 10 sec, what is the maximum line speed the router can
operate at without danger of cycling through the IP datagram ID number space?
25. An IP datagram using the Strict source routing option has to be fragmented. Do you
think the option is copied into each fragment, or is it sufficient to just put it in the first
fragment? Explain your answer.
26. Suppose that instead of using 16 bits for the network part of a class B address origi-
nally, 20 bits had been used. How many class B networks would there have been?
27. Convert the IP address whose hexadecimal representation is C22F1582 to dotted
decimal notation.
28. A network on the Internet has a subnet mask of 255.255.240.0. What is the maximum
number of hosts it can handle?
29. While IP addresses are tried to specific networks, Ethernet addresses are not. Can you
think of a good reason why they are not?
30. A large number of consecutive IP addresses are available starting at 198.16.0.0. Sup-
pose that four organizations, A, B, C, and D, request 4000, 2000, 4000, and 8000 ad-
dresses, respectively, and in that order. For each of these, give the first IP address as-
signed, the last IP address assigned, and the mask in the w.x.y.z/s notation.
31. A router has just received the following new IP addresses: 57.6.96.0/21,
57.6.104.0/21, 57.6.112.0/21, and 57.6.120.0/21. If all of them use the same outgoing
line, can they be aggregated? If so, to what? If not, why not?
32. The set of IP addresses from 29.18.0.0 to 19.18.128.255 has been aggregated to
29.18.0.0/17. However, there is a gap of 1024 unassigned addresses from 29.18.60.0
to 29.18.63.255 that are now suddenly assigned to a host using a different outgoing
line. Is it now necessary to split up the aggregate address into its constituent blocks,
add the new block to the table, and then see if any reaggregation is possible? If not,
what can be done instead?
33. A router has the following (CIDR) entries in its routing table:
Address/mask Next hop
135.46.56.0/22 Interface 0
135.46.60.0/22 Interface 1
192.53.40.0/23 Router 1
default Router 2


---

<a id="page-505"></a>

<!-- Page 505 of 888 -->

CHAP. 5 PROBLEMS 493
For each of the following IP addresses, what does the router do if a packet with that
address arrives?
(a) 135.46.63.10
(b) 135.46.57.14
(c) 135.46.52.2
(d) 192.53.40.7
(e) 192.53.56.7
34. Many companies have a policy of having two (or more) routers connecting the com-
pany to the Internet to provide some redundancy in case one of them goes down. Is
this policy still possible with NAT? Explain your answer.
35. You have just explained the ARP protocol to a friend. When you are all done, he
says: ''I've got it. ARP provides a service to the network layer, so it is part of the data
link layer.'' What do you say to him?
36. Describe a way to reassemble IP fragments at the destination.
37. Most IP datagram reassembly algorithms have a timer to avoid having a lost fragment
tie up reassembly buffers forever. Suppose that a datagram is fragmented into four
fragments. The first three fragments arrive, but the last one is delayed. Eventually,
the timer goes off and the three fragments in the receiver's memory are discarded. A
little later, the last fragment stumbles in. What should be done with it?
38. In IP, the checksum covers only the header and not the data. Why do you suppose this
design was chosen?
39. A person who lives in Boston travels to Minneapolis, taking her portable computer
with her. To her surprise, the LAN at her destination in Minneapolis is a wireless IP
LAN, so she does not have to plug in. Is it still necessary to go through the entire bus-
iness with home agents and foreign agents to make email and other traffic arrive cor-
rectly?
40. IPv6 uses 16-byte addresses. If a block of 1 million addresses is allocated every
picosecond, how long will the addresses last?
41. The Protocol field used in the IPv4 header is not present in the fixed IPv6 header.
Why not?
42. When the IPv6 protocol is introduced, does the ARP protocol have to be changed? If
so, are the changes conceptual or technical?
43. Write a program to simulate routing using flooding. Each packet should contain a
counter that is decremented on each hop. When the counter gets to zero, the packet is
discarded. Time is discrete, with each line handling one packet per time interval.
Make three versions of the program: all lines are flooded, all lines except the input
line are flooded, and only the (statically chosen) best k lines are flooded. Compare
flooding with deterministic routing (k = 1) in terms of both delay and the bandwidth
used.
44. Write a program that simulates a computer network using discrete time. The first
packet on each router queue makes one hop per time interval. Each router has only a
finite number of buffers. If a packet arrives and there is no room for it, it is discarded


---

<a id="page-506"></a>

<!-- Page 506 of 888 -->

494 THE NETWORK LAYER CHAP. 5
and not retransmitted. Instead, there is an end-to-end protocol, complete with time-
outs and acknowledgement packets, that eventually regenerates the packet from the
source router. Plot the throughput of the network as a function of the end-to-end time-
out interval, parameterized by error rate.
45. Write a function to do forwarding in an IP router. The procedure has one parameter,
an IP address. It also has access to a global table consisting of an array of triples.
Each triple contains three integers: an IP address, a subnet mask, and the outline line
to use. The function looks up the IP address in the table using CIDR and returns the
line to use as its value.
46. Use the traceroute (UNIX) or tracert (Windows) programs to trace the route from
your computer to various universities on other continents. Make a list of transoceanic
links you have discovered. Some sites to try are
www.berkeley.edu (California)
www.mit.edu (Massachusetts)
www.vu.nl (Amsterdam)
www.ucl.ac.uk (London)
www.usyd.edu.au (Sydney)
www.u-tokyo.ac.jp (Tokyo)
www.uct.ac.za (Cape Town)
