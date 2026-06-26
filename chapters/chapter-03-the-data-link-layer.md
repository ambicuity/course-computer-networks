# Chapter 3: The Data Link Layer

_Source: printed pages 193-256; extracted PDF pages 205-268._

---

<a id="page-205"></a>

<!-- Page 205 of 888 -->

## The Data Link Layer
In this chapter we will study the design principles for the second layer in our
model, the data link layer. This study deals with algorithms for achieving re-
liable, efficient communication of whole units of information called frames (rath-
er than individual bits, as in the physical layer) between two adjacent machines.
By adjacent, we mean that the two machines are connected by a communication
channel that acts conceptually like a wire (e.g., a coaxial cable, telephone line, or
wireless channel). The essential property of a channel that makes it ''wire-like''
is that the bits are delivered in exactly the same order in which they are sent.
At first you might think this problem is so trivial that there is nothing to
study-machine A just puts the bits on the wire, and machine B just takes them
off. Unfortunately, communication channels make errors occasionally. Fur-
thermore, they have only a finite data rate, and there is a nonzero propagation
delay between the time a bit is sent and the time it is received. These limitations
have important implications for the efficiency of the data transfer. The protocols
used for communications must take all these factors into consideration. These
protocols are the subject of this chapter.
After an introduction to the key design issues present in the data link layer, we
will start our study of its protocols by looking at the nature of errors and how they
can be detected and corrected. Then we will study a series of increasingly com-
plex protocols, each one solving more and more of the problems present in this
layer. Finally, we will conclude with some examples of data link protocols.



---

<a id="page-206"></a>

<!-- Page 206 of 888 -->

194 THE DATA LINK LAYER CHAP. 3
### 3.1 DATA LINK LAYER DESIGN ISSUES
The data link layer uses the services of the physical layer to send and receive
bits over communication channels. It has a number of functions, including:
1. Providing a well-defined service interface to the network layer.
2. Dealing with transmission errors.
3. Regulating the flow of data so that slow receivers are not swamped
by fast senders.
To accomplish these goals, the data link layer takes the packets it gets from the
network layer and encapsulates them into frames for transmission. Each frame
contains a frame header, a payload field for holding the packet, and a frame
trailer, as illustrated in Fig. 3-1. Frame management forms the heart of what the
data link layer does. In the following sections we will examine all the above-
mentioned issues in detail.
Sending machine Receiving machine
Packet Packet
Frame
Header Payload field Trailer Header Payload field Trailer
Figure 3-1. Relationship between packets and frames.
Although this chapter is explicitly about the data link layer and its protocols,
many of the principles we will study here, such as error control and flow control,
are found in transport and other protocols as well. That is because reliability is an
overall goal, and it is achieved when all the layers work together. In fact, in many
networks, these functions are found mostly in the upper layers, with the data link
layer doing the minimal job that is ''good enough.'' However, no matter where
they are found, the principles are pretty much the same. They often show up in
their simplest and purest forms in the data link layer, making this a good place to
examine them in detail.
#### 3.1.1 Services Provided to the Network Layer
The function of the data link layer is to provide services to the network layer.
The principal service is transferring data from the network layer on the source ma-
chine to the network layer on the destination machine. On the source machine is


---

<a id="page-207"></a>

<!-- Page 207 of 888 -->

SEC. 3.1 DATA LINK LAYER DESIGN ISSUES 195
an entity, call it a process, in the network layer that hands some bits to the data
link layer for transmission to the destination. The job of the data link layer is to
transmit the bits to the destination machine so they can be handed over to the net-
work layer there, as shown in Fig. 3-2(a). The actual transmission follows the
path of Fig. 3-2(b), but it is easier to think in terms of two data link layer proc-
esses communicating using a data link protocol. For this reason, we will impli-
citly use the model of Fig. 3-2(a) throughout this chapter.
Host 1 Host 2 Host 1 Host 2
4 4 4 4
3 3 3 3
Virtual
data path
2 2 2 2
1 1 1 1
Actual
data path
(a) (b)
Figure 3-2. (a) Virtual communication. (b) Actual communication.
The data link layer can be designed to offer various services. The actual ser-
vices that are offered vary from protocol to protocol. Three reasonable possibili-
ties that we will consider in turn are:
1. Unacknowledged connectionless service.
2. Acknowledged connectionless service.
3. Acknowledged connection-oriented service.
Unacknowledged connectionless service consists of having the source ma-
chine send independent frames to the destination machine without having the
destination machine acknowledge them. Ethernet is a good example of a data link
layer that provides this class of service. No logical connection is established be-
forehand or released afterward. If a frame is lost due to noise on the line, no


---

<a id="page-208"></a>

<!-- Page 208 of 888 -->

196 THE DATA LINK LAYER CHAP. 3
attempt is made to detect the loss or recover from it in the data link layer. This
class of service is appropriate when the error rate is very low, so recovery is left
to higher layers. It is also appropriate for real-time traffic, such as voice, in which
late data are worse than bad data.
The next step up in terms of reliability is acknowledged connectionless ser-
vice. When this service is offered, there are still no logical connections used, but
each frame sent is individually acknowledged. In this way, the sender knows
whether a frame has arrived correctly or been lost. If it has not arrived within a
specified time interval, it can be sent again. This service is useful over unreliable
channels, such as wireless systems. 802.11 (WiFi) is a good example of this class
of service.
It is perhaps worth emphasizing that providing acknowledgements in the data
link layer is just an optimization, never a requirement. The network layer can al-
ways send a packet and wait for it to be acknowledged by its peer on the remote
machine. If the acknowledgement is not forthcoming before the timer expires, the
sender can just send the entire message again. The trouble with this strategy is
that it can be inefficient. Links usually have a strict maximum frame length
imposed by the hardware, and known propagation delays. The network layer does
not know these parameters. It might send a large packet that is broken up into,
say, 10 frames, of which 2 are lost on average. It would then take a very long time
for the packet to get through. Instead, if individual frames are acknowledged and
retransmitted, then errors can be corrected more directly and more quickly. On
reliable channels, such as fiber, the overhead of a heavyweight data link protocol
may be unnecessary, but on (inherently unreliable) wireless channels it is well
worth the cost.
Getting back to our services, the most sophisticated service the data link layer
can provide to the network layer is connection-oriented service. With this service,
the source and destination machines establish a connection before any data are
transferred. Each frame sent over the connection is numbered, and the data link
layer guarantees that each frame sent is indeed received. Furthermore, it guaran-
tees that each frame is received exactly once and that all frames are received in
the right order. Connection-oriented service thus provides the network layer proc-
esses with the equivalent of a reliable bit stream. It is appropriate over long, unre-
liable links such as a satellite channel or a long-distance telephone circuit. If
acknowledged connectionless service were used, it is conceivable that lost ac-
knowledgements could cause a frame to be sent and received several times, wast-
ing bandwidth.
When connection-oriented service is used, transfers go through three distinct
phases. In the first phase, the connection is established by having both sides ini-
tialize variables and counters needed to keep track of which frames have been re-
ceived and which ones have not. In the second phase, one or more frames are ac-
tually transmitted. In the third and final phase, the connection is released, freeing
up the variables, buffers, and other resources used to maintain the connection.


---

<a id="page-209"></a>

<!-- Page 209 of 888 -->

SEC. 3.1 DATA LINK LAYER DESIGN ISSUES 197
#### 3.1.2 Framing
To provide service to the network layer, the data link layer must use the ser-
vice provided to it by the physical layer. What the physical layer does is accept a
raw bit stream and attempt to deliver it to the destination. If the channel is noisy,
as it is for most wireless and some wired links, the physical layer will add some
redundancy to its signals to reduce the bit error rate to a tolerable level. However,
the bit stream received by the data link layer is not guaranteed to be error free.
Some bits may have different values and the number of bits received may be less
than, equal to, or more than the number of bits transmitted. It is up to the data
link layer to detect and, if necessary, correct errors.
The usual approach is for the data link layer to break up the bit stream into
discrete frames, compute a short token called a checksum for each frame, and in-
clude the checksum in the frame when it is transmitted. (Checksum algorithms
will be discussed later in this chapter.) When a frame arrives at the destination,
the checksum is recomputed. If the newly computed checksum is different from
the one contained in the frame, the data link layer knows that an error has oc-
curred and takes steps to deal with it (e.g., discarding the bad frame and possibly
also sending back an error report).
Breaking up the bit stream into frames is more difficult than it at first appears.
A good design must make it easy for a receiver to find the start of new frames
while using little of the channel bandwidth. We will look at four methods:
1. Byte count.
2. Flag bytes with byte stuffing.
3. Flag bits with bit stuffing.
4. Physical layer coding violations.
The first framing method uses a field in the header to specify the number of
bytes in the frame. When the data link layer at the destination sees the byte count,
it knows how many bytes follow and hence where the end of the frame is. This
technique is shown in Fig. 3-3(a) for four small example frames of sizes 5, 5, 8,
and 8 bytes, respectively.
The trouble with this algorithm is that the count can be garbled by a transmis-
sion error. For example, if the byte count of 5 in the second frame of Fig. 3-3(b)
becomes a 7 due to a single bit flip, the destination will get out of synchroniza-
tion. It will then be unable to locate the correct start of the next frame. Even if the
checksum is incorrect so the destination knows that the frame is bad, it still has no
way of telling where the next frame starts. Sending a frame back to the source
asking for a retransmission does not help either, since the destination does not
know how many bytes to skip over to get to the start of the retransmission. For
this reason, the byte count method is rarely used by itself.


---

<a id="page-210"></a>

<!-- Page 210 of 888 -->

198 THE DATA LINK LAYER CHAP. 3
Byte count One byte
5 1 2 3 4 5 6 7 8 9 8 0 1 2 3 4 5 6 8 7 8 9 0 1 2 3
Frame 1 Frame 2 Frame 3 Frame 4
5 bytes 5 bytes 8 bytes 8 bytes
(a)
Error
5 1 2 3 4 7 6 7 8 9 8 0 1 2 3 4 5 6 8 7 8 9 0 1 2 3
Frame 1 Frame 2 Now a byte
(Wrong) count
(b)
Figure 3-3. A byte stream. (a) Without errors. (b) With one error.
The second framing method gets around the problem of resynchronization
after an error by having each frame start and end with special bytes. Often the
same byte, called a flag byte, is used as both the starting and ending delimiter.
This byte is shown in Fig. 3-4(a) as FLAG. Two consecutive flag bytes indicate
the end of one frame and the start of the next. Thus, if the receiver ever loses syn-
chronization it can just search for two flag bytes to find the end of the current
frame and the start of the next frame.
However, there is a still a problem we have to solve. It may happen that the
flag byte occurs in the data, especially when binary data such as photographs or
songs are being transmitted. This situation would interfere with the framing. One
way to solve this problem is to have the sender's data link layer insert a special
escape byte (ESC) just before each ''accidental'' flag byte in the data. Thus, a
framing flag byte can be distinguished from one in the data by the absence or
presence of an escape byte before it. The data link layer on the receiving end re-
moves the escape bytes before giving the data to the network layer. This techni-
que is called byte stuffing.
Of course, the next question is: what happens if an escape byte occurs in the
middle of the data? The answer is that it, too, is stuffed with an escape byte. At
the receiver, the first escape byte is removed, leaving the data byte that follows it
(which might be another escape byte or the flag byte). Some examples are shown
in Fig. 3-4(b). In all cases, the byte sequence delivered after destuffing is exactly
the same as the original byte sequence. We can still search for a frame boundary
by looking for two flag bytes in a row, without bothering to undo escapes.
The byte-stuffing scheme depicted in Fig. 3-4 is a slight simplification of the
one used in PPP (Point-to-Point Protocol), which is used to carry packets over
communications links. We will discuss PPP near the end of this chapter.


---

<a id="page-211"></a>

<!-- Page 211 of 888 -->

SEC. 3.1 DATA LINK LAYER DESIGN ISSUES 199
FLAG Header Payload field Trailer FLAG
(a)
Original bytes After stuffing
## A Flag B A Esc Flag B
## A Esc B A Esc Esc B
## A Esc Flag B A Esc Esc Esc Flag B
## A Esc Esc B A Esc Esc Esc Esc B
(b)
Figure 3-4. (a) A frame delimited by flag bytes. (b) Four examples of byte se-
quences before and after byte stuffing.
The third method of delimiting the bit stream gets around a disadvantage of
byte stuffing, which is that it is tied to the use of 8-bit bytes. Framing can be also
be done at the bit level, so frames can contain an arbitrary number of bits made up
of units of any size. It was developed for the once very popular HDLC (High-
level Data Link Control) protocol. Each frame begins and ends with a special
bit pattern, 01111110 or 0x7E in hexadecimal. This pattern is a flag byte. When-
ever the sender's data link layer encounters five consecutive 1s in the data, it
automatically stuffs a 0 bit into the outgoing bit stream. This bit stuffing is anal-
ogous to byte stuffing, in which an escape byte is stuffed into the outgoing charac-
ter stream before a flag byte in the data. It also ensures a minimum density of
transitions that help the physical layer maintain synchronization. USB (Universal
Serial Bus) uses bit stuffing for this reason.
When the receiver sees five consecutive incoming 1 bits, followed by a 0 bit,
it automatically destuffs (i.e., deletes) the 0 bit. Just as byte stuffing is completely
transparent to the network layer in both computers, so is bit stuffing. If the user
data contain the flag pattern, 01111110, this flag is transmitted as 011111010 but
stored in the receiver's memory as 01111110. Figure 3-5 gives an example of bit
stuffing.
With bit stuffing, the boundary between two frames can be unambiguously
recognized by the flag pattern. Thus, if the receiver loses track of where it is, all
it has to do is scan the input for flag sequences, since they can only occur at frame
boundaries and never within the data.


---

<a id="page-212"></a>

<!-- Page 212 of 888 -->

200 THE DATA LINK LAYER CHAP. 3
(a) 0 1 1 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 1 0
(b) 0 1 1 0 1 1 1 1 1 0 1 1 1 1 1 0 1 1 1 1 1 0 1 0 0 1 0
Stuffed bits
(c) 0 1 1 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 1 0
Figure 3-5. Bit stuffing. (a) The original data. (b) The data as they appear on
the line. (c) The data as they are stored in the receiver's memory after destuf-
fing.
With both bit and byte stuffing, a side effect is that the length of a frame now
depends on the contents of the data it carries. For instance, if there are no flag
bytes in the data, 100 bytes might be carried in a frame of roughly 100 bytes. If,
however, the data consists solely of flag bytes, each flag byte will be escaped and
the frame will become roughly 200 bytes long. With bit stuffing, the increase
would be roughly 12.5% as 1 bit is added to every byte.
The last method of framing is to use a shortcut from the physical layer. We
saw in Chap. 2 that the encoding of bits as signals often includes redundancy to
help the receiver. This redundancy means that some signals will not occur in reg-
ular data. For example, in the 4B/5B line code 4 data bits are mapped to 5 signal
bits to ensure sufficient bit transitions. This means that 16 out of the 32 signal
possibilities are not used. We can use some reserved signals to indicate the start
and end of frames. In effect, we are using ''coding violations'' to delimit frames.
The beauty of this scheme is that, because they are reserved signals, it is easy to
find the start and end of frames and there is no need to stuff the data.
Many data link protocols use a combination of these methods for safety. A
common pattern used for Ethernet and 802.11 is to have a frame begin with a
well-defined pattern called a preamble. This pattern might be quite long (72 bits
is typical for 802.11) to allow the receiver to prepare for an incoming packet. The
preamble is then followed by a length (i.e., count) field in the header that is used
to locate the end of the frame.
#### 3.1.3 Error Control
Having solved the problem of marking the start and end of each frame, we
come to the next problem: how to make sure all frames are eventually delivered to
the network layer at the destination and in the proper order. Assume for the
moment that the receiver can tell whether a frame that it receives contains correct
or faulty information (we will look at the codes that are used to detect and correct
transmission errors in Sec. 3.2). For unacknowledged connectionless service it
might be fine if the sender just kept outputting frames without regard to whether


---

<a id="page-213"></a>

<!-- Page 213 of 888 -->

SEC. 3.1 DATA LINK LAYER DESIGN ISSUES 201
they were arriving properly. But for reliable, connection-oriented service it would
not be fine at all.
The usual way to ensure reliable delivery is to provide the sender with some
feedback about what is happening at the other end of the line. Typically, the pro-
tocol calls for the receiver to send back special control frames bearing positive or
negative acknowledgements about the incoming frames. If the sender receives a
positive acknowledgement about a frame, it knows the frame has arrived safely.
On the other hand, a negative acknowledgement means that something has gone
wrong and the frame must be transmitted again.
An additional complication comes from the possibility that hardware troubles
may cause a frame to vanish completely (e.g., in a noise burst). In this case, the
receiver will not react at all, since it has no reason to react. Similarly, if the ac-
knowledgement frame is lost, the sender will not know how to proceed. It should
be clear that a protocol in which the sender transmits a frame and then waits for
an acknowledgement, positive or negative, will hang forever if a frame is ever lost
due to, for example, malfunctioning hardware or a faulty communication channel.
This possibility is dealt with by introducing timers into the data link layer.
When the sender transmits a frame, it generally also starts a timer. The timer is
set to expire after an interval long enough for the frame to reach the destination,
be processed there, and have the acknowledgement propagate back to the sender.
Normally, the frame will be correctly received and the acknowledgement will get
back before the timer runs out, in which case the timer will be canceled.
However, if either the frame or the acknowledgement is lost, the timer will go
off, alerting the sender to a potential problem. The obvious solution is to just
transmit the frame again. However, when frames may be transmitted multiple
times there is a danger that the receiver will accept the same frame two or more
times and pass it to the network layer more than once. To prevent this from hap-
pening, it is generally necessary to assign sequence numbers to outgoing frames,
so that the receiver can distinguish retransmissions from originals.
The whole issue of managing the timers and sequence numbers so as to ensure
that each frame is ultimately passed to the network layer at the destination exactly
once, no more and no less, is an important part of the duties of the data link layer
(and higher layers). Later in this chapter, we will look at a series of increasingly
sophisticated examples to see how this management is done.
#### 3.1.4 Flow Control
Another important design issue that occurs in the data link layer (and higher
layers as well) is what to do with a sender that systematically wants to transmit
frames faster than the receiver can accept them. This situation can occur when
the sender is running on a fast, powerful computer and the receiver is running on a
slow, low-end machine. A common situation is when a smart phone requests a
Web page from a far more powerful server, which then turns on the fire hose and


---

<a id="page-214"></a>

<!-- Page 214 of 888 -->

202 THE DATA LINK LAYER CHAP. 3
blasts the data at the poor helpless phone until it is completely swamped. Even if
the transmission is error free, the receiver may be unable to handle the frames as
fast as they arrive and will lose some.
Clearly, something has to be done to prevent this situation. Two approaches
are commonly used. In the first one, feedback-based flow control, the receiver
sends back information to the sender giving it permission to send more data, or at
least telling the sender how the receiver is doing. In the second one, rate-based
flow control, the protocol has a built-in mechanism that limits the rate at which
senders may transmit data, without using feedback from the receiver.
In this chapter we will study feedback-based flow control schemes, primarily
because rate-based schemes are only seen as part of the transport layer (Chap. 5).
Feedback-based schemes are seen at both the link layer and higher layers. The
latter is more common these days, in which case the link layer hardware is de-
signed to run fast enough that it does not cause loss. For example, hardware im-
plementations of the link layer as NICs (Network Interface Cards) are some-
times said to run at ''wire speed,'' meaning that they can handle frames as fast as
they can arrive on the link. Any overruns are then not a link problem, so they are
handled by higher layers.
Various feedback-based flow control schemes are known, but most of them
use the same basic principle. The protocol contains well-defined rules about
when a sender may transmit the next frame. These rules often prohibit frames
from being sent until the receiver has granted permission, either implicitly or ex-
plicitly. For example, when a connection is set up the receiver might say: ''You
may send me n frames now, but after they have been sent, do not send any more
until I have told you to continue.'' We will examine the details shortly.
### 3.2 ERROR DETECTION AND CORRECTION
We saw in Chap. 2 that communication channels have a range of charac-
teristics. Some channels, like optical fiber in telecommunications networks, have
tiny error rates so that transmission errors are a rare occurrence. But other chan-
nels, especially wireless links and aging local loops, have error rates that are ord-
ers of magnitude larger. For these links, transmission errors are the norm. They
cannot be avoided at a reasonable expense or cost in terms of performance. The
conclusion is that transmission errors are here to stay. We have to learn how to
deal with them.
Network designers have developed two basic strategies for dealing with er-
rors. Both add redundant information to the data that is sent. One strategy is to
include enough redundant information to enable the receiver to deduce what the
transmitted data must have been. The other is to include only enough redundancy
to allow the receiver to deduce that an error has occurred (but not which error)


---

<a id="page-215"></a>

<!-- Page 215 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 203
and have it request a retransmission. The former strategy uses error-correcting
codes and the latter uses error-detecting codes. The use of error-correcting
codes is often referred to as FEC (Forward Error Correction).
Each of these techniques occupies a different ecological niche. On channels
that are highly reliable, such as fiber, it is cheaper to use an error-detecting code
and just retransmit the occasional block found to be faulty. However, on channels
such as wireless links that make many errors, it is better to add redundancy to
each block so that the receiver is able to figure out what the originally transmitted
block was. FEC is used on noisy channels because retransmissions are just as
likely to be in error as the first transmission.
A key consideration for these codes is the type of errors that are likely to oc-
cur. Neither error-correcting codes nor error-detecting codes can handle all pos-
sible errors since the redundant bits that offer protection are as likely to be re-
ceived in error as the data bits (which can compromise their protection). It would
be nice if the channel treated redundant bits differently than data bits, but it does
not. They are all just bits to the channel. This means that to avoid undetected er-
rors the code must be strong enough to handle the expected errors.
One model is that errors are caused by extreme values of thermal noise that
overwhelm the signal briefly and occasionally, giving rise to isolated single-bit er-
rors. Another model is that errors tend to come in bursts rather than singly. This
model follows from the physical processes that generate them-such as a deep
fade on a wireless channel or transient electrical interference on a wired channel/
Both models matter in practice, and they have different trade-offs. Having the
errors come in bursts has both advantages and disadvantages over isolated single-
bit errors. On the advantage side, computer data are always sent in blocks of bits.
Suppose that the block size was 1000 bits and the error rate was 0.001 per bit. If
errors were independent, most blocks would contain an error. If the errors came
in bursts of 100, however, only one block in 100 would be affected, on average.
The disadvantage of burst errors is that when they do occur they are much harder
to correct than isolated errors.
Other types of errors also exist. Sometimes, the location of an error will be
known, perhaps because the physical layer received an analog signal that was far
from the expected value for a 0 or 1 and declared the bit to be lost. This situation
is called an erasure channel. It is easier to correct errors in erasure channels than
in channels that flip bits because even if the value of the bit has been lost, at least
we know which bit is in error. However, we often do not have the benefit of eras-
ures.
We will examine both error-correcting codes and error-detecting codes next.
Please keep two points in mind, though. First, we cover these codes in the link
layer because this is the first place that we have run up against the problem of reli-
ably transmitting groups of bits. However, the codes are widely used because
reliability is an overall concern. Error-correcting codes are also seen in the physi-
cal layer, particularly for noisy channels, and in higher layers, particularly for


---

<a id="page-216"></a>

<!-- Page 216 of 888 -->

204 THE DATA LINK LAYER CHAP. 3
real-time media and content distribution. Error-detecting codes are commonly
used in link, network, and transport layers.
The second point to bear in mind is that error codes are applied mathematics.
Unless you are particularly adept at Galois fields or the properties of sparse
matrices, you should get codes with good properties from a reliable source rather
than making up your own. In fact, this is what many protocol standards do, with
the same codes coming up again and again. In the material below, we will study a
simple code in detail and then briefly describe advanced codes. In this way, we
can understand the trade-offs from the simple code and talk about the codes that
are used in practice via the advanced codes.
#### 3.2.1 Error-Correcting Codes
We will examine four different error-correcting codes:
1. Hamming codes.
2. Binary convolutional codes.
3. Reed-Solomon codes.
4. Low-Density Parity Check codes.
All of these codes add redundancy to the information that is sent. A frame con-
sists of m data (i.e., message) bits and r redundant (i.e. check) bits. In a block
code, the r check bits are computed solely as a function of the m data bits with
which they are associated, as though the m bits were looked up in a large table to
find their corresponding r check bits. In a systematic code, the m data bits are
sent directly, along with the check bits, rather than being encoded themselves be-
fore they are sent. In a linear code, the r check bits are computed as a linear
function of the m data bits. Exclusive OR (XOR) or modulo 2 addition is a popu-
lar choice. This means that encoding can be done with operations such as matrix
multiplications or simple logic circuits. The codes we will look at in this section
are linear, systematic block codes unless otherwise noted.
Let the total length of a block be n (i.e., n = m + r). We will describe this as
an (n,m) code. An n-bit unit containing data and check bits is referred to as an n-
bit codeword. The code rate, or simply rate, is the fraction of the codeword that
carries information that is not redundant, or m/n. The rates used in practice vary
widely. They might be 1/2 for a noisy channel, in which case half of the received
information is redundant, or close to 1 for a high-quality channel, with only a
small number of check bits added to a large message.
To understand how errors can be handled, it is necessary to first look closely
at what an error really is. Given any two codewords that may be transmitted or
received-say, 10001001 and 10110001-it is possible to determine how many


---

<a id="page-217"></a>

<!-- Page 217 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 205
corresponding bits differ. In this case, 3 bits differ. To determine how many bits
differ, just XOR the two codewords and count the number of 1 bits in the result.
For example:

The number of bit positions in which two codewords differ is called the Ham-
ming distance (Hamming, 1950). Its significance is that if two codewords are a
Hamming distance d apart, it will require d single-bit errors to convert one into
the other.
Given the algorithm for computing the check bits, it is possible to construct a
complete list of the legal codewords, and from this list to find the two codewords
with the smallest Hamming distance. This distance is the Hamming distance of
the complete code.
In most data transmission applications, all 2m possible data messages are
legal, but due to the way the check bits are computed, not all of the 2n possible
codewords are used. In fact, when there are r check bits, only the small fraction
of 2m /2n or 1/2r of the possible messages will be legal codewords. It is the
sparseness with which the message is embedded in the space of codewords that al-
lows the receiver to detect and correct errors.
The error-detecting and error-correcting properties of a block code depend on
its Hamming distance. To reliably detect d errors, you need a distance d + 1 code
because with such a code there is no way that d single-bit errors can change a
valid codeword into another valid codeword. When the receiver sees an illegal
codeword, it can tell that a transmission error has occurred. Similarly, to correct d
errors, you need a distance 2d + 1 code because that way the legal codewords are
so far apart that even with d changes the original codeword is still closer than any
other codeword. This means the original codeword can be uniquely determined
based on the assumption that a larger number of errors are less likely.
As a simple example of an error-correcting code, consider a code with only
four valid codewords:
0000000000, 0000011111, 1111100000, and 1111111111
This code has a distance of 5, which means that it can correct double errors or
detect quadruple errors. If the codeword 0000000111 arrives and we expect only
single- or double-bit errors, the receiver will know that the original must have
been 0000011111. If, however, a triple error changes 0000000000 into
0000000111, the error will not be corrected properly. Alternatively, if we expect
all of these errors, we can detect them. None of the received codewords are legal
codewords so an error must have occurred. It should be apparent that in this ex-
ample we cannot both correct double errors and detect quadruple errors because
this would require us to interpret a received codeword in two different ways.


---

<a id="page-218"></a>

<!-- Page 218 of 888 -->

206 THE DATA LINK LAYER CHAP. 3
In our example, the task of decoding by finding the legal codeword that is
closest to the received codeword can be done by inspection. Unfortunately, in the
most general case where all codewords need to be evaluated as candidates, this
task can be a time-consuming search. Instead, practical codes are designed so that
they admit shortcuts to find what was likely the original codeword.
Imagine that we want to design a code with m message bits and r check bits
that will allow all single errors to be corrected. Each of the 2m legal messages has
n illegal codewords at a distance of 1 from it. These are formed by systematically
inverting each of the n bits in the n-bit codeword formed from it. Thus, each of
the 2m legal messages requires n + 1 bit patterns dedicated to it. Since the total
number of bit patterns is 2n, we must have (n + 1)2m ≤ 2n. Using n = m + r, this
requirement becomes
(m + r + 1) ≤ 2r (3-1)
Given m, this puts a lower limit on the number of check bits needed to correct sin-
gle errors.
This theoretical lower limit can, in fact, be achieved using a method due to
Hamming (1950). In Hamming codes the bits of the codeword are numbered
consecutively, starting with bit 1 at the left end, bit 2 to its immediate right, and so
on. The bits that are powers of 2 (1, 2, 4, 8, 16, etc.) are check bits. The rest (3,
5, 6, 7, 9, etc.) are filled up with the m data bits. This pattern is shown for an
(11,7) Hamming code with 7 data bits and 4 check bits in Fig. 3-6. Each check bit
forces the modulo 2 sum, or parity, of some collection of bits, including itself, to
be even (or odd). A bit may be included in several check bit computations. To
see which check bits the data bit in position k contributes to, rewrite k as a sum of
powers of 2. For example, 11 = 1 + 2 + 8 and 29 = 1 + 4 + 8 + 16. A bit is
checked by just those check bits occurring in its expansion (e.g., bit 11 is checked
by bits 1, 2, and 8). In the example, the check bits are computed for even parity
sums for a message that is the ASCII letter ''A.''
Check Syndrome
bits 0 1 0 1 Flip
bit 5
Check
1 bit results
error
A p1 p2 m3 p4 m5 m6 m7 p8 m9 m10 m11 A
1000001 0 0 1 0 0 0 0 1 0 0 1 0 0 1 0 1 0 0 1 0 0 1 1000001
Channel
Message Sent Received Message
codeword codeword
Figure 3-6. Example of an (11, 7) Hamming code correcting a single-bit error.
This construction gives a code with a Hamming distance of 3, which means
that it can correct single errors (or detect double errors). The reason for the very
careful numbering of message and check bits becomes apparent in the decoding


---

<a id="page-219"></a>

<!-- Page 219 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 207
process. When a codeword arrives, the receiver redoes the check bit computa-
tions including the values of the received check bits. We call these the check re-
sults. If the check bits are correct then, for even parity sums, each check result
should be zero. In this case the codeword is accepted as valid.
If the check results are not all zero, however, an error has been detected. The
set of check results forms the error syndrome that is used to pinpoint and correct
the error. In Fig. 3-6, a single-bit error occurred on the channel so the check re-
sults are 0, 1, 0, and 1 for k = 8, 4, 2, and 1, respectively. This gives a syndrome
of 0101 or 4 + 1=5. By the design of the scheme, this means that the fifth bit is in
error. Flipping the incorrect bit (which might be a check bit or a data bit) and dis-
carding the check bits gives the correct message of an ASCII ''A.''
Hamming distances are valuable for understanding block codes, and Ham-
ming codes are used in error-correcting memory. However, most networks use
stronger codes. The second code we will look at is a convolutional code. This
code is the only one we will cover that is not a block code. In a convolutional
code, an encoder processes a sequence of input bits and generates a sequence of
output bits. There is no natural message size or encoding boundary as in a block
code. The output depends on the current and previous input bits. That is, the
encoder has memory. The number of previous bits on which the output depends is
called the constraint length of the code. Convolutional codes are specified in
terms of their rate and constraint length.
Convolutional codes are widely used in deployed networks, for example, as
part of the GSM mobile phone system, in satellite communications, and in 802.11.
As an example, a popular convolutional code is shown in Fig. 3-7. This code is
known as the NASA convolutional code of r = 1/2 and k = 7, since it was first
used for the Voyager space missions starting in 1977. Since then it has been
liberally reused, for example, as part of 802.11.
Output
bit 1
Input
## S S S S S S
bit 1 2 3 4 5 6
Output
bit 2
Figure 3-7. The NASA binary convolutional code used in 802.11.
In Fig. 3-7, each input bit on the left-hand side produces two output bits on the
right-hand side that are XOR sums of the input and internal state. Since it deals
with bits and performs linear operations, this is a binary, linear convolutional
code. Since 1 input bit produces 2 output bits, the code rate is 1/2. It is not sys-
tematic since none of the output bits is simply the input bit.


---

<a id="page-220"></a>

<!-- Page 220 of 888 -->

208 THE DATA LINK LAYER CHAP. 3
The internal state is kept in six memory registers. Each time another bit is in-
put the values in the registers are shifted to the right. For example, if 111 is input
and the initial state is all zeros, the internal state, written left to right, will become
100000, 110000, and 111000 after the first, second, and third bits have been input.
The output bits will be 11, followed by 10, and then 01. It takes seven shifts to
flush an input completely so that it does not affect the output. The constraint
length of this code is thus k = 7.
A convolutional code is decoded by finding the sequence of input bits that is
most likely to have produced the observed sequence of output bits (which includes
any errors). For small values of k, this is done with a widely used algorithm de-
veloped by Viterbi (Forney, 1973). The algorithm walks the observed sequence,
keeping for each step and for each possible internal state the input sequence that
would have produced the observed sequence with the fewest errors. The input se-
quence requiring the fewest errors at the end is the most likely message.
Convolutional codes have been popular in practice because it is easy to factor
the uncertainty of a bit being a 0 or a 1 into the decoding. For example, suppose
−1V is the logical 0 level and +1V is the logical 1 level, we might receive 0.9V
and −0.1V for 2 bits. Instead of mapping these signals to 1 and 0 right away, we
would like to treat 0.9V as ''very likely a 1'' and −0.1V as ''maybe a 0'' and cor-
rect the sequence as a whole. Extensions of the Viterbi algorithm can work with
these uncertainties to provide stronger error correction. This approach of working
with the uncertainty of a bit is called soft-decision decoding. Conversely, decid-
ing whether each bit is a 0 or a 1 before subsequent error correction is called
hard-decision decoding.
The third kind of error-correcting code we will describe is the Reed-Solomon
code. Like Hamming codes, Reed-Solomon codes are linear block codes, and
they are often systematic too. Unlike Hamming codes, which operate on individ-
ual bits, Reed-Solomon codes operate on m bit symbols. Naturally, the mathemat-
ics are more involved, so we will describe their operation by analogy.
Reed-Solomon codes are based on the fact that every n degree polynomial is
uniquely determined by n + 1 points. For example, a line having the form ax + b
is determined by two points. Extra points on the same line are redundant, which is
helpful for error correction. Imagine that we have two data points that represent a
line and we send those two data points plus two check points chosen to lie on the
same line. If one of the points is received in error, we can still recover the data
points by fitting a line to the received points. Three of the points will lie on the
line, and one point, the one in error, will not. By finding the line we have cor-
rected the error.
Reed-Solomon codes are actually defined as polynomials that operate over
finite fields, but they work in a similar manner. For m bit symbols, the codewords
are 2m−1 symbols long. A popular choice is to make m = 8 so that symbols are
bytes. A codeword is then 255 bytes long. The (255, 233) code is widely used; it
adds 32 redundant symbols to 233 data symbols. Decoding with error correction


---

<a id="page-221"></a>

<!-- Page 221 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 209
is done with an algorithm developed by Berlekamp and Massey that can effi-
ciently perform the fitting task for moderate-length codes (Massey, 1969).
Reed-Solomon codes are widely used in practice because of their strong
error-correction properties, particularly for burst errors. They are used for DSL,
data over cable, satellite communications, and perhaps most ubiquitously on CDs,
DVDs, and Blu-ray discs. Because they are based on m bit symbols, a single-bit
error and an m-bit burst error are both treated simply as one symbol error. When
2t redundant symbols are added, a Reed-Solomon code is able to correct up to t
errors in any of the transmitted symbols. This means, for example, that the (255,
233) code, which has 32 redundant symbols, can correct up to 16 symbol errors.
Since the symbols may be consecutive and they are each 8 bits, an error burst of
up to 128 bits can be corrected. The situation is even better if the error model is
one of erasures (e.g., a scratch on a CD that obliterates some symbols). In this
case, up to 2t errors can be corrected.
Reed-Solomon codes are often used in combination with other codes such as a
convolutional code. The thinking is as follows. Convolutional codes are effective
at handling isolated bit errors, but they will fail, likely with a burst of errors, if
there are too many errors in the received bit stream. By adding a Reed-Solomon
code within the convolutional code, the Reed-Solomon decoding can mop up the
error bursts, a task at which it is very good. The overall code then provides good
protection against both single and burst errors.
The final error-correcting code we will cover is the LDPC (Low-Density
Parity Check) code. LDPC codes are linear block codes that were invented by
Robert Gallagher in his doctoral thesis (Gallagher, 1962). Like most theses, they
were promptly forgotten, only to be reinvented in 1995 when advances in comput-
ing power had made them practical.
In an LDPC code, each output bit is formed from only a fraction of the input
bits. This leads to a matrix representation of the code that has a low density of 1s,
hence the name for the code. The received codewords are decoded with an
approximation algorithm that iteratively improves on a best fit of the received
data to a legal codeword. This corrects errors.
LDPC codes are practical for large block sizes and have excellent error-cor-
rection abilities that outperform many other codes (including the ones we have
looked at) in practice. For this reason they are rapidly being included in new pro-
tocols. They are part of the standard for digital video broadcasting, 10 Gbps
Ethernet, power-line networks, and the latest version of 802.11. Expect to see
more of them in future networks.
#### 3.2.2 Error-Detecting Codes
Error-correcting codes are widely used on wireless links, which are notori-
ously noisy and error prone when compared to optical fibers. Without error-cor-
recting codes, it would be hard to get anything through. However, over fiber or


---

<a id="page-222"></a>

<!-- Page 222 of 888 -->

210 THE DATA LINK LAYER CHAP. 3
high-quality copper, the error rate is much lower, so error detection and retrans-
mission is usually more efficient there for dealing with the occasional error.
We will examine three different error-detecting codes. They are all linear,
systematic block codes:
1. Parity.
2. Checksums.
3. Cyclic Redundancy Checks (CRCs).
To see how they can be more efficient than error-correcting codes, consider
the first error-detecting code, in which a single parity bit is appended to the data.
The parity bit is chosen so that the number of 1 bits in the codeword is even (or
odd). Doing this is equivalent to computing the (even) parity bit as the modulo 2
sum or XOR of the data bits. For example, when 1011010 is sent in even parity, a
bit is added to the end to make it 10110100. With odd parity 1011010 becomes
10110101. A code with a single parity bit has a distance of 2, since any single-bit
error produces a codeword with the wrong parity. This means that it can detect
single-bit errors.
Consider a channel on which errors are isolated and the error rate is 10−6 per
bit. This may seem a tiny error rate, but it is at best a fair rate for a long wired
cable that is challenging for error detection. Typical LAN links provide bit error
rates of 10−10. Let the block size be 1000 bits. To provide error correction for
1000-bit blocks, we know from Eq. (3-1) that 10 check bits are needed. Thus, a
megabit of data would require 10,000 check bits. To merely detect a block with a
single 1-bit error, one parity bit per block will suffice. Once every 1000 blocks, a
block will be found to be in error and an extra block (1001 bits) will have to be
transmitted to repair the error. The total overhead for the error detection and re-
transmission method is only 2001 bits per megabit of data, versus 10,000 bits for a
Hamming code.
One difficulty with this scheme is that a single parity bit can only reliably
detect a single-bit error in the block. If the block is badly garbled by a long burst
error, the probability that the error will be detected is only 0.5, which is hardly ac-
ceptable. The odds can be improved considerably if each block to be sent is
regarded as a rectangular matrix n bits wide and k bits high. Now, if we compute
and send one parity bit for each row, up to k bit errors will be reliably detected as
long as there is at most one error per row.
However, there is something else we can do that provides better protection
against burst errors: we can compute the parity bits over the data in a different
order than the order in which the data bits are transmitted. Doing so is called
interleaving. In this case, we will compute a parity bit for each of the n columns
and send all the data bits as k rows, sending the rows from top to bottom and the
bits in each row from left to right in the usual manner. At the last row, we send
the n parity bits. This transmission order is shown in Fig. 3-8 for n = 7 and k = 7.


---

<a id="page-223"></a>

<!-- Page 223 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 211
Transmit
N 1001110 order N 1001110
e 1100101 c 1100011 Burst
error
t 1110100 l 1101100
w 1110111 w 1110111
o 1101111 Channel o 1101111
r 1110010 r 1110010
k 1101011 k 1101011
1011110 1011110
Parity bits
Parity errors
Figure 3-8. Interleaving of parity bits to detect a burst error.
Interleaving is a general technique to convert a code that detects (or corrects)
isolated errors into a code that detects (or corrects) burst errors. In Fig. 3-8, when
a burst error of length n = 7 occurs, the bits that are in error are spread across dif-
ferent columns. (A burst error does not imply that all the bits are wrong; it just
implies that at least the first and last are wrong. In Fig. 3-8, 4 bits were flipped
over a range of 7 bits.) At most 1 bit in each of the n columns will be affected, so
the parity bits on those columns will detect the error. This method uses n parity
bits on blocks of kn data bits to detect a single burst error of length n or less.
A burst of length n + 1 will pass undetected, however, if the first bit is
inverted, the last bit is inverted, and all the other bits are correct. If the block is
badly garbled by a long burst or by multiple shorter bursts, the probability that any
of the n columns will have the correct parity by accident is 0.5, so the probability
of a bad block being accepted when it should not be is 2−n.
The second kind of error-detecting code, the checksum, is closely related to
groups of parity bits. The word ''checksum'' is often used to mean a group of
check bits associated with a message, regardless of how are calculated. A group
of parity bits is one example of a checksum. However, there are other, stronger
checksums based on a running sum of the data bits of the message. The checksum
is usually placed at the end of the message, as the complement of the sum func-
tion. This way, errors may be detected by summing the entire received codeword,
both data bits and checksum. If the result comes out to be zero, no error has been
detected.
One example of a checksum is the 16-bit Internet checksum used on all Inter-
net packets as part of the IP protocol (Braden et al., 1988). This checksum is a
sum of the message bits divided into 16-bit words. Because this method operates
on words rather than on bits, as in parity, errors that leave the parity unchanged
can still alter the sum and be detected. For example, if the lowest order bit in two
different words is flipped from a 0 to a 1, a parity check across these bits would
fail to detect an error. However, two 1s will be added to the 16-bit checksum to
produce a different result. The error can then be detected.


---

<a id="page-224"></a>

<!-- Page 224 of 888 -->

212 THE DATA LINK LAYER CHAP. 3
The Internet checksum is computed in one's complement arithmetic instead of
as the modulo 216 sum. In one's complement arithmetic, a negative number is the
bitwise complement of its positive counterpart. Modern computers run two's
complement arithmetic, in which a negative number is the one's complement plus
one. On a two's complement computer, the one's complement sum is equivalent
to taking the sum modulo 216 and adding any overflow of the high order bits back
into the low-order bits. This algorithm gives a more uniform coverage of the data
by the checksum bits. Otherwise, two high-order bits can be added, overflow, and
be lost without changing the sum. There is another benefit, too. One's comple-
ment has two representations of zero, all 0s and all 1s. This allows one value (e.g.,
all 0s) to indicate that there is no checksum, without the need for another field.
For decades, it has always been assumed that frames to be checksummed con-
tain random bits. All analyses of checksum algorithms have been made under this
assumption. Inspection of real data by Partridge et al. (1995) has shown this as-
sumption to be quite wrong. As a consequence, undetected errors are in some
cases much more common than had been previously thought.
The Internet checksum in particular is efficient and simple but provides weak
protection in some cases precisely because it is a simple sum. It does not detect
the deletion or addition of zero data, nor swapping parts of the message, and it
provides weak protection against message splices in which parts of two packets
are put together. These errors may seem very unlikely to occur by random proc-
esses, but they are just the sort of errors that can occur with buggy hardware.
A better choice is Fletcher's checksum (Fletcher, 1982). It includes a posi-
tional component, adding the product of the data and its position to the running
sum. This provides stronger detection of changes in the position of data.
Although the two preceding schemes may sometimes be adequate at higher
layers, in practice, a third and stronger kind of error-detecting code is in wide-
spread use at the link layer: the CRC (Cyclic Redundancy Check), also known
as a polynomial code. Polynomial codes are based upon treating bit strings as
representations of polynomials with coefficients of 0 and 1 only. A k-bit frame is
regarded as the coefficient list for a polynomial with k terms, ranging from x k − 1
to x 0. Such a polynomial is said to be of degree k − 1. The high-order (leftmost)
bit is the coefficient of x k − 1, the next bit is the coefficient of x k − 2, and so on.
For example, 110001 has 6 bits and thus represents a six-term polynomial with
coefficients 1, 1, 0, 0, 0, and 1: 1x 5 + 1x 4 + 0x 3 + 0x 2 + 0x 1 + 1x 0.
Polynomial arithmetic is done modulo 2, according to the rules of algebraic
field theory. It does not have carries for addition or borrows for subtraction. Both
addition and subtraction are identical to exclusive OR. For example:
10011011 00110011 11110000 01010101
+ 11001010 + 11001101 ! 10100110 ! 10101111
01010001 11111110 01010110 11111010
Long division is carried out in exactly the same way as it is in binary except that


---

<a id="page-225"></a>

<!-- Page 225 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 213
the subtraction is again done modulo 2. A divisor is said ''to go into'' a dividend
if the dividend has as many bits as the divisor.
When the polynomial code method is employed, the sender and receiver must
agree upon a generator polynomial, G(x ), in advance. Both the high- and low-
order bits of the generator must be 1. To compute the CRC for some frame with
m bits corresponding to the polynomial M(x ), the frame must be longer than the
generator polynomial. The idea is to append a CRC to the end of the frame in
such a way that the polynomial represented by the checksummed frame is divisi-
ble by G(x ). When the receiver gets the checksummed frame, it tries dividing it
by G(x ). If there is a remainder, there has been a transmission error.
The algorithm for computing the CRC is as follows:
1. Let r be the degree of G(x). Append r zero bits to the low-order end
of the frame so it now contains m + r bits and corresponds to the
polynomial x rM(x).
2. Divide the bit string corresponding to G(x) into the bit string corres-
ponding to x rM(x ), using modulo 2 division.
3. Subtract the remainder (which is always r or fewer bits) from the bit
string corresponding to x rM(x) using modulo 2 subtraction. The re-
sult is the checksummed frame to be transmitted. Call its polynomial
T (x).
Figure 3-9 illustrates the calculation for a frame 1101011111 using the generator
G(x) = x 4 + x + 1.
It should be clear that T (x) is divisible (modulo 2) by G(x). In any division
problem, if you diminish the dividend by the remainder, what is left over is divisi-
ble by the divisor. For example, in base 10, if you divide 210,278 by 10,941, the
remainder is 2399. If you then subtract 2399 from 210,278, what is left over
(207,879) is divisible by 10,941.
Now let us analyze the power of this method. What kinds of errors will be de-
tected? Imagine that a transmission error occurs, so that instead of the bit string
for T (x ) arriving, T (x) + E(x ) arrives. Each 1 bit in E(x ) corresponds to a bit that
has been inverted. If there are k 1 bits in E(x ), k single-bit errors have occurred.
A single burst error is characterized by an initial 1, a mixture of 0s and 1s, and a
final 1, with all other bits being 0.
Upon receiving the checksummed frame, the receiver divides it by G(x ); that
is, it computes [T (x) + E(x)]/G(x). T(x)/G(x ) is 0, so the result of the computa-
tion is simply E(x )/G(x). Those errors that happen to correspond to polynomials
containing G(x ) as a factor will slip by; all other errors will be caught.
If there has been a single-bit error, E (x) = x i, where i determines which bit is
in error. If G(x ) contains two or more terms, it will never divide into E(x ), so all
single-bit errors will be detected.


---

<a id="page-226"></a>

<!-- Page 226 of 888 -->

214 THE DATA LINK LAYER CHAP. 3
Frame: 1 1 0 1 0 1 1 1 1 1
Generator: 1 0 0 1 1
1 1 0 0 0 0 1 1 1 0 Quotient (thrown away)
1 0 0 1 1 1 1 0 1 0 1 1 1 1 1 0 0 0 0 Frame with four zeros appended
1 0 0 1 1
1 0 0 1 1
1 0 0 1 1
0 0 0 0 1
0 0 0 0 0
0 0 0 1 1
0 0 0 0 0
0 0 1 1 1
0 0 0 0 0
0 1 1 1 1
0 0 0 0 0
1 1 1 1 0
1 0 0 1 1
1 1 0 1 0
1 0 0 1 1
1 0 0 1 0
1 0 0 1 1
0 0 0 1 0
0 0 0 0 0
1 0 Remainder
Transmitted frame: 1 1 0 1 0 1 1 1 1 1 0 0 1 0 Frame with four zeros appended
minus remainder
Figure 3-9. Example calculation of the CRC.
If there have been two isolated single-bit errors, E(x) = x i + x j, where i > j.
Alternatively, this can be written as E(x ) = x j(x i − j + 1). If we assume that G(x)
is not divisible by x, a sufficient condition for all double errors to be detected is
that G(x ) does not divide x k + 1 for any k up to the maximum value of i − j (i.e.,
up to the maximum frame length). Simple, low-degree polynomials that give pro-
tection to long frames are known. For example, x 15 + x 14 + 1 will not divide
x k + 1 for any value of k below 32,768.
If there are an odd number of bits in error, E (X) contains an odd number of
terms (e.g., x 5 + x 2 + 1, but not x 2 + 1). Interestingly, no polynomial with an odd
number of terms has x + 1 as a factor in the modulo 2 system. By making x + 1 a
factor of G(x ), we can catch all errors with an odd number of inverted bits.
Finally, and importantly, a polynomial code with r check bits will detect all
burst errors of length ≤ r. A burst error of length k can be represented by
x i(x k − 1 + . . . + 1), where i determines how far from the right-hand end of the re-
ceived frame the burst is located. If G(x ) contains an x 0 term, it will not have x i
as a factor, so if the degree of the parenthesized expression is less than the degree
of G(x), the remainder can never be zero.


---

<a id="page-227"></a>

<!-- Page 227 of 888 -->

SEC. 3.2 ERROR DETECTION AND CORRECTION 215
If the burst length is r + 1, the remainder of the division by G(x) will be zero
if and only if the burst is identical to G(x). By definition of a burst, the first and
last bits must be 1, so whether it matches depends on the r − 1 intermediate bits.
If all combinations are regarded as equally likely, the probability of such an incor-
rect frame being accepted as valid is ½r − 1.
It can also be shown that when an error burst longer than r + 1 bits occurs or
when several shorter bursts occur, the probability of a bad frame getting through
unnoticed is ½r, assuming that all bit patterns are equally likely.
Certain polynomials have become international standards. The one used in
IEEE 802 followed the example of Ethernet and is
x 32 + x 26 + x 23 + x 22 + x 16 + x 12 + x 11 + x 10 + x 8 + x 7 + x 5 + x 4 + x 2 + x 1 + 1
Among other desirable properties, it has the property that it detects all bursts of
length 32 or less and all bursts affecting an odd number of bits. It has been used
widely since the 1980s. However, this does not mean it is the best choice. Using
an exhaustive computational search, Castagnoli et al. (1993) and Koopman (2002)
found the best CRCs. These CRCs have a Hamming distance of 6 for typical
message sizes, while the IEEE standard CRC-32 has a Hamming distance of only
4.
Although the calculation required to compute the CRC may seem complicat-
ed, it is easy to compute and verify CRCs in hardware with simple shift register
circuits (Peterson and Brown, 1961). In practice, this hardware is nearly always
used. Dozens of networking standards include various CRCs, including virtually
all LANs (e.g., Ethernet, 802.11) and point-to-point links (e.g., packets over
SONET).
### 3.3 ELEMENTARY DATA LINK PROTOCOLS
To introduce the subject of protocols, we will begin by looking at three proto-
cols of increasing complexity. For interested readers, a simulator for these and
subsequent protocols is available via the Web (see the preface). Before we look
at the protocols, it is useful to make explicit some of the assumptions underlying
the model of communication.
To start with, we assume that the physical layer, data link layer, and network
layer are independent processes that communicate by passing messages back and
forth. A common implementation is shown in Fig. 3-10. The physical layer proc-
ess and some of the data link layer process run on dedicate hardware called a NIC
(Network Interface Card). The rest of the link layer process and the network
layer process run on the main CPU as part of the operating system, with the soft-
ware for the link layer process often taking the form of a device driver. Howev-
er, other implementations are also possible (e.g., three processes offloaded to ded-
icated hardware called a network accelerator, or three processes running on the


---

<a id="page-228"></a>

<!-- Page 228 of 888 -->

216 THE DATA LINK LAYER CHAP. 3
main CPU on a software-defined ratio). Actually, the preferred implementation
changes from decade to decade with technology trade-offs. In any event, treating
the three layers as separate processes makes the discussion conceptually cleaner
and also serves to emphasize the independence of the layers.
Computer
Application
Operating system
Network
Driver
Link
Network Interface
Link
Card (NIC)
PHY
Cable (medium)
Figure 3-10. Implementation of the physical, data link, and network layers.
Another key assumption is that machine A wants to send a long stream of data
to machine B, using a reliable, connection-oriented service. Later, we will consid-
er the case where B also wants to send data to A simultaneously. A is assumed to
have an infinite supply of data ready to send and never has to wait for data to be
produced. Instead, when A's data link layer asks for data, the network layer is al-
ways able to comply immediately. (This restriction, too, will be dropped later.)
We also assume that machines do not crash. That is, these protocols deal with
communication errors, but not the problems caused by computers crashing and
rebooting.
As far as the data link layer is concerned, the packet passed across the inter-
face to it from the network layer is pure data, whose every bit is to be delivered to
the destination's network layer. The fact that the destination's network layer may
interpret part of the packet as a header is of no concern to the data link layer.
When the data link layer accepts a packet, it encapsulates the packet in a
frame by adding a data link header and trailer to it (see Fig. 3-1). Thus, a frame
consists of an embedded packet, some control information (in the header), and a
checksum (in the trailer). The frame is then transmitted to the data link layer on
the other machine. We will assume that there exist suitable library procedures
to physical layer to send a frame and from physical layer to receive a frame.
These procedures compute and append or check the checksum (which is usually
done in hardware) so that we do not need to worry about it as part of the protocols
we develop in this section. They might use the CRC algorithm discussed in the
previous section, for example.
Initially, the receiver has nothing to do. It just sits around waiting for some-
thing to happen. In the example protocols throughout this chapter we will indicate
that the data link layer is waiting for something to happen by the procedure call


---

<a id="page-229"></a>

<!-- Page 229 of 888 -->

SEC. 3.3 ELEMENTARY DATA LINK PROTOCOLS 217
#define MAX PKT 1024 /* determines packet size in bytes */
typedef enum {false, true} boolean; /* boolean type */
typedef unsigned int seq nr; /* sequence or ack numbers */
typedef struct {unsigned char data[MAX PKT];} packet; /* packet definition */
typedef enum {data, ack, nak} frame kind; /* frame kind definition */
typedef struct { /* frames are transported in this layer */
frame kind kind; /* what kind of frame is it? */
seq nr seq; /* sequence number */
seq nr ack; /* acknowledgement number */
packet info; /* the network layer packet */
} frame;
/* Wait for an event to happen; return its type in event. */
void wait for event(event type *event);
/* Fetch a packet from the network layer for transmission on the channel. */
void from network layer(packet *p);
/* Deliver information from an inbound frame to the network layer. */
void to network layer(packet *p);
/* Go get an inbound frame from the physical layer and copy it to r. */
void from physical layer(frame *r);
/* Pass the frame to the physical layer for transmission. */
void to physical layer(frame *s);
/* Start the clock running and enable the timeout event. */
void start timer(seq nr k);
/* Stop the clock and disable the timeout event. */
void stop timer(seq nr k);
/* Start an auxiliary timer and enable the ack timeout event. */
void start ack timer(void);
/* Stop the auxiliary timer and disable the ack timeout event. */
void stop ack timer(void);
/* Allow the network layer to cause a network layer ready event. */
void enable network layer(void);
/* Forbid the network layer from causing a network layer ready event. */
void disable network layer(void);
/* Macro inc is expanded in-line: increment k circularly. */
#define inc(k) if (k < MAX SEQ) k = k + 1; else k = 0
Figure 3-11. Some definitions needed in the protocols to follow. These defini-
tions are located in the file protocol.h.


---

<a id="page-230"></a>

<!-- Page 230 of 888 -->

218 THE DATA LINK LAYER CHAP. 3
wait for event(&event). This procedure only returns when something has hap-
pened (e.g., a frame has arrived). Upon return, the variable event tells what hap-
pened. The set of possible events differs for the various protocols to be described
and will be defined separately for each protocol. Note that in a more realistic
situation, the data link layer will not sit in a tight loop waiting for an event, as we
have suggested, but will receive an interrupt, which will cause it to stop whatever
it was doing and go handle the incoming frame. Nevertheless, for simplicity we
will ignore all the details of parallel activity within the data link layer and assume
that it is dedicated full time to handling just our one channel.
When a frame arrives at the receiver, the checksum is recomputed. If the
checksum in the frame is incorrect (i.e., there was a transmission error), the data
link layer is so informed (event = cksum err ). If the inbound frame arrived
undamaged, the data link layer is also informed (event = frame arrival ) so that it
can acquire the frame for inspection using from physical layer. As soon as the
receiving data link layer has acquired an undamaged frame, it checks the control
information in the header, and, if everything is all right, passes the packet portion
to the network layer. Under no circumstances is a frame header ever given to a
network layer.
There is a good reason why the network layer must never be given any part of
the frame header: to keep the network and data link protocols completely sepa-
rate. As long as the network layer knows nothing at all about the data link proto-
col or the frame format, these things can be changed without requiring changes to
the network layer's software. This happens whenever a new NIC is installed in a
computer. Providing a rigid interface between the network and data link layers
greatly simplifies the design task because communication protocols in different
layers can evolve independently.
Figure 3-11 shows some declarations (in C) common to many of the protocols
to be discussed later. Five data structures are defined there: boolean, seq nr,
packet, frame kind, and frame. A boolean is an enumerated type and can take on
the values true and false. A seq nr is a small integer used to number the frames
so that we can tell them apart. These sequence numbers run from 0 up to and in-
cluding MAX SEQ, which is defined in each protocol needing it. A packet is the
unit of information exchanged between the network layer and the data link layer
on the same machine, or between network layer peers. In our model it always
contains MAX PKT bytes, but more realistically it would be of variable length.
A frame is composed of four fields: kind, seq, ack, and info, the first three of
which contain control information and the last of which may contain actual data to
be transferred. These control fields are collectively called the frame header.
The kind field tells whether there are any data in the frame, because some of
the protocols distinguish frames containing only control information from those
containing data as well. The seq and ack fields are used for sequence numbers
and acknowledgements, respectively; their use will be described in more detail
later. The info field of a data frame contains a single packet; the info field of a


---

<a id="page-231"></a>

<!-- Page 231 of 888 -->

SEC. 3.3 ELEMENTARY DATA LINK PROTOCOLS 219
control frame is not used. A more realistic implementation would use a variable-
length info field, omitting it altogether for control frames.
Again, it is important to understand the relationship between a packet and a
frame. The network layer builds a packet by taking a message from the transport
layer and adding the network layer header to it. This packet is passed to the data
link layer for inclusion in the info field of an outgoing frame. When the frame ar-
rives at the destination, the data link layer extracts the packet from the frame and
passes the packet to the network layer. In this manner, the network layer can act
as though machines can exchange packets directly.
A number of procedures are also listed in Fig. 3-11. These are library rou-
tines whose details are implementation dependent and whose inner workings will
not concern us further in the following discussions. The procedure wait for event
sits in a tight loop waiting for something to happen, as mentioned earlier. The
procedures to network layer and from network layer are used by the data link
layer to pass packets to the network layer and accept packets from the network
layer, respectively. Note that from physical layer and to physical layer pass
frames between the data link layer and the physical layer. In other words, to net-
work layer and from network layer deal with the interface between layers 2 and
3, whereas from physical layer and to physical layer deal with the interface be-
tween layers 1 and 2.
In most of the protocols, we assume that the channel is unreliable and loses
entire frames upon occasion. To be able to recover from such calamities, the
sending data link layer must start an internal timer or clock whenever it sends a
frame. If no reply has been received within a certain predetermined time interval,
the clock times out and the data link layer receives an interrupt signal.
In our protocols this is handled by allowing the procedure wait for event to
return event = timeout. The procedures start timer and stop timer turn the timer
on and off, respectively. Timeout events are possible only when the timer is run-
ning and before stop timer is called. It is explicitly permitted to call start timer
while the timer is running; such a call simply resets the clock to cause the next
timeout after a full timer interval has elapsed (unless it is reset or turned off).
The procedures start ack timer and stop ack timer control an auxiliary timer
used to generate acknowledgements under certain conditions.
The procedures enable network layer and disable network layer are used in
the more sophisticated protocols, where we no longer assume that the network
layer always has packets to send. When the data link layer enables the network
layer, the network layer is then permitted to interrupt when it has a packet to be
sent. We indicate this with event = network layer ready. When the network
layer is disabled, it may not cause such events. By being careful about when it
enables and disables its network layer, the data link layer can prevent the network
layer from swamping it with packets for which it has no buffer space.
Frame sequence numbers are always in the range 0 to MAX SEQ (inclusive),
where MAX SEQ is different for the different protocols. It is frequently necessary


---

<a id="page-232"></a>

<!-- Page 232 of 888 -->

220 THE DATA LINK LAYER CHAP. 3
to advance a sequence number by 1 circularly (i.e., MAX SEQ is followed by 0).
The macro inc performs this incrementing. It has been defined as a macro be-
cause it is used in-line within the critical path. As we will see later, the factor
limiting network performance is often protocol processing, so defining simple op-
erations like this as macros does not affect the readability of the code but does im-
prove performance.
The declarations of Fig. 3-11 are part of each of the protocols we will discuss
shortly. To save space and to provide a convenient reference, they have been
extracted and listed together, but conceptually they should be merged with the
protocols themselves. In C, this merging is done by putting the definitions in a
special header file, in this case protocol.h, and using the #include facility of the C
preprocessor to include them in the protocol files.
#### 3.3.1 A Utopian Simplex Protocol
As an initial example we will consider a protocol that is as simple as it can be
because it does not worry about the possibility of anything going wrong. Data are
transmitted in one direction only. Both the transmitting and receiving network
layers are always ready. Processing time can be ignored. Infinite buffer space is
available. And best of all, the communication channel between the data link lay-
ers never damages or loses frames. This thoroughly unrealistic protocol, which
we will nickname ''Utopia,'' is simply to show the basic structure on which we
will build. It's implementation is shown in Fig. 3-12.
The protocol consists of two distinct procedures, a sender and a receiver. The
sender runs in the data link layer of the source machine, and the receiver runs in
the data link layer of the destination machine. No sequence numbers or acknowl-
edgements are used here, so MAX SEQ is not needed. The only event type pos-
sible is frame arrival (i.e., the arrival of an undamaged frame).
The sender is in an infinite while loop just pumping data out onto the line as
fast as it can. The body of the loop consists of three actions: go fetch a packet
from the (always obliging) network layer, construct an outbound frame using the
variable s, and send the frame on its way. Only the info field of the frame is used
by this protocol, because the other fields have to do with error and flow control
and there are no errors or flow control restrictions here.
The receiver is equally simple. Initially, it waits for something to happen, the
only possibility being the arrival of an undamaged frame. Eventually, the frame
arrives and the procedure wait for event returns, with event set to frame arrival
(which is ignored anyway). The call to from physical layer removes the newly
arrived frame from the hardware buffer and puts it in the variable r, where the re-
ceiver code can get at it. Finally, the data portion is passed on to the network
layer, and the data link layer settles back to wait for the next frame, effectively
suspending itself until the frame arrives.


---

<a id="page-233"></a>

<!-- Page 233 of 888 -->

SEC. 3.3 ELEMENTARY DATA LINK PROTOCOLS 221
/* Protocol 1 (Utopia) provides for data transmission in one direction only, from
sender to receiver. The communication channel is assumed to be error free
and the receiver is assumed to be able to process all the input infinitely quickly.
Consequently, the sender just sits in a loop pumping data out onto the line as
fast as it can. */
typedef enum {frame arrival} event type;
#include "protocol.h"
void sender1(void)
{
frame s; /* buffer for an outbound frame */
packet buffer; /* buffer for an outbound packet */
while (true) {
from network layer(&buffer); /* go get something to send */
s.info = buffer; /* copy it into s for transmission */
to physical layer(&s); /* send it on its way */
} /* Tomorrow, and tomorrow, and tomorrow,
Creeps in this petty pace from day to day
To the last syllable of recorded time.
- Macbeth, V, v */
}
void receiver1(void)
{
frame r;
event type event; /* filled in by wait, but not used here */
while (true) {
wait for event(&event); /* only possibility is frame arrival */
from physical layer(&r); /* go get the inbound frame */
to network layer(&r.info); /* pass the data to the network layer */
}
}
Figure 3-12. A utopian simplex protocol.
The utopia protocol is unrealistic because it does not handle either flow con-
trol or error correction. Its processing is close to that of an unacknowledged con-
nectionless service that relies on higher layers to solve these problems, though
even an unacknowledged connectionless service would do some error detection.
#### 3.3.2 A Simplex Stop-and-Wait Protocol for an Error-Free Channel
Now we will tackle the problem of preventing the sender from flooding the
receiver with frames faster than the latter is able to process them. This situation
can easily happen in practice so being able to prevent it is of great importance.


---

<a id="page-234"></a>

<!-- Page 234 of 888 -->

222 THE DATA LINK LAYER CHAP. 3
The communication channel is still assumed to be error free, however, and the
data traffic is still simplex.
One solution is to build the receiver to be powerful enough to process a con-
tinuous stream of back-to-back frames (or, equivalently, define the link layer to be
slow enough that the receiver can keep up). It must have sufficient buffering and
processing abilities to run at the line rate and must be able to pass the frames that
are received to the network layer quickly enough. However, this is a worst-case
solution. It requires dedicated hardware and can be wasteful of resources if the
utilization of the link is mostly low. Moreover, it just shifts the problem of deal-
ing with a sender that is too fast elsewhere; in this case to the network layer.
A more general solution to this problem is to have the receiver provide feed-
back to the sender. After having passed a packet to its network layer, the receiver
sends a little dummy frame back to the sender which, in effect, gives the sender
permission to transmit the next frame. After having sent a frame, the sender is re-
quired by the protocol to bide its time until the little dummy (i.e., acknowledge-
ment) frame arrives. This delay is a simple example of a flow control protocol.
Protocols in which the sender sends one frame and then waits for an acknowl-
edgement before proceeding are called stop-and-wait. Figure 3-13 gives an ex-
ample of a simplex stop-and-wait protocol.
Although data traffic in this example is simplex, going only from the sender to
the receiver, frames do travel in both directions. Consequently, the communica-
tion channel between the two data link layers needs to be capable of bidirectional
information transfer. However, this protocol entails a strict alternation of flow:
first the sender sends a frame, then the receiver sends a frame, then the sender
sends another frame, then the receiver sends another one, and so on. A half-
duplex physical channel would suffice here.
As in protocol 1, the sender starts out by fetching a packet from the network
layer, using it to construct a frame, and sending it on its way. But now, unlike in
protocol 1, the sender must wait until an acknowledgement frame arrives before
looping back and fetching the next packet from the network layer. The sending
data link layer need not even inspect the incoming frame as there is only one pos-
sibility. The incoming frame is always an acknowledgement.
The only difference between receiver1 and receiver2 is that after delivering a
packet to the network layer, receiver2 sends an acknowledgement frame back to
the sender before entering the wait loop again. Because only the arrival of the
frame back at the sender is important, not its contents, the receiver need not put
any particular information in it.
#### 3.3.3 A Simplex Stop-and-Wait Protocol for a Noisy Channel
Now let us consider the normal situation of a communication channel that
makes errors. Frames may be either damaged or lost completely. However, we
assume that if a frame is damaged in transit, the receiver hardware will detect this


---

<a id="page-235"></a>

<!-- Page 235 of 888 -->

SEC. 3.3 ELEMENTARY DATA LINK PROTOCOLS 223
/* Protocol 2 (Stop-and-wait) also provides for a one-directional flow of data from
sender to receiver. The communication channel is once again assumed to be error
free, as in protocol 1. However, this time the receiver has only a finite buffer
capacity and a finite processing speed, so the protocol must explicitly prevent
the sender from flooding the receiver with data faster than it can be handled. */
typedef enum {frame arrival} event type;
#include "protocol.h"
void sender2(void)
{
frame s; /* buffer for an outbound frame */
packet buffer; /* buffer for an outbound packet */
event type event; /* frame arrival is the only possibility */
while (true) {
from network layer(&buffer); /* go get something to send */
s.info = buffer; /* copy it into s for transmission */
to physical layer(&s); /* bye-bye little frame */
wait for event(&event); /* do not proceed until given the go ahead */
}
}
void receiver2(void)
{
frame r, s; /* buffers for frames */
event type event; /* frame arrival is the only possibility */
while (true) {
wait for event(&event); /* only possibility is frame arrival */
from physical layer(&r); /* go get the inbound frame */
to network layer(&r.info); /* pass the data to the network layer */
to physical layer(&s); /* send a dummy frame to awaken sender */
}
}
Figure 3-13. A simplex stop-and-wait protocol.
when it computes the checksum. If the frame is damaged in such a way that the
checksum is nevertheless correct-an unlikely occurrence-this protocol (and all
other protocols) can fail (i.e., deliver an incorrect packet to the network layer).
At first glance it might seem that a variation of protocol 2 would work: adding
a timer. The sender could send a frame, but the receiver would only send an ac-
knowledgement frame if the data were correctly received. If a damaged frame ar-
rived at the receiver, it would be discarded. After a while the sender would time
out and send the frame again. This process would be repeated until the frame
finally arrived intact.
This scheme has a fatal flaw in it though. Think about the problem and try to
discover what might go wrong before reading further.


---

<a id="page-236"></a>

<!-- Page 236 of 888 -->

224 THE DATA LINK LAYER CHAP. 3
To see what might go wrong, remember that the goal of the data link layer is
to provide error-free, transparent communication between network layer proc-
esses. The network layer on machine A gives a series of packets to its data link
layer, which must ensure that an identical series of packets is delivered to the net-
work layer on machine B by its data link layer. In particular, the network layer on
B has no way of knowing that a packet has been lost or duplicated, so the data link
layer must guarantee that no combination of transmission errors, however unlike-
ly, can cause a duplicate packet to be delivered to a network layer.
Consider the following scenario:
1. The network layer on A gives packet 1 to its data link layer. The
packet is correctly received at B and passed to the network layer on
B. B sends an acknowledgement frame back to A.
2. The acknowledgement frame gets lost completely. It just never ar-
rives at all. Life would be a great deal simpler if the channel man-
gled and lost only data frames and not control frames, but sad to say,
the channel is not very discriminating.
3. The data link layer on A eventually times out. Not having received
an acknowledgement, it (incorrectly) assumes that its data frame was
lost or damaged and sends the frame containing packet 1 again.
4. The duplicate frame also arrives intact at the data link layer on B and
is unwittingly passed to the network layer there. If A is sending a file
to B, part of the file will be duplicated (i.e., the copy of the file made
by B will be incorrect and the error will not have been detected). In
other words, the protocol will fail.
Clearly, what is needed is some way for the receiver to be able to distinguish
a frame that it is seeing for the first time from a retransmission. The obvious way
to achieve this is to have the sender put a sequence number in the header of each
frame it sends. Then the receiver can check the sequence number of each arriving
frame to see if it is a new frame or a duplicate to be discarded.
Since the protocol must be correct and the sequence number field in the head-
er is likely to be small to use the link efficiently, the question arises: what is the
minimum number of bits needed for the sequence number? The header might pro-
vide 1 bit, a few bits, 1 byte, or multiple bytes for a sequence number depending
on the protocol. The important point is that it must carry sequence numbers that
are large enough for the protocol to work correctly, or it is not much of a protocol.
The only ambiguity in this protocol is between a frame, m, and its direct suc-
cessor, m + 1. If frame m is lost or damaged, the receiver will not acknowledge it,
so the sender will keep trying to send it. Once it has been correctly received, the
receiver will send an acknowledgement to the sender. It is here that the potential


---

<a id="page-237"></a>

<!-- Page 237 of 888 -->

SEC. 3.3 ELEMENTARY DATA LINK PROTOCOLS 225
trouble crops up. Depending upon whether the acknowledgement frame gets back
to the sender correctly or not, the sender may try to send m or m + 1.
At the sender, the event that triggers the transmission of frame m + 1 is the ar-
rival of an acknowledgement for frame m. But this situation implies that m − 1
has been correctly received, and furthermore that its acknowledgement has also
been correctly received by the sender. Otherwise, the sender would not have
begun with m, let alone have been considering m + 1. As a consequence, the only
ambiguity is between a frame and its immediate predecessor or successor, not be-
tween the predecessor and successor themselves.
A 1-bit sequence number (0 or 1) is therefore sufficient. At each instant of
time, the receiver expects a particular sequence number next. When a frame con-
taining the correct sequence number arrives, it is accepted and passed to the net-
work layer, then acknowledged. Then the expected sequence number is incre-
mented modulo 2 (i.e., 0 becomes 1 and 1 becomes 0). Any arriving frame con-
taining the wrong sequence number is rejected as a duplicate. However, the last
valid acknowledgement is repeated so that the sender can eventually discover that
the frame has been received.
An example of this kind of protocol is shown in Fig. 3-14. Protocols in which
the sender waits for a positive acknowledgement before advancing to the next
data item are often called ARQ (Automatic Repeat reQuest) or PAR (Positive
Acknowledgement with Retransmission). Like protocol 2, this one also trans-
mits data only in one direction.
Protocol 3 differs from its predecessors in that both sender and receiver have a
variable whose value is remembered while the data link layer is in the wait state.
The sender remembers the sequence number of the next frame to send in
next frame to send; the receiver remembers the sequence number of the next
frame expected in frame expected. Each protocol has a short initialization phase
before entering the infinite loop.
After transmitting a frame, the sender starts the timer running. If it was al-
ready running, it will be reset to allow another full timer interval. The interval
should be chosen to allow enough time for the frame to get to the receiver, for the
receiver to process it in the worst case, and for the acknowledgement frame to
propagate back to the sender. Only when that interval has elapsed is it safe to as-
sume that either the transmitted frame or its acknowledgement has been lost, and
to send a duplicate. If the timeout interval is set too short, the sender will transmit
unnecessary frames. While these extra frames will not affect the correctness of
the protocol, they will hurt performance.
After transmitting a frame and starting the timer, the sender waits for some-
thing exciting to happen. Only three possibilities exist: an acknowledgement
frame arrives undamaged, a damaged acknowledgement frame staggers in, or the
timer expires. If a valid acknowledgement comes in, the sender fetches the next
packet from its network layer and puts it in the buffer, overwriting the previous
packet. It also advances the sequence number. If a damaged frame arrives or the


---

<a id="page-238"></a>

<!-- Page 238 of 888 -->

226 THE DATA LINK LAYER CHAP. 3
timer expires, neither the buffer nor the sequence number is changed so that a
duplicate can be sent. In all cases, the contents of the buffer (either the next pack-
et or a duplicate) are then sent.
When a valid frame arrives at the receiver, its sequence number is checked to
see if it is a duplicate. If not, it is accepted, passed to the network layer, and an
acknowledgement is generated. Duplicates and damaged frames are not passed to
the network layer, but they do cause the last correctly received frame to be
acknowledged to signal the sender to advance to the next frame or retransmit a
damaged frame.
### 3.4 SLIDING WINDOW PROTOCOLS
In the previous protocols, data frames were transmitted in one direction only.
In most practical situations, there is a need to transmit data in both directions.
One way of achieving full-duplex data transmission is to run two instances of one
of the previous protocols, each using a separate link for simplex data traffic (in
different directions). Each link is then comprised of a ''forward'' channel (for
data) and a ''reverse'' channel (for acknowledgements). In both cases the capaci-
ty of the reverse channel is almost entirely wasted.
A better idea is to use the same link for data in both directions. After all, in
protocols 2 and 3 it was already being used to transmit frames both ways, and the
reverse channel normally has the same capacity as the forward channel. In this
model the data frames from A to B are intermixed with the acknowledgement
frames from A to B. By looking at the kind field in the header of an incoming
frame, the receiver can tell whether the frame is data or an acknowledgement.
Although interleaving data and control frames on the same link is a big im-
provement over having two separate physical links, yet another improvement is
possible. When a data frame arrives, instead of immediately sending a separate
control frame, the receiver restrains itself and waits until the network layer passes
it the next packet. The acknowledgement is attached to the outgoing data frame
(using the ack field in the frame header). In effect, the acknowledgement gets a
free ride on the next outgoing data frame. The technique of temporarily delaying
outgoing acknowledgements so that they can be hooked onto the next outgoing
data frame is known as piggybacking.
The principal advantage of using piggybacking over having distinct acknowl-
edgement frames is a better use of the available channel bandwidth. The ack field
in the frame header costs only a few bits, whereas a separate frame would need a
header, the acknowledgement, and a checksum. In addition, fewer frames sent
generally means a lighter processing load at the receiver. In the next protocol to
be examined, the piggyback field costs only 1 bit in the frame header. It rarely
costs more than a few bits.
However, piggybacking introduces a complication not present with separate
acknowledgements. How long should the data link layer wait for a packet onto


---

<a id="page-239"></a>

<!-- Page 239 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 227
/* Protocol 3 (PAR) allows unidirectional data flow over an unreliable channel. */
#define MAX SEQ 1 /* must be 1 for protocol 3 */
typedef enum {frame arrival, cksum err, timeout} event type;
#include "protocol.h"
void sender3(void)
{
seq nr next frame to send; /* seq number of next outgoing frame */
frame s; /* scratch variable */
packet buffer; /* buffer for an outbound packet */
event type event;
next frame to send = 0; /* initialize outbound sequence numbers */
from network layer(&buffer); /* fetch first packet */
while (true) {
s.info = buffer; /* construct a frame for transmission */
s.seq = next frame to send; /* insert sequence number in frame */
to physical layer(&s); /* send it on its way */
start timer(s.seq); /* if answer takes too long, time out */
wait for event(&event); /* frame arrival, cksum err, timeout */
if (event == frame arrival) {
from physical layer(&s); /* get the acknowledgement */
if (s.ack == next frame to send) {
stop timer(s.ack); /* turn the timer off */
from network layer(&buffer); /* get the next one to send */
inc(next frame to send); /* invert next frame to send */
}
}
}
}
void receiver3(void)
{
seq nr frame expected;
frame r, s;
event type event;
frame expected = 0;
while (true) {
wait for event(&event); /* possibilities: frame arrival, cksum err */
if (event == frame arrival) { /* a valid frame has arrived */
from physical layer(&r); /* go get the newly arrived frame */
if (r.seq == frame expected) { /* this is what we have been waiting for */
to network layer(&r.info); /* pass the data to the network layer */
inc(frame expected); /* next time expect the other sequence nr */
}
s.ack = 1 − frame expected; /* tell which frame is being acked */
to physical layer(&s); /* send acknowledgement */
}
}
}
Figure 3-14. A positive acknowledgement with retransmission protocol.


---

<a id="page-240"></a>

<!-- Page 240 of 888 -->

228 THE DATA LINK LAYER CHAP. 3
which to piggyback the acknowledgement? If the data link layer waits longer
than the sender's timeout period, the frame will be retransmitted, defeating the
whole purpose of having acknowledgements. If the data link layer were an oracle
and could foretell the future, it would know when the next network layer packet
was going to come in and could decide either to wait for it or send a separate ac-
knowledgement immediately, depending on how long the projected wait was
going to be. Of course, the data link layer cannot foretell the future, so it must
resort to some ad hoc scheme, such as waiting a fixed number of milliseconds. If
a new packet arrives quickly, the acknowledgement is piggybacked onto it.
Otherwise, if no new packet has arrived by the end of this time period, the data
link layer just sends a separate acknowledgement frame.
The next three protocols are bidirectional protocols that belong to a class cal-
led sliding window protocols. The three differ among themselves in terms of ef-
ficiency, complexity, and buffer requirements, as discussed later. In these, as in
all sliding window protocols, each outbound frame contains a sequence number,
ranging from 0 up to some maximum. The maximum is usually 2n − 1 so the se-
quence number fits exactly in an n-bit field. The stop-and-wait sliding window
protocol uses n = 1, restricting the sequence numbers to 0 and 1, but more sophis-
ticated versions can use an arbitrary n.
The essence of all sliding window protocols is that at any instant of time, the
sender maintains a set of sequence numbers corresponding to frames it is permit-
ted to send. These frames are said to fall within the sending window. Similarly,
the receiver also maintains a receiving window corresponding to the set of frames
it is permitted to accept. The sender's window and the receiver's window need
not have the same lower and upper limits or even have the same size. In some
protocols they are fixed in size, but in others they can grow or shrink over the
course of time as frames are sent and received.
Although these protocols give the data link layer more freedom about the
order in which it may send and receive frames, we have definitely not dropped the
requirement that the protocol must deliver packets to the destination network layer
in the same order they were passed to the data link layer on the sending machine.
Nor have we changed the requirement that the physical communication channel is
''wire-like,'' that is, it must deliver all frames in the order sent.
The sequence numbers within the sender's window represent frames that have
been sent or can be sent but are as yet not acknowledged. Whenever a new packet
arrives from the network layer, it is given the next highest sequence number, and
the upper edge of the window is advanced by one. When an acknowledgement
comes in, the lower edge is advanced by one. In this way the window continu-
ously maintains a list of unacknowledged frames. Figure 3-15 shows an example.
Since frames currently within the sender's window may ultimately be lost or
damaged in transit, the sender must keep all of these frames in its memory for
possible retransmission. Thus, if the maximum window size is n, the sender needs
n buffers to hold the unacknowledged frames. If the window ever grows to its


---

<a id="page-241"></a>

<!-- Page 241 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 229
Sender 7 0 7 0 7 0 7 0
6 1 6 1 6 1 6 1
5 2 5 2 5 2 5 2
4 3 4 3 4 3 4 3
Receiver
7 0 7 0 7 0 7 0
6 1 6 1 6 1 6 1
5 2 5 2 5 2 5 2
4 3 4 3 4 3 4 3
(a) (b) (c) (d)
Figure 3-15. A sliding window of size 1, with a 3-bit sequence number. (a) Ini-
tially. (b) After the first frame has been sent. (c) After the first frame has been
received. (d) After the first acknowledgement has been received.
maximum size, the sending data link layer must forcibly shut off the network
layer until another buffer becomes free.
The receiving data link layer's window corresponds to the frames it may ac-
cept. Any frame falling within the window is put in the receiver's buffer. When a
frame whose sequence number is equal to the lower edge of the window is re-
ceived, it is passed to the network layer and the window is rotated by one. Any
frame falling outside the window is discarded. In all of these cases, a subsequent
acknowledgement is generated so that the sender may work out how to proceed.
Note that a window size of 1 means that the data link layer only accepts frames in
order, but for larger windows this is not so. The network layer, in contrast, is al-
ways fed data in the proper order, regardless of the data link layer's window size.
Figure 3-15 shows an example with a maximum window size of 1. Initially,
no frames are outstanding, so the lower and upper edges of the sender's window
are equal, but as time goes on, the situation progresses as shown. Unlike the send-
er's window, the receiver's window always remains at its initial size, rotating as
the next frame is accepted and delivered to the network layer.
#### 3.4.1 A One-Bit Sliding Window Protocol
Before tackling the general case, let us examine a sliding window protocol
with a window size of 1. Such a protocol uses stop-and-wait since the sender
transmits a frame and waits for its acknowledgement before sending the next one.


---

<a id="page-242"></a>

<!-- Page 242 of 888 -->

230 THE DATA LINK LAYER CHAP. 3
Figure 3-16 depicts such a protocol. Like the others, it starts out by defining
some variables. Next frame to send tells which frame the sender is trying to
send. Similarly, frame expected tells which frame the receiver is expecting. In
both cases, 0 and 1 are the only possibilities.
/* Protocol 4 (Sliding window) is bidirectional. */
#define MAX SEQ 1 /* must be 1 for protocol 4 */
typedef enum {frame arrival, cksum err, timeout} event type;
#include "protocol.h"
void protocol4 (void)
{
seq nr next frame to send; /* 0 or 1 only */
seq nr frame expected; /* 0 or 1 only */
frame r, s; /* scratch variables */
packet buffer; /* current packet being sent */
event type event;
next frame to send = 0; /* next frame on the outbound stream */
frame expected = 0; /* frame expected next */
from network layer(&buffer); /* fetch a packet from the network layer */
s.info = buffer; /* prepare to send the initial frame */
s.seq = next frame to send; /* insert sequence number into frame */
s.ack = 1 − frame expected; /* piggybacked ack */
to physical layer(&s); /* transmit the frame */
start timer(s.seq); /* start the timer running */
while (true) {
wait for event(&event); /* frame arrival, cksum err, or timeout */
if (event == frame arrival) { /* a frame has arrived undamaged */
from physical layer(&r); /* go get it */
if (r.seq == frame expected) { /* handle inbound frame stream */
to network layer(&r.info); /* pass packet to network layer */
inc(frame expected); /* invert seq number expected next */
}
if (r.ack == next frame to send) { /* handle outbound frame stream */
stop timer(r.ack); /* turn the timer off */
from network layer(&buffer); /* fetch new pkt from network layer */
inc(next frame to send); /* invert sender's sequence number */
}
}
s.info = buffer; /* construct outbound frame */
s.seq = next frame to send; /* insert sequence number into it */
s.ack = 1 − frame expected; /* seq number of last received frame */
to physical layer(&s); /* transmit a frame */
start timer(s.seq); /* start the timer running */
}
}
Figure 3-16. A 1-bit sliding window protocol.


---

<a id="page-243"></a>

<!-- Page 243 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 231
Under normal circumstances, one of the two data link layers goes first and
transmits the first frame. In other words, only one of the data link layer programs
should contain the to physical layer and start timer procedure calls outside the
main loop. The starting machine fetches the first packet from its network layer,
builds a frame from it, and sends it. When this (or any) frame arrives, the receiv-
ing data link layer checks to see if it is a duplicate, just as in protocol 3. If the
frame is the one expected, it is passed to the network layer and the receiver's win-
dow is slid up.
The acknowledgement field contains the number of the last frame received
without error. If this number agrees with the sequence number of the frame the
sender is trying to send, the sender knows it is done with the frame stored in buff-
er and can fetch the next packet from its network layer. If the sequence number
disagrees, it must continue trying to send the same frame. Whenever a frame is
received, a frame is also sent back.
Now let us examine protocol 4 to see how resilient it is to pathological scen-
arios. Assume that computer A is trying to send its frame 0 to computer B and
that B is trying to send its frame 0 to A. Suppose that A sends a frame to B, but
A's timeout interval is a little too short. Consequently, A may time out repeatedly,
sending a series of identical frames, all with seq = 0 and ack = 1.
When the first valid frame arrives at computer B, it will be accepted and
frame expected will be set to a value of 1. All the subsequent frames received
will be rejected because B is now expecting frames with sequence number 1, not
0. Furthermore, since all the duplicates will have ack = 1 and B is still waiting for
an acknowledgement of 0, B will not go and fetch a new packet from its network
layer.
After every rejected duplicate comes in, B will send A a frame containing
seq = 0 and ack = 0. Eventually, one of these will arrive correctly at A, causing A
to begin sending the next packet. No combination of lost frames or premature
timeouts can cause the protocol to deliver duplicate packets to either network
layer, to skip a packet, or to deadlock. The protocol is correct.
However, to show how subtle protocol interactions can be, we note that a pe-
culiar situation arises if both sides simultaneously send an initial packet. This
synchronization difficulty is illustrated by Fig. 3-17. In part (a), the normal opera-
tion of the protocol is shown. In (b) the peculiarity is illustrated. If B waits for
A's first frame before sending one of its own, the sequence is as shown in (a), and
every frame is accepted.
However, if A and B simultaneously initiate communication, their first frames
cross, and the data link layers then get into situation (b). In (a) each frame arrival
brings a new packet for the network layer; there are no duplicates. In (b) half of
the frames contain duplicates, even though there are no transmission errors. Simi-
lar situations can occur as a result of premature timeouts, even when one side
clearly starts first. In fact, if multiple premature timeouts occur, frames may be
sent three or more times, wasting valuable bandwidth.


---

<a id="page-244"></a>

<!-- Page 244 of 888 -->

232 THE DATA LINK LAYER CHAP. 3
A sends (0, 1, A0) A sends (0, 1, A0) B sends (0, 1, B0)
B gets (0, 1, A0)* B gets (0, 1, A0)*
B sends (0, 0, B0) B sends (0, 0, B0)
A gets (0, 0, B0)*
A gets (0, 1, B0)*
A sends (1, 0, A1)
A sends (0, 0, A0)
B gets (1, 0, A1)*
B sends (1, 1, B1) B gets (0, 0, A0)
A gets (1, 1, B1)* B sends (1, 0, B1)
A sends (0, 1, A2) A gets (0, 0, B0)
B gets (0, 1, A2)* A sends (1, 0, A1)
B sends (0, 0, B2) B gets (1, 0, A1)*
A gets (0, 0, B2)* B sends (1, 1, B1)
A sends (1, 0, A3)
B gets (1, 0, A3)* A gets (1, 0, B1)*
A sends (1, 1, A1)
B sends (1, 1, B3) B gets (1, 1, A1)
B sends (0, 1, B2)
Time
(a) (b)
Figure 3-17. Two scenarios for protocol 4. (a) Normal case. (b) Abnormal
case. The notation is (seq, ack, packet number). An asterisk indicates where a
network layer accepts a packet.
#### 3.4.2 A Protocol Using Go-Back-N
Until now we have made the tacit assumption that the transmission time re-
quired for a frame to arrive at the receiver plus the transmission time for the ac-
knowledgement to come back is negligible. Sometimes this assumption is clearly
false. In these situations the long round-trip time can have important implications
for the efficiency of the bandwidth utilization. As an example, consider a 50-kbps
satellite channel with a 500-msec round-trip propagation delay. Let us imagine
trying to use protocol 4 to send 1000-bit frames via the satellite. At t = 0 the
sender starts sending the first frame. At t = 20 msec the frame has been com-
pletely sent. Not until t = 270 msec has the frame fully arrived at the receiver,
and not until t = 520 msec has the acknowledgement arrived back at the sender,
under the best of circumstances (of no waiting in the receiver and a short ac-
knowledgement frame). This means that the sender was blocked 500/520 or 96%
of the time. In other words, only 4% of the available bandwidth was used. Clear-
ly, the combination of a long transit time, high bandwidth, and short frame length
is disastrous in terms of efficiency.
The problem described here can be viewed as a consequence of the rule re-
quiring a sender to wait for an acknowledgement before sending another frame. If
we relax that restriction, much better efficiency can be achieved. Basically, the
solution lies in allowing the sender to transmit up to w frames before blocking, in-
stead of just 1. With a large enough choice of w the sender will be able to con-
tinuously transmit frames since the acknowledgements will arrive for previous
frames before the window becomes full, preventing the sender from blocking.


---

<a id="page-245"></a>

<!-- Page 245 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 233
To find an appropriate value for w we need to know how many frames can fit
inside the channel as they propagate from sender to receiver. This capacity is de-
termined by the bandwidth in bits/sec multiplied by the one-way transit time, or
the bandwidth-delay product of the link. We can divide this quantity by the
number of bits in a frame to express it as a number of frames. Call this quantity
BD. Then w should be set to 2BD + 1. Twice the bandwidth-delay is the number
of frames that can be outstanding if the sender continuously sends frames when
the round-trip time to receive an acknowledgement is considered. The ''+1'' is
because an acknowledgement frame will not be sent until after a complete frame
is received.
For the example link with a bandwidth of 50 kbps and a one-way transit time
of 250 msec, the bandwidth-delay product is 12.5 kbit or 12.5 frames of 1000 bits
each. 2BD + 1 is then 26 frames. Assume the sender begins sending frame 0 as
before and sends a new frame every 20 msec. By the time it has finished sending
26 frames, at t = 520 msec, the acknowledgement for frame 0 will have just arri-
ved. Thereafter, acknowledgements will arrive every 20 msec, so the sender will
always get permission to continue just when it needs it. From then onwards, 25 or
26 unacknowledged frames will always be outstanding. Put in other terms, the
sender's maximum window size is 26.
For smaller window sizes, the utilization of the link will be less than 100%
since the sender will be blocked sometimes. We can write the utilization as the
fraction of time that the sender is not blocked:
w
link utilization ≤
1 + 2BD
This value is an upper bound because it does not allow for any frame processing
time and treats the acknowledgement frame as having zero length, since it is
usually short. The equation shows the need for having a large window w when-
ever the bandwidth-delay product is large. If the delay is high, the sender will ra-
pidly exhaust its window even for a moderate bandwidth, as in the satellite ex-
ample. If the bandwidth is high, even for a moderate delay the sender will
exhaust its window quickly unless it has a large window (e.g., a 1-Gbps link with
1-msec delay holds 1 megabit). With stop-and-wait for which w = 1, if there is
even one frame's worth of propagation delay the efficiency will be less than 50%.
This technique of keeping multiple frames in flight is an example of pipelin-
ing. Pipelining frames over an unreliable communication channel raises some
serious issues. First, what happens if a frame in the middle of a long stream is
damaged or lost? Large numbers of succeeding frames will arrive at the receiver
before the sender even finds out that anything is wrong. When a damaged frame
arrives at the receiver, it obviously should be discarded, but what should the re-
ceiver do with all the correct frames following it? Remember that the receiving
data link layer is obligated to hand packets to the network layer in sequence.


---

<a id="page-246"></a>

<!-- Page 246 of 888 -->

234 THE DATA LINK LAYER CHAP. 3
Two basic approaches are available for dealing with errors in the presence of
pipelining, both of which are shown in Fig. 3-18.
Timeout interval
0 1 2 3 4 5 6 7 8 2 3 4 5 6 7 8 9
0 1 2 3 4 5 6 7
A c k A c k A c k A c k A c k A c k A c k A c k
0 1 E D D D D D D 2 3 4 5 6 7 8
Error Frames discarded by data link layer
Time
(a)
0 1 2 3 4 5 2 6 7 8 9 10 11 12 13 14 15
A c k 0 A c k 1 N a k 2 A c k 5 A c k 6 A c k 7 A c k 8 A c k 9 A c k 1 0 A c k 1 1 A c k 1 2 A c k 1 3
0 1 E 3 4 5 2 6 7 8 9 10 11 12 13 14
Error Frames buffered
by data link layer
(b)
Figure 3-18. Pipelining and error recovery. Effect of an error when
(a) receiver's window size is 1 and (b) receiver's window size is large.
One option, called go-back-n, is for the receiver simply to discard all subsequent
frames, sending no acknowledgements for the discarded frames. This strategy
corresponds to a receive window of size 1. In other words, the data link layer
refuses to accept any frame except the next one it must give to the network layer.
If the sender's window fills up before the timer runs out, the pipeline will begin to
empty. Eventually, the sender will time out and retransmit all unacknowledged
frames in order, starting with the damaged or lost one. This approach can waste a
lot of bandwidth if the error rate is high.
In Fig. 3-18(b) we see go-back-n for the case in which the receiver's window
is large. Frames 0 and 1 are correctly received and acknowledged. Frame 2,
however, is damaged or lost. The sender, unaware of this problem, continues to
send frames until the timer for frame 2 expires. Then it backs up to frame 2 and
starts over with it, sending 2, 3, 4, etc. all over again.
The other general strategy for handling errors when frames are pipelined is
called selective repeat. When it is used, a bad frame that is received is discarded,
but any good frames received after it are accepted and buffered. When the sender
times out, only the oldest unacknowledged frame is retransmitted. If that frame


---

<a id="page-247"></a>

<!-- Page 247 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 235
arrives correctly, the receiver can deliver to the network layer, in sequence, all the
frames it has buffered. Selective repeat corresponds to a receiver window larger
than 1. This approach can require large amounts of data link layer memory if the
window is large.
Selective repeat is often combined with having the receiver send a negative
acknowledgement (NAK) when it detects an error, for example, when it receives a
checksum error or a frame out of sequence. NAKs stimulate retransmission be-
fore the corresponding timer expires and thus improve performance.
In Fig. 3-18(b), frames 0 and 1 are again correctly received and acknowledged
and frame 2 is lost. When frame 3 arrives at the receiver, the data link layer there
notices that it has missed a frame, so it sends back a NAK for 2 but buffers 3.
When frames 4 and 5 arrive, they, too, are buffered by the data link layer instead
of being passed to the network layer. Eventually, the NAK 2 gets back to the
sender, which immediately resends frame 2. When that arrives, the data link layer
now has 2, 3, 4, and 5 and can pass all of them to the network layer in the correct
order. It can also acknowledge all frames up to and including 5, as shown in the
figure. If the NAK should get lost, eventually the sender will time out for frame 2
and send it (and only it) of its own accord, but that may be a quite a while later.
These two alternative approaches are trade-offs between efficient use of band-
width and data link layer buffer space. Depending on which resource is scarcer,
one or the other can be used. Figure 3-19 shows a go-back-n protocol in which
the receiving data link layer only accepts frames in order; frames following an
error are discarded. In this protocol, for the first time we have dropped the as-
sumption that the network layer always has an infinite supply of packets to send.
When the network layer has a packet it wants to send, it can cause a net-
work layer ready event to happen. However, to enforce the flow control limit on
the sender window or the number of unacknowledged frames that may be out-
standing at any time, the data link layer must be able to keep the network layer
from bothering it with more work. The library procedures enable network layer
and disable network layer do this job.
The maximum number of frames that may be outstanding at any instant is not
the same as the size of the sequence number space. For go-back-n, MAX SEQ
frames may be outstanding at any instant, even though there are MAX SEQ + 1
distinct sequence numbers (which are 0, 1, . . . , MAX SEQ). We will see an
even tighter restriction for the next protocol, selective repeat. To see why this res-
triction is required, consider the following scenario with MAX SEQ = 7:
1. The sender sends frames 0 through 7.
2. A piggybacked acknowledgement for 7 comes back to the sender.
3. The sender sends another eight frames, again with sequence numbers
0 through 7.
4. Now another piggybacked acknowledgement for frame 7 comes in.


---

<a id="page-248"></a>

<!-- Page 248 of 888 -->

236 THE DATA LINK LAYER CHAP. 3
/* Protocol 5 (Go-back-n) allows multiple outstanding frames. The sender may transmit up
to MAX SEQ frames without waiting for an ack. In addition, unlike in the previous
protocols, the network layer is not assumed to have a new packet all the time. Instead,
the network layer causes a network layer ready event when there is a packet to send. */
#define MAX SEQ 7
typedef enum {frame arrival, cksum err, timeout, network layer ready} event type;
#include "protocol.h"
static boolean between(seq nr a, seq nr b, seq nr c)
{
/* Return true if a <= b < c circularly; false otherwise. */
if (((a <= b) && (b < c)) || ((c < a) && (a <= b)) || ((b < c) && (c < a)))
return(true);
else
return(false);
}
static void send data(seq nr frame nr, seq nr frame expected, packet buffer[ ])
{
/* Construct and send a data frame. */
frame s; /* scratch variable */
s.info = buffer[frame nr]; /* insert packet into frame */
s.seq = frame nr; /* insert sequence number into frame */
s.ack = (frame expected + MAX SEQ) % (MAX SEQ + 1); /* piggyback ack */
to physical layer(&s); /* transmit the frame */
start timer(frame nr); /* start the timer running */
}
void protocol5(void)
{
seq nr next frame to send; /* MAX SEQ > 1; used for outbound stream */
seq nr ack expected; /* oldest frame as yet unacknowledged */
seq nr frame expected; /* next frame expected on inbound stream */
frame r; /* scratch variable */
packet buffer[MAX SEQ + 1]; /* buffers for the outbound stream */
seq nr nbuffered; /* number of output buffers currently in use */
seq nr i; /* used to index into the buffer array */
event type event;
enable network layer(); /* allow network layer ready events */
ack expected = 0; /* next ack expected inbound */
next frame to send = 0; /* next frame going out */
frame expected = 0; /* number of frame expected inbound */
nbuffered = 0; /* initially no packets are buffered */
while (true) {
wait for event(&event); /* four possibilities: see event type above */


---

<a id="page-249"></a>

<!-- Page 249 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 237
switch(event) {
case network layer ready: /* the network layer has a packet to send */
/* Accept, save, and transmit a new frame. */
from network layer(&buffer[next frame to send]); /* fetch new packet */
nbuffered = nbuffered + 1; /* expand the sender's window */
send data(next frame to send, frame expected, buffer);/* transmit the frame */
inc(next frame to send); /* advance sender's upper window edge */
break;
case frame arrival: /* a data or control frame has arrived */
from physical layer(&r); /* get incoming frame from physical layer */
if (r.seq == frame expected) {
/* Frames are accepted only in order. */
to network layer(&r.info); /* pass packet to network layer */
inc(frame expected); /* advance lower edge of receiver's window */
}
/* Ack n implies n − 1, n − 2, etc. Check for this. */
while (between(ack expected, r.ack, next frame to send)) {
/* Handle piggybacked ack. */
nbuffered = nbuffered − 1; /* one frame fewer buffered */
stop timer(ack expected); /* frame arrived intact; stop timer */
inc(ack expected); /* contract sender's window */
}
break;
case cksum err: break; /* just ignore bad frames */
case timeout: /* trouble; retransmit all outstanding frames */
next frame to send = ack expected; /* start retransmitting here */
for (i = 1; i <= nbuffered; i++) {
send data(next frame to send, frame expected, buffer);/* resend frame */
inc(next frame to send); /* prepare to send the next one */
}
}
if (nbuffered < MAX SEQ)
enable network layer();
else
disable network layer();
}
}
Figure 3-19. A sliding window protocol using go-back-n.
The question is this: did all eight frames belonging to the second batch arrive suc-
cessfully, or did all eight get lost (counting discards following an error as lost)?
In both cases the receiver would be sending frame 7 as the acknowledgement.


---

<a id="page-250"></a>

<!-- Page 250 of 888 -->

238 THE DATA LINK LAYER CHAP. 3
The sender has no way of telling. For this reason the maximum number of out-
standing frames must be restricted to MAX SEQ.
Although protocol 5 does not buffer the frames arriving after an error, it does
not escape the problem of buffering altogether. Since a sender may have to
retransmit all the unacknowledged frames at a future time, it must hang on to all
transmitted frames until it knows for sure that they have been accepted by the re-
ceiver. When an acknowledgement comes in for frame n, frames n − 1, n − 2,
and so on are also automatically acknowledged. This type of acknowledgement is
called a cumulative acknowledgement. This property is especially important
when some of the previous acknowledgement-bearing frames were lost or gar-
bled. Whenever any acknowledgement comes in, the data link layer checks to see
if any buffers can now be released. If buffers can be released (i.e., there is some
room available in the window), a previously blocked network layer can now be al-
lowed to cause more network layer ready events.
For this protocol, we assume that there is always reverse traffic on which to
piggyback acknowledgements. Protocol 4 does not need this assumption since it
sends back one frame every time it receives a frame, even if it has already sent
that frame. In the next protocol we will solve the problem of one-way traffic in an
elegant way.
Because protocol 5 has multiple outstanding frames, it logically needs multi-
ple timers, one per outstanding frame. Each frame times out independently of all
the other ones. However, all of these timers can easily be simulated in software
using a single hardware clock that causes interrupts periodically. The pending
timeouts form a linked list, with each node of the list containing the number of
clock ticks until the timer expires, the frame being timed, and a pointer to the next
node.
Real
time
10:00:00.000 10:00:00.005
5 1 8 2 6 3 8 2 6 3
Pointer to next timeout
Frame being timed
Ticks to go
(a) (b)
Figure 3-20. Simulation of multiple timers in software. (a) The queued time-
outs. (b) The situation after the first timeout has expired.
As an illustration of how the timers could be implemented, consider the ex-
ample of Fig. 3-20(a). Assume that the clock ticks once every 1 msec. Initially,


---

<a id="page-251"></a>

<!-- Page 251 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 239
the real time is 10:00:00.000; three timeouts are pending, at 10:00:00.005,
10:00:00.013, and 10:00:00.019. Every time the hardware clock ticks, the real
time is updated and the tick counter at the head of the list is decremented. When
the tick counter becomes zero, a timeout is caused and the node is removed from
the list, as shown in Fig. 3-20(b). Although this organization requires the list to
be scanned when start timer or stop timer is called, it does not require much
work per tick. In protocol 5, both of these routines have been given a parameter
indicating which frame is to be timed.
#### 3.4.3 A Protocol Using Selective Repeat
The go-back-n protocol works well if errors are rare, but if the line is poor it
wastes a lot of bandwidth on retransmitted frames. An alternative strategy, the
selective repeat protocol, is to allow the receiver to accept and buffer the frames
following a damaged or lost one.
In this protocol, both sender and receiver maintain a window of outstanding
and acceptable sequence numbers, respectively. The sender's window size starts
out at 0 and grows to some predefined maximum. The receiver's window, in con-
trast, is always fixed in size and equal to the predetermined maximum. The re-
ceiver has a buffer reserved for each sequence number within its fixed window.
Associated with each buffer is a bit (arrived ) telling whether the buffer is full or
empty. Whenever a frame arrives, its sequence number is checked by the function
between to see if it falls within the window. If so and if it has not already been re-
ceived, it is accepted and stored. This action is taken without regard to whether or
not the frame contains the next packet expected by the network layer. Of course,
it must be kept within the data link layer and not passed to the network layer until
all the lower-numbered frames have already been delivered to the network layer
in the correct order. A protocol using this algorithm is given in Fig. 3-21.
Nonsequential receive introduces further constraints on frame sequence num-
bers compared to protocols in which frames are only accepted in order. We can
illustrate the trouble most easily with an example. Suppose that we have a 3-bit
sequence number, so that the sender is permitted to transmit up to seven frames
before being required to wait for an acknowledgement. Initially, the sender's and
receiver's windows are as shown in Fig. 3-22(a). The sender now transmits
frames 0 through 6. The receiver's window allows it to accept any frame with a
sequence number between 0 and 6 inclusive. All seven frames arrive correctly, so
the receiver acknowledges them and advances its window to allow receipt of 7, 0,
1, 2, 3, 4, or 5, as shown in Fig. 3-22(b). All seven buffers are marked empty.
It is at this point that disaster strikes in the form of a lightning bolt hitting the
telephone pole and wiping out all the acknowledgements. The protocol should
operate correctly despite this disaster. The sender eventually times out and re-
transmits frame 0. When this frame arrives at the receiver, a check is made to see
if it falls within the receiver's window. Unfortunately, in Fig. 3-22(b) frame 0 is


---

<a id="page-252"></a>

<!-- Page 252 of 888 -->

240 THE DATA LINK LAYER CHAP. 3
/* Protocol 6 (Selective repeat) accepts frames out of order but passes packets to the
network layer in order. Associated with each outstanding frame is a timer. When the timer
expires, only that frame is retransmitted, not all the outstanding frames, as in protocol 5. */
#define MAX SEQ 7 /* should be 2ˆn − 1 */
#define NR BUFS ((MAX SEQ + 1)/2)
typedef enum {frame arrival, cksum err, timeout, network layer ready, ack timeout} event type;
#include "protocol.h"
boolean no nak = true; /* no nak has been sent yet */
seq nr oldest frame = MAX SEQ + 1; /* initial value is only for the simulator */
static boolean between(seq nr a, seq nr b, seq nr c)
{
/* Same as between in protocol 5, but shorter and more obscure. */
return ((a <= b) && (b < c)) || ((c < a) && (a <= b)) || ((b < c) && (c < a));
}
static void send frame(frame kind fk, seq nr frame nr, seq nr frame expected, packet buffer[ ])
{
/* Construct and send a data, ack, or nak frame. */
frame s; /* scratch variable */
s.kind = fk; /* kind == data, ack, or nak */
if (fk == data) s.info = buffer[frame nr % NR BUFS];
s.seq = frame nr; /* only meaningful for data frames */
s.ack = (frame expected + MAX SEQ) % (MAX SEQ + 1);
if (fk == nak) no nak = false; /* one nak per frame, please */
to physical layer(&s); /* transmit the frame */
if (fk == data) start timer(frame nr % NR BUFS);
stop ack timer(); /* no need for separate ack frame */
}
void protocol6(void)
{
seq nr ack expected; /* lower edge of sender's window */
seq nr next frame to send; /* upper edge of sender's window + 1 */
seq nr frame expected; /* lower edge of receiver's window */
seq nr too far; /* upper edge of receiver's window + 1 */
int i; /* index into buffer pool */
frame r; /* scratch variable */
packet out buf[NR BUFS]; /* buffers for the outbound stream */
packet in buf[NR BUFS]; /* buffers for the inbound stream */
boolean arrived[NR BUFS]; /* inbound bit map */
seq nr nbuffered; /* how many output buffers currently used */
event type event;
enable network layer(); /* initialize */
ack expected = 0; /* next ack expected on the inbound stream */
next frame to send = 0; /* number of next outgoing frame */
frame expected = 0;
too far = NR BUFS;
nbuffered = 0; /* initially no packets are buffered */
for (i = 0; i < NR BUFS; i++) arrived[i] = false;


---

<a id="page-253"></a>

<!-- Page 253 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 241
while (true) {
wait for event(&event); /* five possibilities: see event type above */
switch(event) {
case network layer ready: /* accept, save, and transmit a new frame */
nbuffered = nbuffered + 1; /* expand the window */
from network layer(&out buf[next frame to send % NR BUFS]); /* fetch new packet */
send frame(data, next frame to send, frame expected, out buf);/* transmit the frame */
inc(next frame to send); /* advance upper window edge */
break;
case frame arrival: /* a data or control frame has arrived */
from physical layer(&r); /* fetch incoming frame from physical layer */
if (r.kind == data) {
/* An undamaged frame has arrived. */
if ((r.seq != frame expected) && no nak)
send frame(nak, 0, frame expected, out buf); else start ack timer();
if (between(frame expected,r.seq,too far) && (arrived[r.seq%NR BUFS]==false)) {
/* Frames may be accepted in any order. */
arrived[r.seq % NR BUFS] = true; /* mark buffer as full */
in buf[r.seq % NR BUFS] = r.info; /* insert data into buffer */
while (arrived[frame expected % NR BUFS]) {
/* Pass frames and advance window. */
to network layer(&in buf[frame expected % NR BUFS]);
no nak = true;
arrived[frame expected % NR BUFS] = false;
inc(frame expected); /* advance lower edge of receiver's window */
inc(too far); /* advance upper edge of receiver's window */
start ack timer(); /* to see if a separate ack is needed */
}
}
}
if((r.kind==nak) && between(ack expected,(r.ack+1)%(MAX SEQ+1),next frame to send))
send frame(data, (r.ack+1) % (MAX SEQ + 1), frame expected, out buf);
while (between(ack expected, r.ack, next frame to send)) {
nbuffered = nbuffered − 1; /* handle piggybacked ack */
stop timer(ack expected % NR BUFS); /* frame arrived intact */
inc(ack expected); /* advance lower edge of sender's window */
}
break;
case cksum err:
if (no nak) send frame(nak, 0, frame expected, out buf); /* damaged frame */
break;
case timeout:
send frame(data, oldest frame, frame expected, out buf); /* we timed out */
break;
case ack timeout:
send frame(ack,0,frame expected, out buf); /* ack timer expired; send ack */
}
if (nbuffered < NR BUFS) enable network layer(); else disable network layer();
}
}
Figure 3-21. A sliding window protocol using selective repeat.


---

<a id="page-254"></a>

<!-- Page 254 of 888 -->

242 THE DATA LINK LAYER CHAP. 3
within the new window, so it is accepted as a new frame. The receiver also sends
a (piggybacked) acknowledgement for frame 6, since 0 through 6 have been re-
ceived.
The sender is happy to learn that all its transmitted frames did actually arrive
correctly, so it advances its window and immediately sends frames 7, 0, 1, 2, 3, 4,
and 5. Frame 7 will be accepted by the receiver and its packet will be passed di-
rectly to the network layer. Immediately thereafter, the receiving data link layer
checks to see if it has a valid frame 0 already, discovers that it does, and passes
the old buffered packet to the network layer as if it were a new packet. Conse-
quently, the network layer gets an incorrect packet, and the protocol fails.
The essence of the problem is that after the receiver advanced its window, the
new range of valid sequence numbers overlapped the old one. Consequently, the
following batch of frames might be either duplicates (if all the acknowledgements
were lost) or new ones (if all the acknowledgements were received). The poor re-
ceiver has no way of distinguishing these two cases.
The way out of this dilemma lies in making sure that after the receiver has ad-
vanced its window there is no overlap with the original window. To ensure that
there is no overlap, the maximum window size should be at most half the range of
the sequence numbers. This situation is shown in Fig. 3-22(c) and Fig. 3-22(d).
With 3 bits, the sequence numbers range from 0 to 7. Only four unacknowledged
frames should be outstanding at any instant. That way, if the receiver has just ac-
cepted frames 0 through 3 and advanced its window to permit acceptance of
frames 4 through 7, it can unambiguously tell if subsequent frames are retransmis-
sions (0 through 3) or new ones (4 through 7). In general, the window size for
protocol 6 will be (MAX SEQ + 1)/2.
An interesting question is: how many buffers must the receiver have? Under
no conditions will it ever accept frames whose sequence numbers are below the
lower edge of the window or frames whose sequence numbers are above the upper
edge of the window. Consequently, the number of buffers needed is equal to the
window size, not to the range of sequence numbers. In the preceding example of
a 3-bit sequence number, four buffers, numbered 0 through 3, are needed. When
frame i arrives, it is put in buffer i mod 4. Notice that although i and (i + 4) mod
4 are ''competing'' for the same buffer, they are never within the window at the
same time, because that would imply a window size of at least 5.
For the same reason, the number of timers needed is equal to the number of
buffers, not to the size of the sequence space. Effectively, a timer is associated
with each buffer. When the timer runs out, the contents of the buffer are retrans-
mitted.
Protocol 6 also relaxes the implicit assumption that the channel is heavily
loaded. We made this assumption in protocol 5 when we relied on frames being
sent in the reverse direction on which to piggyback acknowledgements. If the re-
verse traffic is light, the acknowledgements may be held up for a long period of
time, which can cause problems. In the extreme, if there is a lot of traffic in one


---

<a id="page-255"></a>

<!-- Page 255 of 888 -->

SEC. 3.4 SLIDING WINDOW PROTOCOLS 243
Sender 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
Receiver 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
(a) (b) (c) (d)
Figure 3-22. (a) Initial situation with a window of size7. (b) After 7 frames
have been sent and received but not acknowledged. (c) Initial situation with a
window size of 4. (d) After 4 frames have been sent and received but not
acknowledged.
direction and no traffic in the other direction, the protocol will block when the
sender window reaches its maximum.
To relax this assumption, an auxiliary timer is started by start ack timer after
an in-sequence data frame arrives. If no reverse traffic has presented itself before
this timer expires, a separate acknowledgement frame is sent. An interrupt due to
the auxiliary timer is called an ack timeout event. With this arrangement, traffic
flow in only one direction is possible because the lack of reverse data frames onto
which acknowledgements can be piggybacked is no longer an obstacle. Only one
auxiliary timer exists, and if start ack timer is called while the timer is running, it
has no effect. The timer is not reset or extended since its purpose is to provide
some minimum rate of acknowledgements.
It is essential that the timeout associated with the auxiliary timer be appreci-
ably shorter than the timeout used for timing out data frames. This condition is
required to ensure that a correctly received frame is acknowledged early enough
that the frame's retransmission timer does not expire and retransmit the frame.
Protocol 6 uses a more efficient strategy than protocol 5 for dealing with er-
rors. Whenever the receiver has reason to suspect that an error has occurred, it
sends a negative acknowledgement (NAK) frame back to the sender. Such a
frame is a request for retransmission of the frame specified in the NAK. In two
cases, the receiver should be suspicious: when a damaged frame arrives or a frame
other than the expected one arrives (potential lost frame). To avoid making multi-
ple requests for retransmission of the same lost frame, the receiver should keep
track of whether a NAK has already been sent for a given frame. The variable
no nak in protocol 6 is true if no NAK has been sent yet for frame expected. If
the NAK gets mangled or lost, no real harm is done, since the sender will eventu-
ally time out and retransmit the missing frame anyway. If the wrong frame ar-
rives after a NAK has been sent and lost, no nak will be true and the auxiliary
timer will be started. When it expires, an ACK will be sent to resynchronize the
sender to the receiver's current status.


---

<a id="page-256"></a>

<!-- Page 256 of 888 -->

244 THE DATA LINK LAYER CHAP. 3
In some situations, the time required for a frame to propagate to the destina-
tion, be processed there, and have the acknowledgement come back is (nearly)
constant. In these situations, the sender can adjust its timer to be ''tight,'' just
slightly larger than the normal time interval expected between sending a frame
and receiving its acknowledgement. NAKs are not useful in this case.
However, in other situations the time can be highly variable. For example, if
the reverse traffic is sporadic, the time before acknowledgement will be shorter
when there is reverse traffic and longer when there is not. The sender is faced
with the choice of either setting the interval to a small value (and risking unneces-
sary retransmissions), or setting it to a large value (and going idle for a long
period after an error). Both choices waste bandwidth. In general, if the standard
deviation of the acknowledgement interval is large compared to the interval itself,
the timer is set ''loose'' to be conservative. NAKs can then appreciably speed up
retransmission of lost or damaged frames.
Closely related to the matter of timeouts and NAKs is the question of deter-
mining which frame caused a timeout. In protocol 5, it is always ack expected,
because it is always the oldest. In protocol 6, there is no trivial way to determine
who timed out. Suppose that frames 0 through 4 have been transmitted, meaning
that the list of outstanding frames is 01234, in order from oldest to youngest.
Now imagine that 0 times out, 5 (a new frame) is transmitted, 1 times out, 2 times
out, and 6 (another new frame) is transmitted. At this point the list of outstanding
frames is 3405126, from oldest to youngest. If all inbound traffic (i.e., acknowl-
edgement-bearing frames) is lost for a while, the seven outstanding frames will
time out in that order.
To keep the example from getting even more complicated than it already is,
we have not shown the timer administration. Instead, we just assume that the
variable oldest frame is set upon timeout to indicate which frame timed out.
### 3.5 EXAMPLE DATA LINK PROTOCOLS
Within a single building, LANs are widely used for interconnection, but most
wide-area network infrastructure is built up from point-to-point lines. In Chap. 4,
we will look at LANs. Here we will examine the data link protocols found on
point-to-point lines in the Internet in two common situations. The first situation is
when packets are sent over SONET optical fiber links in wide-area networks.
These links are widely used, for example, to connect routers in the different loca-
tions of an ISP's network.
The second situation is for ADSL links running on the local loop of the tele-
phone network at the edge of the Internet. These links connect millions of individ-
uals and businesses to the Internet.
The Internet needs point-to-point links for these uses, as well as dial-up mo-
dems, leased lines, and cable modems, and so on. A standard protocol called PPP


---

<a id="page-257"></a>

<!-- Page 257 of 888 -->

SEC. 3.5 EXAMPLE DATA LINK PROTOCOLS 245
(Point-to-Point Protocol) is used to send packets over these links. PPP is de-
fined in RFC 1661 and further elaborated in RFC 1662 and other RFCs (Simpson,
1994a, 1994b). SONET and ADSL links both apply PPP, but in different ways.
#### 3.5.1 Packet over SONET
SONET, which we covered in Sec. 2.6.4, is the physical layer protocol that is
most commonly used over the wide-area optical fiber links that make up the back-
bone of communications networks, including the telephone system. It provides a
bitstream that runs at a well-defined rate, for example 2.4 Gbps for an OC-48 link.
This bitstream is organized as fixed-size byte payloads that recur every 125 µsec,
whether or not there is user data to send.
To carry packets across these links, some framing mechanism is needed to
distinguish occasional packets from the continuous bitstream in which they are
transported. PPP runs on IP routers to provide this mechanism, as shown in
Fig. 3-23.
IP packet
Router IP IP
PPP frame
PPP PPP
Optical
SONET SONET SONET payload SONET payload
fiber
(a) (b)
Figure 3-23. Packet over SONET. (a) A protocol stack. (b) Frame relationships.
PPP improves on an earlier, simpler protocol called SLIP (Serial Line Inter-
net Protocol) and is used to handle error detection link configuration, support
multiple protocols, permit authentication, and more. With a wide set of options,
PPP provides three main features:
1. A framing method that unambiguously delineates the end of one
frame and the start of the next one. The frame format also handles
error detection.
2. A link control protocol for bringing lines up, testing them, negotiat-
ing options, and bringing them down again gracefully when they are
no longer needed. This protocol is called LCP (Link Control Pro-
tocol).
3. A way to negotiate network-layer options in a way that is indepen-
dent of the network layer protocol to be used. The method chosen is
to have a different NCP (Network Control Protocol) for each net-
work layer supported.


---

<a id="page-258"></a>

<!-- Page 258 of 888 -->

246 THE DATA LINK LAYER CHAP. 3
The PPP frame format was chosen to closely resemble the frame format of
HDLC (High-level Data Link Control), a widely used instance of an earlier
family of protocols, since there was no need to reinvent the wheel.
The primary difference between PPP and HDLC is that PPP is byte oriented
rather than bit oriented. In particular, PPP uses byte stuffing and all frames are an
integral number of bytes. HDLC uses bit stuffing and allows frames of, say, 30.25
bytes.
There is a second major difference in practice, however. HDLC provides re-
liable transmission with a sliding window, acknowledgements, and timeouts in the
manner we have studied. PPP can also provide reliable transmission in noisy en-
vironments, such as wireless networks; the exact details are defined in RFC 1663.
However, this is rarely done in practice. Instead, an ''unnumbered mode'' is near-
ly always used in the Internet to provide connectionless unacknowledged service.
The PPP frame format is shown in Fig. 3-24. All PPP frames begin with the
standard HDLC flag byte of 0x7E (01111110). The flag byte is stuffed if it occurs
within the Payload field using the escape byte 0x7D. The following byte is the
escaped byte XORed with 0x20, which flips the 5th bit. For example, 0x7D 0x5E
is the escape sequence for the flag byte 0x7E. This means the start and end of
frames can be searched for simply by scanning for the byte 0x7E since it will not
occur elsewhere. The destuffing rule when receiving a frame is to look for 0x7D,
remove it, and XOR the following byte with 0x20. Also, only one flag byte is
needed between frames. Multiple flag bytes can be used to fill the link when there
are no frames to be sent.
After the start-of-frame flag byte comes the Address field. This field is al-
ways set to the binary value 11111111 to indicate that all stations are to accept the
frame. Using this value avoids the issue of having to assign data link addresses.
Bytes 1 1 1 1 or 2 Variable 2 or 4 1
Flag Address Control Flag
Protocol Payload Checksum
01111110 11111111 00000011 01111110
Figure 3-24. The PPP full frame format for unnumbered mode operation.
The Address field is followed by the Control field, the default value of which
is 00000011. This value indicates an unnumbered frame.
Since the Address and Control fields are always constant in the default con-
figuration, LCP provides the necessary mechanism for the two parties to negotiate
an option to omit them altogether and save 2 bytes per frame.
The fourth PPP field is the Protocol field. Its job is to tell what kind of packet
is in the Payload field. Codes starting with a 0 bit are defined for IP version 4, IP
version 6, and other network layer protocols that might be used, such as IPX and


---

<a id="page-259"></a>

<!-- Page 259 of 888 -->

SEC. 3.5 EXAMPLE DATA LINK PROTOCOLS 247
AppleTalk. Codes starting with a 1 bit are used for PPP configuration protocols,
including LCP and a different NCP for each network layer protocol supported.
The default size of the Protocol field is 2 bytes, but it can be negotiated down to 1
byte using LCP. The designers were perhaps overly cautious in thinking that
someday there might be more than 256 protocols in use.
The Payload field is variable length, up to some negotiated maximum. If the
length is not negotiated using LCP during line setup, a default length of 1500
bytes is used. Padding may follow the payload if it is needed.
After the Payload field comes the Checksum field, which is normally 2 bytes,
but a 4-byte checksum can be negotiated. The 4-byte checksum is in fact the same
32-bit CRC whose generator polynomial is given at the end of Sec. 3.2.2. The 2-
byte checksum is also an industry-standard CRC.
PPP is a framing mechanism that can carry the packets of multiple protocols
over many types of physical layers. To use PPP over SONET, the choices to make
are spelled out in RFC 2615 (Malis and Simpson, 1999). A 4-byte checksum is
used, since this is the primary means of detecting transmission errors over the
physical, link, and network layers. It is recommended that the Address, Control,
and Protocol fields not be compressed, since SONET links already run at relative-
ly high rates.
There is also one unusual feature. The PPP payload is scrambled (as described
in Sec. 2.5.1) before it is inserted into the SONET payload. Scrambling XORs the
payload with a long pseudorandom sequence before it is transmitted. The issue is
that the SONET bitstream needs frequent bit transitions for synchronization.
These transitions come naturally with the variation in voice signals, but in data
communication the user chooses the information that is sent and might send a
packet with a long run of 0s. With scrambling, the likelihood of a user being able
to cause problems by sending a long run of 0s is made extremely low.
Before PPP frames can be carried over SONET lines, the PPP link must be es-
tablished and configured. The phases that the link goes through when it is brought
up, used, and taken down again are shown in Fig. 3-25.
The link starts in the DEAD state, which means that there is no connection at
the physical layer. When a physical layer connection is established, the link
moves to ESTABLISH. At this point, the PPP peers exchange a series of LCP
packets, each carried in the Payload field of a PPP frame, to select the PPP op-
tions for the link from the possibilities mentioned above. The initiating peer pro-
poses options, and the responding peer either accepts or rejects them, in whole or
part. The responder can also make alternative proposals.
If LCP option negotiation is successful, the link reaches the AUTHENTICATE
state. Now the two parties can check each other's identities, if desired. If
authentication is successful, the NETWORK state is entered and a series of NCP
packets are sent to configure the network layer. It is difficult to generalize about
the NCP protocols because each one is specific to some network layer protocol
and allows configuration requests to be made that are specific to that protocol.


---

<a id="page-260"></a>

<!-- Page 260 of 888 -->

248 THE DATA LINK LAYER CHAP. 3
Carrier Both sides Authentication
detected agree on options successful
## Establish Authenticate
Failed
## Dead Network
Failed
## Terminate Open
Carrier Done NCP
dropped configuration
Figure 3-25. State diagram for bringing a PPP link up and down.
For IP, for example, the assignment of IP addresses to both ends of the link is the
most important possibility.
Once OPEN is reached, data transport can take place. It is in this state that IP
packets are carried in PPP frames across the SONET line. When data transport is
finished, the link moves into the TERMINATE state, and from there it moves back
to the DEAD state when the physical layer connection is dropped.
#### 3.5.2 ADSL (Asymmetric Digital Subscriber Loop)
ADSL connects millions of home subscribers to the Internet at megabit/sec
rates over the same telephone local loop that is used for plain old telephone ser-
vice. In Sec. 2.5.3, we described how a device called a DSL modem is added on
the home side. It sends bits over the local loop to a device called a DSLAM (DSL
Access Multiplexer), pronounced ''dee-slam,'' in the telephone company's local
office. Now we will explore in more detail how packets are carried over ADSL
links.
The overall picture for the protocols and devices used with ADSL is shown in
Fig. 3-26. Different protocols are deployed in different networks, so we have cho-
sen to show the most popular scenario. Inside the home, a computer such as a PC
sends IP packets to the DSL modem using a link layer like Ethernet. The DSL
modem then sends the IP packets over the local loop to the DSLAM using the
protocols that we are about to study. At the DSLAM (or a router connected to it
depending on the implementation) the IP packets are extracted and enter an ISP
network so that they may reach any destination on the Internet.
The protocols shown over the ADSL link in Fig. 3-26 start at the bottom with
the ADSL physical layer. They are based on a digital modulation scheme called


---

<a id="page-261"></a>

<!-- Page 261 of 888 -->

SEC. 3.5 EXAMPLE DATA LINK PROTOCOLS 249
## Ip Dsl Ip Dslam
PPP modem PPP (with router)
PC
## Aal5 Aal5
Ethernet Link
ATM ATM
Local Internet
Ethernet ADSL ADSL
loop
Customer's home ISP's office
Figure 3-26. ADSL protocol stacks.
orthogonal frequency division multiplexing (also known as discrete multitone), as
we saw in Sec 2.5.3. Near the top of the stack, just below the IP network layer, is
PPP. This protocol is the same PPP that we have just studied for packet over
SONET transports. It works in the same way to establish and configure the link
and carry IP packets.
In between ADSL and PPP are ATM and AAL5. These are new protocols that
we have not seen before. ATM (Asynchronous Transfer Mode) was designed
in the early 1990s and launched with incredible hype. It promised a network tech-
nology that would solve the world's telecommunications problems by merging
voice, data, cable television, telegraph, carrier pigeon, tin cans connected by
strings, tom toms, and everything else into an integrated system that could do
everything for everyone. This did not happen. In large part, the problems of ATM
were similar to those we described concerning the OSI protocols, that is, bad tim-
ing, technology, implementation, and politics. Nevertheless, ATM was much
more successful than OSI. While it has not taken over the world, it remains wide-
ly used in niches including broadband access lines such as DSL, and WAN links
inside telephone networks.
ATM is a link layer that is based on the transmission of fixed-length cells of
information. The ''Asynchronous'' in its name means that the cells do not always
need to be sent in the way that bits are continuously sent over synchronous lines,
as in SONET. Cells only need to be sent when there is information to carry.
ATM is a connection-oriented technology. Each cell carries a virtual circuit
identifier in its header and devices use this identifier to forward cells along the
paths of established connections.
The cells are each 53 bytes long, consisting of a 48-byte payload plus a 5-byte
header. By using small cells, ATM can flexibly divide the bandwidth of a physi-
cal layer link among different users in fine slices. This ability is useful when, for
example, sending both voice and data over one link without having long data
packets that would cause large variations in the delay of the voice samples. The
unusual choice for the cell length (e.g., compared to the more natural choice of a


---

<a id="page-262"></a>

<!-- Page 262 of 888 -->

250 THE DATA LINK LAYER CHAP. 3
power of 2) is an indication of just how political the design of ATM was. The
48-byte size for the payload was a compromise to resolve a deadlock between
Europe, which wanted 32-byte cells, and the U.S., which wanted 64-byte cells. A
brief overview of ATM is given by Siu and Jain (1995).
To send data over an ATM network, it needs to be mapped into a sequence of
cells. This mapping is done with an ATM adaptation layer in a process called seg-
mentation and reassembly. Several adaptation layers have been defined for dif-
ferent services, ranging from periodic voice samples to packet data. The main one
used for packet data is AAL5 (ATM Adaptation Layer 5).
An AAL5 frame is shown in Fig. 3-27. Instead of a header, it has a trailer that
gives the length and has a 4-byte CRC for error detection. Naturally, the CRC is
the same one used for PPP and IEEE 802 LANs like Ethernet. Wang and
Crowcroft (1992) have shown that it is strong enough to detect nontraditional er-
rors such as cell reordering. As well as a payload, the AAL5 frame has padding.
This rounds out the overall length to be a multiple of 48 bytes so that the frame
can be evenly divided into cells. No addresses are needed on the frame as the vir-
tual circuit identifier carried in each cell will get it to the right destination.
Bytes 1 or 2 Variable 0 to 47 2 2 4
PPP protocol PPP payload Pad Unused Length CRC
AAL5 payload AAL5 trailer
Figure 3-27. AAL5 frame carrying PPP data.
Now that we have described ATM, we have only to describe how PPP makes
use of ATM in the case of ADSL. It is done with yet another standard called
PPPoA (PPP over ATM). This standard is not really a protocol (so it does not
appear in Fig. 3-26) but more a specification of how to work with both PPP and
AAL5 frames. It is described in RFC 2364 (Gross et al., 1998).
Only the PPP protocol and payload fields are placed in the AAL5 payload, as
shown in Fig. 3-27. The protocol field indicates to the DSLAM at the far end
whether the payload is an IP packet or a packet from another protocol such as
LCP. The far end knows that the cells contain PPP information because an ATM
virtual circuit is set up for this purpose.
Within the AAL5 frame, PPP framing is not needed as it would serve no pur-
pose; ATM and AAL5 already provide the framing. More framing would be
worthless. The PPP CRC is also not needed because AAL5 already includes the
very same CRC. This error detection mechanism supplements the ADSL physical
layer coding of a Reed-Solomon code for error correction and a 1-byte CRC for
the detection of any remaining errors not otherwise caught. This scheme has a
much more sophisticated error-recovery mechanism than when packets are sent
over a SONET line because ADSL is a much noisier channel.


---

<a id="page-263"></a>

<!-- Page 263 of 888 -->

SEC. 3.6 SUMMARY 251
### 3.6 SUMMARY
The task of the data link layer is to convert the raw bit stream offered by the
physical layer into a stream of frames for use by the network layer. The link layer
can present this stream with varying levels of reliability, ranging from con-
nectionless, unacknowledged service to reliable, connection-oriented service.
Various framing methods are used, including byte count, byte stuffing, and bit
stuffing. Data link protocols can provide error control to detect or correct dam-
aged frames and to retransmit lost frames. To prevent a fast sender from overrun-
ning a slow receiver, the data link protocol can also provide flow control. The sli-
ding window mechanism is widely used to integrate error control and flow control
in a simple way. When the window size is 1 packet, the protocol is stop-and-wait.
Codes for error correction and detection add redundant information to mes-
sages by using a variety of mathematical techniques. Convolutional codes and
Reed-Solomon codes are widely deployed for error correction, with low-density
parity check codes increasing in popularity. The codes for error detection that are
used in practice include cyclic redundancy checks and checksums. All these codes
can be applied at the link layer, as well as at the physical layer and higher layers.
We examined a series of protocols that provide a reliable link layer using ac-
knowledgements and retransmissions, or ARQ (Automatic Repeat reQuest), under
more realistic assumptions. Starting from an error-free environment in which the
receiver can handle any frame sent to it, we introduced flow control, followed by
error control with sequence numbers and the stop-and-wait algorithm. Then we
used the sliding window algorithm to allow bidirectional communication and
introduce the concept of piggybacking. The last two protocols pipeline the trans-
mission of multiple frames to prevent the sender from blocking on a link with a
long propagation delay. The receiver can either discard all frames other than the
next one in sequence, or buffer out-of-order frames and send negative acknowl-
edgements for greater bandwidth efficiency. The former strategy is a go-back-n
protocol, and the latter strategy is a selective repeat protocol.
The Internet uses PPP as the main data link protocol over point-to-point lines.
It provides a connectionless unacknowledged service, using flag bytes to delimit
frames and a CRC for error detection. It is used to carry packets across a range of
links, including SONET links in wide-area networks and ADSL links for the
home.
PROBLEMS
1. An upper-layer packet is split into 10 frames, each of which has an 80% chance of ar-
riving undamaged. If no error control is done by the data link protocol, how many
times must the message be sent on average to get the entire thing through?


---

<a id="page-264"></a>

<!-- Page 264 of 888 -->

252 THE DATA LINK LAYER CHAP. 3
2. The following character encoding is used in a data link protocol:
## A: 01000111 B: 11100011 Flag: 01111110 Esc: 11100000
Show the bit sequence transmitted (in binary) for the four-character frame A B ESC
FLAG when each of the following framing methods is used:
(a) Byte count.
(b) Flag bytes with byte stuffing.
(c) Starting and ending flag bytes with bit stuffing.
3. The following data fragment occurs in the middle of a data stream for which the byte-
stuffing algorithm described in the text is used: A B ESC C ESC FLAG FLAG D.
What is the output after stuffing?
4. What is the maximum overhead in byte-stuffing algorithm?
5. One of your classmates, Scrooge, has pointed out that it is wasteful to end each frame
with a flag byte and then begin the next one with a second flag byte. One flag byte
could do the job as well, and a byte saved is a byte earned. Do you agree?
6. A bit string, 0111101111101111110, needs to be transmitted at the data link layer.
What is the string actually transmitted after bit stuffing?
7. Can you think of any circumstances under which an open-loop protocol (e.g., a Ham-
ming code) might be preferable to the feedback-type protocols discussed throughout
this chapter?
8. To provide more reliability than a single parity bit can give, an error-detecting coding
scheme uses one parity bit for checking all the odd-numbered bits and a second parity
bit for all the even-numbered bits. What is the Hamming distance of this code?
9. Sixteen-bit messages are transmitted using a Hamming code. How many check bits
are needed to ensure that the receiver can detect and correct single-bit errors? Show
the bit pattern transmitted for the message 1101001100110101. Assume that even par-
ity is used in the Hamming code.
10. A 12-bit Hamming code whose hexadecimal value is 0xE4F arrives at a receiver.
What was the original value in hexadecimal? Assume that not more than 1 bit is in
error.
11. One way of detecting errors is to transmit data as a block of n rows of k bits per row
and add parity bits to each row and each column. The bitin the lower-right corner is a
parity bit that checks its row and its column. Will this scheme detect all single errors?
Double errors? Triple errors? Show that this scheme cannot detect some four-bit er-
rors.
12. Suppose that data are transmitted in blocks of sizes 1000 bits. What is the maximum
error rate under which error detection and retransmission mechanism (1 parity bit per
block) is better than using Hamming code? Assume that bit errors are independent of
one another and no bit error occurs during retransmission.
13. A block of bits with n rows and k columns uses horizontal and vertical parity bits for
error detection. Suppose that exactly 4 bits are inverted due to transmission errors.
Derive an expression for the probability that the error will be undetected.


---

<a id="page-265"></a>

<!-- Page 265 of 888 -->

CHAP. 3 PROBLEMS 253
14. Using the convolutional coder of Fig. 3-7, what is the output sequence when the input
sequence is 10101010 (left to right) and the internal state is initially all zero?
15. Suppose that a message 1001 1100 1010 0011 is transmitted using Internet Checksum
(4-bit word). What is the value of the checksum?
16. What is the remainder obtained by dividing x 7 + x 5 + 1 by the generator polynomial
x 3 + 1?
17. A bit stream 10011101 is transmitted using the standard CRC method described in the
text. The generator polynomial is x 3 + 1. Show the actual bit string transmitted. Sup-
pose that the third bit from the left is inverted during transmission. Show that this
error is detected at the receiver's end. Give an example of bit errors in the bit string
transmitted that will not be detected by the receiver.
18. A 1024-bit message is sent that contains 992 data bits and 32 CRC bits. CRC is com-
puted using the IEEE 802 standardized, 32-degree CRC polynomial. For each of the
following, explain whether the errors during message transmission will be detected by
the receiver:
(a) There was a single-bit error.
(b) There were two isolated bit errors.
(c) There were 18 isolated bit errors.
(d) There were 47 isolated bit errors.
(e) There was a 24-bit long burst error.
(f) There was a 35-bit long burst error.
19. In the discussion of ARQ protocol in Section 3.3.3, a scenario was outlined that re-
sulted in the receiver accepting two copies of the same frame due to a loss of acknowl-
edgement frame. Is it possible that a receiver may accept multiple copies of the same
frame when none of the frames (message or acknowledgement) are lost?
20. A channel has a bit rate of 4 kbps and a propagation delay of 20 msec. For what range
of frame sizes does stop-and-wait give an efficiency of at least 50%?
21. In protocol 3, is it possible for the sender to start the timer when it is already running?
If so, how might this occur? If not, why is it impossible?
22. A 3000-km-long T1 trunk is used to transmit 64-byte frames using protocol 5. If the
propagation speed is 6 µsec/km, how many bits should the sequence numbers be?
23. Imagine a sliding window protocol using so many bits for sequence numbers that
wraparound never occurs. What relations must hold among the four window edges
and the window size, which is constant and the same for both the sender and the re-
ceiver?
24. If the procedure between in protocol 5 checked for the condition a ≤ b ≤ c instead of
the condition a ≤ b < c, would that have any effect on the protocol's correctness or ef-
ficiency? Explain your answer.
25. In protocol 6, when a data frame arrives, a check is made to see if the sequence num-
ber differs from the one expected and no nak is true. If both conditions hold, a NAK
is sent. Otherwise, the auxiliary timer is started. Suppose that the else clause were
omitted. Would this change affect the protocol's correctness?


---

<a id="page-266"></a>

<!-- Page 266 of 888 -->

254 THE DATA LINK LAYER CHAP. 3
26. Suppose that the three-statement while loop near the end of protocol 6 was removed
from the code. Would this affect the correctness of the protocol or just the per-
formance? Explain your answer.
27. The distance from earth to a distant planet is approximately 9 × 1010 m. What is the
channel utilization if a stop-and-wait protocol is used for frame transmission on a 64
Mbps point-to-point link? Assume that the frame size is 32 KB and the speed of light
is 3 × 108 m/s.
28. In the previous problem, suppose a sliding window protocol is used instead. For what
send window size will the link utilization be 100%? You may ignore the protocol
processing times at the sender and the receiver.
29. In protocol 6, the code for frame arrival has a section used for NAKs. This section is
invoked if the incoming frame is a NAK and another condition is met. Give a scenario
where the presence of this other condition is essential.
30. Consider the operation of protocol 6 over a 1-Mbps perfect (i.e., error-free) line. The
maximum frame size is 1000 bits. New packets are generated 1 second apart. The
timeout interval is 10 msec. If the special acknowledgement timer were eliminated,
unnecessary timeouts would occur. How many times would the average message be
transmitted?
31. In protocol 6, MAX SEQ = 2n − 1. While this condition is obviously desirable to
make efficient use of header bits, we have not demonstrated that it is essential. Does
the protocol work correctly for MAX SEQ = 4, for example?
32. Frames of 1000 bits are sent over a 1-Mbps channel using a geostationary satellite
whose propagation time from the earth is 270 msec. Acknowledgements are always
piggybacked onto data frames. The headers are very short. Three-bit sequence num-
bers are used. What is the maximum achievable channel utilization for
(a) Stop-and-wait?
(b) Protocol 5?
(c) Protocol 6?
33. Compute the fraction of the bandwidth that is wasted on overhead (headers and re-
transmissions) for protocol 6 on a heavily loaded 50-kbps satellite channel with data
frames consisting of 40 header and 3960 data bits. Assume that the signal propagation
time from the earth to the satellite is 270 msec. ACK frames never occur. NAK frames
are 40 bits. The error rate for data frames is 1%, and the error rate for NAK frames is
negligible. The sequence numbers are 8 bits.
34. Consider an error-free 64-kbps satellite channel used to send 512-byte data frames in
one direction, with very short acknowledgements coming back the other way. What is
the maximum throughput for window sizes of 1, 7, 15, and 127? The earth-satellite
propagation time is 270 msec.
35. A 100-km-long cable runs at the T1 data rate. The propagation speed in the cable is
2/3 the speed of light in vacuum. How many bits fit in the cable?
36. Give at least one reason why PPP uses byte stuffing instead of bit stuffing to prevent
accidental flag bytes within the payload from causing confusion.


---

<a id="page-267"></a>

<!-- Page 267 of 888 -->

CHAP. 3 PROBLEMS 255
37. What is the minimum overhead to send an IP packet using PPP? Count only the over-
head introduced by PPP itself, not the IP header overhead. What is the maximum
overhead?
38. A 100-byte IP packet is transmitted over a local loop using ADSL protocol stack. How
many ATM cells will be transmitted? Briefly describe their contents.
39. The goal of this lab exercise is to implement an error-detection mechanism using the
standard CRC algorithm described in the text. Write two programs, generator and
verifier. The generator program reads from standard input a line of ASCII text con-
taining an n-bit message consisting of a string of 0s and 1s. The second line is the k-
bit polynomial, also in ASCII. It outputs to standard output a line of ASCII text with
n + k 0s and 1s representing the message to be transmitted. Then it outputs the poly-
nomial, just as it read it in. The verifier program reads in the output of the generator
program and outputs a message indicating whether it is correct or not. Finally, write a
program, alter, that inverts 1 bit on the first line depending on its argument (the bit
number counting the leftmost bit as 1) but copies the rest of the two lines correctly.
By typing
generator <file | verifier
you should see that the message is correct, but by typing
generator <file | alter arg | verifier
you should get the error message.


---

<a id="page-268"></a>

<!-- Page 268 of 888 -->

This page intentionally left blank
