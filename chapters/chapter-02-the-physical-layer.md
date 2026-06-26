# Chapter 2: The Physical Layer

_Source: printed pages 89-192; extracted PDF pages 101-204._

---

<a id="page-101"></a>

<!-- Page 101 of 888 -->

## The Physical Layer
In this chapter we will look at the lowest layer in our protocol model, the
physical layer. It defines the electrical, timing and other interfaces by which bits
are sent as signals over channels. The physical layer is the foundation on which
the network is built. The properties of different kinds of physical channels deter-
mine the performance (e.g., throughput, latency, and error rate) so it is a good
place to start our journey into networkland.
We will begin with a theoretical analysis of data transmission, only to dis-
cover that Mother (Parent?) Nature puts some limits on what can be sent over a
channel. Then we will cover three kinds of transmission media: guided (copper
wire and fiber optics), wireless (terrestrial radio), and satellite. Each of these
technologies has different properties that affect the design and performance of the
networks that use them. This material will provide background information on the
key transmission technologies used in modern networks.
Next comes digital modulation, which is all about how analog signals are con-
verted into digital bits and back again. After that we will look at multiplexing
schemes, exploring how multiple conversations can be put on the same transmis-
sion medium at the same time without interfering with one another.
Finally, we will look at three examples of communication systems used in
practice for wide area computer networks: the (fixed) telephone system, the
mobile phone system, and the cable television system. Each of these is important
in practice, so we will devote a fair amount of space to each one.



---

<a id="page-102"></a>

<!-- Page 102 of 888 -->

90 THE PHYSICAL LAYER CHAP. 2
### 2.1 THE THEORETICAL BASIS FOR DATA COMMUNICATION
Information can be transmitted on wires by varying some physical property
such as voltage or current. By representing the value of this voltage or current as
a single-valued function of time, f(t), we can model the behavior of the signal and
analyze it mathematically. This analysis is the subject of the following sections.
#### 2.1.1 Fourier Analysis
In the early 19th century, the French mathematician Jean-Baptiste Fourier
proved that any reasonably behaved periodic function, g(t) with period T, can be
constructed as the sum of a (possibly infinite) number of sines and cosines:
1 ∞ ∞
g(t) = c + Σ a sin(2πnft ) + Σ b cos(2πnft) (2-1)
n n

n =1 n =1
where f = 1/T is the fundamental frequency, a and b are the sine and cosine am-
n n
plitudes of the nth harmonics (terms), and c is a constant. Such a decomposition
is called a Fourier series. From the Fourier series, the function can be recon-
structed. That is, if the period, T, is known and the amplitudes are given, the orig-
inal function of time can be found by performing the sums of Eq. (2-1).
A data signal that has a finite duration, which all of them do, can be handled
by just imagining that it repeats the entire pattern over and over forever (i.e., the
interval from T to 2T is the same as from 0 to T, etc.).
The a amplitudes can be computed for any given g(t) by multiplying both
n
sides of Eq. (2-1) by sin(2πkft ) and then integrating from 0 to T. Since
T 0 for k + n
∫sin(2πkft ) sin(2πnft ) dt = 
T /2 for k = n
0 
only one term of the summation survives: a . The b summation vanishes com-
n n
pletely. Similarly, by multiplying Eq. (2-1) by cos(2πkft ) and integrating between
0 and T, we can derive b . By just integrating both sides of the equation as it
n
stands, we can find c. The results of performing these operations are as follows:
T T T
2 2 2
a = ∫g(t) sin(2πnft ) dt b = ∫g(t) cos(2πnft ) dt c = ∫g(t) dt
n n
T T T
0 0 0
#### 2.1.2 Bandwidth-Limited Signals
The relevance of all of this to data communication is that real channels affect
different frequency signals differently. Let us consider a specific example: the
transmission of the ASCII character ''b'' encoded in an 8-bit byte. The bit pattern
that is to be transmitted is 01100010. The left-hand part of Fig. 2-1(a) shows the


---

<a id="page-103"></a>

<!-- Page 103 of 888 -->

SEC. 2.1 THE THEORETICAL BASIS FOR DATA COMMUNICATION 91
voltage output by the transmitting computer. The Fourier analysis of this signal
yields the coefficients:

a = [cos(πn /4) − cos(3πn /4) + cos(6πn /4) − cos(7πn /4)]
n
πn

b = [sin(3πn /4) − sin(πn /4) + sin(7πn /4) − sin(6πn /4)]
n
πn
c = 3/4
The root-mean-square amplitudes, ,a2 + b2 , for the first few terms are shown on
n n
the right-hand side of Fig. 2-1(a). These values are of interest because their
squares are proportional to the energy transmitted at the corresponding frequency.
No transmission facility can transmit signals without losing some power in the
process. If all the Fourier components were equally diminished, the resulting sig-
nal would be reduced in amplitude but not distorted [i.e., it would have the same
nice squared-off shape as Fig. 2-1(a)]. Unfortunately, all transmission facilities
diminish different Fourier components by different amounts, thus introducing dis-
tortion. Usually, for a wire, the amplitudes are transmitted mostly undiminished
from 0 up to some frequency f [measured in cycles/sec or Hertz (Hz)], with all

frequencies above this cutoff frequency attenuated. The width of the frequency
range transmitted without being strongly attenuated is called the bandwidth. In
practice, the cutoff is not really sharp, so often the quoted bandwidth is from 0 to
the frequency at which the received power has fallen by half.
The bandwidth is a physical property of the transmission medium that de-
pends on, for example, the construction, thickness, and length of a wire or fiber.
Filters are often used to further limit the bandwidth of a signal. 802.11 wireless
channels are allowed to use up to roughly 20 MHz, for example, so 802.11 radios
filter the signal bandwidth to this size. As another example, traditional (analog)
television channels occupy 6 MHz each, on a wire or over the air. This filtering
lets more signals share a given region of spectrum, which improves the overall ef-
ficiency of the system. It means that the frequency range for some signals will
not start at zero, but this does not matter. The bandwidth is still the width of the
band of frequencies that are passed, and the information that can be carried de-
pends only on this width and not on the starting and ending frequencies. Signals
that run from 0 up to a maximum frequency are called baseband signals. Signals
that are shifted to occupy a higher range of frequencies, as is the case for all wire-
less transmissions, are called passband signals.
Now let us consider how the signal of Fig. 2-1(a) would look if the bandwidth
were so low that only the lowest frequencies were transmitted [i.e., if the function
were being approximated by the first few terms of Eq. (2-1)]. Figure 2-1(b)
shows the signal that results from a channel that allows only the first harmonic


---

<a id="page-104"></a>

<!-- Page 104 of 888 -->

92 THE PHYSICAL LAYER CHAP. 2
0 1 1 0 0 0 1 0

0 Time T

Time
edutilpmasmr
0.50
0.25
1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
Harmonic number
(a)
1 harmonic

(b)
2 harmonics
1 2
(c)
4 harmonics
1 2 3 4
(d)
8 harmonics
1 2 3 4 5 6 7 8
Harmonic number
(e)
Figure 2-1. (a) A binary signal and its root-mean-square Fourier amplitudes.
(b)-(e) Successive approximations to the original signal.


---

<a id="page-105"></a>

<!-- Page 105 of 888 -->

SEC. 2.1 THE THEORETICAL BASIS FOR DATA COMMUNICATION 93
(the fundamental, f) to pass through. Similarly, Fig. 2-1(c)-(e) show the spectra
and reconstructed functions for higher-bandwidth channels. For digital transmis-
sion, the goal is to receive a signal with just enough fidelity to reconstruct the se-
quence of bits that was sent. We can already do this easily in Fig. 2-1(e), so it is
wasteful to use more harmonics to receive a more accurate replica.
Given a bit rate of b bits/sec, the time required to send the 8 bits in our ex-
ample 1 bit at a time is 8/b sec, so the frequency of the first harmonic of this sig-
nal is b /8 Hz. An ordinary telephone line, often called a voice-grade line, has an
artificially introduced cutoff frequency just above 3000 Hz. The presence of this
restriction means that the number of the highest harmonic passed through is
roughly 3000/(b/8), or 24,000/b (the cutoff is not sharp).
For some data rates, the numbers work out as shown in Fig. 2-2. From these
numbers, it is clear that trying to send at 9600 bps over a voice-grade telephone
line will transform Fig. 2-1(a) into something looking like Fig. 2-1(c), making
accurate reception of the original binary bit stream tricky. It should be obvious
that at data rates much higher than 38.4 kbps, there is no hope at all for binary sig-
nals, even if the transmission facility is completely noiseless. In other words, lim-
iting the bandwidth limits the data rate, even for perfect channels. However, cod-
ing schemes that make use of several voltage levels do exist and can achieve high-
er data rates. We will discuss these later in this chapter.
Bps T (msec) First harmonic (Hz) # Harmonics sent
300 26.67 37.5 80
600 13.33 75 40
1200 6.67 150 20
2400 3.33 300 10
4800 1.67 600 5
9600 0.83 1200 2
19200 0.42 2400 1
38400 0.21 4800 0
Figure 2-2. Relation between data rate and harmonics for our example.
There is much confusion about bandwidth because it means different things to
electrical engineers and to computer scientists. To electrical engineers, (analog)
bandwidth is (as we have described above) a quantity measured in Hz. To com-
puter scientists, (digital) bandwidth is the maximum data rate of a channel, a
quantity measured in bits/sec. That data rate is the end result of using the analog
bandwidth of a physical channel for digital transmission, and the two are related,
as we discuss next. In this book, it will be clear from the context whether we
mean analog bandwidth (Hz) or digital bandwidth (bits/sec).


---

<a id="page-106"></a>

<!-- Page 106 of 888 -->

94 THE PHYSICAL LAYER CHAP. 2
#### 2.1.3 The Maximum Data Rate of a Channel
As early as 1924, an AT&T engineer, Henry Nyquist, realized that even a per-
fect channel has a finite transmission capacity. He derived an equation expressing
the maximum data rate for a finite-bandwidth noiseless channel. In 1948, Claude
Shannon carried Nyquist's work further and extended it to the case of a channel
subject to random (that is, thermodynamic) noise (Shannon, 1948). This paper is
the most important paper in all of information theory. We will just briefly sum-
marize their now classical results here.
Nyquist proved that if an arbitrary signal has been run through a low-pass fil-
ter of bandwidth B, the filtered signal can be completely reconstructed by making
only 2B (exact) samples per second. Sampling the line faster than 2B times per
second is pointless because the higher-frequency components that such sampling
could recover have already been filtered out. If the signal consists of V discrete
levels, Nyquist's theorem states:
maximum data rate = 2B log V bits /sec (2-2)

For example, a noiseless 3-kHz channel cannot transmit binary (i.e., two-level)
signals at a rate exceeding 6000 bps.
So far we have considered only noiseless channels. If random noise is pres-
ent, the situation deteriorates rapidly. And there is always random (thermal) noise
present due to the motion of the molecules in the system. The amount of thermal
noise present is measured by the ratio of the signal power to the noise power, call-
ed the SNR (Signal-to-Noise Ratio). If we denote the signal power by S and the
noise power by N, the signal-to-noise ratio is S/N. Usually, the ratio is expressed
on a log scale as the quantity 10 log S /N because it can vary over a tremendous

range. The units of this log scale are called decibels (dB), with ''deci'' meaning
10 and ''bel'' chosen to honor Alexander Graham Bell, who invented the tele-
phone. An S /N ratio of 10 is 10 dB, a ratio of 100 is 20 dB, a ratio of 1000 is 30
dB, and so on. The manufacturers of stereo amplifiers often characterize the
bandwidth (frequency range) over which their products are linear by giving the 3-
dB frequency on each end. These are the points at which the amplification factor
has been approximately halved (because 10 log 0.5 ∼∼ −3).

Shannon's major result is that the maximum data rate or capacity of a noisy
channel whose bandwidth is B Hz and whose signal-to-noise ratio is S/N, is given
by:
maximum number of bits/sec = B log (1 + S/N) (2-3)

This tells us the best capacities that real channels can have. For example, ADSL
(Asymmetric Digital Subscriber Line), which provides Internet access over nor-
mal telephone lines, uses a bandwidth of around 1 MHz. The SNR depends
strongly on the distance of the home from the telephone exchange, and an SNR of
around 40 dB for short lines of 1 to 2 km is very good. With these characteristics,


---

<a id="page-107"></a>

<!-- Page 107 of 888 -->

SEC. 2.1 THE THEORETICAL BASIS FOR DATA COMMUNICATION 95
the channel can never transmit much more than 13 Mbps, no matter how many or
how few signal levels are used and no matter how often or how infrequently sam-
ples are taken. In practice, ADSL is specified up to 12 Mbps, though users often
see lower rates. This data rate is actually very good, with over 60 years of com-
munications techniques having greatly reduced the gap between the Shannon ca-
pacity and the capacity of real systems.
Shannon's result was derived from information-theory arguments and applies
to any channel subject to thermal noise. Counterexamples should be treated in the
same category as perpetual motion machines. For ADSL to exceed 13 Mbps, it
must either improve the SNR (for example by inserting digital repeaters in the
lines closer to the customers) or use more bandwidth, as is done with the evolu-
tion to ASDL2+.
### 2.2 GUIDED TRANSMISSION MEDIA
The purpose of the physical layer is to transport bits from one machine to an-
other. Various physical media can be used for the actual transmission. Each one
has its own niche in terms of bandwidth, delay, cost, and ease of installation and
maintenance. Media are roughly grouped into guided media, such as copper wire
and fiber optics, and unguided media, such as terrestrial wireless, satellite, and
lasers through the air. We will look at guided media in this section, and unguided
media in the next sections.
#### 2.2.1 Magnetic Media
One of the most common ways to transport data from one computer to another
is to write them onto magnetic tape or removable media (e.g., recordable DVDs),
physically transport the tape or disks to the destination machine, and read them
back in again. Although this method is not as sophisticated as using a geosyn-
chronous communication satellite, it is often more cost effective, especially for
applications in which high bandwidth or cost per bit transported is the key factor.
A simple calculation will make this point clear. An industry-standard Ultrium
tape can hold 800 gigabytes. A box 60 × 60 × 60 cm can hold about 1000 of these
tapes, for a total capacity of 800 terabytes, or 6400 terabits (6.4 petabits). A box
of tapes can be delivered anywhere in the United States in 24 hours by Federal
Express and other companies. The effective bandwidth of this transmission is
6400 terabits/86,400 sec, or a bit over 70 Gbps. If the destination is only an hour
away by road, the bandwidth is increased to over 1700 Gbps. No computer net-
work can even approach this. Of course, networks are getting faster, but tape den-
sities are increasing, too.
If we now look at cost, we get a similar picture. The cost of an Ultrium tape
is around $40 when bought in bulk. A tape can be reused at least 10 times, so the


---

<a id="page-108"></a>

<!-- Page 108 of 888 -->

96 THE PHYSICAL LAYER CHAP. 2
tape cost is maybe $4000 per box per usage. Add to this another $1000 for ship-
ping (probably much less), and we have a cost of roughly $5000 to ship 800 TB.
This amounts to shipping a gigabyte for a little over half a cent. No network can
beat that. The moral of the story is:
Never underestimate the bandwidth of a station wagon full of tapes
hurtling down the highway.
#### 2.2.2 Twisted Pairs
Although the bandwidth characteristics of magnetic tape are excellent, the de-
lay characteristics are poor. Transmission time is measured in minutes or hours,
not milliseconds. For many applications an online connection is needed. One of
the oldest and still most common transmission media is twisted pair. A twisted
pair consists of two insulated copper wires, typically about 1 mm thick. The wires
are twisted together in a helical form, just like a DNA molecule. Twisting is done
because two parallel wires constitute a fine antenna. When the wires are twisted,
the waves from different twists cancel out, so the wire radiates less effectively. A
signal is usually carried as the difference in voltage between the two wires in the
pair. This provides better immunity to external noise because the noise tends to
affect both wires the same, leaving the differential unchanged.
The most common application of the twisted pair is the telephone system.
Nearly all telephones are connected to the telephone company (telco) office by a
twisted pair. Both telephone calls and ADSL Internet access run over these lines.
Twisted pairs can run several kilometers without amplification, but for longer dis-
tances the signal becomes too attenuated and repeaters are needed. When many
twisted pairs run in parallel for a substantial distance, such as all the wires coming
from an apartment building to the telephone company office, they are bundled to-
gether and encased in a protective sheath. The pairs in these bundles would inter-
fere with one another if it were not for the twisting. In parts of the world where
telephone lines run on poles above ground, it is common to see bundles several
centimeters in diameter.
Twisted pairs can be used for transmitting either analog or digital information.
The bandwidth depends on the thickness of the wire and the distance traveled, but
several megabits/sec can be achieved for a few kilometers in many cases. Due to
their adequate performance and low cost, twisted pairs are widely used and are
likely to remain so for years to come.
Twisted-pair cabling comes in several varieties. The garden variety deployed
in many office buildings is called Category 5 cabling, or ''Cat 5.'' A category 5
twisted pair consists of two insulated wires gently twisted together. Four such
pairs are typically grouped in a plastic sheath to protect the wires and keep them
together. This arrangement is shown in Fig. 2-3.
Different LAN standards may use the twisted pairs differently. For example,
100-Mbps Ethernet uses two (out of the four) pairs, one pair for each direction.


---

<a id="page-109"></a>

<!-- Page 109 of 888 -->

SEC. 2.2 GUIDED TRANSMISSION MEDIA 97
Twisted pair
Figure 2-3. Category 5 UTP cable with four twisted pairs.
To reach higher speeds, 1-Gbps Ethernet uses all four pairs in both directions si-
multaneously; this requires the receiver to factor out the signal that is transmitted
locally.
Some general terminology is now in order. Links that can be used in both di-
rections at the same time, like a two-lane road, are called full-duplex links. In
contrast, links that can be used in either direction, but only one way at a time, like
a single-track railroad line. are called half-duplex links. A third category con-
sists of links that allow traffic in only one direction, like a one-way street. They
are called simplex links.
Returning to twisted pair, Cat 5 replaced earlier Category 3 cables with a
similar cable that uses the same connector, but has more twists per meter. More
twists result in less crosstalk and a better-quality signal over longer distances,
making the cables more suitable for high-speed computer communication, espe-
cially 100-Mbps and 1-Gbps Ethernet LANs.
New wiring is more likely to be Category 6 or even Category 7. These
categories has more stringent specifications to handle signals with greater band-
widths. Some cables in Category 6 and above are rated for signals of 500 MHz
and can support the 10-Gbps links that will soon be deployed.
Through Category 6, these wiring types are referred to as UTP (Unshielded
Twisted Pair) as they consist simply of wires and insulators. In contrast to these,
Category 7 cables have shielding on the individual twisted pairs, as well as around
the entire cable (but inside the plastic protective sheath). Shielding reduces the
susceptibility to external interference and crosstalk with other nearby cables to
meet demanding performance specifications. The cables are reminiscent of the
high-quality, but bulky and expensive shielded twisted pair cables that IBM intro-
duced in the early 1980s, but which did not prove popular outside of IBM in-
stallations. Evidently, it is time to try again.
#### 2.2.3 Coaxial Cable
Another common transmission medium is the coaxial cable (known to its
many friends as just ''coax'' and pronounced ''co-ax''). It has better shielding and
greater bandwidth than unshielded twisted pairs, so it can span longer distances at


---

<a id="page-110"></a>

<!-- Page 110 of 888 -->

98 THE PHYSICAL LAYER CHAP. 2
higher speeds. Two kinds of coaxial cable are widely used. One kind, 50-ohm
cable, is commonly used when it is intended for digital transmission from the
start. The other kind, 75-ohm cable, is commonly used for analog transmission
and cable television. This distinction is based on historical, rather than technical,
factors (e.g., early dipole antennas had an impedance of 300 ohms, and it was
easy to use existing 4:1 impedance-matching transformers). Starting in the mid-
1990s, cable TV operators began to provide Internet access over cable, which has
made 75-ohm cable more important for data communication.
A coaxial cable consists of a stiff copper wire as the core, surrounded by an
insulating material. The insulator is encased by a cylindrical conductor, often as a
closely woven braided mesh. The outer conductor is covered in a protective plas-
tic sheath. A cutaway view of a coaxial cable is shown in Fig. 2-4.
Copper Insulating Braided Protective
core material outer plastic
conductor covering
Figure 2-4. A coaxial cable.
The construction and shielding of the coaxial cable give it a good combination
of high bandwidth and excellent noise immunity. The bandwidth possible de-
pends on the cable quality and length. Modern cables have a bandwidth of up to a
few GHz. Coaxial cables used to be widely used within the telephone system for
long-distance lines but have now largely been replaced by fiber optics on long-
haul routes. Coax is still widely used for cable television and metropolitan area
networks, however.
#### 2.2.4 Power Lines
The telephone and cable television networks are not the only sources of wir-
ing that can be reused for data communication. There is a yet more common kind
of wiring: electrical power lines. Power lines deliver electrical power to houses,
and electrical wiring within houses distributes the power to electrical outlets.
The use of power lines for data communication is an old idea. Power lines
have been used by electricity companies for low-rate communication such as re-
mote metering for many years, as well in the home to control devices (e.g., the
X10 standard). In recent years there has been renewed interest in high-rate com-
munication over these lines, both inside the home as a LAN and outside the home


---

<a id="page-111"></a>

<!-- Page 111 of 888 -->

SEC. 2.2 GUIDED TRANSMISSION MEDIA 99
for broadband Internet access. We will concentrate on the most common scenario:
using electrical wires inside the home.
The convenience of using power lines for networking should be clear. Simply
plug a TV and a receiver into the wall, which you must do anyway because they
need power, and they can send and receive movies over the electrical wiring. This
configuration is shown in Fig. 2-5. There is no other plug or radio. The data sig-
nal is superimposed on the low-frequency power signal (on the active or ''hot''
wire) as both signals use the wiring at the same time.
Electric cable Data signal
Power signal
Figure 2-5. A network that uses household electrical wiring.
The difficulty with using household electrical wiring for a network is that it
was designed to distribute power signals. This task is quite different than distri-
buting data signals, at which household wiring does a horrible job. Electrical sig-
nals are sent at 50-60 Hz and the wiring attenuates the much higher frequency
(MHz) signals needed for high-rate data communication. The electrical properties
of the wiring vary from one house to the next and change as appliances are turned
on and off, which causes data signals to bounce around the wiring. Transient cur-
rents when appliances switch on and off create electrical noise over a wide range
of frequencies. And without the careful twisting of twisted pairs, electrical wiring
acts as a fine antenna, picking up external signals and radiating signals of its own.
This behavior means that to meet regulatory requirements, the data signal must
exclude licensed frequencies such as the amateur radio bands.
Despite these difficulties, it is practical to send at least 100 Mbps over typical
household electrical wiring by using communication schemes that resist impaired
frequencies and bursts of errors. Many products use various proprietary standards
for power-line networking, so international standards are actively under develop-
ment.
#### 2.2.5 Fiber Optics
Many people in the computer industry take enormous pride in how fast com-
puter technology is improving as it follows Moore's law, which predicts a dou-
bling of the number of transistors per chip roughly every two years (Schaller,


---

<a id="page-112"></a>

<!-- Page 112 of 888 -->

100 THE PHYSICAL LAYER CHAP. 2
1997). The original (1981) IBM PC ran at a clock speed of 4.77 MHz. Twenty-
eight years later, PCs could run a four-core CPU at 3 GHz. This increase is a gain
of a factor of around 2500, or 16 per decade. Impressive.
In the same period, wide area communication links went from 45 Mbps (a T3
line in the telephone system) to 100 Gbps (a modern long distance line). This
gain is similarly impressive, more than a factor of 2000 and close to 16 per
decade, while at the same time the error rate went from 10−5 per bit to almost
zero. Furthermore, single CPUs are beginning to approach physical limits, which
is why it is now the number of CPUs that is being increased per chip. In contrast,
the achievable bandwidth with fiber technology is in excess of 50,000 Gbps (50
Tbps) and we are nowhere near reaching these limits. The current practical limit
of around 100 Gbps is due to our inability to convert between electrical and opti-
cal signals any faster. To build higher-capacity links, many channels are simply
carried in parallel over a single fiber.
In this section we will study fiber optics to learn how that transmission tech-
nology works. In the ongoing race between computing and communication, com-
munication may yet win because of fiber optic networks. The implication of this
would be essentially infinite bandwidth and a new conventional wisdom that com-
puters are hopelessly slow so that networks should try to avoid computation at all
costs, no matter how much bandwidth that wastes. This change will take a while
to sink in to a generation of computer scientists and engineers taught to think in
terms of the low Shannon limits imposed by copper.
Of course, this scenario does not tell the whole story because it does not in-
clude cost. The cost to install fiber over the last mile to reach consumers and
bypass the low bandwidth of wires and limited availability of spectrum is tremen-
dous. It also costs more energy to move bits than to compute. We may always
have islands of inequities where either computation or communication is essen-
tially free. For example, at the edge of the Internet we throw computation and
storage at the problem of compressing and caching content, all to make better use
of Internet access links. Within the Internet, we may do the reverse, with com-
panies such as Google moving huge amounts of data across the network to where
it is cheaper to store or compute on it.
Fiber optics are used for long-haul transmission in network backbones, high-
speed LANs (although so far, copper has always managed catch up eventually),
and high-speed Internet access such as FttH (Fiber to the Home). An optical
transmission system has three key components: the light source, the transmission
medium, and the detector. Conventionally, a pulse of light indicates a 1 bit and
the absence of light indicates a 0 bit. The transmission medium is an ultra-thin
fiber of glass. The detector generates an electrical pulse when light falls on it. By
attaching a light source to one end of an optical fiber and a detector to the other,
we have a unidirectional data transmission system that accepts an electrical sig-
nal, converts and transmits it by light pulses, and then reconverts the output to an
electrical signal at the receiving end.


---

<a id="page-113"></a>

<!-- Page 113 of 888 -->

SEC. 2.2 GUIDED TRANSMISSION MEDIA 101
This transmission system would leak light and be useless in practice were it
not for an interesting principle of physics. When a light ray passes from one
medium to another-for example, from fused silica to air-the ray is refracted
(bent) at the silica/air boundary, as shown in Fig. 2-6(a). Here we see a light ray
incident on the boundary at an angle α emerging at an angle β . The amount of
1 1
refraction depends on the properties of the two media (in particular, their indices
of refraction). For angles of incidence above a certain critical value, the light is
refracted back into the silica; none of it escapes into the air. Thus, a light ray
incident at or above the critical angle is trapped inside the fiber, as shown in
Fig. 2-6(b), and can propagate for many kilometers with virtually no loss.
Air
Air/silica Total internal
boundary
β1 β2 β3
reflection.
α1 α2 α3
Silica Light source
(a) (b)
Figure 2-6. (a) Three examples of a light ray from inside a silica fiber imping-
ing on the air/silica boundary at different angles. (b) Light trapped by total inter-
nal reflection.
The sketch of Fig. 2-6(b) shows only one trapped ray, but since any light ray
incident on the boundary above the critical angle will be reflected internally,
many different rays will be bouncing around at different angles. Each ray is said
to have a different mode, so a fiber having this property is called a multimode
fiber.
However, if the fiber's diameter is reduced to a few wavelengths of light the
fiber acts like a wave guide and the light can propagate only in a straight line,
without bouncing, yielding a single-mode fiber. Single-mode fibers are more ex-
pensive but are widely used for longer distances. Currently available single-mode
fibers can transmit data at 100 Gbps for 100 km without amplification. Even
higher data rates have been achieved in the laboratory for shorter distances.
Transmission of Light Through Fiber
Optical fibers are made of glass, which, in turn, is made from sand, an inex-
pensive raw material available in unlimited amounts. Glassmaking was known to
the ancient Egyptians, but their glass had to be no more than 1 mm thick or the


---

<a id="page-114"></a>

<!-- Page 114 of 888 -->

102 THE PHYSICAL LAYER CHAP. 2
light could not shine through. Glass transparent enough to be useful for windows
was developed during the Renaissance. The glass used for modern optical fibers
is so transparent that if the oceans were full of it instead of water, the seabed
would be as visible from the surface as the ground is from an airplane on a clear
day.
The attenuation of light through glass depends on the wavelength of the light
(as well as on some physical properties of the glass). It is defined as the ratio of
input to output signal power. For the kind of glass used in fibers, the attenuation
is shown in Fig. 2-7 in units of decibels per linear kilometer of fiber. For exam-
ple, a factor of two loss of signal power gives an attenuation of 10 log 2 = 3 dB.

The figure shows the near-infrared part of the spectrum, which is what is used in
practice. Visible light has slightly shorter wavelengths, from 0.4 to 0.7 microns.
(1 micron is 10−6 meters.) The true metric purist would refer to these wave-
lengths as 400 nm to 700 nm, but we will stick with traditional usage.
0.85µ 1.30µ 1.55µ
### 2.0 Band Band Band
1.8
1.6
1.4
1.2
1.0
0.8
0.6
0.4
0.2
0 0.8 0.9 1.0 1.1 1.2 1.3
Wavelength (microns)
)mk/Bd(noitaunettA
### 1.4 1.5 1.6 1.7 1.8
Figure 2-7. Attenuation of light through fiber in the infrared region.
Three wavelength bands are most commonly used at present for optical com-
munication. They are centered at 0.85, 1.30, and 1.55 microns, respectively. All
three bands are 25,000 to 30,000 GHz wide. The 0.85-micron band was used first.
It has higher attenuation and so is used for shorter distances, but at that wave-
length the lasers and electronics could be made from the same material (gallium
arsenide). The last two bands have good attenuation properties (less than 5% loss
per kilometer). The 1.55-micron band is now widely used with erbium-doped
amplifiers that work directly in the optical domain.


---

<a id="page-115"></a>

<!-- Page 115 of 888 -->

SEC. 2.2 GUIDED TRANSMISSION MEDIA 103
Light pulses sent down a fiber spread out in length as they propagate. This
spreading is called chromatic dispersion. The amount of it is wavelength depen-
dent. One way to keep these spread-out pulses from overlapping is to increase the
distance between them, but this can be done only by reducing the signaling rate.
Fortunately, it has been discovered that making the pulses in a special shape relat-
ed to the reciprocal of the hyperbolic cosine causes nearly all the dispersion ef-
fects cancel out, so it is possible to send pulses for thousands of kilometers with-
out appreciable shape distortion. These pulses are called solitons. A considerable
amount of research is going on to take solitons out of the lab and into the field.
Fiber Cables
Fiber optic cables are similar to coax, except without the braid. Figure 2-8(a)
shows a single fiber viewed from the side. At the center is the glass core through
which the light propagates. In multimode fibers, the core is typically 50 microns
in diameter, about the thickness of a human hair. In single-mode fibers, the core
is 8 to 10 microns.
Sheath Jacket
Core
(glass)
Cladding Jacket
(glass) (plastic) Core Cladding
(a) (b)
Figure 2-8. (a) Side view of a single fiber. (b) End view of a sheath with three fibers.
The core is surrounded by a glass cladding with a lower index of refraction
than the core, to keep all the light in the core. Next comes a thin plastic jacket to
protect the cladding. Fibers are typically grouped in bundles, protected by an
outer sheath. Figure 2-8(b) shows a sheath with three fibers.
Terrestrial fiber sheaths are normally laid in the ground within a meter of the
surface, where they are occasionally subject to attacks by backhoes or gophers.
Near the shore, transoceanic fiber sheaths are buried in trenches by a kind of
seaplow. In deep water, they just lie on the bottom, where they can be snagged by
fishing trawlers or attacked by giant squid.
Fibers can be connected in three different ways. First, they can terminate in
connectors and be plugged into fiber sockets. Connectors lose about 10 to 20% of
the light, but they make it easy to reconfigure systems.
Second, they can be spliced mechanically. Mechanical splices just lay the
two carefully cut ends next to each other in a special sleeve and clamp them in


---

<a id="page-116"></a>

<!-- Page 116 of 888 -->

104 THE PHYSICAL LAYER CHAP. 2
place. Alignment can be improved by passing light through the junction and then
making small adjustments to maximize the signal. Mechanical splices take train-
ed personnel about 5 minutes and result in a 10% light loss.
Third, two pieces of fiber can be fused (melted) to form a solid connection. A
fusion splice is almost as good as a single drawn fiber, but even here, a small
amount of attenuation occurs.
For all three kinds of splices, reflections can occur at the point of the splice,
and the reflected energy can interfere with the signal.
Two kinds of light sources are typically used to do the signaling. These are
LEDs (Light Emitting Diodes) and semiconductor lasers. They have different
properties, as shown in Fig. 2-9. They can be tuned in wavelength by inserting
Fabry-Perot or Mach-Zehnder interferometers between the source and the fiber.
Fabry-Perot interferometers are simple resonant cavities consisting of two parallel
mirrors. The light is incident perpendicular to the mirrors. The length of the cav-
ity selects out those wavelengths that fit inside an integral number of times.
Mach-Zehnder interferometers separate the light into two beams. The two beams
travel slightly different distances. They are recombined at the end and are in
phase for only certain wavelengths.
Item LED Semiconductor laser
Data rate Low High
Fiber type Multi-mode Multi-mode or single-mode
Distance Short Long
Lifetime Long life Short life
Temperature sensitivity Minor Substantial
Cost Low cost Expensive
Figure 2-9. A comparison of semiconductor diodes and LEDs as light sources.
The receiving end of an optical fiber consists of a photodiode, which gives off
an electrical pulse when struck by light. The response time of photodiodes, which
convert the signal from the optical to the electrical domain, limits data rates to
about 100 Gbps. Thermal noise is also an issue, so a pulse of light must carry
enough energy to be detected. By making the pulses powerful enough, the error
rate can be made arbitrarily small.
Comparison of Fiber Optics and Copper Wire
It is instructive to compare fiber to copper. Fiber has many advantages. To
start with, it can handle much higher bandwidths than copper. This alone would
require its use in high-end networks. Due to the low attenuation, repeaters are
needed only about every 50 km on long lines, versus about every 5 km for copper,


---

<a id="page-117"></a>

<!-- Page 117 of 888 -->

SEC. 2.2 GUIDED TRANSMISSION MEDIA 105
resulting in a big cost saving. Fiber also has the advantage of not being affected
by power surges, electromagnetic interference, or power failures. Nor is it affect-
ed by corrosive chemicals in the air, important for harsh factory environments.
Oddly enough, telephone companies like fiber for a different reason: it is thin
and lightweight. Many existing cable ducts are completely full, so there is no
room to add new capacity. Removing all the copper and replacing it with fiber
empties the ducts, and the copper has excellent resale value to copper refiners
who see it as very high-grade ore. Also, fiber is much lighter than copper. One
thousand twisted pairs 1 km long weigh 8000 kg. Two fibers have more capacity
and weigh only 100 kg, which reduces the need for expensive mechanical support
systems that must be maintained. For new routes, fiber wins hands down due to
its much lower installation cost. Finally, fibers do not leak light and are difficult
to tap. These properties give fiber good security against potential wiretappers.
On the downside, fiber is a less familiar technology requiring skills not all en-
gineers have, and fibers can be damaged easily by being bent too much. Since op-
tical transmission is inherently unidirectional, two-way communication requires
either two fibers or two frequency bands on one fiber. Finally, fiber interfaces
cost more than electrical interfaces. Nevertheless, the future of all fixed data
communication over more than short distances is clearly with fiber. For a dis-
cussion of all aspects of fiber optics and their networks, see Hecht (2005).
### 2.3 WIRELESS TRANSMISSION
Our age has given rise to information junkies: people who need to be online
all the time. For these mobile users, twisted pair, coax, and fiber optics are of no
use. They need to get their ''hits'' of data for their laptop, notebook, shirt pocket,
palmtop, or wristwatch computers without being tethered to the terrestrial com-
munication infrastructure. For these users, wireless communication is the answer.
In the following sections, we will look at wireless communication in general.
It has many other important applications besides providing connectivity to users
who want to surf the Web from the beach. Wireless has advantages for even fixed
devices in some circumstances. For example, if running a fiber to a building is
difficult due to the terrain (mountains, jungles, swamps, etc.), wireless may be
better. It is noteworthy that modern wireless digital communication began in the
Hawaiian Islands, where large chunks of Pacific Ocean separated the users from
their computer center and the telephone system was inadequate.
#### 2.3.1 The Electromagnetic Spectrum
When electrons move, they create electromagnetic waves that can propagate
through space (even in a vacuum). These waves were predicted by the British
physicist James Clerk Maxwell in 1865 and first observed by the German


---

<a id="page-118"></a>

<!-- Page 118 of 888 -->

106 THE PHYSICAL LAYER CHAP. 2
physicist Heinrich Hertz in 1887. The number of oscillations per second of a
wave is called its frequency, f, and is measured in Hz (in honor of Heinrich
Hertz). The distance between two consecutive maxima (or minima) is called the
wavelength, which is universally designated by the Greek letter λ (lambda).
When an antenna of the appropriate size is attached to an electrical circuit, the
electromagnetic waves can be broadcast efficiently and received by a receiver
some distance away. All wireless communication is based on this principle.
In a vacuum, all electromagnetic waves travel at the same speed, no matter
what their frequency. This speed, usually called the speed of light, c, is approxi-
mately 3 × 108 m/sec, or about 1 foot (30 cm) per nanosecond. (A case could be
made for redefining the foot as the distance light travels in a vacuum in 1 nsec
rather than basing it on the shoe size of some long-dead king.) In copper or fiber
the speed slows to about 2/3 of this value and becomes slightly frequency depen-
dent. The speed of light is the ultimate speed limit. No object or signal can ever
move faster than it.
The fundamental relation between f, λ, and c (in a vacuum) is
λf = c (2-4)
Since c is a constant, if we know f, we can find λ, and vice versa. As a rule of
thumb, when λ is in meters and f is in MHz, λf ∼∼ 300. For example, 100-MHz
waves are about 3 meters long, 1000-MHz waves are 0.3 meters long, and 0.1-
meter waves have a frequency of 3000 MHz.
The electromagnetic spectrum is shown in Fig. 2-10. The radio, microwave,
infrared, and visible light portions of the spectrum can all be used for transmitting
information by modulating the amplitude, frequency, or phase of the waves.
Ultraviolet light, X-rays, and gamma rays would be even better, due to their high-
er frequencies, but they are hard to produce and modulate, do not propagate well
through buildings, and are dangerous to living things. The bands listed at the bot-
tom of Fig. 2-10 are the official ITU (International Telecommunication Union)
names and are based on the wavelengths, so the LF band goes from 1 km to 10 km
(approximately 30 kHz to 300 kHz). The terms LF, MF, and HF refer to Low,
Medium, and High Frequency, respectively. Clearly, when the names were as-
signed nobody expected to go above 10 MHz, so the higher bands were later
named the Very, Ultra, Super, Extremely, and Tremendously High Frequency
bands. Beyond that there are no names, but Incredibly, Astonishingly, and Prodi-
giously High Frequency (IHF, AHF, and PHF) would sound nice.
We know from Shannon [Eq. (2-3)] that the amount of information that a sig-
nal such as an electromagnetic wave can carry depends on the received power and
is proportional to its bandwidth. From Fig. 2-10 it should now be obvious why
networking people like fiber optics so much. Many GHz of bandwidth are avail-
able to tap for data transmission in the microwave band, and even more in fiber
because it is further to the right in our logarithmic scale. As an example, consider
the 1.30-micron band of Fig. 2-7, which has a width of 0.17 microns. If we use


---

<a id="page-119"></a>

<!-- Page 119 of 888 -->

SEC. 2.3 WIRELESS TRANSMISSION 107
f (Hz) 100 102 104 106 108 1010 1012 1014 1016 1018 1020 1022 1024
Radio Microwave Infrared UV X-ray Gamma ray
Visible
light
f (Hz) 104 105 106 107 108 109 1010 1011 1012 1013 1014 1015 1016
Fiber
Twisted pair Satellite
Coax Terrestrial optics
AM FM microwave
Maritime radio radio
TV
Band LF MF HF VHF UHF SHF EHF THF
Figure 2-10. The electromagnetic spectrum and its uses for communication.
Eq. (2-4) to find the start and end frequencies from the start and end wavelengths,
we find the frequency range to be about 30,000 GHz. With a reasonable signal-
to-noise ratio of 10 dB, this is 300 Tbps.
Most transmissions use a relatively narrow frequency band (i.e., ∆f / f << 1).
They concentrate their signals in this narrow band to use the spectrum efficiently
and obtain reasonable data rates by transmitting with enough power. However, in
some cases, a wider band is used, with three variations. In frequency hopping
spread spectrum, the transmitter hops from frequency to frequency hundreds of
times per second. It is popular for military communication because it makes
transmissions hard to detect and next to impossible to jam. It also offers good
resistance to multipath fading and narrowband interference because the receiver
will not be stuck on an impaired frequency for long enough to shut down commu-
nication. This robustness makes it useful for crowded parts of the spectrum, such
as the ISM bands we will describe shortly. This technique is used commercially,
for example, in Bluetooth and older versions of 802.11.
As a curious footnote, the technique was coinvented by the Austrian-born sex
goddess Hedy Lamarr, the first woman to appear nude in a motion picture (the
1933 Czech film Extase). Her first husband was an armaments manufacturer who
told her how easy it was to block the radio signals then used to control torpedoes.
When she discovered that he was selling weapons to Hitler, she was horrified, dis-
guised herself as a maid to escape him, and fled to Hollywood to continue her
career as a movie actress. In her spare time, she invented frequency hopping to
help the Allied war effort. Her scheme used 88 frequencies, the number of keys


---

<a id="page-120"></a>

<!-- Page 120 of 888 -->

108 THE PHYSICAL LAYER CHAP. 2
(and frequencies) on the piano. For their invention, she and her friend, the mu-
sical composer George Antheil, received U.S. patent 2,292,387. However, they
were unable to convince the U.S. Navy that their invention had any practical use
and never received any royalties. Only years after the patent expired did it be-
come popular.
A second form of spread spectrum, direct sequence spread spectrum, uses a
code sequence to spread the data signal over a wider frequency band. It is widely
used commercially as a spectrally efficient way to let multiple signals share the
same frequency band. These signals can be given different codes, a method called
CDMA (Code Division Multiple Access) that we will return to later in this chap-
ter. This method is shown in contrast with frequency hopping in Fig. 2-11. It
forms the basis of 3G mobile phone networks and is also used in GPS (Global
Positioning System). Even without different codes, direct sequence spread spec-
trum, like frequency hopping spread spectrum, can tolerate narrowband inter-
ference and multipath fading because only a fraction of the desired signal is lost.
It is used in this role in older 802.11b wireless LANs. For a fascinating and de-
tailed history of spread spectrum communication, see Scholtz (1982).
Frequency
Direct
hopping
(CDMA user with sequence spread
different code) spread spectrum
spectrum
Ultrawideband
underlay
(CDMA user with
different code)
Frequency
Figure 2-11. Spread spectrum and ultra-wideband (UWB) communication.
A third method of communication with a wider band is UWB (Ultra-
WideBand) communication. UWB sends a series of rapid pulses, varying their
positions to communicate information. The rapid transitions lead to a signal that
is spread thinly over a very wide frequency band. UWB is defined as signals that
have a bandwidth of at least 500 MHz or at least 20% of the center frequency of
their frequency band. UWB is also shown in Fig. 2-11. With this much band-
width, UWB has the potential to communicate at high rates. Because it is spread
across a wide band of frequencies, it can tolerate a substantial amount of relative-
ly strong interference from other narrowband signals. Just as importantly, since
UWB has very little energy at any given frequency when used for short-range
transmission, it does not cause harmful interference to those other narrowband
radio signals. It is said to underlay the other signals. This peaceful coexistence
has led to its application in wireless PANs that run at up to 1 Gbps, although com-
mercial success has been mixed. It can also be used for imaging through solid ob-
jects (ground, walls, and bodies) or as part of precise location systems.


---

<a id="page-121"></a>

<!-- Page 121 of 888 -->

SEC. 2.3 WIRELESS TRANSMISSION 109
We will now discuss how the various parts of the electromagnetic spectrum of
Fig. 2-11 are used, starting with radio. We will assume that all transmissions use
a narrow frequency band unless otherwise stated.
#### 2.3.2 Radio Transmission
Radio frequency (RF) waves are easy to generate, can travel long distances,
and can penetrate buildings easily, so they are widely used for communication,
both indoors and outdoors. Radio waves also are omnidirectional, meaning that
they travel in all directions from the source, so the transmitter and receiver do not
have to be carefully aligned physically.
Sometimes omnidirectional radio is good, but sometimes it is bad. In the
1970s, General Motors decided to equip all its new Cadillacs with computer-con-
trolled antilock brakes. When the driver stepped on the brake pedal, the computer
pulsed the brakes on and off instead of locking them on hard. One fine day an
Ohio Highway Patrolman began using his new mobile radio to call headquarters,
and suddenly the Cadillac next to him began behaving like a bucking bronco.
When the officer pulled the car over, the driver claimed that he had done nothing
and that the car had gone crazy.
Eventually, a pattern began to emerge: Cadillacs would sometimes go berserk,
but only on major highways in Ohio and then only when the Highway Patrol was
watching. For a long, long time General Motors could not understand why Cadil-
lacs worked fine in all the other states and also on minor roads in Ohio. Only
after much searching did they discover that the Cadillac's wiring made a fine an-
tenna for the frequency used by the Ohio Highway Patrol's new radio system.
The properties of radio waves are frequency dependent. At low frequencies,
radio waves pass through obstacles well, but the power falls off sharply with dis-
tance from the source-at least as fast as 1/r 2 in air-as the signal energy is
spread more thinly over a larger surface. This attenuation is called path loss. At
high frequencies, radio waves tend to travel in straight lines and bounce off obsta-
cles. Path loss still reduces power, though the received signal can depend strongly
on reflections as well. High-frequency radio waves are also absorbed by rain and
other obstacles to a larger extent than are low-frequency ones. At all frequencies,
radio waves are subject to interference from motors and other electrical equip-
ment.
It is interesting to compare the attenuation of radio waves to that of signals in
guided media. With fiber, coax and twisted pair, the signal drops by the same
fraction per unit distance, for example 20 dB per 100m for twisted pair. With
radio, the signal drops by the same fraction as the distance doubles, for example 6
dB per doubling in free space. This behavior means that radio waves can travel
long distances, and interference between users is a problem. For this reason, all
governments tightly regulate the use of radio transmitters, with few notable ex-
ceptions, which are discussed later in this chapter.


---

<a id="page-122"></a>

<!-- Page 122 of 888 -->

110 THE PHYSICAL LAYER CHAP. 2
In the VLF, LF, and MF bands, radio waves follow the ground, as illustrated
in Fig. 2-12(a). These waves can be detected for perhaps 1000 km at the lower
frequencies, less at the higher ones. AM radio broadcasting uses the MF band,
which is why the ground waves from Boston AM radio stations cannot be heard
easily in New York. Radio waves in these bands pass through buildings easily,
which is why portable radios work indoors. The main problem with using these
bands for data communication is their low bandwidth [see Eq. (2-4)].
G
wa
ro

u
e
nd Ionosphe r e
Earth's surface Earth's surface
(a) (b)
Figure 2-12. (a) In the VLF, LF, and MF bands, radio waves follow the curva-
ture of the earth. (b) In the HF band, they bounce off the ionosphere.
In the HF and VHF bands, the ground waves tend to be absorbed by the earth.
However, the waves that reach the ionosphere, a layer of charged particles cir-
cling the earth at a height of 100 to 500 km, are refracted by it and sent back to
earth, as shown in Fig. 2-12(b). Under certain atmospheric conditions, the signals
can bounce several times. Amateur radio operators (hams) use these bands to talk
long distance. The military also communicate in the HF and VHF bands.
#### 2.3.3 Microwave Transmission
Above 100 MHz, the waves travel in nearly straight lines and can therefore be
narrowly focused. Concentrating all the energy into a small beam by means of a
parabolic antenna (like the familiar satellite TV dish) gives a much higher signal-
to-noise ratio, but the transmitting and receiving antennas must be accurately
aligned with each other. In addition, this directionality allows multiple trans-
mitters lined up in a row to communicate with multiple receivers in a row without
interference, provided some minimum spacing rules are observed. Before fiber
optics, for decades these microwaves formed the heart of the long-distance tele-
phone transmission system. In fact, MCI, one of AT&T's first competitors after it
was deregulated, built its entire system with microwave communications passing
between towers tens of kilometers apart. Even the company's name reflected this
(MCI stood for Microwave Communications, Inc.). MCI has since gone over to
fiber and through a long series of corporate mergers and bankruptcies in the
telecommunications shuffle has become part of Verizon.


---

<a id="page-123"></a>

<!-- Page 123 of 888 -->

SEC. 2.3 WIRELESS TRANSMISSION 111
Microwaves travel in a straight line, so if the towers are too far apart, the
earth will get in the way (think about a Seattle-to-Amsterdam link). Thus, re-
peaters are needed periodically. The higher the towers are, the farther apart they
can be. The distance between repeaters goes up very roughly with the square root
of the tower height. For 100-meter-high towers, repeaters can be 80 km apart.
Unlike radio waves at lower frequencies, microwaves do not pass through
buildings well. In addition, even though the beam may be well focused at the
transmitter, there is still some divergence in space. Some waves may be refracted
off low-lying atmospheric layers and may take slightly longer to arrive than the
direct waves. The delayed waves may arrive out of phase with the direct wave
and thus cancel the signal. This effect is called multipath fading and is often a
serious problem. It is weather and frequency dependent. Some operators keep
10% of their channels idle as spares to switch on when multipath fading tem-
porarily wipes out some frequency band.
The demand for more and more spectrum drives operators to yet higher fre-
quencies. Bands up to 10 GHz are now in routine use, but at about 4 GHz a new
problem sets in: absorption by water. These waves are only a few centimeters
long and are absorbed by rain. This effect would be fine if one were planning to
build a huge outdoor microwave oven for roasting passing birds, but for communi-
cation it is a severe problem. As with multipath fading, the only solution is to
shut off links that are being rained on and route around them.
In summary, microwave communication is so widely used for long-distance
telephone communication, mobile phones, television distribution, and other pur-
poses that a severe shortage of spectrum has developed. It has several key advan-
tages over fiber. The main one is that no right of way is needed to lay down
cables. By buying a small plot of ground every 50 km and putting a microwave
tower on it, one can bypass the telephone system entirely. This is how MCI man-
aged to get started as a new long-distance telephone company so quickly. (Sprint,
another early competitor to the deregulated AT&T, went a completely different
route: it was formed by the Southern Pacific Railroad, which already owned a
large amount of right of way and just buried fiber next to the tracks.)
Microwave is also relatively inexpensive. Putting up two simple towers
(which can be just big poles with four guy wires) and putting antennas on each
one may be cheaper than burying 50 km of fiber through a congested urban area
or up over a mountain, and it may also be cheaper than leasing the telephone com-
pany's fiber, especially if the telephone company has not yet even fully paid for
the copper it ripped out when it put in the fiber.
The Politics of the Electromagnetic Spectrum
To prevent total chaos, there are national and international agreements about
who gets to use which frequencies. Since everyone wants a higher data rate,
everyone wants more spectrum. National governments allocate spectrum for AM


---

<a id="page-124"></a>

<!-- Page 124 of 888 -->

112 THE PHYSICAL LAYER CHAP. 2
and FM radio, television, and mobile phones, as well as for telephone companies,
police, maritime, navigation, military, government, and many other competing
users. Worldwide, an agency of ITU-R (WRC) tries to coordinate this allocation
so devices that work in multiple countries can be manufactured. However, coun-
tries are not bound by ITU-R's recommendations, and the FCC (Federal Commu-
nication Commission), which does the allocation for the United States, has occa-
sionally rejected ITU-R's recommendations (usually because they required some
politically powerful group to give up some piece of the spectrum).
Even when a piece of spectrum has been allocated to some use, such as
mobile phones, there is the additional issue of which carrier is allowed to use
which frequencies. Three algorithms were widely used in the past. The oldest al-
gorithm, often called the beauty contest, requires each carrier to explain why its
proposal serves the public interest best. Government officials then decide which
of the nice stories they enjoy most. Having some government official award prop-
erty worth billions of dollars to his favorite company often leads to bribery, corr-
uption, nepotism, and worse. Furthermore, even a scrupulously honest govern-
ment official who thought that a foreign company could do a better job than any
of the national companies would have a lot of explaining to do.
This observation led to algorithm 2, holding a lottery among the interested
companies. The problem with that idea is that companies with no interest in using
the spectrum can enter the lottery. If, say, a fast food restaurant or shoe store
chain wins, it can resell the spectrum to a carrier at a huge profit and with no risk.
Bestowing huge windfalls on alert but otherwise random companies has been
severely criticized by many, which led to algorithm 3: auction off the bandwidth
to the highest bidder. When the British government auctioned off the frequencies
needed for third-generation mobile systems in 2000, it expected to get about $4
billion. It actually received about $40 billion because the carriers got into a feed-
ing frenzy, scared to death of missing the mobile boat. This event switched on
nearby governments' greedy bits and inspired them to hold their own auctions. It
worked, but it also left some of the carriers with so much debt that they are close
to bankruptcy. Even in the best cases, it will take many years to recoup the
licensing fee.
A completely different approach to allocating frequencies is to not allocate
them at all. Instead, let everyone transmit at will, but regulate the power used so
that stations have such a short range that they do not interfere with each other.
Accordingly, most governments have set aside some frequency bands, called the
ISM (Industrial, Scientific, Medical) bands for unlicensed usage. Garage door
openers, cordless phones, radio-controlled toys, wireless mice, and numerous
other wireless household devices use the ISM bands. To minimize interference
between these uncoordinated devices, the FCC mandates that all devices in the
ISM bands limit their transmit power (e.g., to 1 watt) and use other techniques to
spread their signals over a range of frequencies. Devices may also need to take
care to avoid interference with radar installations.


---

<a id="page-125"></a>

<!-- Page 125 of 888 -->

SEC. 2.3 WIRELESS TRANSMISSION 113
The location of these bands varies somewhat from country to country. In the
United States, for example, the bands that networking devices use in practice
without requiring a FCC license are shown in Fig. 2-13. The 900-MHz band was
used for early versions of 802.11, but it is crowded. The 2.4-GHz band is avail-
able in most countries and widely used for 802.11b/g and Bluetooth, though it is
subject to interference from microwave ovens and radar installations. The 5-GHz
part of the spectrum includes U-NII (Unlicensed National Information
Infrastructure) bands. The 5-GHz bands are relatively undeveloped but, since
they have the most bandwidth and are used by 802.11a, they are quickly gaining
in popularity.
ISM band ISM band ISM band
26 83.5 100 255 100
MHz MHz MHz MHz MHz
902 928 2.4 2.4835 5.25 5.35 5.47 5.725 5.825
MHz MHz GHz GHz GHz GHz GHz GHz GHz
U-NII bands
Figure 2-13. ISM and U-NII bands used in the United States by wireless devices.
The unlicensed bands have been a roaring success over the past decade. The
ability to use the spectrum freely has unleashed a huge amount of innovation in
wireless LANs and PANs, evidenced by the widespread deployment of technolo-
gies such as 802.11 and Bluetooth. To continue this innovation, more spectrum is
needed. One exciting development in the U.S. is the FCC decision in 2009 to
allow unlicensed use of white spaces around 700 MHz. White spaces are fre-
quency bands that have been allocated but are not being used locally. The tran-
sition from analog to all-digital television broadcasts in the U.S. in 2010 freed up
white spaces around 700 MHz. The only difficulty is that, to use the white
spaces, unlicensed devices must be able to detect any nearby licensed trans-
mitters, including wireless microphones, that have first rights to use the frequency
band.
Another flurry of activity is happening around the 60-GHz band. The FCC
opened 57 GHz to 64 GHz for unlicensed operation in 2001. This range is an
enormous portion of spectrum, more than all the other ISM bands combined, so it
can support the kind of high-speed networks that would be needed to stream
high-definition TV through the air across your living room. At 60 GHz, radio


---

<a id="page-126"></a>

<!-- Page 126 of 888 -->

114 THE PHYSICAL LAYER CHAP. 2
waves are absorbed by oxygen. This means that signals do not propagate far,
making them well suited to short-range networks. The high frequencies (60 GHz
is in the Extremely High Frequency or ''millimeter'' band, just below infrared
radiation) posed an initial challenge for equipment makers, but products are now
on the market.
#### 2.3.4 Infrared Transmission
Unguided infrared waves are widely used for short-range communication.
The remote controls used for televisions, VCRs, and stereos all use infrared com-
munication. They are relatively directional, cheap, and easy to build but have a
major drawback: they do not pass through solid objects. (Try standing between
your remote control and your television and see if it still works.) In general, as
we go from long-wave radio toward visible light, the waves behave more and
more like light and less and less like radio.
On the other hand, the fact that infrared waves do not pass through solid walls
well is also a plus. It means that an infrared system in one room of a building will
not interfere with a similar system in adjacent rooms or buildings: you cannot
control your neighbor's television with your remote control. Furthermore, securi-
ty of infrared systems against eavesdropping is better than that of radio systems
precisely for this reason. Therefore, no government license is needed to operate
an infrared system, in contrast to radio systems, which must be licensed outside
the ISM bands. Infrared communication has a limited use on the desktop, for ex-
ample, to connect notebook computers and printers with the IrDA (Infrared Data
Association) standard, but it is not a major player in the communication game.
#### 2.3.5 Light Transmission
Unguided optical signaling or free-space optics has been in use for centuries.
Paul Revere used binary optical signaling from the Old North Church just prior to
his famous ride. A more modern application is to connect the LANs in two build-
ings via lasers mounted on their rooftops. Optical signaling using lasers is
inherently unidirectional, so each end needs its own laser and its own photodetec-
tor. This scheme offers very high bandwidth at very low cost and is relatively
secure because it is difficult to tap a narrow laser beam. It is also relatively easy
to install and, unlike microwave transmission, does not require an FCC license.
The laser's strength, a very narrow beam, is also its weakness here. Aiming a
laser beam 1 mm wide at a target the size of a pin head 500 meters away requires
the marksmanship of a latter-day Annie Oakley. Usually, lenses are put into the
system to defocus the beam slightly. To add to the difficulty, wind and tempera-
ture changes can distort the beam and laser beams also cannot penetrate rain or
thick fog, although they normally work well on sunny days. However, many of
these factors are not an issue when the use is to connect two spacecraft.


---

<a id="page-127"></a>

<!-- Page 127 of 888 -->

SEC. 2.3 WIRELESS TRANSMISSION 115
One of the authors (AST) once attended a conference at a modern hotel in
Europe at which the conference organizers thoughtfully provided a room full of
terminals to allow the attendees to read their email during boring presentations.
Since the local PTT was unwilling to install a large number of telephone lines for
just 3 days, the organizers put a laser on the roof and aimed it at their university's
computer science building a few kilometers away. They tested it the night before
the conference and it worked perfectly. At 9 A.M. on a bright, sunny day, the link
failed completely and stayed down all day. The pattern repeated itself the next
two days. It was not until after the conference that the organizers discovered the
problem: heat from the sun during the daytime caused convection currents to rise
up from the roof of the building, as shown in Fig. 2-14. This turbulent air diverted
the beam and made it dance around the detector, much like a shimmering road on
a hot day. The lesson here is that to work well in difficult conditions as well as
good conditions, unguided optical links need to be engineered with a sufficient
margin of error.
Laser beam
misses the detector
Photodetector Region of
turbulent seeing Laser
Heat rising
off the building
Figure 2-14. Convection currents can interfere with laser communication sys-
tems. A bidirectional system with two lasers is pictured here.
Unguided optical communication may seem like an exotic networking tech-
nology today, but it might soon become much more prevalent. We are surrounded


---

<a id="page-128"></a>

<!-- Page 128 of 888 -->

116 THE PHYSICAL LAYER CHAP. 2
by cameras (that sense light) and displays (that emit light using LEDs and other
technology). Data communication can be layered on top of these displays by en-
coding information in the pattern at which LEDs turn on and off that is below the
threshold of human perception. Communicating with visible light in this way is
inherently safe and creates a low-speed network in the immediate vicinity of the
display. This could enable all sorts of fanciful ubiquitous computing scenarios.
The flashing lights on emergency vehicles might alert nearby traffic lights and
vehicles to help clear a path. Informational signs might broadcast maps. Even fes-
tive lights might broadcast songs that are synchronized with their display.
### 2.4 COMMUNICATION SATELLITES
In the 1950s and early 1960s, people tried to set up communication systems
by bouncing signals off metallized weather balloons. Unfortunately, the received
signals were too weak to be of any practical use. Then the U.S. Navy noticed a
kind of permanent weather balloon in the sky-the moon-and built an opera-
tional system for ship-to-shore communication by bouncing signals off it.
Further progress in the celestial communication field had to wait until the first
communication satellite was launched. The key difference between an artificial
satellite and a real one is that the artificial one can amplify the signals before
sending them back, turning a strange curiosity into a powerful communication
system.
Communication satellites have some interesting properties that make them
attractive for many applications. In its simplest form, a communication satellite
can be thought of as a big microwave repeater in the sky. It contains several
transponders, each of which listens to some portion of the spectrum, amplifies
the incoming signal, and then rebroadcasts it at another frequency to avoid inter-
ference with the incoming signal. This mode of operation is known as a bent
pipe. Digital processing can be added to separately manipulate or redirect data
streams in the overall band, or digital information can even be received by the sat-
ellite and rebroadcast. Regenerating signals in this way improves performance
compared to a bent pipe because the satellite does not amplify noise in the upward
signal. The downward beams can be broad, covering a substantial fraction of the
earth's surface, or narrow, covering an area only hundreds of kilometers in diame-
ter.
According to Kepler's law, the orbital period of a satellite varies as the radius
of the orbit to the 3/2 power. The higher the satellite, the longer the period. Near
the surface of the earth, the period is about 90 minutes. Consequently, low-orbit
satellites pass out of view fairly quickly, so many of them are needed to provide
continuous coverage and ground antennas must track them. At an altitude of
about 35,800 km, the period is 24 hours. At an altitude of 384,000 km, the period
is about one month, as anyone who has observed the moon regularly can testify.


---

<a id="page-129"></a>

<!-- Page 129 of 888 -->

SEC. 2.4 COMMUNICATION SATELLITES 117
A satellite's period is important, but it is not the only issue in determining
where to place it. Another issue is the presence of the Van Allen belts, layers of
highly charged particles trapped by the earth's magnetic field. Any satellite flying
within them would be destroyed fairly quickly by the particles. These factors lead
to three regions in which satellites can be placed safely. These regions and some
of their properties are illustrated in Fig. 2-15. Below we will briefly describe the
satellites that inhabit each of these regions.
Altitude (km) Type Latency (ms) Sats needed
35,000 GEO 270 3
30,000
25,000
20,000
Upper Van Allen belt
15,000
10,000 MEO 35-85 10
5,000
Lower Van Allen belt
0 1-7 50
LEO
Figure 2-15. Communication satellites and some of their properties, including
altitude above the earth, round-trip delay time, and number of satellites needed
for global coverage.
#### 2.4.1 Geostationary Satellites
In 1945, the science fiction writer Arthur C. Clarke calculated that a satellite
at an altitude of 35,800 km in a circular equatorial orbit would appear to remain
motionless in the sky, so it would not need to be tracked (Clarke, 1945). He went
on to describe a complete communication system that used these (manned) geo-
stationary satellites, including the orbits, solar panels, radio frequencies, and
launch procedures. Unfortunately, he concluded that satellites were impractical
due to the impossibility of putting power-hungry, fragile vacuum tube amplifiers
into orbit, so he never pursued this idea further, although he wrote some science
fiction stories about it.
The invention of the transistor changed all that, and the first artificial commu-
nication satellite, Telstar, was launched in July 1962. Since then, communication
satellites have become a multibillion dollar business and the only aspect of outer
space that has become highly profitable. These high-flying satellites are often
called GEO (Geostationary Earth Orbit) satellites.


---

<a id="page-130"></a>

<!-- Page 130 of 888 -->

118 THE PHYSICAL LAYER CHAP. 2
With current technology, it is unwise to have geostationary satellites spaced
much closer than 2 degrees in the 360-degree equatorial plane, to avoid inter-
ference. With a spacing of 2 degrees, there can only be 360/2 = 180 of these sat-
ellites in the sky at once. However, each transponder can use multiple frequen-
cies and polarizations to increase the available bandwidth.
To prevent total chaos in the sky, orbit slot allocation is done by ITU. This
process is highly political, with countries barely out of the stone age demanding
''their'' orbit slots (for the purpose of leasing them to the highest bidder). Other
countries, however, maintain that national property rights do not extend up to the
moon and that no country has a legal right to the orbit slots above its territory. To
add to the fight, commercial telecommunication is not the only application. Tele-
vision broadcasters, governments, and the military also want a piece of the orbit-
ing pie.
Modern satellites can be quite large, weighing over 5000 kg and consuming
several kilowatts of electric power produced by the solar panels. The effects of
solar, lunar, and planetary gravity tend to move them away from their assigned
orbit slots and orientations, an effect countered by on-board rocket motors. This
fine-tuning activity is called station keeping. However, when the fuel for the
motors has been exhausted (typically after about 10 years) the satellite drifts and
tumbles helplessly, so it has to be turned off. Eventually, the orbit decays and the
satellite reenters the atmosphere and burns up (or very rarely crashes to earth).
Orbit slots are not the only bone of contention. Frequencies are an issue, too,
because the downlink transmissions interfere with existing microwave users.
Consequently, ITU has allocated certain frequency bands to satellite users. The
main ones are listed in Fig. 2-16. The C band was the first to be designated for
commercial satellite traffic. Two frequency ranges are assigned in it, the lower
one for downlink traffic (from the satellite) and the upper one for uplink traffic (to
the satellite). To allow traffic to go both ways at the same time, two channels are
required. These channels are already overcrowded because they are also used by
the common carriers for terrestrial microwave links. The L and S bands were
added by international agreement in 2000. However, they are narrow and also
crowded.
Band Downlink Uplink Bandwidth Problems
L 1.5 GHz 1.6 GHz 15 MHz Low bandwidth; crowded
S 1.9 GHz 2.2 GHz 70 MHz Low bandwidth; crowded
C 4.0 GHz 6.0 GHz 500 MHz Terrestrial interference
Ku 11 GHz 14 GHz 500 MHz Rain
Ka 20 GHz 30 GHz 3500 MHz Rain, equipment cost
Figure 2-16. The principal satellite bands.


---

<a id="page-131"></a>

<!-- Page 131 of 888 -->

SEC. 2.4 COMMUNICATION SATELLITES 119
The next-highest band available to commercial telecommunication carriers is
the Ku (K under) band. This band is not (yet) congested, and at its higher fre-
quencies, satellites can be spaced as close as 1 degree. However, another problem
exists: rain. Water absorbs these short microwaves well. Fortunately, heavy
storms are usually localized, so using several widely separated ground stations in-
stead of just one circumvents the problem, but at the price of extra antennas, extra
cables, and extra electronics to enable rapid switching between stations. Band-
width has also been allocated in the Ka (K above) band for commercial satellite
traffic, but the equipment needed to use it is expensive. In addition to these com-
mercial bands, many government and military bands also exist.
A modern satellite has around 40 transponders, most often with a 36-MHz
bandwidth. Usually, each transponder operates as a bent pipe, but recent satellites
have some on-board processing capacity, allowing more sophisticated operation.
In the earliest satellites, the division of the transponders into channels was static:
the bandwidth was simply split up into fixed frequency bands. Nowadays, each
transponder beam is divided into time slots, with various users taking turns. We
will study these two techniques (frequency division multiplexing and time divis-
ion multiplexing) in detail later in this chapter.
The first geostationary satellites had a single spatial beam that illuminated
about 1/3 of the earth's surface, called its footprint. With the enormous decline
in the price, size, and power requirements of microelectronics, a much more
sophisticated broadcasting strategy has become possible. Each satellite is
equipped with multiple antennas and multiple transponders. Each downward
beam can be focused on a small geographical area, so multiple upward and down-
ward transmissions can take place simultaneously. Typically, these so-called spot
beams are elliptically shaped, and can be as small as a few hundred km in diame-
ter. A communication satellite for the United States typically has one wide beam
for the contiguous 48 states, plus spot beams for Alaska and Hawaii.
A recent development in the communication satellite world is the develop-
ment of low-cost microstations, sometimes called VSATs (Very Small Aperture
Terminals) (Abramson, 2000). These tiny terminals have 1-meter or smaller an-
tennas (versus 10 m for a standard GEO antenna) and can put out about 1 watt of
power. The uplink is generally good for up to 1 Mbps, but the downlink is often
up to several megabits/sec. Direct broadcast satellite television uses this technol-
ogy for one-way transmission.
In many VSAT systems, the microstations do not have enough power to com-
municate directly with one another (via the satellite, of course). Instead, a special
ground station, the hub, with a large, high-gain antenna is needed to relay traffic
between VSATs, as shown in Fig. 2-17. In this mode of operation, either the
sender or the receiver has a large antenna and a powerful amplifier. The trade-off
is a longer delay in return for having cheaper end-user stations.
VSATs have great potential in rural areas. It is not widely appreciated, but
over half the world's population lives more than hour's walk from the nearest


---

<a id="page-132"></a>

<!-- Page 132 of 888 -->

120 THE PHYSICAL LAYER CHAP. 2
Communication
satellite
1 4
3 2
VSAT
Hub
Figure 2-17. VSATs using a hub.
telephone. Stringing telephone wires to thousands of small villages is far beyond
the budgets of most Third World governments, but installing 1-meter VSAT
dishes powered by solar cells is often feasible. VSATs provide the technology
that will wire the world.
Communication satellites have several properties that are radically different
from terrestrial point-to-point links. To begin with, even though signals to and
from a satellite travel at the speed of light (nearly 300,000 km/sec), the long
round-trip distance introduces a substantial delay for GEO satellites. Depending
on the distance between the user and the ground station and the elevation of the
satellite above the horizon, the end-to-end transit time is between 250 and 300
msec. A typical value is 270 msec (540 msec for a VSAT system with a hub).
For comparison purposes, terrestrial microwave links have a propagation
delay of roughly 3 µsec /km, and coaxial cable or fiber optic links have a delay of
approximately 5 µsec /km. The latter are slower than the former because electro-
magnetic signals travel faster in air than in solid materials.
Another important property of satellites is that they are inherently broadcast
media. It does not cost more to send a message to thousands of stations within a
transponder's footprint than it does to send to one. For some applications, this
property is very useful. For example, one could imagine a satellite broadcasting
popular Web pages to the caches of a large number of computers spread over a
wide area. Even when broadcasting can be simulated with point-to-point lines,


---

<a id="page-133"></a>

<!-- Page 133 of 888 -->

SEC. 2.4 COMMUNICATION SATELLITES 121
satellite broadcasting may be much cheaper. On the other hand, from a privacy
point of view, satellites are a complete disaster: everybody can hear everything.
Encryption is essential when security is required.
Satellites also have the property that the cost of transmitting a message is in-
dependent of the distance traversed. A call across the ocean costs no more to ser-
vice than a call across the street. Satellites also have excellent error rates and can
be deployed almost instantly, a major consideration for disaster response and mili-
tary communication.
#### 2.4.2 Medium-Earth Orbit Satellites
At much lower altitudes, between the two Van Allen belts, we find the MEO
(Medium-Earth Orbit) satellites. As viewed from the earth, these drift slowly in
longitude, taking something like 6 hours to circle the earth. Accordingly, they
must be tracked as they move through the sky. Because they are lower than the
GEOs, they have a smaller footprint on the ground and require less powerful
transmitters to reach them. Currently they are used for navigation systems rather
than telecommunications, so we will not examine them further here. The constel-
lation of roughly 30 GPS (Global Positioning System) satellites orbiting at about
20,200 km are examples of MEO satellites.
#### 2.4.3 Low-Earth Orbit Satellites
Moving down in altitude, we come to the LEO (Low-Earth Orbit) satellites.
Due to their rapid motion, large numbers of them are needed for a complete sys-
tem. On the other hand, because the satellites are so close to the earth, the ground
stations do not need much power, and the round-trip delay is only a few millisec-
onds. The launch cost is substantially cheaper too. In this section we will exam-
ine two examples of satellite constellations for voice service, Iridium and Glo-
balstar.
For the first 30 years of the satellite era, low-orbit satellites were rarely used
because they zip into and out of view so quickly. In 1990, Motorola broke new
ground by filing an application with the FCC asking for permission to launch 77
low-orbit satellites for the Iridium project (element 77 is iridium). The plan was
later revised to use only 66 satellites, so the project should have been renamed
Dysprosium (element 66), but that probably sounded too much like a disease. The
idea was that as soon as one satellite went out of view, another would replace it.
This proposal set off a feeding frenzy among other communication companies.
All of a sudden, everyone wanted to launch a chain of low-orbit satellites.
After seven years of cobbling together partners and financing, communication
service began in November 1998. Unfortunately, the commercial demand for
large, heavy satellite telephones was negligible because the mobile phone network
had grown in a spectacular way since 1990. As a consequence, Iridium was not


---

<a id="page-134"></a>

<!-- Page 134 of 888 -->

122 THE PHYSICAL LAYER CHAP. 2
profitable and was forced into bankruptcy in August 1999 in one of the most spec-
tacular corporate fiascos in history. The satellites and other assets (worth $5 bil-
lion) were later purchased by an investor for $25 million at a kind of extraterres-
trial garage sale. Other satellite business ventures promptly followed suit.
The Iridium service restarted in March 2001 and has been growing ever since.
It provides voice, data, paging, fax, and navigation service everywhere on land,
air, and sea, via hand-held devices that communicate directly with the Iridium sat-
ellites. Customers include the maritime, aviation, and oil exploration industries,
as well as people traveling in parts of the world lacking a telecom infrastructure
(e.g., deserts, mountains, the South Pole, and some Third World countries).
The Iridium satellites are positioned at an altitude of 750 km, in circular polar
orbits. They are arranged in north-south necklaces, with one satellite every 32
degrees of latitude, as shown in Fig. 2-18. Each satellite has a maximum of 48
cells (spot beams) and a capacity of 3840 channels, some of which are used for
paging and navigation, while others are used for data and voice.
Each satellite has
four neighbors
Figure 2-18. The Iridium satellites form six necklaces around the earth.
With six satellite necklaces the entire earth is covered, as suggested by
Fig. 2-18. An interesting property of Iridium is that communication between dis-
tant customers takes place in space, as shown in Fig. 2-19(a). Here we see a call-
er at the North Pole contacting a satellite directly overhead. Each satellite has four
neighbors with which it can communicate, two in the same necklace (shown) and
two in adjacent necklaces (not shown). The satellites relay the call across this
grid until it is finally sent down to the callee at the South Pole.
An alternative design to Iridium is Globalstar. It is based on 48 LEO satel-
lites but uses a different switching scheme than that of Iridium. Whereas Iridium
relays calls from satellite to satellite, which requires sophisticated switching
equipment in the satellites, Globalstar uses a traditional bent-pipe design. The
call originating at the North Pole in Fig. 2-19(b) is sent back to earth and picked


---

<a id="page-135"></a>

<!-- Page 135 of 888 -->

SEC. 2.4 COMMUNICATION SATELLITES 123
Satellite switches Bent-pipe
in space satellite
Switching
on the
ground
(a) (b)
Figure 2-19. (a) Relaying in space. (b) Relaying on the ground.
up by the large ground station at Santa's Workshop. The call is then routed via a
terrestrial network to the ground station nearest the callee and delivered by a
bent-pipe connection as shown. The advantage of this scheme is that it puts much
of the complexity on the ground, where it is easier to manage. Also, the use of
large ground station antennas that can put out a powerful signal and receive a
weak one means that lower-powered telephones can be used. After all, the tele-
phone puts out only a few milliwatts of power, so the signal that gets back to the
ground station is fairly weak, even after having been amplified by the satellite.
Satellites continue to be launched at a rate of around 20 per year, including
ever-larger satellites that now weigh over 5000 kilograms. But there are also very
small satellites for the more budget-conscious organization. To make space re-
search more accessible, academics from Cal Poly and Stanford got together in
1999 to define a standard for miniature satellites and an associated launcher that
would greatly lower launch costs (Nugent et al., 2008). CubeSats are satellites in
units of 10 cm × 10 cm × 10 cm cubes, each weighing no more than 1 kilogram,
that can be launched for as little as $40,000 each. The launcher flies as a sec-
ondary payload on commercial space missions. It is basically a tube that takes up
to three units of cubesats and uses springs to release them into orbit. Roughly 20
cubesats have launched so far, with many more in the works. Most of them com-
municate with ground stations on the UHF and VHF bands.
#### 2.4.4 Satellites Versus Fiber
A comparison between satellite communication and terrestrial communication
is instructive. As recently as 25 years ago, a case could be made that the future of
communication lay with communication satellites. After all, the telephone system


---

<a id="page-136"></a>

<!-- Page 136 of 888 -->

124 THE PHYSICAL LAYER CHAP. 2
had changed little in the previous 100 years and showed no signs of changing in
the next 100 years. This glacial movement was caused in no small part by the
regulatory environment in which the telephone companies were expected to pro-
vide good voice service at reasonable prices (which they did), and in return got a
guaranteed profit on their investment. For people with data to transmit, 1200-bps
modems were available. That was pretty much all there was.
The introduction of competition in 1984 in the United States and somewhat
later in Europe changed all that radically. Telephone companies began replacing
their long-haul networks with fiber and introduced high-bandwidth services like
ADSL (Asymmetric Digital Subscriber Line). They also stopped their long-time
practice of charging artificially high prices to long-distance users to subsidize
local service. All of a sudden, terrestrial fiber connections looked like the winner.
Nevertheless, communication satellites have some major niche markets that
fiber does not (and, sometimes, cannot) address. First, when rapid deployment is
critical, satellites win easily. A quick response is useful for military communica-
tion systems in times of war and disaster response in times of peace. Following
the massive December 2004 Sumatra earthquake and subsequent tsunami, for ex-
ample, communications satellites were able to restore communications to first re-
sponders within 24 hours. This rapid response was possible because there is a de-
veloped satellite service provider market in which large players, such as Intelsat
with over 50 satellites, can rent out capacity pretty much anywhere it is needed.
For customers served by existing satellite networks, a VSAT can be set up easily
and quickly to provide a megabit/sec link to elsewhere in the world.
A second niche is for communication in places where the terrestrial infra-
structure is poorly developed. Many people nowadays want to communicate
everywhere they go. Mobile phone networks cover those locations with good
population density, but do not do an adequate job in other places (e.g., at sea or in
the desert). Conversely, Iridium provides voice service everywhere on Earth,
even at the South Pole. Terrestrial infrastructure can also be expensive to install,
depending on the terrain and necessary rights of way. Indonesia, for example, has
its own satellite for domestic telephone traffic. Launching one satellite was
cheaper than stringing thousands of undersea cables among the 13,677 islands in
the archipelago.
A third niche is when broadcasting is essential. A message sent by satellite
can be received by thousands of ground stations at once. Satellites are used to dis-
tribute much network TV programming to local stations for this reason. There is
now a large market for satellite broadcasts of digital TV and radio directly to end
users with satellite receivers in their homes and cars. All sorts of other content
can be broadcast too. For example, an organization transmitting a stream of
stock, bond, or commodity prices to thousands of dealers might find a satellite
system to be much cheaper than simulating broadcasting on the ground.
In short, it looks like the mainstream communication of the future will be ter-
restrial fiber optics combined with cellular radio, but for some specialized uses,


---

<a id="page-137"></a>

<!-- Page 137 of 888 -->

SEC. 2.4 COMMUNICATION SATELLITES 125
satellites are better. However, there is one caveat that applies to all of this:
economics. Although fiber offers more bandwidth, it is conceivable that terres-
trial and satellite communication could compete aggressively on price. If ad-
vances in technology radically cut the cost of deploying a satellite (e.g., if some
future space vehicle can toss out dozens of satellites on one launch) or low-orbit
satellites catch on in a big way, it is not certain that fiber will win all markets.
### 2.5 DIGITAL MODULATION AND MULTIPLEXING
Now that we have studied the properties of wired and wireless channels, we
turn our attention to the problem of sending digital information. Wires and wire-
less channels carry analog signals such as continuously varying voltage, light
intensity, or sound intensity. To send digital information, we must devise analog
signals to represent bits. The process of converting between bits and signals that
represent them is called digital modulation.
We will start with schemes that directly convert bits into a signal. These
schemes result in baseband transmission, in which the signal occupies frequen-
cies from zero up to a maximum that depends on the signaling rate. It is common
for wires. Then we will consider schemes that regulate the amplitude, phase, or
frequency of a carrier signal to convey bits. These schemes result in passband
transmission, in which the signal occupies a band of frequencies around the fre-
quency of the carrier signal. It is common for wireless and optical channels for
which the signals must reside in a given frequency band.
Channels are often shared by multiple signals. After all, it is much more con-
venient to use a single wire to carry several signals than to install a wire for every
signal. This kind of sharing is called multiplexing. It can be accomplished in
several different ways. We will present methods for time, frequency, and code di-
vision multiplexing.
The modulation and multiplexing techniques we describe in this section are
all widely used for wires, fiber, terrestrial wireless, and satellite channels. In the
following sections, we will look at examples of networks to see them in action.
#### 2.5.1 Baseband Transmission
The most straightforward form of digital modulation is to use a positive volt-
age to represent a 1 and a negative voltage to represent a 0. For an optical fiber,
the presence of light might represent a 1 and the absence of light might represent a
0. This scheme is called NRZ (Non-Return-to-Zero ). The odd name is for his-
torical reasons, and simply means that the signal follows the data. An example is
shown in Fig. 2-20(b).
Once sent, the NRZ signal propagates down the wire. At the other end, the
receiver converts it into bits by sampling the signal at regular intervals of time.


---

<a id="page-138"></a>

<!-- Page 138 of 888 -->

126 THE PHYSICAL LAYER CHAP. 2
(a) Bit stream 1 0 0 0 0 1 0 1 1 1 1
(b) Non-Return to Zero (NRZ)
(c) NRZ Invert (NRZI)
(d) Manchester
(Clock that is XORed with bits)
(e) Bipolar encoding
(also Alternate Mark
Inversion, AMI)
Figure 2-20. Line codes: (a) Bits, (b) NRZ, (c) NRZI, (d) Manchester, (e) Bi-
polar or AMI.
This signal will not look exactly like the signal that was sent. It will be attenuated
and distorted by the channel and noise at the receiver. To decode the bits, the re-
ceiver maps the signal samples to the closest symbols. For NRZ, a positive volt-
age will be taken to indicate that a 1 was sent and a negative voltage will be taken
to indicate that a 0 was sent.
NRZ is a good starting point for our studies because it is simple, but it is sel-
dom used by itself in practice. More complex schemes can convert bits to signals
that better meet engineering considerations. These schemes are called line codes.
Below, we describe line codes that help with bandwidth efficiency, clock recov-
ery, and DC balance.
Bandwidth Efficiency
With NRZ, the signal may cycle between the positive and negative levels up
to every 2 bits (in the case of alternating 1s and 0s). This means that we need a
bandwidth of at least B/2 Hz when the bit rate is B bits/sec. This relation comes
from the Nyquist rate [Eq. (2-2)]. It is a fundamental limit, so we cannot run NRZ
faster without using more bandwidth. Bandwidth is often a limited resource, even
for wired channels, Higher-frequency signals are increasingly attenuated, making
them less useful, and higher-frequency signals also require faster electronics.
One strategy for using limited bandwidth more efficiently is to use more than
two signaling levels. By using four voltages, for instance, we can send 2 bits at
once as a single symbol. This design will work as long as the signal at the re-
ceiver is sufficiently strong to distinguish the four levels. The rate at which the
signal changes is then half the bit rate, so the needed bandwidth has been reduced.


---

<a id="page-139"></a>

<!-- Page 139 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 127
We call the rate at which the signal changes the symbol rate to distinguish it
from the bit rate. The bit rate is the symbol rate multiplied by the number of bits
per symbol. An older name for the symbol rate, particularly in the context of de-
vices called telephone modems that convey digital data over telephone lines, is
the baud rate. In the literature, the terms ''bit rate'' and ''baud rate'' are often
used incorrectly.
Note that the number of signal levels does not need to be a power of two.
Often it is not, with some of the levels used for protecting against errors and sim-
plifying the design of the receiver.
Clock Recovery
For all schemes that encode bits into symbols, the receiver must know when
one symbol ends and the next symbol begins to correctly decode the bits. With
NRZ, in which the symbols are simply voltage levels, a long run of 0s or 1s leaves
the signal unchanged. After a while it is hard to tell the bits apart, as 15 zeros
look much like 16 zeros unless you have a very accurate clock.
Accurate clocks would help with this problem, but they are an expensive solu-
tion for commodity equipment. Remember, we are timing bits on links that run at
many megabits/sec, so the clock would have to drift less than a fraction of a
microsecond over the longest permitted run. This might be reasonable for slow
links or short messages, but it is not a general solution.
One strategy is to send a separate clock signal to the receiver. Another clock
line is no big deal for computer buses or short cables in which there are many
lines in parallel, but it is wasteful for most network links since if we had another
line to send a signal we could use it to send data. A clever trick here is to mix the
clock signal with the data signal by XORing them together so that no extra line is
needed. The results are shown in Fig. 2-20(d). The clock makes a clock tran-
sition in every bit time, so it runs at twice the bit rate. When it is XORed with the
0 level it makes a low-to-high transition that is simply the clock. This transition is
a logical 0. When it is XORed with the 1 level it is inverted and makes a high-to-
low transition. This transition is a logical 1. This scheme is called Manchester
encoding and was used for classic Ethernet.
The downside of Manchester encoding is that it requires twice as much band-
width as NRZ because of the clock, and we have learned that bandwidth often
matters. A different strategy is based on the idea that we should code the data to
ensure that there are enough transitions in the signal. Consider that NRZ will
have clock recovery problems only for long runs of 0s and 1s. If there are fre-
quent transitions, it will be easy for the receiver to stay synchronized with the in-
coming stream of symbols.
As a step in the right direction, we can simplify the situation by coding a 1 as
a transition and a 0 as no transition, or vice versa. This coding is called NRZI
(Non-Return-to-Zero Inverted), a twist on NRZ. An example is shown in


---

<a id="page-140"></a>

<!-- Page 140 of 888 -->

128 THE PHYSICAL LAYER CHAP. 2
Fig. 2-20(c). The popular USB (Universal Serial Bus) standard for connecting
computer peripherals uses NRZI. With it, long runs of 1s do not cause a problem.
Of course, long runs of 0s still cause a problem that we must fix. If we were
the telephone company, we might simply require that the sender not transmit too
many 0s. Older digital telephone lines in the U.S., called T1 lines, did in fact re-
quire that no more than 15 consecutive 0s be sent for them to work correctly. To
really fix the problem we can break up runs of 0s by mapping small groups of bits
to be transmitted so that groups with successive 0s are mapped to slightly longer
patterns that do not have too many consecutive 0s.
A well-known code to do this is called 4B/5B. Every 4 bits is mapped into
a5-bit pattern with a fixed translation table. The five bit patterns are chosen so
that there will never be a run of more than three consecutive 0s. The mapping is
shown in Fig. 2-21. This scheme adds 25% overhead, which is better than the
100% overhead of Manchester encoding. Since there are 16 input combinations
and 32 output combinations, some of the output combinations are not used. Put-
ting aside the combinations with too many successive 0s, there are still some
codes left. As a bonus, we can use these nondata codes to represent physical layer
control signals. For example, in some uses ''11111'' represents an idle line and
''11000'' represents the start of a frame.
Data (4B) Codeword (5B) Data (4B) Codeword (5B)
0000 11110 1000 10010
0001 01001 1001 10011
0010 10100 1010 10110
0011 10101 1011 10111
0100 01010 1100 11010
0101 01011 1101 11011
0110 01110 1110 11100
0111 01111 1111 11101
Figure 2-21. 4B/5B mapping.
An alternative approach is to make the data look random, known as scram-
bling. In this case it is very likely that there will be frequent transitions. A
scrambler works by XORing the data with a pseudorandom sequence before it is
transmitted. This mixing will make the data as random as the pseudorandom se-
quence (assuming it is independent of the pseudorandom sequence). The receiver
then XORs the incoming bits with the same pseudorandom sequence to recover
the real data. For this to be practical, the pseudorandom sequence must be easy to
create. It is commonly given as the seed to a simple random number generator.
Scrambling is attractive because it adds no bandwidth or time overhead. In
fact, it often helps to condition the signal so that it does not have its energy in


---

<a id="page-141"></a>

<!-- Page 141 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 129
dominant frequency components (caused by repetitive data patterns) that might
radiate electromagnetic interference. Scrambling helps because random signals
tend to be ''white,'' or have energy spread across the frequency components.
However, scrambling does not guarantee that there will be no long runs. It is
possible to get unlucky occasionally. If the data are the same as the pseudorandom
sequence, they will XOR to all 0s. This outcome does not generally occur with a
long pseudorandom sequence that is difficult to predict. However, with a short or
predictable sequence, it might be possible for malicious users to send bit patterns
that cause long runs of 0s after scrambling and cause links to fail. Early versions
of the standards for sending IP packets over SONET links in the telephone system
had this defect (Malis and Simpson, 1999). It was possible for users to send cer-
tain ''killer packets'' that were guaranteed to cause problems.
Balanced Signals
Signals that have as much positive voltage as negative voltage even over short
periods of time are called balanced signals. They average to zero, which means
that they have no DC electrical component. The lack of a DC component is an
advantage because some channels, such as coaxial cable or lines with transform-
ers, strongly attenuate a DC component due to their physical properties. Also, one
method of connecting the receiver to the channel called capacitive coupling
passes only the AC portion of a signal. In either case, if we send a signal whose
average is not zero, we waste energy as the DC component will be filtered out.
Balancing helps to provide transitions for clock recovery since there is a mix
of positive and negative voltages. It also provides a simple way to calibrate re-
ceivers because the average of the signal can be measured and used as a decision
threshold to decode symbols. With unbalanced signals, the average may be drift
away from the true decision level due to a density of 1s, for example, which
would cause more symbols to be decoded with errors.
A straightforward way to construct a balanced code is to use two voltage lev-
els to represent a logical 1, (say +1 V or −1 V) with 0 V representing a logical
zero. To send a 1, the transmitter alternates between the +1 V and −1 V levels so
that they always average out. This scheme is called bipolar encoding. In tele-
phone networks it is called AMI (Alternate Mark Inversion), building on old
terminology in which a 1 is called a ''mark'' and a 0 is called a ''space.'' An ex-
ample is given in Fig. 2-20(e).
Bipolar encoding adds a voltage level to achieve balance. Alternatively we
can use a mapping like 4B/5B to achieve balance (as well as transitions for clock
recovery). An example of this kind of balanced code is the 8B/10B line code. It
maps 8 bits of input to 10 bits of output, so it is 80% efficient, just like the 4B/5B
line code. The 8 bits are split into a group of 5 bits, which is mapped to 6 bits,
and a group of 3 bits, which is mapped to 4 bits. The 6-bit and 4-bit symbols are


---

<a id="page-142"></a>

<!-- Page 142 of 888 -->

130 THE PHYSICAL LAYER CHAP. 2
then concatenated. In each group, some input patterns can be mapped to balanced
output patterns that have the same number of 0s and 1s. For example, ''001'' is
mapped to ''1001,'' which is balanced. But there are not enough combinations for
all output patterns to be balanced. For these cases, each input pattern is mapped
to two output patterns. One will have an extra 1 and the alternate will have an
extra 0. For example, ''000'' is mapped to both ''1011'' and its complement
''0100.'' As input bits are mapped to output bits, the encoder remembers the
disparity from the previous symbol. The disparity is the total number of 0s or 1s
by which the signal is out of balance. The encoder then selects either an output
pattern or its alternate to reduce the disparity. With 8B/10B, the disparity will be
at most 2 bits. Thus, the signal will never be far from balanced. There will also
never be more than five consecutive 1s or 0s, to help with clock recovery.
#### 2.5.2 Passband Transmission
Often, we want to use a range of frequencies that does not start at zero to send
information across a channel. For wireless channels, it is not practical to send
very low frequency signals because the size of the antenna needs to be a fraction
of the signal wavelength, which becomes large. In any case, regulatory con-
straints and the need to avoid interference usually dictate the choice of frequen-
cies. Even for wires, placing a signal in a given frequency band is useful to let
different kinds of signals coexist on the channel. This kind of transmission is call-
ed passband transmission because an arbitrary band of frequencies is used to pass
the signal.
Fortunately, our fundamental results from earlier in the chapter are all in
terms of bandwidth, or the width of the frequency band. The absolute frequency
values do not matter for capacity. This means that we can take a baseband signal
that occupies 0 to B Hz and shift it up to occupy a passband of S to S +B Hz with-
out changing the amount of information that it can carry, even though the signal
will look different. To process a signal at the receiver, we can shift it back down
to baseband, where it is more convenient to detect symbols.
Digital modulation is accomplished with passband transmission by regulating
or modulating a carrier signal that sits in the passband. We can modulate the am-
plitude, frequency, or phase of the carrier signal. Each of these methods has a cor-
responding name. In ASK (Amplitude Shift Keying), two different amplitudes
are used to represent 0 and 1. An example with a nonzero and a zero level is
shown in Fig. 2-22(b). More than two levels can be used to represent more symb-
ols. Similarly, with FSK (Frequency Shift Keying), two or more different tones
are used. The example in Fig. 2-21(c) uses just two frequencies. In the simplest
form of PSK (Phase Shift Keying), the carrier wave is systematically shifted 0 or
180 degrees at each symbol period. Because there are two phases, it is called
BPSK (Binary Phase Shift Keying). ''Binary'' here refers to the two symbols,
not that the symbols represent 2 bits. An example is shown in Fig. 2-22(c). A


---

<a id="page-143"></a>

<!-- Page 143 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 131
better scheme that uses the channel bandwidth more efficiently is to use four
shifts, e.g., 45, 135, 225, or 315 degrees, to transmit 2 bits of information per sym-
bol. This version is called QPSK (Quadrature Phase Shift Keying).
0 1 0 1 1 0 0 1 0 0 1 0 0
(a)
(b)
(c)
(d) Phase changes
Figure 2-22. (a) A binary signal. (b) Amplitude shift keying. (c) Frequency
shift keying. (d) Phase shift keying.
We can combine these schemes and use more levels to transmit more bits per
symbol. Only one of frequency and phase can be modulated at a time because
they are related, with frequency being the rate of change of phase over time.
Usually, amplitude and phase are modulated in combination. Three examples are
shown in Fig. 2-23. In each example, the points give the legal amplitude and
phase combinations of each symbol. In Fig. 2-23(a), we see equidistant dots at
45, 135, 225, and 315 degrees. The phase of a dot is indicated by the angle a line
from it to the origin makes with the positive x-axis. The amplitude of a dot is the
distance from the origin. This figure is a representation of QPSK.
This kind of diagram is called a constellation diagram. In Fig. 2-23(b) we
see a modulation scheme with a denser constellation. Sixteen combinations of
amplitudes and phase are used, so the modulation scheme can be used to transmit


---

<a id="page-144"></a>

<!-- Page 144 of 888 -->

132 THE PHYSICAL LAYER CHAP. 2
90 90 90
180 0 0 180 0
270 270 270
(a) (b) (c)
Figure 2-23. (a) QPSK. (b) QAM-16. (c) QAM-64.
4 bits per symbol. It is called QAM-16, where QAM stands for Quadrature Am-
plitude Modulation. Figure 2-23(c) is a still denser modulation scheme with 64
different combinations, so 6 bits can be transmitted per symbol. It is called
QAM-64. Even higher-order QAMs are used too. As you might suspect from
these constellations, it is easier to build electronics to produce symbols as a com-
bination of values on each axis than as a combination of amplitude and phase
values. That is why the patterns look like squares rather than concentric circles.
The constellations we have seen so far do not show how bits are assigned to
symbols. When making the assignment, an important consideration is that a small
burst of noise at the receiver not lead to many bit errors. This might happen if we
assigned consecutive bit values to adjacent symbols. With QAM-16, for example,
if one symbol stood for 0111 and the neighboring symbol stood for 1000, if the re-
ceiver mistakenly picks the adjacent symbol it will cause all of the bits to be
wrong. A better solution is to map bits to symbols so that adjacent symbols differ
in only 1 bit position. This mapping is called a Gray code. Fig. 2-24 shows a
QAM-16 constellation that has been Gray coded. Now if the receiver decodes the
symbol in error, it will make only a single bit error in the expected case that the
decoded symbol is close to the transmitted symbol.
#### 2.5.3 Frequency Division Multiplexing
The modulation schemes we have seen let us send one signal to convey bits
along a wired or wireless link. However, economies of scale play an important
role in how we use networks. It costs essentially the same amount of money to in-
stall and maintain a high-bandwidth transmission line as a low-bandwidth line be-
tween two different offices (i.e., the costs come from having to dig the trench and
not from what kind of cable or fiber goes into it). Consequently, multiplexing
schemes have been developed to share lines among many signals.


---

<a id="page-145"></a>

<!-- Page 145 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 133
Q
0000 0100 1100 1000
B When 1101 is sent:
0001 0101 1101 1001 Point Decodes as Bit errors
E
## A C A 1101 0
B 1100 1

0011 0111 1111 1011 C 1001 1
D 1111 1
E 0101 1
0010 0110 1110 1010
Figure 2-24. Gray-coded QAM-16.
FDM (Frequency Division Multiplexing) takes advantage of passband trans-
mission to share a channel. It divides the spectrum into frequency bands, with
each user having exclusive possession of some band in which to send their signal.
AM radio broadcasting illustrates FDM. The allocated spectrum is about 1 MHz,
roughly 500 to 1500 kHz. Different frequencies are allocated to different logical
channels (stations), each operating in a portion of the spectrum, with the
interchannel separation great enough to prevent interference.
For a more detailed example, in Fig. 2-25 we show three voice-grade tele-
phone channels multiplexed using FDM. Filters limit the usable bandwidth to
about 3100 Hz per voice-grade channel. When many channels are multiplexed to-
gether, 4000 Hz is allocated per channel. The excess is called a guard band. It
keeps the channels well separated. First the voice channels are raised in frequen-
cy, each by a different amount. Then they can be combined because no two chan-
nels now occupy the same portion of the spectrum. Notice that even though there
are gaps between the channels thanks to the guard bands, there is some overlap
between adjacent channels. The overlap is there because real filters do not have
ideal sharp edges. This means that a strong spike at the edge of one channel will
be felt in the adjacent one as nonthermal noise.
This scheme has been used to multiplex calls in the telephone system for
many years, but multiplexing in time is now preferred instead. However, FDM
continues to be used in telephone networks, as well as cellular, terrestrial wireless,
and satellite networks at a higher level of granularity.
When sending digital data, it is possible to divide the spectrum efficiently
without using guard bands. In OFDM (Orthogonal Frequency Division Multi-
plexing), the channel bandwidth is divided into many subcarriers that indepen-
dently send data (e.g., with QAM). The subcarriers are packed tightly together in
the frequency domain. Thus, signals from each subcarrier extend into adjacent
ones. However, as seen in Fig. 2-26, the frequency response of each subcarrier is


---

<a id="page-146"></a>

<!-- Page 146 of 888 -->

134 THE PHYSICAL LAYER CHAP. 2
Channel 1

Channel 2

Channel 3

300 3100
rotcafnoitaunettA Channel 2
Channel 1 Channel 3
60 64 68 72
Frequency (kHz)
(c)
60 64 68 72
Frequency (Hz) Frequency (kHz)
(a) (b)
Figure 2-25. Frequency division multiplexing. (a) The original bandwidths.
(b) The bandwidths raised in frequency. (c) The multiplexed channel.
designed so that it is zero at the center of the adjacent subcarriers. The subcarriers
can therefore be sampled at their center frequencies without interference from
their neighbors. To make this work, a guard time is needed to repeat a portion of
the symbol signals in time so that they have the desired frequency response.
However, this overhead is much less than is needed for many guard bands.
Power
Separation One OFDM subcarrier(shaded)
f
Frequency
f 1 f 2 f 3 f 4 f 5
Figure 2-26. Orthogonal frequency division multiplexing (OFDM).
The idea of OFDM has been around for a long time, but it is only in the last
decade that it has been widely adopted, following the realization that it is possible


---

<a id="page-147"></a>

<!-- Page 147 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 135
to implement OFDM efficiently in terms of a Fourier transform of digital data
over all subcarriers (instead of separately modulating each subcarrier). OFDM is
used in 802.11, cable networks and power line networking, and is planned for
fourth-generation cellular systems. Usually, one high-rate stream of digital infor-
mation is split into many low-rate streams that are transmitted on the subcarriers
in parallel. This division is valuable because degradations of the channel are easi-
er to cope with at the subcarrier level; some subcarriers may be very degraded and
excluded in favor of subcarriers that are received well.
#### 2.5.4 Time Division Multiplexing
An alternative to FDM is TDM (Time Division Multiplexing). Here, the
users take turns (in a round-robin fashion), each one periodically getting the entire
bandwidth for a little burst of time. An example of three streams being multi-
plexed with TDM is shown in Fig. 2-27. Bits from each input stream are taken in
a fixed time slot and output to the aggregate stream. This stream runs at the sum
rate of the individual streams. For this to work, the streams must be synchronized
in time. Small intervals of guard time analogous to a frequency guard band may
be added to accommodate small timing variations.

Round-robin
2 2 1 3 2 1 3 2
TDM
multiplexer
3 Guard time
Figure 2-27. Time Division Multiplexing (TDM).
TDM is used widely as part of the telephone and cellular networks. To avoid
one point of confusion, let us be clear that it is quite different from the alternative
STDM (Statistical Time Division Multiplexing). The prefix ''statistical'' is
added to indicate that the individual streams contribute to the multiplexed stream
not on a fixed schedule, but according to the statistics of their demand. STDM is
packet switching by another name.
#### 2.5.5 Code Division Multiplexing
There is a third kind of multiplexing that works in a completely different way
than FDM and TDM. CDM (Code Division Multiplexing) is a form of spread
spectrum communication in which a narrowband signal is spread out over a
wider frequency band. This can make it more tolerant of interference, as well as
allowing multiple signals from different users to share the same frequency band.
Because code division multiplexing is mostly used for the latter purpose it is com-
monly called CDMA (Code Division Multiple Access).


---

<a id="page-148"></a>

<!-- Page 148 of 888 -->

136 THE PHYSICAL LAYER CHAP. 2
CDMA allows each station to transmit over the entire frequency spectrum all
the time. Multiple simultaneous transmissions are separated using coding theory.
Before getting into the algorithm, let us consider an analogy: an airport lounge
with many pairs of people conversing. TDM is comparable to pairs of people in
the room taking turns speaking. FDM is comparable to the pairs of people speak-
ing at different pitches, some high-pitched and some low-pitched such that each
pair can hold its own conversation at the same time as but independently of the
others. CDMA is comparable to each pair of people talking at once, but in a dif-
ferent language. The French-speaking couple just hones in on the French, reject-
ing everything that is not French as noise. Thus, the key to CDMA is to be able to
extract the desired signal while rejecting everything else as random noise. A
somewhat simplified description of CDMA follows.
In CDMA, each bit time is subdivided into m short intervals called chips.
Typically, there are 64 or 128 chips per bit, but in the example given here we will
use 8 chips/bit for simplicity. Each station is assigned a unique m-bit code called
a chip sequence. For pedagogical purposes, it is convenient to use a bipolar nota-
tion to write these codes as sequences of −1 and +1. We will show chip se-
quences in parentheses.
To transmit a 1 bit, a station sends its chip sequence. To transmit a 0 bit, it
sends the negation of its chip sequence. No other patterns are permitted. Thus,
for m = 8, if station A is assigned the chip sequence (−1 −1 −1 +1 +1 −1 +1 +1), it
can send a 1 bit by transmiting the chip sequence and a 0 by transmitting
(+1 +1 +1 −1 −1 +1 −1 −1). It is really signals with these voltage levels that are
sent, but it is sufficient for us to think in terms of the sequences.
Increasing the amount of information to be sent from b bits/sec to mb
chips/sec for each station means that the bandwidth needed for CDMA is greater
by a factor of m than the bandwidth needed for a station not using CDMA (assum-
ing no changes in the modulation or encoding techniques). If we have a 1-MHz
band available for 100 stations, with FDM each one would have 10 kHz and could
send at 10 kbps (assuming 1 bit per Hz). With CDMA, each station uses the full 1
MHz, so the chip rate is 100 chips per bit to spread the station's bit rate of 10 kbps
across the channel.
In Fig. 2-28(a) and (b) we show the chip sequences assigned to four example
stations and the signals that they represent. Each station has its own unique chip
sequence. Let us use the symbol S to indicate the m-chip vector for station S, and
S for its negation. All chip sequences are pairwise orthogonal, by which we
mean that the normalized inner product of any two distinct chip sequences, S and
T (written as S T), is 0. It is known how to generate such orthogonal chip se-
quences using a method known as Walsh codes. In mathematical terms, ortho-
gonality of the chip sequences can be expressed as follows:
1 m
S T ≡ Σ S T = 0 (2-5)
i i

i =1


---

<a id="page-149"></a>

<!-- Page 149 of 888 -->

SEC. 2.5 DIGITAL MODULATION AND MULTIPLEXING 137
In plain English, as many pairs are the same as are different. This orthogonality
property will prove crucial later. Note that if S T = 0, then S T is also 0. The
normalized inner product of any chip sequence with itself is 1:
1 m 1 m 1 m
S S = Σ S S = Σ S2 = Σ (±1)2 = 1
i i i
m m m
i =1 i =1 i =1
This follows because each of the m terms in the inner product is 1, so the sum is
m. Also note that S S =− 1.
A = (-1 -1 -1 +1 +1 -1 +1 +1)
B = (-1 -1 +1 -1 +1 +1 +1 -1)
C = (-1 +1 -1 +1 +1 +1 -1 -1)
D = (-1 +1 -1 -1 -1 -1 +1 -1)
(a) (b)
S = C = (-1 +1 -1 +1 +1 +1 -1 -1) S C = [1+1-1+1+1+1-1-1]/8 = 1
1 1
S = B+C = (-2 0 0 0 +2 +2 0 -2) S C = [2+0+0+0+2+2+0+2]/8 = 1
2 2
S = A+B = ( 0 0 -2 +2 0 -2 0 +2) S C = [0+0+2+2+0-2+0-2]/8 = 0
3 3
S = A+B+C = (-1 +1 -3 +3 +1 -1 -1 +1) S C = [1+1+3+3+1-1+1-1]/8 = 1
4 4
S = A+B+C+D = (-4 0 -2 0 +2 0 +2 -2) S C = [4+0+2+0+2+0-2+2]/8 = 1
5 5
S = A+B+C+D = (-2 -2 0 -2 0 -2 +4 0) S C = [2-2+0-2+0-2-4+0]/8 = -1
6 6
(c) (d)
Figure 2-28. (a) Chip sequences for four stations. (b) Signals the sequences
represent (c) Six examples of transmissions. (d) Recovery of station C's signal.
During each bit time, a station can transmit a 1 (by sending its chip sequence),
it can transmit a 0 (by sending the negative of its chip sequence), or it can be
silent and transmit nothing. We assume for now that all stations are synchronized
in time, so all chip sequences begin at the same instant. When two or more sta-
tions transmit simultaneously, their bipolar sequences add linearly. For example,
if in one chip period three stations output +1 and one station outputs −1, +2 will
be received. One can think of this as signals that add as voltages superimposed on
the channel: three stations output +1 V and one station outputs −1 V, so that 2 V is
received. For instance, in Fig. 2-28(c) we see six examples of one or more sta-
tions transmitting 1 bit at the same time. In the first example, C transmits a 1 bit,
so we just get C's chip sequence. In the second example, both B and C transmit 1
bits, so we get the sum of their bipolar chip sequences, namely:
(−1 −1 +1 −1 +1 +1 +1 −1) + (−1 +1 −1 +1 +1 +1 −1 −1) = (−2 0 0 0 +2 +2 0 −2)
To recover the bit stream of an individual station, the receiver must know that
station's chip sequence in advance. It does the recovery by computing the nor-
malized inner product of the received chip sequence and the chip sequence of the
station whose bit stream it is trying to recover. If the received chip sequence is S
and the receiver is trying to listen to a station whose chip sequence is C, it just
computes the normalized inner product, S C.


---

<a id="page-150"></a>

<!-- Page 150 of 888 -->

138 THE PHYSICAL LAYER CHAP. 2
To see why this works, just imagine that two stations, A and C, both transmit a
1 bit at the same time that B transmits a 0 bit, as is the case in the third example.
The receiver sees the sum, S = A + B + C, and computes
S C = (A + B + C) C = A C + B C + C C = 0 + 0 + 1 = 1
The first two terms vanish because all pairs of chip sequences have been carefully
chosen to be orthogonal, as shown in Eq. (2-5). Now it should be clear why this
property must be imposed on the chip sequences.
To make the decoding process more concrete, we show six examples in
Fig. 2-28(d). Suppose that the receiver is interested in extracting the bit sent by
station C from each of the six signals S through S . It calculates the bit by sum-
1 6
ming the pairwise products of the received S and the C vector of Fig. 2-28(a) and
then taking 1/8 of the result (since m = 8 here). The examples include cases
where C is silent, sends a 1 bit, and sends a 0 bit, individually and in combination
with other transmissions. As shown, the correct bit is decoded each time. It is
just like speaking French.
In principle, given enough computing capacity, the receiver can listen to all
the senders at once by running the decoding algorithm for each of them in paral-
lel. In real life, suffice it to say that this is easier said than done, and it is useful to
know which senders might be transmitting.
In the ideal, noiseless CDMA system we have studied here, the number of sta-
tions that send concurrently can be made arbitrarily large by using longer chip se-
quences. For 2n stations, Walsh codes can provide 2n orthogonal chip sequences
of length 2n. However, one significant limitation is that we have assumed that all
the chips are synchronized in time at the receiver. This synchronization is not
even approximately true in some applications, such as cellular networks (in which
CDMA has been widely deployed starting in the 1990s). It leads to different de-
signs. We will return to this topic later in the chapter and describe how asynchro-
nous CDMA differs from synchronous CDMA.
As well as cellular networks, CDMA is used by satellites and cable networks.
We have glossed over many complicating factors in this brief introduction. En-
gineers who want to gain a deep understanding of CDMA should read Viterbi
(1995) and Lee and Miller (1998). These references require quite a bit of back-
ground in communication engineering, however.
### 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK
When two computers owned by the same company or organization and locat-
ed close to each other need to communicate, it is often easiest just to run a cable
between them. LANs work this way. However, when the distances are large or
there are many computers or the cables have to pass through a public road or other
public right of way, the costs of running private cables are usually prohibitive.


---

<a id="page-151"></a>

<!-- Page 151 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 139
Furthermore, in just about every country in the world, stringing private transmis-
sion lines across (or underneath) public property is also illegal. Consequently, the
network designers must rely on the existing telecommunication facilities.
These facilities, especially the PSTN (Public Switched Telephone Net-
work), were usually designed many years ago, with a completely different goal in
mind: transmitting the human voice in a more-or-less recognizable form. Their
suitability for use in computer-computer communication is often marginal at best.
To see the size of the problem, consider that a cheap commodity cable running be-
tween two computers can transfer data at 1 Gbps or more. In contrast, typical
ADSL, the blazingly fast alternative to a telephone modem, runs at around 1
Mbps. The difference between the two is the difference between cruising in an
airplane and taking a leisurely stroll.
Nonetheless, the telephone system is tightly intertwined with (wide area)
computer networks, so it is worth devoting some time to study it in detail. The
limiting factor for networking purposes turns out to be the ''last mile'' over which
customers connect, not the trunks and switches inside the telephone network.
This situation is changing with the gradual rollout of fiber and digital technology
at the edge of the network, but it will take time and money. During the long wait,
computer systems designers used to working with systems that give at least three
orders of magnitude better performance have devoted much time and effort to fig-
ure out how to use the telephone network efficiently.
In the following sections we will describe the telephone system and show how
it works. For additional information about the innards of the telephone system see
Bellamy (2000).
#### 2.6.1 Structure of the Telephone System
Soon after Alexander Graham Bell patented the telephone in 1876 (just a few
hours ahead of his rival, Elisha Gray), there was an enormous demand for his new
invention. The initial market was for the sale of telephones, which came in pairs.
It was up to the customer to string a single wire between them. If a telephone
owner wanted to talk to n other telephone owners, separate wires had to be strung
to all n houses. Within a year, the cities were covered with wires passing over
houses and trees in a wild jumble. It became immediately obvious that the model
of connecting every telephone to every other telephone, as shown in Fig. 2-29(a),
was not going to work.
To his credit, Bell saw this problem early on and formed the Bell Telephone
Company, which opened its first switching office (in New Haven, Connecticut) in
1878. The company ran a wire to each customer's house or office. To make a
call, the customer would crank the phone to make a ringing sound in the telephone
company office to attract the attention of an operator, who would then manually
connect the caller to the callee by using a short jumper cable to connect the caller
to the callee. The model of a single switching office is illustrated in Fig. 2-29(b).


---

<a id="page-152"></a>

<!-- Page 152 of 888 -->

140 THE PHYSICAL LAYER CHAP. 2
(a) (b) (c)
Figure 2-29. (a) Fully interconnected network. (b) Centralized switch.
(c) Two-level hierarchy.
Pretty soon, Bell System switching offices were springing up everywhere and
people wanted to make long-distance calls between cities, so the Bell System
began to connect the switching offices. The original problem soon returned: to
connect every switching office to every other switching office by means of a wire
between them quickly became unmanageable, so second-level switching offices
were invented. After a while, multiple second-level offices were needed, as illus-
trated in Fig. 2-29(c). Eventually, the hierarchy grew to five levels.
By 1890, the three major parts of the telephone system were in place: the
switching offices, the wires between the customers and the switching offices (by
now balanced, insulated, twisted pairs instead of open wires with an earth return),
and the long-distance connections between the switching offices. For a short
technical history of the telephone system, see Hawley (1991).
While there have been improvements in all three areas since then, the basic
Bell System model has remained essentially intact for over 100 years. The fol-
lowing description is highly simplified but gives the essential flavor nevertheless.
Each telephone has two copper wires coming out of it that go directly to the tele-
phone company's nearest end office (also called a local central office). The dis-
tance is typically 1 to 10 km, being shorter in cities than in rural areas. In the
United States alone there are about 22,000 end offices. The two-wire connections
between each subscriber's telephone and the end office are known in the trade as
the local loop. If the world's local loops were stretched out end to end, they
would extend to the moon and back 1000 times.
At one time, 80% of AT&T's capital value was the copper in the local loops.
AT&T was then, in effect, the world's largest copper mine. Fortunately, this fact
was not well known in the investment community. Had it been known, some cor-
porate raider might have bought AT&T, ended all telephone service in the United
States, ripped out all the wire, and sold it to a copper refiner for a quick payback.


---

<a id="page-153"></a>

<!-- Page 153 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 141
If a subscriber attached to a given end office calls another subscriber attached
to the same end office, the switching mechanism within the office sets up a direct
electrical connection between the two local loops. This connection remains intact
for the duration of the call.
If the called telephone is attached to another end office, a different procedure
has to be used. Each end office has a number of outgoing lines to one or more
nearby switching centers, called toll offices (or, if they are within the same local
area, tandem offices). These lines are called toll connecting trunks. The num-
ber of different kinds of switching centers and their topology varies from country
to country depending on the country's telephone density.
If both the caller's and callee's end offices happen to have a toll connecting
trunk to the same toll office (a likely occurrence if they are relatively close by),
the connection may be established within the toll office. A telephone network
consisting only of telephones (the small dots), end offices (the large dots), and toll
offices (the squares) is shown in Fig. 2-29(c).
If the caller and callee do not have a toll office in common, a path will have to
be established between two toll offices. The toll offices communicate with each
other via high-bandwidth intertoll trunks (also called interoffice trunks). Prior
to the 1984 breakup of AT&T, the U.S. telephone system used hierarchical rout-
ing to find a path, going to higher levels of the hierarchy until there was a switch-
ing office in common. This was then replaced with more flexible, nonhierarchical
routing. Figure 2-30 shows how a long-distance connection might be routed.
Intermediate
Telephone End Toll switching Toll End Telephone
office office office(s) office office
Very high
Local Toll Toll Local
bandwidth
loop connecting connecting loop
intertoll
trunk trunk
trunks
Figure 2-30. A typical circuit route for a long-distance call.
A variety of transmission media are used for telecommunication. Unlike
modern office buildings, where the wiring is commonly Category 5, local loops to
homes mostly consist of Category 3 twisted pairs, with fiber just starting to
appear. Between switching offices, coaxial cables, microwaves, and especially
fiber optics are widely used.
In the past, transmission throughout the telephone system was analog, with
the actual voice signal being transmitted as an electrical voltage from source to
destination. With the advent of fiber optics, digital electronics, and computers, all
the trunks and switches are now digital, leaving the local loop as the last piece of


---

<a id="page-154"></a>

<!-- Page 154 of 888 -->

142 THE PHYSICAL LAYER CHAP. 2
analog technology in the system. Digital transmission is preferred because it is
not necessary to accurately reproduce an analog waveform after it has passed
through many amplifiers on a long call. Being able to correctly distinguish a 0
from a 1 is enough. This property makes digital transmission more reliable than
analog. It is also cheaper and easier to maintain.
In summary, the telephone system consists of three major components:
1. Local loops (analog twisted pairs going to houses and businesses).
2. Trunks (digital fiber optic links connecting the switching offices).
3. Switching offices (where calls are moved from one trunk to another).
After a short digression on the politics of telephones, we will come back to each
of these three components in some detail. The local loops provide everyone ac-
cess to the whole system, so they are critical. Unfortunately, they are also the
weakest link in the system. For the long-haul trunks, the main issue is how to col-
lect multiple calls together and send them out over the same fiber. This calls for
multiplexing, and we apply FDM and TDM to do it. Finally, there are two funda-
mentally different ways of doing switching; we will look at both.
#### 2.6.2 The Politics of Telephones
For decades prior to 1984, the Bell System provided both local and long-dis-
tance service throughout most of the United States. In the 1970s, the U.S. Federal
Government came to believe that this was an illegal monopoly and sued to break
it up. The government won, and on January 1, 1984, AT&T was broken up into
AT&T Long Lines, 23 BOCs (Bell Operating Companies), and a few other
pieces. The 23 BOCs were grouped into seven regional BOCs (RBOCs) to make
them economically viable. The entire nature of telecommunication in the United
States was changed overnight by court order (not by an act of Congress).
The exact specifications of the divestiture were described in the so-called
MFJ (Modified Final Judgment), an oxymoron if ever there was one-if the
judgment could be modified, it clearly was not final. This event led to increased
competition, better service, and lower long-distance rates for consumers and busi-
nesses. However, prices for local service rose as the cross subsidies from long-
distance calling were eliminated and local service had to become self supporting.
Many other countries have now introduced competition along similar lines.
Of direct relevance to our studies is that the new competitive framework
caused a key technical feature to be added to the architecture of the telephone net-
work. To make it clear who could do what, the United States was divided up into
164 LATAs (Local Access and Transport Areas). Very roughly, a LATA is
about as big as the area covered by one area code. Within each LATA, there was
one LEC (Local Exchange Carrier) with a monopoly on traditional telephone


---

<a id="page-155"></a>

<!-- Page 155 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 143
service within its area. The most important LECs were the BOCs, although some
LATAs contained one or more of the 1500 independent telephone companies op-
erating as LECs.
The new feature was that all inter-LATA traffic was handled by a different
kind of company, an IXC (IntereXchange Carrier). Originally, AT&T Long
Lines was the only serious IXC, but now there are well-established competitors
such as Verizon and Sprint in the IXC business. One of the concerns at the
breakup was to ensure that all the IXCs would be treated equally in terms of line
quality, tariffs, and the number of digits their customers would have to dial to use
them. The way this is handled is illustrated in Fig. 2-31. Here we see three ex-
ample LATAs, each with several end offices. LATAs 2 and 3 also have a small
hierarchy with tandem offices (intra-LATA toll offices).
IXC #1's IXC #2's
toll office toll office
1 2
IXC POP
1 2 1 2 1 2 Tandem
office
End
office
To local loops
## Lata 1 Lata 2 Lata 3
Figure 2-31. The relationship of LATAs, LECs, and IXCs. All the circles are
LEC switching offices. Each hexagon belongs to the IXC whose number is in it.
Any IXC that wishes to handle calls originating in a LATA can build a
switching office called a POP (Point of Presence) there. The LEC is required to
connect each IXC to every end office, either directly, as in LATAs 1 and 3, or
indirectly, as in LATA 2. Furthermore, the terms of the connection, both techni-
cal and financial, must be identical for all IXCs. This requirement enables, a sub-
scriber in, say, LATA 1, to choose which IXC to use for calling subscribers in
LATA 3.
As part of the MFJ, the IXCs were forbidden to offer local telephone service
and the LECs were forbidden to offer inter-LATA telephone service, although


---

<a id="page-156"></a>

<!-- Page 156 of 888 -->

144 THE PHYSICAL LAYER CHAP. 2
both were free to enter any other business, such as operating fried chicken restau-
rants. In 1984, that was a fairly unambiguous statement. Unfortunately, technolo-
gy has a funny way of making the law obsolete. Neither cable television nor mo-
bile phones were covered by the agreement. As cable television went from one
way to two way and mobile phones exploded in popularity, both LECs and IXCs
began buying up or merging with cable and mobile operators.
By 1995, Congress saw that trying to maintain a distinction between the vari-
ous kinds of companies was no longer tenable and drafted a bill to preserve ac-
cessibility for competition but allow cable TV companies, local telephone com-
panies, long-distance carriers, and mobile operators to enter one another's busi-
nesses. The idea was that any company could then offer its customers a single
integrated package containing cable TV, telephone, and information services and
that different companies would compete on service and price. The bill was en-
acted into law in February 1996 as a major overhaul of telecommunications regu-
lation. As a result, some BOCs became IXCs and some other companies, such as
cable television operators, began offering local telephone service in competition
with the LECs.
One interesting property of the 1996 law is the requirement that LECs imple-
ment local number portability. This means that a customer can change local
telephone companies without having to get a new telephone number. Portability
for mobile phone numbers (and between fixed and mobile lines) followed suit in
2003. These provisions removed a huge hurdle for many people, making them
much more inclined to switch LECs. As a result, the U.S. telecommunications
landscape became much more competitive, and other countries have followed
suit. Often other countries wait to see how this kind of experiment works out in
the U.S. If it works well, they do the same thing; if it works badly, they try some-
thing else.
#### 2.6.3 The Local Loop: Modems, ADSL, and Fiber
It is now time to start our detailed study of how the telephone system works.
Let us begin with the part that most people are familiar with: the two-wire local
loop coming from a telephone company end office into houses. The local loop is
also frequently referred to as the ''last mile,'' although the length can be up to
several miles. It has carried analog information for over 100 years and is likely to
continue doing so for some years to come, due to the high cost of converting to
digital.
Much effort has been devoted to squeezing data networking out of the copper
local loops that are already deployed. Telephone modems send digital data be-
tween computers over the narrow channel the telephone network provides for a
voice call. They were once widely used, but have been largely displaced by
broadband technologies such as ADSL that. reuse the local loop to send digital
data from a customer to the end office, where they are siphoned off to the Internet.


---

<a id="page-157"></a>

<!-- Page 157 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 145
Both modems and ADSL must deal with the limitations of old local loops: rel-
atively narrow bandwidth, attenuation and distortion of signals, and susceptibility
to electrical noise such as crosstalk.
In some places, the local loop has been modernized by installing optical fiber
to (or very close to) the home. Fiber is the way of the future. These installations
support computer networks from the ground up, with the local loop having ample
bandwidth for data services. The limiting factor is what people will pay, not the
physics of the local loop.
In this section we will study the local loop, both old and new. We will cover
telephone modems, ADSL, and fiber to the home.
Telephone Modems
To send bits over the local loop, or any other physical channel for that matter,
they must be converted to analog signals that can be transmitted over the channel.
This conversion is accomplished using the methods for digital modulation that we
studied in the previous section. At the other end of the channel, the analog signal
is converted back to bits.
A device that converts between a stream of digital bits and an analog signal
that represents the bits is called a modem, which is short for ''modulator demodu-
lator.'' Modems come in many varieties: telephone modems, DSL modems, cable
modems, wireless modems, etc. The modem may be built into the computer
(which is now common for telephone modems) or be a separate box (which is
common for DSL and cable modems). Logically, the modem is inserted between
the (digital) computer and the (analog) telephone system, as seen in Fig. 2-32.
Computer Trunk (digital, fiber) Digital line
Local loop
ISP 2
(analog)
Analog line
Modem
Codec
ISP 1
End
office
Codec Modem
Figure 2-32. The use of both analog and digital transmission for a computer-
to-computer call. Conversion is done by the modems and codecs.
Telephone modems are used to send bits between two computers over a
voice-grade telephone line, in place of the conversation that usually fills the line.
The main difficulty in doing so is that a voice-grade telephone line is limited to
3100 Hz, about what is sufficient to carry a conversation. This bandwidth is more
than four orders of magnitude less than the bandwidth that is used for Ethernet or


---

<a id="page-158"></a>

<!-- Page 158 of 888 -->

146 THE PHYSICAL LAYER CHAP. 2
### 802.11 (WiFi). Unsurprisingly, the data rates of telephone modems are also four
orders of magnitude less than that of Ethernet and 802.11.
Let us run the numbers to see why this is the case. The Nyquist theorem tells
us that even with a perfect 3000-Hz line (which a telephone line is decidedly not),
there is no point in sending symbols at a rate faster than 6000 baud. In practice,
most modems send at a rate of 2400 symbols/sec, or 2400 baud, and focus on get-
ting multiple bits per symbol while allowing traffic in both directions at the same
time (by using different frequencies for different directions).
The humble 2400-bps modem uses 0 volts for a logical 0 and 1 volt for a logi-
cal 1, with 1 bit per symbol. One step up, it can use four different symbols, as in
the four phases of QPSK, so with 2 bits/symbol it can get a data rate of 4800 bps.
A long progression of higher rates has been achieved as technology has im-
proved. Higher rates require a larger set of symbols or constellation. With many
symbols, even a small amount of noise in the detected amplitude or phase can re-
sult in an error. To reduce the chance of errors, standards for the higher-speed
modems use some of the symbols for error correction. The schemes are known as
TCM (Trellis Coded Modulation) (Ungerboeck, 1987).
The V.32 modem standard uses 32 constellation points to transmit 4 data bits
and 1 check bit per symbol at 2400 baud to achieve 9600 bps with error cor-
rection. The next step above 9600 bps is 14,400 bps. It is called V.32 bis and
transmits 6 data bits and 1 check bit per symbol at 2400 baud. Then comes V.34,
which achieves 28,800 bps by transmitting 12 data bits/symbol at 2400 baud. The
constellation now has thousands of points. The final modem in this series is V.34
bis which uses 14 data bits/symbol at 2400 baud to achieve 33,600 bps.
Why stop here? The reason that standard modems stop at 33,600 is that the
Shannon limit for the telephone system is about 35 kbps based on the average
length of local loops and the quality of these lines. Going faster than this would
violate the laws of physics (department of thermodynamics).
However, there is one way we can change the situation. At the telephone
company end office, the data are converted to digital form for transmission within
the telephone network (the core of the telephone network converted from analog
to digital long ago). The 35-kbps limit is for the situation in which there are two
local loops, one at each end. Each of these adds noise to the signal. If we could
get rid of one of these local loops, we would increase the SNR and the maximum
rate would be doubled.
This approach is how 56-kbps modems are made to work. One end, typically
an ISP, gets a high-quality digital feed from the nearest end office. Thus, when
one end of the connection is a high-quality signal, as it is with most ISPs now, the
maximum data rate can be as high as 70 kbps. Between two home users with
modems and analog lines, the maximum is still 33.6 kbps.
The reason that 56-kbps modems (rather than 70-kbps modems) are in use has
to do with the Nyquist theorem. A telephone channel is carried inside the tele-
phone system as digital samples. Each telephone channel is 4000 Hz wide when


---

<a id="page-159"></a>

<!-- Page 159 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 147
the guard bands are included. The number of samples per second needed to
reconstruct it is thus 8000. The number of bits per sample in the U.S. is 8, one of
which may be used for control purposes, allowing 56,000 bits/sec of user data. In
Europe, all 8 bits are available to users, so 64,000-bit/sec modems could have
been used, but to get international agreement on a standard, 56,000 was chosen.
The end result is the V.90 and V.92 modem standards. They provide for a
56-kbps downstream channel (ISP to user) and a 33.6-kbps and 48-kbps upstream
channel (user to ISP), respectively. The asymmetry is because there is usually
more data transported from the ISP to the user than the other way. It also means
that more of the limited bandwidth can be allocated to the downstream channel to
increase the chances of it actually working at 56 kbps.
Digital Subscriber Lines
When the telephone industry finally got to 56 kbps, it patted itself on the back
for a job well done. Meanwhile, the cable TV industry was offering speeds up to
10 Mbps on shared cables. As Internet access became an increasingly important
part of their business, the telephone companies (LECs) began to realize they need-
ed a more competitive product. Their answer was to offer new digital services
over the local loop.
Initially, there were many overlapping high-speed offerings, all under the gen-
eral name of xDSL (Digital Subscriber Line), for various x. Services with more
bandwidth than standard telephone service are sometimes called broadband, al-
though the term really is more of a marketing concept than a specific technical
concept. Later, we will discuss what has become the most popular of these ser-
vices, ADSL (Asymmetric DSL). We will also use the term DSL or xDSL as
shorthand for all flavors.
The reason that modems are so slow is that telephones were invented for car-
rying the human voice and the entire system has been carefully optimized for this
purpose. Data have always been stepchildren. At the point where each local loop
terminates in the end office, the wire runs through a filter that attenuates all fre-
quencies below 300 Hz and above 3400 Hz. The cutoff is not sharp-300 Hz and
3400 Hz are the 3-dB points-so the bandwidth is usually quoted as 4000 Hz even
though the distance between the 3 dB points is 3100 Hz. Data on the wire are thus
also restricted to this narrow band.
The trick that makes xDSL work is that when a customer subscribes to it, the
incoming line is connected to a different kind of switch, one that does not have
this filter, thus making the entire capacity of the local loop available. The limiting
factor then becomes the physics of the local loop, which supports roughly 1 MHz,
not the artificial 3100 Hz bandwidth created by the filter.
Unfortunately, the capacity of the local loop falls rather quickly with distance
from the end office as the signal is increasingly degraded along the wire. It also
depends on the thickness and general quality of the twisted pair. A plot of the


---

<a id="page-160"></a>

<!-- Page 160 of 888 -->

148 THE PHYSICAL LAYER CHAP. 2
potential bandwidth as a function of distance is given in Fig. 2-33. This figure as-
sumes that all the other factors are optimal (new wires, modest bundles, etc.).

0 1000 2000 3000 4000 5000 6000
Meters
spbM
Figure 2-33. Bandwidth versus distance over Category 3 UTP for DSL.
The implication of this figure creates a problem for the telephone company.
When it picks a speed to offer, it is simultaneously picking a radius from its end
offices beyond which the service cannot be offered. This means that when distant
customers try to sign up for the service, they may be told ''Thanks a lot for your
interest, but you live 100 meters too far from the nearest end office to get this ser-
vice. Could you please move?'' The lower the chosen speed is, the larger the
radius and the more customers are covered. But the lower the speed, the less
attractive the service is and the fewer the people who will be willing to pay for it.
This is where business meets technology.
The xDSL services have all been designed with certain goals in mind. First,
the services must work over the existing Category 3 twisted pair local loops. Sec-
ond, they must not affect customers' existing telephones and fax machines. Third,
they must be much faster than 56 kbps. Fourth, they should be always on, with
just a monthly charge and no per-minute charge.
To meet the technical goals, the available 1.1 MHz spectrum on the local loop
is divided into 256 independent channels of 4312.5 Hz each. This arrangement is
shown in Fig. 2-34. The OFDM scheme, which we saw in the previous section, is
used to send data over these channels, though it is often called DMT (Discrete
MultiTone) in the context of ADSL. Channel 0 is used for POTS (Plain Old
Telephone Service). Channels 1-5 are not used, to keep the voice and data sig-
nals from interfering with each other. Of the remaining 250 channels, one is used
for upstream control and one is used for downstream control. The rest are avail-
able for user data.
In principle, each of the remaining channels can be used for a full-duplex data
stream, but harmonics, crosstalk, and other effects keep practical systems well


---

<a id="page-161"></a>

<!-- Page 161 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 149
rewoP
256 4-kHz Channels
0 25 1100 kHz
Voice Upstream Downstream
Figure 2-34. Operation of ADSL using discrete multitone modulation.
below the theoretical limit. It is up to the provider to determine how many chan-
nels are used for upstream and how many for downstream. A 50/50 mix of
upstream and downstream is technically possible, but most providers allocate
something like 80-90% of the bandwidth to the downstream channel since most
users download more data than they upload. This choice gives rise to the ''A'' in
ADSL. A common split is 32 channels for upstream and the rest downstream. It
is also possible to have a few of the highest upstream channels be bidirectional for
increased bandwidth, although making this optimization requires adding a special
circuit to cancel echoes.
The international ADSL standard, known as G.dmt, was approved in 1999. It
allows speeds of as much as 8 Mbps downstream and 1 Mbps upstream. It was
superseded by a second generation in 2002, called ADSL2, with various im-
provements to allow speeds of as much as 12 Mbps downstream and 1 Mbps up-
stream. Now we have ADSL2+, which doubles the downstream speed to 24
Mbps by doubling the bandwidth to use 2.2 MHz over the twisted pair.
However, the numbers quoted here are best-case speeds for good lines close
(within 1 to 2 km) to the exchange. Few lines support these rates, and few pro-
viders offer these speeds. Typically, providers offer something like 1 Mbps
downstream and 256 kbps upstream (standard service), 4 Mbps downstream and 1
Mbps upstream (improved service), and 8 Mbps downstream and 2 Mbps
upstream (premium service).
Within each channel, QAM modulation is used at a rate of roughly 4000
symbols/sec. The line quality in each channel is constantly monitored and the
data rate is adjusted by using a larger or smaller constellation, like those in
Fig. 2-23. Different channels may have different data rates, with up to 15 bits per
symbol sent on a channel with a high SNR, and down to 2, 1, or no bits per sym-
bol sent on a channel with a low SNR depending on the standard.
A typical ADSL arrangement is shown in Fig. 2-35. In this scheme, a tele-
phone company technician must install a NID (Network Interface Device) on the
customer's premises. This small plastic box marks the end of the telephone com-
pany's property and the start of the customer's property. Close to the NID (or
sometimes combined with it) is a splitter, an analog filter that separates the


---

<a id="page-162"></a>

<!-- Page 162 of 888 -->

150 THE PHYSICAL LAYER CHAP. 2
0-4000-Hz band used by POTS from the data. The POTS signal is routed to the
existing telephone or fax machine. The data signal is routed to an ADSL modem,
which uses digital signal processing to implement OFDM. Since most ADSL
modems are external, the computer must be connected to them at high speed.
Usually, this is done using Ethernet, a USB cable, or 802.11.
Voice
switch Telephone
Codec
Splitter Telephone Splitter
line
NID
Computer
DSLAM
ADSL Ethernet
modem
To ISP
Telephone company end office Customer premises
Figure 2-35. A typical ADSL equipment configuration.
At the other end of the wire, on the end office side, a corresponding splitter is
installed. Here, the voice portion of the signal is filtered out and sent to the nor-
mal voice switch. The signal above 26 kHz is routed to a new kind of device call-
ed a DSLAM (Digital Subscriber Line Access Multiplexer), which contains the
same kind of digital signal processor as the ADSL modem. Once the bits have
been recovered from the signal, packets are formed and sent off to the ISP.
This complete separation between the voice system and ADSL makes it rel-
atively easy for a telephone company to deploy ADSL. All that is needed is buy-
ing a DSLAM and splitter and attaching the ADSL subscribers to the splitter.
Other high-bandwidth services (e.g., ISDN) require much greater changes to the
existing switching equipment.
One disadvantage of the design of Fig. 2-35 is the need for a NID and splitter
on the customer's premises. Installing these can only be done by a telephone
company technician, necessitating an expensive ''truck roll'' (i.e., sending a tech-
nician to the customer's premises). Therefore, an alternative, splitterless design,
informally called G.lite, has also been standardized. It is the same as Fig. 2-35
but without the customer's splitter. The existing telephone line is used as is. The
only difference is that a microfilter has to be inserted into each telephone jack


---

<a id="page-163"></a>

<!-- Page 163 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 151
between the telephone or ADSL modem and the wire. The microfilter for the
telephone is a low-pass filter eliminating frequencies above 3400 Hz; the microfil-
ter for the ADSL modem is a high-pass filter eliminating frequencies below 26
kHz. However, this system is not as reliable as having a splitter, so G.lite can be
used only up to 1.5 Mbps (versus 8 Mbps for ADSL with a splitter). For more
information about ADSL, see Starr (2003).
Fiber To The Home
Deployed copper local loops limit the performance of ADSL and telephone
modems. To let them provide faster and better network services, telephone com-
panies are upgrading local loops at every opportunity by installing optical fiber all
the way to houses and offices. The result is called FttH (Fiber To The Home).
While FttH technology has been available for some time, deployments only began
to take off in 2005 with growth in the demand for high-speed Internet from cus-
tomers used to DSL and cable who wanted to download movies. Around 4% of
U.S. houses are now connected to FttH with Internet access speeds of up to 100
Mbps.
Several variations of the form ''FttX'' (where X stands for the basement, curb,
or neighborhood) exist. They are used to note that the fiber deployment may
reach close to the house. In this case, copper (twisted pair or coaxial cable) pro-
vides fast enough speeds over the last short distance. The choice of how far to lay
the fiber is an economic one, balancing cost with expected revenue. In any case,
the point is that optical fiber has crossed the traditional barrier of the ''last mile.''
We will focus on FttH in our discussion.
Like the copper wires before it, the fiber local loop is passive. This means no
powered equipment is required to amplify or otherwise process signals. The fiber
simply carries signals between the home and the end office. This in turn reduces
cost and improves reliability.
Usually, the fibers from the houses are joined together so that only a single
fiber reaches the end office per group of up to 100 houses. In the downstream di-
rection, optical splitters divide the signal from the end office so that it reaches all
the houses. Encryption is needed for security if only one house should be able to
decode the signal. In the upstream direction, optical combiners merge the signals
from the houses into a single signal that is received at the end office.
This architecture is called a PON (Passive Optical Network), and it is shown
in Fig. 2-36. It is common to use one wavelength shared between all the houses
for downstream transmission, and another wavelength for upstream transmission.
Even with the splitting, the tremendous bandwidth and low attenuation of
fiber mean that PONs can provide high rates to users over distances of up to 20
km. The actual data rates and other details depend on the type of PON. Two kinds
are common. GPONs (Gigabit-capable PONs) come from the world of telecom-
munications, so they are defined by an ITU standard. EPONs (Ethernet PONs)


---

<a id="page-164"></a>

<!-- Page 164 of 888 -->

152 THE PHYSICAL LAYER CHAP. 2
Fiber
Rest of
network
Optical
End office splitter/combiner
Figure 2-36. Passive optical network for Fiber To The Home.
are more in tune with the world of networking, so they are defined by an IEEE
standard. Both run at around a gigabit and can carry traffic for different services,
including Internet, video, and voice. For example, GPONs provide 2.4 Gbps
downstream and 1.2 or 2.4 Gbps upstream.
Some protocol is needed to share the capacity of the single fiber at the end
office between the different houses. The downstream direction is easy. The end
office can send messages to each different house in whatever order it likes. In the
upstream direction, however, messages from different houses cannot be sent at the
same time, or different signals would collide. The houses also cannot hear each
other's transmissions so they cannot listen before transmitting. The solution is
that equipment at the houses requests and is granted time slots to use by equip-
ment in the end office. For this to work, there is a ranging process to adjust the
transmission times from the houses so that all the signals received at the end
office are synchronized. The design is similar to cable modems, which we cover
later in this chapter. For more information on the future of PONs, see Grobe and
Elbers (2008).
#### 2.6.4 Trunks and Multiplexing
Trunks in the telephone network are not only much faster than the local loops,
they are different in two other respects. The core of the telephone network carries
digital information, not analog information; that is, bits not voice. This necessi-
tates a conversion at the end office to digital form for transmission over the long-
haul trunks. The trunks carry thousands, even millions, of calls simultaneously.
This sharing is important for achieving economies of scale, since it costs essen-
tially the same amount of money to install and maintain a high-bandwidth trunk as
a low-bandwidth trunk between two switching offices. It is accomplished with
versions of TDM and FDM multiplexing.
Below we will briefly examine how voice signals are digitized so that they
can be transported by the telephone network. After that, we will see how TDM is
used to carry bits on trunks, including the TDM system used for fiber optics


---

<a id="page-165"></a>

<!-- Page 165 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 153
(SONET). Then we will turn to FDM as it is applied to fiber optics, which is call-
ed wavelength division multiplexing.
Digitizing Voice Signals
Early in the development of the telephone network, the core handled voice
calls as analog information. FDM techniques were used for many years to multi-
plex 4000-Hz voice channels (comprised of 3100 Hz plus guard bands) into larger
and larger units. For example, 12 calls in the 60 kHz-to-108 kHz band is known
as a group and five groups (a total of 60 calls) are known as a supergroup, and
so on. These FDM methods are still used over some copper wires and microwave
channels. However, FDM requires analog circuitry and is not amenable to being
done by a computer. In contrast, TDM can be handled entirely by digital elec-
tronics, so it has become far more widespread in recent years. Since TDM can
only be used for digital data and the local loops produce analog signals, a conver-
sion is needed from analog to digital in the end office, where all the individual
local loops come together to be combined onto outgoing trunks.
The analog signals are digitized in the end office by a device called a codec
(short for ''coder-decoder''). The codec makes 8000 samples per second (125
µsec/sample) because the Nyquist theorem says that this is sufficient to capture all
the information from the 4-kHz telephone channel bandwidth. At a lower sam-
pling rate, information would be lost; at a higher one, no extra information would
be gained. Each sample of the amplitude of the signal is quantized to an 8-bit
number.
This technique is called PCM (Pulse Code Modulation). It forms the heart
of the modern telephone system. As a consequence, virtually all time intervals
within the telephone system are multiples of 125 µsec. The standard
uncompressed data rate for a voice-grade telephone call is thus 8 bits every 125
µsec, or 64 kbps.
At the other end of the call, an analog signal is recreated from the quantized
samples by playing them out (and smoothing them) over time. It will not be ex-
actly the same as the original analog signal, even though we sampled at the
Nyquist rate, because the samples were quantized. To reduce the error due to
quantization, the quantization levels are unevenly spaced. A logarithmic scale is
used that gives relatively more bits to smaller signal amplitudes and relatively
fewer bits to large signal amplitudes. In this way the error is proportional to the
signal amplitude.
Two versions of quantization are widely used: µ-law, used in North America
and Japan, and A-law, used in Europe and the rest of the world. Both versions are
specified in standard ITU G.711. An equivalent way to think about this process is
to imagine that the dynamic range of the signal (or the ratio between the largest
and smallest possible values) is compressed before it is (evenly) quantized, and
then expanded when the analog signal is recreated. For this reason it is called


---

<a id="page-166"></a>

<!-- Page 166 of 888 -->

154 THE PHYSICAL LAYER CHAP. 2
companding. It is also possible to compress the samples after they are digitized
so that they require much less than 64 kbps. However, we will leave this topic for
when we explore audio applications such as voice over IP.
Time Division Multiplexing
TDM based on PCM is used to carry multiple voice calls over trunks by send-
ing a sample from each call every 125 µsec. When digital transmission began
emerging as a feasible technology, ITU (then called CCITT) was unable to reach
agreement on an international standard for PCM. Consequently, a variety of
incompatible schemes are now in use in different countries around the world.
The method used in North America and Japan is the T1 carrier, depicted in
Fig. 2-37. (Technically speaking, the format is called DS1 and the carrier is call-
ed T1, but following widespread industry tradition, we will not make that subtle
distinction here.) The T1 carrier consists of 24 voice channels multiplexed toget-
her. Each of the 24 channels, in turn, gets to insert 8 bits into the output stream.
193-bit frame (125 µsec)
Channel Channel Channel Channel Channel
1 2 3 4 24

Bit 1 is 7 Data Bit 8 is for
a framing bits per signaling
code channel
per sample
Figure 2-37. The T1 carrier (1.544 Mbps).
A frame consists of 24 × 8 = 192 bits plus one extra bit for control purposes,
yielding 193 bits every 125 µsec. This gives a gross data rate of 1.544 Mbps, of
which 8 kbps is for signaling. The 193rd bit is used for frame synchronization and
signaling. In one variation, the 193rd bit is used across a group of 24 frames call-
ed an extended superframe. Six of the bits, in the 4th, 8th, 12th, 16th, 20th, and
24th positions, take on the alternating pattern 001011 . . . . Normally, the receiver
keeps checking for this pattern to make sure that it has not lost synchronization.
Six more bits are used to send an error check code to help the receiver confirm
that it is synchronized. If it does get out of sync, the receiver can scan for the pat-
tern and validate the error check code to get resynchronized. The remaining 12


---

<a id="page-167"></a>

<!-- Page 167 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 155
bits are used for control information for operating and maintaining the network,
such as performance reporting from the remote end.
The T1 format has several variations. The earlier versions sent signaling
information in-band, meaning in the same channel as the data, by using some of
the data bits. This design is one form of channel-associated signaling, because
each channel has its own private signaling subchannel. In one arrangement, the
least significant bit out of an 8-bit sample on each channel is used in every sixth
frame. It has the colorful name of robbed-bit signaling. The idea is that a few
stolen bits will not matter for voice calls. No one will hear the difference.
For data, however, it is another story. Delivering the wrong bits is unhelpful,
to say the least. If older versions of T1 are used to carry data, only 7 of 8 bits, or
56 kbps can be used in each of the 24 channels. Instead, newer versions of T1
provide clear channels in which all of the bits may be used to send data. Clear
channels are what businesses who lease a T1 line want when they send data across
the telephone network in place of voice samples. Signaling for any voice calls is
then handled out-of-band, meaning in a separate channel from the data. Often,
the signaling is done with common-channel signaling in which there is a shared
signaling channel. One of the 24 channels may be used for this purpose.
Outside North America and Japan, the 2.048-Mbps E1 carrier is used instead
of T1. This carrier has 32 8-bit data samples packed into the basic 125-µsec
frame. Thirty of the channels are used for information and up to two are used for
signaling. Each group of four frames provides 64 signaling bits, half of which are
used for signaling (whether channel-associated or common-channel) and half of
which are used for frame synchronization or are reserved for each country to use
as it wishes.
Time division multiplexing allows multiple T1 carriers to be multiplexed into
higher-order carriers. Figure 2-38 shows how this can be done. At the left we see
four T1 channels being multiplexed into one T2 channel. The multiplexing at T2
and above is done bit for bit, rather than byte for byte with the 24 voice channels
that make up a T1 frame. Four T1 streams at 1.544 Mbps should generate 6.176
Mbps, but T2 is actually 6.312 Mbps. The extra bits are used for framing and re-
covery in case the carrier slips. T1 and T3 are widely used by customers, whereas
T2 and T4 are only used within the telephone system itself, so they are not well
known.
At the next level, seven T2 streams are combined bitwise to form a T3 stream.
Then six T3 streams are joined to form a T4 stream. At each step a small amount
of overhead is added for framing and recovery in case the synchronization be-
tween sender and receiver is lost.
Just as there is little agreement on the basic carrier between the United States
and the rest of the world, there is equally little agreement on how it is to be multi-
plexed into higher-bandwidth carriers. The U.S. scheme of stepping up by 4, 7,
and 6 did not strike everyone else as the way to go, so the ITU standard calls for
multiplexing four streams into one stream at each level. Also, the framing and


---

<a id="page-168"></a>

<!-- Page 168 of 888 -->

156 THE PHYSICAL LAYER CHAP. 2
4 T1 streams in 7 T2 streams in 6 T3 streams in
4 0 1 T2 stream out
5 1
4:1 6 5 4 3 2 1 0 7:1 6:1
6 2
7 3
### 1.544 Mbps 6.312 Mbps 44.736 Mbps 274.176 Mbps
## T1 T2 T3 T4
Figure 2-38. Multiplexing T1 streams into higher carriers.
recovery data are different in the U.S. and ITU standards. The ITU hierarchy for
32, 128, 512, 2048, and 8192 channels runs at speeds of 2.048, 8.848, 34.304,
139.264, and 565.148 Mbps.
SONET/SDH
In the early days of fiber optics, every telephone company had its own
proprietary optical TDM system. After AT&T was broken up in 1984, local tele-
phone companies had to connect to multiple long-distance carriers, all with dif-
ferent optical TDM systems, so the need for standardization became obvious. In
1985, Bellcore, the RBOC's research arm, began working on a standard, called
SONET (Synchronous Optical NETwork).
Later, ITU joined the effort, which resulted in a SONET standard and a set of
parallel ITU recommendations (G.707, G.708, and G.709) in 1989. The ITU
recommendations are called SDH (Synchronous Digital Hierarchy) but differ
from SONET only in minor ways. Virtually all the long-distance telephone traffic
in the United States, and much of it elsewhere, now uses trunks running SONET
in the physical layer. For additional information about SONET, see Bellamy
(2000), Goralski (2002), and Shepard (2001).
The SONET design had four major goals. First and foremost, SONET had to
make it possible for different carriers to interwork. Achieving this goal required
defining a common signaling standard with respect to wavelength, timing, fram-
ing structure, and other issues.
Second, some means was needed to unify the U.S., European, and Japanese
digital systems, all of which were based on 64-kbps PCM channels but combined
them in different (and incompatible) ways.
Third, SONET had to provide a way to multiplex multiple digital channels.
At the time SONET was devised, the highest-speed digital carrier actually used
widely in the United States was T3, at 44.736 Mbps. T4 was defined, but not used


---

<a id="page-169"></a>

<!-- Page 169 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 157
much, and nothing was even defined above T4 speed. Part of SONET's mission
was to continue the hierarchy to gigabits/sec and beyond. A standard way to mul-
tiplex slower channels into one SONET channel was also needed.
Fourth, SONET had to provide support for operations, administration, and
maintenance (OAM), which are needed to manage the network. Previous systems
did not do this very well.
An early decision was to make SONET a traditional TDM system, with the
entire bandwidth of the fiber devoted to one channel containing time slots for the
various subchannels. As such, SONET is a synchronous system. Each sender and
receiver is tied to a common clock. The master clock that controls the system has
an accuracy of about 1 part in 109. Bits on a SONET line are sent out at extreme-
ly precise intervals, controlled by the master clock.
The basic SONET frame is a block of 810 bytes put out every 125 µsec.
Since SONET is synchronous, frames are emitted whether or not there are any
useful data to send. Having 8000 frames/sec exactly matches the sampling rate of
the PCM channels used in all digital telephony systems.
The 810-byte SONET frames are best described as a rectangle of bytes, 90
columns wide by 9 rows high. Thus, 8 × 810 = 6480 bits are transmitted 8000
times per second, for a gross data rate of 51.84 Mbps. This layout is the basic
SONET channel, called STS-1 (Synchronous Transport Signal-1). All SONET
trunks are multiples of STS-1.
The first three columns of each frame are reserved for system management
information, as illustrated in Fig. 2-39. In this block, the first three rows contain
the section overhead; the next six contain the line overhead. The section overhead
is generated and checked at the start and end of each section, whereas the line
overhead is generated and checked at the start and end of each line.
A SONET transmitter sends back-to-back 810-byte frames, without gaps be-
tween them, even when there are no data (in which case it sends dummy data).
From the receiver's point of view, all it sees is a continuous bit stream, so how
does it know where each frame begins? The answer is that the first 2 bytes of
each frame contain a fixed pattern that the receiver searches for. If it finds this
pattern in the same place in a large number of consecutive frames, it assumes that
it is in sync with the sender. In theory, a user could insert this pattern into the
payload in a regular way, but in practice it cannot be done due to the multiplexing
of multiple users into the same frame and other reasons.
The remaining 87 columns of each frame hold 87 × 9 × 8 × 8000 = 50.112
Mbps of user data. This user data could be voice samples, T1 and other carriers
swallowed whole, or packets. SONET is simply a convenient container for tran-
sporting bits. The SPE (Synchronous Payload Envelope), which carries the user
data does not always begin in row 1, column 4. The SPE can begin anywhere
within the frame. A pointer to the first byte is contained in the first row of the line
overhead. The first column of the SPE is the path overhead (i.e., the header for
the end-to-end path sublayer protocol).


---

<a id="page-170"></a>

<!-- Page 170 of 888 -->

158 THE PHYSICAL LAYER CHAP. 2
3 Columns
for overhead
87 Columns
Sonet
9 . . . frame
Rows
(125 µsec)
Sonet
. . .
frame
(125 µsec)
Section Line Path
SPE
overhead overhead overhead
Figure 2-39. Two back-to-back SONET frames.
The ability to allow the SPE to begin anywhere within the SONET frame and
even to span two frames, as shown in Fig. 2-39, gives added flexibility to the sys-
tem. For example, if a payload arrives at the source while a dummy SONET
frame is being constructed, it can be inserted into the current frame instead of
being held until the start of the next one.
The SONET/SDH multiplexing hierarchy is shown in Fig. 2-40. Rates from
STS-1 to STS-768 have been defined, ranging from roughly a T3 line to 40 Gbps.
Even higher rates will surely be defined over time, with OC-3072 at 160 Gbps
being the next in line if and when it becomes technologically feasible. The opti-
cal carrier corresponding to STS-n is called OC-n but is bit for bit the same except
for a certain bit reordering needed for synchronization. The SDH names are dif-
ferent, and they start at OC-3 because ITU-based systems do not have a rate near
### 51.84 Mbps. We have shown the common rates, which proceed from OC-3 in
multiples of four. The gross data rate includes all the overhead. The SPE data
rate excludes the line and section overhead. The user data rate excludes all over-
head and counts only the 87 payload columns.
As an aside, when a carrier, such as OC-3, is not multiplexed, but carries the
data from only a single source, the letter c (for concatenated) is appended to the
designation, so OC-3 indicates a 155.52-Mbps carrier consisting of three separate
OC-1 carriers, but OC-3c indicates a data stream from a single source at 155.52
Mbps. The three OC-1 streams within an OC-3c stream are interleaved by
column-first column 1 from stream 1, then column 1 from stream 2, then column
1 from stream 3, followed by column 2 from stream 1, and so on-leading to a
frame 270 columns wide and 9 rows deep.


---

<a id="page-171"></a>

<!-- Page 171 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 159
SONET SDH Data rate (Mbps)
Electrical Optical Optical Gross SPE User
STS-1 OC-1 51.84 50.112 49.536
STS-3 OC-3 STM-1 155.52 150.336 148.608
STS-12 OC-12 STM-4 622.08 601.344 594.432
STS-48 OC-48 STM-16 2488.32 2405.376 2377.728
STS-192 OC-192 STM-64 9953.28 9621.504 9510.912
STS-768 OC-768 STM-256 39813.12 38486.016 38043.648
Figure 2-40. SONET and SDH multiplex rates.
Wavelength Division Multiplexing
A form of frequency division multiplexing is used as well as TDM to harness
the tremendous bandwidth of fiber optic channels. It is called WDM (Wave-
length Division Multiplexing). The basic principle of WDM on fibers is dep-
icted in Fig. 2-41. Here four fibers come together at an optical combiner, each
with its energy present at a different wavelength. The four beams are combined
onto a single shared fiber for transmission to a distant destination. At the far end,
the beam is split up over as many fibers as there were on the input side. Each out-
put fiber contains a short, specially constructed core that filters out all but one
wavelength. The resulting signals can be routed to their destination or recombin-
ed in different ways for additional multiplexed transport.
There is really nothing new here. This way of operating is just frequency di-
vision multiplexing at very high frequencies, with the term WDM owing to the
description of fiber optic channels by their wavelength or ''color'' rather than fre-
quency. As long as each channel has its own frequency (i.e., wavelength) range
and all the ranges are disjoint, they can be multiplexed together on the long-haul
fiber. The only difference with electrical FDM is that an optical system using a
diffraction grating is completely passive and thus highly reliable.
The reason WDM is popular is that the energy on a single channel is typically
only a few gigahertz wide because that is the current limit of how fast we can con-
vert between electrical and optical signals. By running many channels in parallel
on different wavelengths, the aggregate bandwidth is increased linearly with the
number of channels. Since the bandwidth of a single fiber band is about 25,000
GHz (see Fig. 2-7), there is theoretically room for 2500 10-Gbps channels even at
1 bit/Hz (and higher rates are also possible).
WDM technology has been progressing at a rate that puts computer technolo-
gy to shame. WDM was invented around 1990. The first commercial systems
had eight channels of 2.5 Gbps per channel. By 1998, systems with 40 channels


---

<a id="page-172"></a>

<!-- Page 172 of 888 -->

160 THE PHYSICAL LAYER CHAP. 2
Spectrum
on the
shared fiber
rewoP
Fiber 4
spectrum
λ
rewoP
Fiber 3
spectrum
λ
rewoP
Fiber 2
spectrum
λ
rewoP
Fiber 1
spectrum
λ
λ1
λ1 +λ2 +λ3 +λ4
rewoP
λ
Filter
Fiber 1 λ2
λ2
Fiber 2 λ4
λ3 Combiner Splitter
Fiber 3 λ1
λ4 Long-haul shared fiber
Fiber 4 λ3
Figure 2-41. Wavelength division multiplexing.
of 2.5 Gbps were on the market. By 2006, there were products with 192 channels
of 10 Gbps and 64 channels of 40 Gbps, capable of moving up to 2.56 Tbps. This
bandwidth is enough to transmit 80 full-length DVD movies per second. The
channels are also packed tightly on the fiber, with 200, 100, or as little as 50 GHz
of separation. Technology demonstrations by companies after bragging rights
have shown 10 times this capacity in the lab, but going from the lab to the field
usually takes at least a few years. When the number of channels is very large and
the wavelengths are spaced close together, the system is referred to as DWDM
(Dense WDM).
One of the drivers of WDM technology is the development of all-optical com-
ponents. Previously, every 100 km it was necessary to split up all the channels
and convert each one to an electrical signal for amplification separately before
reconverting them to optical signals and combining them. Nowadays, all-optical
amplifiers can regenerate the entire signal once every 1000 km without the need
for multiple opto-electrical conversions.
In the example of Fig. 2-41, we have a fixed-wavelength system. Bits from
input fiber 1 go to output fiber 3, bits from input fiber 2 go to output fiber 1, etc.
However, it is also possible to build WDM systems that are switched in the opti-
cal domain. In such a device, the output filters are tunable using Fabry-Perot or
Mach-Zehnder interferometers. These devices allow the selected frequencies to
be changed dynamically by a control computer. This ability provides a large
amount of flexibility to provision many different wavelength paths through the
telephone network from a fixed set of fibers. For more information about optical
networks and WDM, see Ramaswami et al. (2009).


---

<a id="page-173"></a>

<!-- Page 173 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 161
#### 2.6.5 Switching
From the point of view of the average telephone engineer, the phone system is
divided into two principal parts: outside plant (the local loops and trunks, since
they are physically outside the switching offices) and inside plant (the switches,
which are inside the switching offices). We have just looked at the outside plant.
Now it is time to examine the inside plant.
Two different switching techniques are used by the network nowadays: circuit
switching and packet switching. The traditional telephone system is based on cir-
cuit switching, but packet switching is beginning to make inroads with the rise of
voice over IP technology. We will go into circuit switching in some detail and
contrast it with packet switching. Both kinds of switching are important enough
that we will come back to them when we get to the network layer.
Circuit Switching
Conceptually, when you or your computer places a telephone call, the switch-
ing equipment within the telephone system seeks out a physical path all the way
from your telephone to the receiver's telephone. This technique is called circuit
switching. It is shown schematically in Fig. 2-42(a). Each of the six rectangles
represents a carrier switching office (end office, toll office, etc.). In this example,
each office has three incoming lines and three outgoing lines. When a call passes
through a switching office, a physical connection is (conceptually) established be-
tween the line on which the call came in and one of the output lines, as shown by
the dotted lines.
In the early days of the telephone, the connection was made by the operator
plugging a jumper cable into the input and output sockets. In fact, a surprising lit-
tle story is associated with the invention of automatic circuit switching equipment.
It was invented by a 19th-century Missouri undertaker named Almon B. Strowger.
Shortly after the telephone was invented, when someone died, one of the survivors
would call the town operator and say ''Please connect me to an undertaker.'' Un-
fortunately for Mr. Strowger, there were two undertakers in his town, and the
other one's wife was the town telephone operator. He quickly saw that either he
was going to have to invent automatic telephone switching equipment or he was
going to go out of business. He chose the first option. For nearly 100 years, the
circuit-switching equipment used worldwide was known as Strowger gear. (His-
tory does not record whether the now-unemployed switchboard operator got a job
as an information operator, answering questions such as ''What is the phone num-
ber of an undertaker?'')
The model shown in Fig. 2-42(a) is highly simplified, of course, because parts
of the physical path between the two telephones may, in fact, be microwave or
fiber links onto which thousands of calls are multiplexed. Nevertheless, the basic
idea is valid: once a call has been set up, a dedicated path between both ends
exists and will continue to exist until the call is finished.


---

<a id="page-174"></a>

<!-- Page 174 of 888 -->

162 THE PHYSICAL LAYER CHAP. 2
Physical (copper)
connection set up
when call is made
(a)
Switching office
Computer Packets queued
for subsequent
transmission
Computer
(b)
Figure 2-42. (a) Circuit switching. (b) Packet switching.
An important property of circuit switching is the need to set up an end-to-end
path before any data can be sent. The elapsed time between the end of dialing and
the start of ringing can easily be 10 sec, more on long-distance or international
calls. During this time interval, the telephone system is hunting for a path, as
shown in Fig. 2-43(a). Note that before data transmission can even begin, the call
request signal must propagate all the way to the destination and be acknowledged.
For many computer applications (e.g., point-of-sale credit verification), long setup
times are undesirable.
As a consequence of the reserved path between the calling parties, once the
setup has been completed, the only delay for data is the propagation time for the
electromagnetic signal, about 5 msec per 1000 km. Also as a consequence of the
established path, there is no danger of congestion-that is, once the call has been
put through, you never get busy signals. Of course, you might get one before the
connection has been established due to lack of switching or trunk capacity.
Packet Switching
The alternative to circuit switching is packet switching, shown in Fig. 2-
42(b) and described in Chap. 1. With this technology, packets are sent as soon as
they are available. There is no need to set up a dedicated path in advance, unlike


---

<a id="page-175"></a>

<!-- Page 175 of 888 -->

SEC. 2.6 THE PUBLIC SWITCHED TELEPHONE NETWORK 163
Call request signal
Pkt 1
Propagation Pkt 2
delay
Pkt 1 Queuing
Pkt 3 delay
Pkt 2
Pkt 1
Pkt 3
Time Pkt 2
spent
hunting
Pkt 3
for an
outgoing
Call
trunk
accept
signal
Data
AB BC CD
trunk trunk trunk
## A B C D A B C D
(a) (b)
emiT
Figure 2-43. Timing of events in (a) circuit switching, (b) packet switching.
with circuit switching. It is up to routers to use store-and-forward transmission to
send each packet on its way to the destination on its own. This procedure is
unlike circuit switching, in which the result of the connection setup is the reserva-
tion of bandwidth all the way from the sender to the receiver. All data on the cir-
cuit follows this path. Among other properties, having all the data follow the
same path means that it cannot arrive out of order. With packet switching there is
no fixed path, so different packets can follow different paths, depending on net-
work conditions at the time they are sent, and they may arrive out of order.
Packet-switching networks place a tight upper limit on the size of packets.
This ensures that no user can monopolize any transmission line for very long (e.g.,
many milliseconds), so that packet-switched networks can handle interactive traf-
fic. It also reduces delay since the first packet of a long message can be for-
warded before the second one has fully arrived. However, the store-and-forward
delay of accumulating a packet in the router's memory before it is sent on to the


---

<a id="page-176"></a>

<!-- Page 176 of 888 -->

164 THE PHYSICAL LAYER CHAP. 2
next router exceeds that of circuit switching. With circuit switching, the bits just
flow through the wire continuously.
Packet and circuit switching also differ in other ways. Because no bandwidth
is reserved with packet switching, packets may have to wait to be forwarded.
This introduces queuing delay and congestion if many packets are sent at the
same time. On the other hand, there is no danger of getting a busy signal and
being unable to use the network. Thus, congestion occurs at different times with
circuit switching (at setup time) and packet switching (when packets are sent).
If a circuit has been reserved for a particular user and there is no traffic, its
bandwidth is wasted. It cannot be used for other traffic. Packet switching does
not waste bandwidth and thus is more efficient from a system perspective. Under-
standing this trade-off is crucial for comprehending the difference between circuit
switching and packet switching. The trade-off is between guaranteed service and
wasting resources versus not guaranteeing service and not wasting resources.
Packet switching is more fault tolerant than circuit switching. In fact, that is
why it was invented. If a switch goes down, all of the circuits using it are termi-
nated and no more traffic can be sent on any of them. With packet switching,
packets can be routed around dead switches.
A final difference between circuit and packet switching is the charging algo-
rithm. With circuit switching, charging has historically been based on distance
and time. For mobile phones, distance usually does not play a role, except for in-
ternational calls, and time plays only a coarse role (e.g., a calling plan with 2000
free minutes costs more than one with 1000 free minutes and sometimes nights or
weekends are cheap). With packet switching, connect time is not an issue, but the
volume of traffic is. For home users, ISPs usually charge a flat monthly rate be-
cause it is less work for them and their customers can understand this model, but
backbone carriers charge regional networks based on the volume of their traffic.
The differences are summarized in Fig. 2-44. Traditionally, telephone net-
works have used circuit switching to provide high-quality telephone calls, and
computer networks have used packet switching for simplicity and efficiency.
However, there are notable exceptions. Some older computer networks have been
circuit switched under the covers (e.g., X.25) and some newer telephone networks
use packet switching with voice over IP technology. This looks just like a stan-
dard telephone call on the outside to users, but inside the network packets of voice
data are switched. This approach has let upstarts market cheap international calls
via calling cards, though perhaps with lower call quality than the incumbents.
### 2.7 THE MOBILE TELEPHONE SYSTEM
The traditional telephone system, even if it someday gets multigigabit end-to-
end fiber, will still not be able to satisfy a growing group of users: people on the
go. People now expect to make phone calls and to use their phones to check


---

<a id="page-177"></a>

<!-- Page 177 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 165
Item Circuit switched Packet switched
Call setup Required Not needed
Dedicated physical path Yes No
Each packet follows the same route Yes No
Packets arrive in order Yes No
Is a switch crash fatal Yes No
Bandwidth available Fixed Dynamic
Time of possible congestion At setup time On every packet
Potentially wasted bandwidth Yes No
Store-and-forward transmission No Yes
Charging Per minute Per packet
Figure 2-44. A comparison of circuit-switched and packet-switched networks.
email and surf the Web from airplanes, cars, swimming pools, and while jogging
in the park. Consequently, there is a tremendous amount of interest in wireless
telephony. In the following sections we will study this topic in some detail.
The mobile phone system is used for wide area voice and data communica-
tion. Mobile phones (sometimes called cell phones) have gone through three
distinct generations, widely called 1G, 2G, and 3G. The generations are:
1. Analog voice.
2. Digital voice.
3. Digital voice and data (Internet, email, etc.).
(Mobile phones should not be confused with cordless phones that consist of a
base station and a handset sold as a set for use within the home. These are never
used for networking, so we will not examine them further.)
Although most of our discussion will be about the technology of these sys-
tems, it is interesting to note how political and tiny marketing decisions can have
a huge impact. The first mobile system was devised in the U.S. by AT&T and
mandated for the whole country by the FCC. As a result, the entire U.S. had a
single (analog) system and a mobile phone purchased in California also worked in
New York. In contrast, when mobile phones came to Europe, every country de-
vised its own system, which resulted in a fiasco.
Europe learned from its mistake and when digital came around, the govern-
ment-run PTTs got together and standardized on a single system (GSM), so any
European mobile phone will work anywhere in Europe. By then, the U.S. had de-
cided that government should not be in the standardization business, so it left digi-
tal to the marketplace. This decision resulted in different equipment manufact-
urers producing different kinds of mobile phones. As a consequence, in the U.S.


---

<a id="page-178"></a>

<!-- Page 178 of 888 -->

166 THE PHYSICAL LAYER CHAP. 2
two major-and completely incompatible-digital mobile phone systems were
deployed, as well as other minor systems.
Despite an initial lead by the U.S., mobile phone ownership and usage in
Europe is now far greater than in the U.S. Having a single system that works any-
where in Europe and with any provider is part of the reason, but there is more. A
second area where the U.S. and Europe differed is in the humble matter of phone
numbers. In the U.S., mobile phones are mixed in with regular (fixed) telephones.
Thus, there is no way for a caller to see if, say, (212) 234-5678 is a fixed tele-
phone (cheap or free call) or a mobile phone (expensive call). To keep people
from getting nervous about placing calls, the telephone companies decided to
make the mobile phone owner pay for incoming calls. As a consequence, many
people hesitated buying a mobile phone for fear of running up a big bill by just re-
ceiving calls. In Europe, mobile phone numbers have a special area code (analo-
gous to 800 and 900 numbers) so they are instantly recognizable. Consequently,
the usual rule of ''caller pays'' also applies to mobile phones in Europe (except for
international calls, where costs are split).
A third issue that has had a large impact on adoption is the widespread use of
prepaid mobile phones in Europe (up to 75% in some areas). These can be pur-
chased in many stores with no more formality than buying a digital camera. You
pay and you go. They are preloaded with a balance of, for example, 20 or 50
euros and can be recharged (using a secret PIN code) when the balance drops to
zero. As a consequence, practically every teenager and many small children in
Europe have (usually prepaid) mobile phones so their parents can locate them,
without the danger of the child running up a huge bill. If the mobile phone is used
only occasionally, its use is essentially free since there is no monthly charge or
charge for incoming calls.
#### 2.7.1 First-Generation (1G) Mobile Phones: Analog Voice
Enough about the politics and marketing aspects of mobile phones. Now let
us look at the technology, starting with the earliest system. Mobile radiotele-
phones were used sporadically for maritime and military communication during
the early decades of the 20th century. In 1946, the first system for car-based tele-
phones was set up in St. Louis. This system used a single large transmitter on top
of a tall building and had a single channel, used for both sending and receiving.
To talk, the user had to push a button that enabled the transmitter and disabled the
receiver. Such systems, known as push-to-talk systems, were installed in several
cities beginning in the late 1950s. CB radio, taxis, and police cars often use this
technology.
In the 1960s, IMTS (Improved Mobile Telephone System) was installed.
It, too, used a high-powered (200-watt) transmitter on top of a hill but it had two
frequencies, one for sending and one for receiving, so the push-to-talk button was


---

<a id="page-179"></a>

<!-- Page 179 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 167
no longer needed. Since all communication from the mobile telephones went
inbound on a different channel than the outbound signals, the mobile users could
not hear each other (unlike the push-to-talk system used in taxis).
IMTS supported 23 channels spread out from 150 MHz to 450 MHz. Due to
the small number of channels, users often had to wait a long time before getting a
dial tone. Also, due to the large power of the hilltop transmitters, adjacent sys-
tems had to be several hundred kilometers apart to avoid interference. All in all,
the limited capacity made the system impractical.
Advanced Mobile Phone System
All that changed with AMPS (Advanced Mobile Phone System), invented
by Bell Labs and first installed in the United States in 1982. It was also used in
England, where it was called TACS, and in Japan, where it was called MCS-L1.
AMPS was formally retired in 2008, but we will look at it to understand the con-
text for the 2G and 3G systems that improved on it.
In all mobile phone systems, a geographic region is divided up into cells,
which is why the devices are sometimes called cell phones. In AMPS, the cells
are typically 10 to 20 km across; in digital systems, the cells are smaller. Each
cell uses some set of frequencies not used by any of its neighbors. The key idea
that gives cellular systems far more capacity than previous systems is the use of
relatively small cells and the reuse of transmission frequencies in nearby (but not
adjacent) cells. Whereas an IMTS system 100 km across can have only one call
on each frequency, an AMPS system might have 100 10-km cells in the same area
and be able to have 10 to 15 calls on each frequency, in widely separated cells.
Thus, the cellular design increases the system capacity by at least an order of
magnitude, more as the cells get smaller. Furthermore, smaller cells mean that
less power is needed, which leads to smaller and cheaper transmitters and
handsets.
The idea of frequency reuse is illustrated in Fig. 2-45(a). The cells are nor-
mally roughly circular, but they are easier to model as hexagons. In Fig. 2-45(a),
the cells are all the same size. They are grouped in units of seven cells. Each
letter indicates a group of frequencies. Notice that for each frequency set, there is
a buffer about two cells wide where that frequency is not reused, providing for
good separation and low interference.
Finding locations high in the air to place base station antennas is a major
issue. This problem has led some telecommunication carriers to forge alliances
with the Roman Catholic Church, since the latter owns a substantial number of
exalted potential antenna sites worldwide, all conveniently under a single man-
agement.
In an area where the number of users has grown to the point that the system is
overloaded, the power can be reduced and the overloaded cells split into smaller


---

<a id="page-180"></a>

<!-- Page 180 of 888 -->

168 THE PHYSICAL LAYER CHAP. 2
B
B G C
G C A
A F D
F D E
E B
G C
A
F D
E
(a) (b)
Figure 2-45. (a) Frequencies are not reused in adjacent cells. (b) To add more
users, smaller cells can be used.
microcells to permit more frequency reuse, as shown in Fig. 2-45(b). Telephone
companies sometimes create temporary microcells, using portable towers with
satellite links at sporting events, rock concerts, and other places where large num-
bers of mobile users congregate for a few hours.
At the center of each cell is a base station to which all the telephones in the
cell transmit. The base station consists of a computer and transmitter/receiver
connected to an antenna. In a small system, all the base stations are connected to
a single device called an MSC (Mobile Switching Center) or MTSO (Mobile
Telephone Switching Office). In a larger one, several MSCs may be needed, all
of which are connected to a second-level MSC, and so on. The MSCs are essen-
tially end offices as in the telephone system, and are in fact connected to at least
one telephone system end office. The MSCs communicate with the base stations,
each other, and the PSTN using a packet-switching network.
At any instant, each mobile telephone is logically in one specific cell and un-
der the control of that cell's base station. When a mobile telephone physically
leaves a cell, its base station notices the telephone's signal fading away and asks
all the surrounding base stations how much power they are getting from it. When
the answers come back, the base station then transfers ownership to the cell get-
ting the strongest signal; under most conditions that is the cell where the tele-
phone is now located. The telephone is then informed of its new boss, and if a
call is in progress, it is asked to switch to a new channel (because the old one is
not reused in any of the adjacent cells). This process, called handoff, takes about
300 msec. Channel assignment is done by the MSC, the nerve center of the sys-
tem. The base stations are really just dumb radio relays.


---

<a id="page-181"></a>

<!-- Page 181 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 169
Channels
AMPS uses FDM to separate the channels. The system uses 832 full-duplex
channels, each consisting of a pair of simplex channels. This arrangement is
known as FDD (Frequency Division Duplex). The 832 simplex channels from
824 to 849 MHz are used for mobile to base station transmission, and 832 simplex
channels from 869 to 894 MHz are used for base station to mobile transmission.
Each of these simplex channels is 30 kHz wide.
The 832 channels are divided into four categories. Control channels (base to
mobile) are used to manage the system. Paging channels (base to mobile) alert
mobile users to calls for them. Access channels (bidirectional) are used for call
setup and channel assignment. Finally, data channels (bidirectional) carry voice,
fax, or data. Since the same frequencies cannot be reused in nearby cells and 21
channels are reserved in each cell for control, the actual number of voice channels
available per cell is much smaller than 832, typically about 45.
Call Management
Each mobile telephone in AMPS has a 32-bit serial number and a 10-digit
telephone number in its programmable read-only memory. The telephone number
is represented as a 3-digit area code in 10 bits and a 7-digit subscriber number in
24 bits. When a phone is switched on, it scans a preprogrammed list of 21 control
channels to find the most powerful signal. The phone then broadcasts its 32-bit
serial number and 34-bit telephone number. Like all the control information in
AMPS, this packet is sent in digital form, multiple times, and with an error-cor-
recting code, even though the voice channels themselves are analog.
When the base station hears the announcement, it tells the MSC, which
records the existence of its new customer and also informs the customer's home
MSC of his current location. During normal operation, the mobile telephone
reregisters about once every 15 minutes.
To make a call, a mobile user switches on the phone, enters the number to be
called on the keypad, and hits the SEND button. The phone then transmits the
number to be called and its own identity on the access channel. If a collision oc-
curs there, it tries again later. When the base station gets the request, it informs
the MSC. If the caller is a customer of the MSC's company (or one of its
partners), the MSC looks for an idle channel for the call. If one is found, the
channel number is sent back on the control channel. The mobile phone then auto-
matically switches to the selected voice channel and waits until the called party
picks up the phone.
Incoming calls work differently. To start with, all idle phones continuously
listen to the paging channel to detect messages directed at them. When a call is
placed to a mobile phone (either from a fixed phone or another mobile phone), a
packet is sent to the callee's home MSC to find out where it is. A packet is then


---

<a id="page-182"></a>

<!-- Page 182 of 888 -->

170 THE PHYSICAL LAYER CHAP. 2
sent to the base station in its current cell, which sends a broadcast on the paging
channel of the form ''Unit 14, are you there?'' The called phone responds with a
''Yes'' on the access channel. The base then says something like: ''Unit 14, call
for you on channel 3.'' At this point, the called phone switches to channel 3 and
starts making ringing sounds (or playing some melody the owner was given as a
birthday present).
#### 2.7.2 Second-Generation (2G) Mobile Phones: Digital Voice
The first generation of mobile phones was analog; the second generation is
digital. Switching to digital has several advantages. It provides capacity gains by
allowing voice signals to be digitized and compressed. It improves security by al-
lowing voice and control signals to be encrypted. This in turn deters fraud and
eavesdropping, whether from intentional scanning or echoes of other calls due to
RF propagation. Finally, it enables new services such as text messaging.
Just as there was no worldwide standardization during the first generation,
there was also no worldwide standardization during the second, either. Several
different systems were developed, and three have been widely deployed. D-
AMPS (Digital Advanced Mobile Phone System) is a digital version of AMPS
that coexists with AMPS and uses TDM to place multiple calls on the same fre-
quency channel. It is described in International Standard IS-54 and its successor
IS-136. GSM (Global System for Mobile communications) has emerged as the
dominant system, and while it was slow to catch on in the U.S. it is now used vir-
tually everywhere in the world. Like D-AMPS, GSM is based on a mix of FDM
and TDM. CDMA (Code Division Multiple Access), described in International
Standard IS-95, is a completely different kind of system and is based on neither
FDM mor TDM. While CDMA has not become the dominant 2G system, its
technology has become the basis for 3G systems.
Also, the name PCS (Personal Communications Services) is sometimes
used in the marketing literature to indicate a second-generation (i.e., digital) sys-
tem. Originally it meant a mobile phone using the 1900 MHz band, but that dis-
tinction is rarely made now.
We will now describe GSM, since it is the dominant 2G system. In the next
section we will have more to say about CDMA when we describe 3G systems.
GSM-The Global System for Mobile Communications
GSM started life in the 1980s as an effort to produce a single European 2G
standard. The task was assigned to a telecommunications group called (in French)
Groupe Speciale´ Mobile. The first GSM systems were deployed starting in 1991
and were a quick success. It soon became clear that GSM was going to be more
than a European success, with uptake stretching to countries as far away as Aus-
tralia, so GSM was renamed to have a more worldwide appeal.


---

<a id="page-183"></a>

<!-- Page 183 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 171
GSM and the other mobile phone systems we will study retain from 1G sys-
tems a design based on cells, frequency reuse across cells, and mobility with
handoffs as subscribers move. It is the details that differ. Here, we will briefly
discuss some of the main properties of GSM. However, the printed GSM stan-
dard is over 5000 [sic] pages long. A large fraction of this material relates to en-
gineering aspects of the system, especially the design of receivers to handle mul-
tipath signal propagation, and synchronizing transmitters and receivers. None of
this will be even mentioned here.
Fig. 2-46 shows that the GSM architecture is similar to the AMPS architec-
ture, though the components have different names. The mobile itself is now di-
vided into the handset and a removable chip with subscriber and account infor-
mation called a SIM card, short for Subscriber Identity Module. It is the SIM
card that activates the handset and contains secrets that let the mobile and the net-
work identify each other and encrypt conversations. A SIM card can be removed
and plugged into a different handset to turn that handset into your mobile as far as
the network is concerned.
Air
interface BSC HLR
## Sim Msc Pstn
card
VLR
BSC
Cell tower and
Handset base station
Figure 2-46. GSM mobile network architecture.
The mobile talks to cell base stations over an air interface that we will de-
scribe in a moment. The cell base stations are each connected to a BSC (Base
Station Controller) that controls the radio resources of cells and handles handoff.
The BSC in turn is connected to an MSC (as in AMPS) that routes calls and con-
nects to the PSTN (Public Switched Telephone Network).
To be able to route calls, the MSC needs to know where mobiles can currently
be found. It maintains a database of nearby mobiles that are associated with the
cells it manages. This database is called the VLR (Visitor Location Register).
There is also a database in the mobile network that gives the last known location
of each mobile. It is called the HLR (Home Location Register). This database is
used to route incoming calls to the right locations. Both databases must be kept
up to date as mobiles move from cell to cell.
We will now describe the air interface in some detail. GSM runs on a range
of frequencies worldwide, including 900, 1800, and 1900 MHz. More spectrum is
allocated than for AMPS in order to support a much larger number of users. GSM


---

<a id="page-184"></a>

<!-- Page 184 of 888 -->

172 THE PHYSICAL LAYER CHAP. 2
is a frequency division duplex cellular system, like AMPS. That is, each mobile
transmits on one frequency and receives on another, higher frequency (55 MHz
higher for GSM versus 80 MHz higher for AMPS). However, unlike with AMPS,
with GSM a single frequency pair is split by time-division multiplexing into time
slots. In this way it is shared by multiple mobiles.
To handle multiple mobiles, GSM channels are much wider than the AMPS
channels (200-kHz versus 30 kHz). One 200-kHz channel is shown in Fig. 2-47.
A GSM system operating in the 900-MHz region has 124 pairs of simplex chan-
nels. Each simplex channel is 200 kHz wide and supports eight separate con-
nections on it, using time division multiplexing. Each currently active station is
assigned one time slot on one channel pair. Theoretically, 992 channels can be
supported in each cell, but many of them are not available, to avoid frequency
conflicts with neighboring cells. In Fig. 2-47, the eight shaded time slots all be-
long to the same connection, four of them in each direction. Transmitting and re-
ceiving does not happen in the same time slot because the GSM radios cannot
transmit and receive at the same time and it takes time to switch from one to the
other. If the mobile device assigned to 890.4/935.4 MHz and time slot 2 wanted
to transmit to the base station, it would use the lower four shaded slots (and the
ones following them in time), putting some data in each slot until all the data had
been sent.
### 959.8 MHz
### 935.4 MHz
### 935.2 MHz
### 914.8 MHz
### 890.4 MHz
### 890.2 MHz
ycneuqerF
TDM frame
Channel

Base
2 to mobile

Mobile
to base

Time
Figure 2-47. GSM uses 124 frequency channels, each of which uses an eight-
slot TDM system.
The TDM slots shown in Fig. 2-47 are part of a complex framing hierarchy.
Each TDM slot has a specific structure, and groups of TDM slots form mul-
tiframes, also with a specific structure. A simplified version of this hierarchy is
shown in Fig. 2-48. Here we can see that each TDM slot consists of a 148-bit
data frame that occupies the channel for 577 µsec (including a 30-µsec guard time


---

<a id="page-185"></a>

<!-- Page 185 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 173
after each slot). Each data frame starts and ends with three 0 bits, for frame del-
ineation purposes. It also contains two 57-bit Information fields, each one having
a control bit that indicates whether the following Information field is for voice or
data. Between the Information fields is a 26-bit Sync (training) field that is used
by the receiver to synchronize to the sender's frame boundaries.
32,500-Bit multiframe sent in 120 msec

0 1 2 3 4 5 6 7 8 9 10 11 T 13 14 15 16 17 18 19 20 21 22 23 24

Reserved
for future
1250-Bit TDM frame sent in 4.615 msec use
0 1 2 3 4 5 6 7
8.25-bit
(30 µsec)
guard time
148-Bit data frame sent in 547 µsec
000 Information Sync Information 000
Bits 3 57 26 57 3
Voice/data bit
Figure 2-48. A portion of the GSM framing structure.
A data frame is transmitted in 547 µsec, but a transmitter is only allowed to
send one data frame every 4.615 msec, since it is sharing the channel with seven
other stations. The gross rate of each channel is 270,833 bps, divided among eight
users. However, as with AMPS, the overhead eats up a large fraction of the band-
width, ultimately leaving 24.7 kbps worth of payload per user before error cor-
rection. After error correction, 13 kbps is left for speech. While this is substan-
tially less than 64 kbps PCM for uncompressed voice signals in the fixed tele-
phone network, compression on the mobile device can reach these levels with lit-
tle loss of quality.
As can be seen from Fig. 2-48, eight data frames make up a TDM frame and
26 TDM frames make up a 120-msec multiframe. Of the 26 TDM frames in a
multiframe, slot 12 is used for control and slot 25 is reserved for future use, so
only 24 are available for user traffic.
However, in addition to the 26-slot multiframe shown in Fig. 2-48, a 51-slot
multiframe (not shown) is also used. Some of these slots are used to hold several
control channels used to manage the system. The broadcast control channel is a
continuous stream of output from the base station containing the base station's
identity and the channel status. All mobile stations monitor their signal strength
to see when they have moved into a new cell.


---

<a id="page-186"></a>

<!-- Page 186 of 888 -->

174 THE PHYSICAL LAYER CHAP. 2
The dedicated control channel is used for location updating, registration,
and call setup. In particular, each BSC maintains a database of mobile stations
currently under its jurisdiction, the VLR. Information needed to maintain the
VLR is sent on the dedicated control channel.
Finally, there is the common control channel, which is split up into three
logical subchannels. The first of these subchannels is the paging channel, which
the base station uses to announce incoming calls. Each mobile station monitors it
continuously to watch for calls it should answer. The second is the random ac-
cess channel, which allows users to request a slot on the dedicated control chan-
nel. If two requests collide, they are garbled and have to be retried later. Using
the dedicated control channel slot, the station can set up a call. The assigned slot
is announced on the third subchannel, the access grant channel.
Finally, GSM differs from AMPS in how handoff is handled. In AMPS, the
MSC manages it completely without help from the mobile devices. With time
slots in GSM, the mobile is neither sending nor receiving most of the time. The
idle slots are an opportunity for the mobile to measure signal quality to other
nearby base stations. It does so and sends this information to the BSC. The BSC
can use it to determine when a mobile is leaving one cell and entering another so
it can perform the handoff. This design is called MAHO (Mobile Assisted
HandOff).
#### 2.7.3 Third-Generation (3G) Mobile Phones: Digital Voice and Data
The first generation of mobile phones was analog voice, and the second gen-
eration was digital voice. The third generation of mobile phones, or 3G as it is
called, is all about digital voice and data.
A number of factors are driving the industry. First, data traffic already
exceeds voice traffic on the fixed network and is growing exponentially, whereas
voice traffic is essentially flat. Many industry experts expect data traffic to dom-
inate voice on mobile devices as well soon. Second, the telephone, entertainment,
and computer industries have all gone digital and are rapidly converging. Many
people are drooling over lightweight, portable devices that act as a telephone, mu-
sic and video player, email terminal, Web interface, gaming machine, and more,
all with worldwide wireless connectivity to the Internet at high bandwidth.
Apple's iPhone is a good example of this kind of 3G device. With it, people
get hooked on wireless data services, and AT&T wireless data volumes are rising
steeply with the popularity of iPhones. The trouble is, the iPhone uses a 2.5G net-
work (an enhanced 2G network, but not a true 3G network) and there is not
enough data capacity to keep users happy. 3G mobile telephony is all about pro-
viding enough wireless bandwidth to keep these future users happy.
ITU tried to get a bit more specific about this vision starting back around
1992. It issued a blueprint for getting there called IMT-2000, where IMT stood


---

<a id="page-187"></a>

<!-- Page 187 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 175
for International Mobile Telecommunications . The basic services that the
IMT-2000 network was supposed to provide to its users are:
1. High-quality voice transmission.
2. Messaging (replacing email, fax, SMS, chat, etc.).
3. Multimedia (playing music, viewing videos, films, television, etc.).
4. Internet access (Web surfing, including pages with audio and video).
Additional services might be video conferencing, telepresence, group game play-
ing, and m-commerce (waving your telephone at the cashier to pay in a store).
Furthermore, all these services are supposed to be available worldwide (with
automatic connection via a satellite when no terrestrial network can be located),
instantly (always on), and with quality of service guarantees.
ITU envisioned a single worldwide technology for IMT-2000, so manufact-
urers could build a single device that could be sold and used anywhere in the
world (like CD players and computers and unlike mobile phones and televisions).
Having a single technology would also make life much simpler for network opera-
tors and would encourage more people to use the services. Format wars, such as
the Betamax versus VHS battle with videorecorders, are not good for business.
As it turned out, this was a bit optimistic. The number 2000 stood for three
things: (1) the year it was supposed to go into service, (2) the frequency it was
supposed to operate at (in MHz), and (3) the bandwidth the service should have
(in kbps). It did not make it on any of the three counts. Nothing was imple-
mented by 2000. ITU recommended that all governments reserve spectrum at 2
GHz so devices could roam seamlessly from country to country. China reserved
the required bandwidth but nobody else did. Finally, it was recognized that 2
Mbps is not currently feasible for users who are too mobile (due to the difficulty
of performing handoffs quickly enough). More realistic is 2 Mbps for stationary
indoor users (which will compete head-on with ADSL), 384 kbps for people walk-
ing, and 144 kbps for connections in cars.
Despite these initial setbacks, much has been accomplished since then. Sev-
eral IMT proposals were made and, after some winnowing, it came down to two
main ones. The first one, WCDMA (Wideband CDMA), was proposed by
Ericsson and was pushed by the European Union, which called it UMTS (Univer-
sal Mobile Telecommunications System). The other contender was
CDMA2000, proposed by Qualcomm.
Both of these systems are more similar than different in that they are based on
broadband CDMA; WCDMA uses 5-MHz channels and CDMA2000 uses 1.25-
MHz channels. If the Ericsson and Qualcomm engineers were put in a room and
told to come to a common design, they probably could find one fairly quickly.
The trouble is that the real problem is not engineering, but politics (as usual).
Europe wanted a system that interworked with GSM, whereas the U.S. wanted a


---

<a id="page-188"></a>

<!-- Page 188 of 888 -->

176 THE PHYSICAL LAYER CHAP. 2
system that was compatible with one already widely deployed in the U.S. (IS-95).
Each side also supported its local company (Ericsson is based in Sweden; Qual-
comm is in California). Finally, Ericsson and Qualcomm were involved in num-
erous lawsuits over their respective CDMA patents.
Worldwide, 10-15% of mobile subscribers already use 3G technologies. In
North America and Europe, around a third of mobile subscribers are 3G. Japan
was an early adopter and now nearly all mobile phones in Japan are 3G. These
figures include the deployment of both UMTS and CDMA2000, and 3G continues
to be one great cauldron of activity as the market shakes out. To add to the confu-
sion, UMTS became a single 3G standard with multiple incompatible options, in-
cluding CDMA2000. This change was an effort to unify the various camps, but it
just papers over the technical differences and obscures the focus of ongoing
efforts. We will use UMTS to mean WCDMA, as distinct from CDMA2000.
We will focus our discussion on the use of CDMA in cellular networks, as it
is the distinguishing feature of both systems. CDMA is neither FDM nor TDM
but a kind of mix in which each user sends on the same frequency band at the
same time. When it was first proposed for cellular systems, the industry gave it
approximately the same reaction that Columbus first got from Queen Isabella
when he proposed reaching India by sailing in the wrong direction. However,
through the persistence of a single company, Qualcomm, CDMA succeeded as a
2G system (IS-95) and matured to the point that it became the technical basis for
3G.
To make CDMA work in the mobile phone setting requires more than the
basic CDMA technique that we described in the previous section. Specifically,
we described synchronous CDMA, in which the chip sequences are exactly
orthogonal. This design works when all users are synchronized on the start time of
their chip sequences, as in the case of the base station transmitting to mobiles.
The base station can transmit the chip sequences starting at the same time so that
the signals will be orthogonal and able to be separated. However, it is difficult to
synchronize the transmissions of independent mobile phones. Without care, their
transmissions would arrive at the base station at different times, with no guarantee
of orthogonality. To let mobiles send to the base station without synchronization,
we want code sequences that are orthogonal to each other at all possible offsets,
not simply when they are aligned at the start.
While it is not possible to find sequences that are exactly orthogonal for this
general case, long pseudorandom sequences come close enough. They have the
property that, with high probability, they have a low cross-correlation with each
other at all offsets. This means that when one sequence is multiplied by another
sequence and summed up to compute the inner product, the result will be small; it
would be zero if they were orthogonal. (Intuitively, random sequences should al-
ways look different from each other. Multiplying them together should then pro-
duce a random signal, which will sum to a small result.) This lets a receiver filter
unwanted transmissions out of the received signal. Also, the auto-correlation of


---

<a id="page-189"></a>

<!-- Page 189 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 177
pseudorandom sequences is also small, with high probability, except at a zero off-
set. This means that when one sequence is multiplied by a delayed copy of itself
and summed, the result will be small, except when the delay is zero. (Intuitively,
a delayed random sequence looks like a different random sequence, and we are
back to the cross-correlation case.) This lets a receiver lock onto the beginning of
the wanted transmission in the received signal.
The use of pseudorandom sequences lets the base station receive CDMA mes-
sages from unsynchronized mobiles. However, an implicit assumption in our dis-
cussion of CDMA is that the power levels of all mobiles are the same at the re-
ceiver. If they are not, a small cross-correlation with a powerful signal might
overwhelm a large auto-correlation with a weak signal. Thus, the transmit power
on mobiles must be controlled to minimize interference between competing sig-
nals. It is this interference that limits the capacity of CDMA systems.
The power levels received at a base station depend on how far away the trans-
mitters are as well as how much power they transmit. There may be many mobile
stations at varying distances from the base station. A good heuristic to equalize
the received power is for each mobile station to transmit to the base station at the
inverse of the power level it receives from the base station. In other words, a
mobile station receiving a weak signal from the base station will use more power
than one getting a strong signal. For more accuracy, the base station also gives
each mobile feedback to increase, decrease, or hold steady its transmit power. The
feedback is frequent (1500 times per second) because good power control is im-
portant to minimize interference.
Another improvement over the basic CDMA scheme we described earlier is to
allow different users to send data at different rates. This trick is accomplished
naturally in CDMA by fixing the rate at which chips are transmitted and assigning
users chip sequences of different lengths. For example, in WCDMA, the chip rate
is 3.84 Mchips/sec and the spreading codes vary from 4 to 256 chips. With a 256-
chip code, around 12 kbps is left after error correction, and this capacity is suffi-
cient for a voice call. With a 4-chip code, the user data rate is close to 1 Mbps.
Intermediate-length codes give intermediate rates; to get to multiple Mbps, the
mobile must use more than one 5-MHz channel at once.
Now let us describe the advantages of CDMA, given that we have dealt with
the problems of getting it to work. It has three main advantages. First, CDMA
can improve capacity by taking advantage of small periods when some trans-
mitters are silent. In polite voice calls, one party is silent while the other talks. On
average, the line is busy only 40% of the time. However, the pauses may be small
and are difficult to predict. With TDM or FDM systems, it is not possible to reas-
sign time slots or frequency channels quickly enough to benefit from these small
silences. However, in CDMA, by simply not transmitting one user lowers the in-
terference for other users, and it is likely that some fraction of users will not be
transmitting in a busy cell at any given time. Thus CDMA takes advantage of ex-
pected silences to allow a larger number of simultaneous calls.


---

<a id="page-190"></a>

<!-- Page 190 of 888 -->

178 THE PHYSICAL LAYER CHAP. 2
Second, with CDMA each cell uses the same frequencies. Unlike GSM and
AMPS, FDM is not needed to separate the transmissions of different users. This
eliminates complicated frequency planning tasks and improves capacity. It also
makes it easy for a base station to use multiple directional antennas, or sectored
antennas, instead of an omnidirectional antenna. Directional antennas concen-
trate a signal in the intended direction and reduce the signal, and hence inter-
ference, in other directions. This in turn increases capacity. Three sector designs
are common. The base station must track the mobile as it moves from sector to
sector. This tracking is easy with CDMA because all frequencies are used in all
sectors.
Third, CDMA facilitates soft handoff, in which the mobile is acquired by the
new base station before the previous one signs off. In this way there is no loss of
continuity. Soft handoff is shown in Fig. 2-49. It is easy with CDMA because all
frequencies are used in each cell. The alternative is a hard handoff, in which the
old base station drops the call before the new one acquires it. If the new one is
unable to acquire it (e.g., because there is no available frequency), the call is
disconnected abruptly. Users tend to notice this, but it is inevitable occasionally
with the current design. Hard handoff is the norm with FDM designs to avoid the
cost of having the mobile transmit or receive on two frequencies simultaneously.
(a) (b) (c)
Figure 2-49. Soft handoff (a) before, (b) during, and (c) after.
Much has been written about 3G, most of it praising it as the greatest thing
since sliced bread. Meanwhile, many operators have taken cautious steps in the
direction of 3G by going to what is sometimes called 2.5G, although 2.1G might
be more accurate. One such system is EDGE (Enhanced Data rates for GSM
Evolution), which is just GSM with more bits per symbol. The trouble is, more
bits per symbol also means more errors per symbol, so EDGE has nine different
schemes for modulation and error correction, differing in terms of how much of
the bandwidth is devoted to fixing the errors introduced by the higher speed.
EDGE is one step along an evolutionary path that is defined from GSM to
WCDMA. Similarly, there is an evolutionary path defined for operators to
upgrade from IS-95 to CDMA2000 networks.
Even though 3G networks are not fully deployed yet, some researchers regard
3G as a done deal. These people are already working on 4G systems under the


---

<a id="page-191"></a>

<!-- Page 191 of 888 -->

SEC. 2.7 THE MOBILE TELEPHONE SYSTEM 179
name of LTE (Long Term Evolution). Some of the proposed features of 4G in-
clude: high bandwidth; ubiquity (connectivity everywhere); seamless integration
with other wired and wireless IP networks, including 802.11 access points; adap-
tive resource and spectrum management; and high quality of service for multi-
media. For more information see Astely et al. (2009) and Larmo et al. (2009).
Meanwhile, wireless networks with 4G levels of performance are already
available. The main example is 802.16, also known as WiMAX. For an overview
of mobile WiMAX see Ahmadi (2009). To say the industry is in a state of flux is
a huge understatement. Check back in a few years to see what has happened.
### 2.8 CABLE TELEVISION
We have now studied both the fixed and wireless telephone systems in a fair
amount of detail. Both will clearly play a major role in future networks. But
there is another major player that has emerged over the past decade for Internet
access: cable television networks. Many people nowadays get their telephone and
Internet service over cable. In the following sections we will look at cable tele-
vision as a network in more detail and contrast it with the telephone systems we
have just studied. Some relevant references for more information are Donaldson
and Jones (2001), Dutta-Roy (2001), and Fellows and Jones (2001).
#### 2.8.1 Community Antenna Television
Cable television was conceived in the late 1940s as a way to provide better
reception to people living in rural or mountainous areas. The system initially con-
sisted of a big antenna on top of a hill to pluck the television signal out of the air,
an amplifier, called the headend, to strengthen it, and a coaxial cable to deliver it
to people's houses, as illustrated in Fig. 2-50.
Antenna for picking
up distant signals
Headend
Drop cable
Tap Coaxial cable
Figure 2-50. An early cable television system.
In the early years, cable television was called Community Antenna Televis-
ion. It was very much a mom-and-pop operation; anyone handy with electronics


---

<a id="page-192"></a>

<!-- Page 192 of 888 -->

180 THE PHYSICAL LAYER CHAP. 2
could set up a service for his town, and the users would chip in to pay the costs.
As the number of subscribers grew, additional cables were spliced onto the origi-
nal cable and amplifiers were added as needed. Transmission was one way, from
the headend to the users. By 1970, thousands of independent systems existed.
In 1974, Time Inc. started a new channel, Home Box Office, with new content
(movies) distributed only on cable. Other cable-only channels followed, focusing
on news, sports, cooking, and many other topics. This development gave rise to
two changes in the industry. First, large corporations began buying up existing
cable systems and laying new cable to acquire new subscribers. Second, there
was now a need to connect multiple systems, often in distant cities, in order to dis-
tribute the new cable channels. The cable companies began to lay cable between
the cities to connect them all into a single system. This pattern was analogous to
what happened in the telephone industry 80 years earlier with the connection of
previously isolated end offices to make long-distance calling possible.
#### 2.8.2 Internet over Cable
Over the course of the years the cable system grew and the cables between the
various cities were replaced by high-bandwidth fiber, similar to what happened in
the telephone system. A system with fiber for the long-haul runs and coaxial
cable to the houses is called an HFC (Hybrid Fiber Coax) system. The electro-
optical converters that interface between the optical and electrical parts of the sys-
tem are called fiber nodes. Because the bandwidth of fiber is so much greater
than that of coax, a fiber node can feed multiple coaxial cables. Part of a modern
HFC system is shown in Fig. 2-51(a).
Over the past decade, many cable operators decided to get into the Internet
access business, and often the telephony business as well. Technical differences
between the cable plant and telephone plant had an effect on what had to be done
to achieve these goals. For one thing, all the one-way amplifiers in the system
had to be replaced by two-way amplifiers to support upstream as well as down-
stream transmissions. While this was happening, early Internet over cable sys-
tems used the cable television network for downstream transmissions and a dial-
up connection via the telephone network for upstream transmissions. It was a
clever workaround, but not much of a network compared to what it could be.
However, there is another difference between the HFC system of Fig. 2-51(a)
and the telephone system of Fig. 2-51(b) that is much harder to remove. Down in
the neighborhoods, a single cable is shared by many houses, whereas in the tele-
phone system, every house has its own private local loop. When used for televis-
ion broadcasting, this sharing is a natural fit. All the programs are broadcast on
the cable and it does not matter whether there are 10 viewers or 10,000 viewers.
When the same cable is used for Internet access, however, it matters a lot if there
are 10 users or 10,000. If one user decides to download a very large file, that
bandwidth is potentially being taken away from other users. The more users there


---

<a id="page-193"></a>

<!-- Page 193 of 888 -->

SEC. 2.8 CABLE TELEVISION 181
High-bandwidth
fiber
Switch Coaxial
trunk
cable
Fiber node
Head-
end
Tap
House
Fiber
(a)
House
Toll High-bandwidth End Local
office fiber trunk office loop
Fiber
Copper
twisted pair
(b)
Figure 2-51. (a) Cable television. (b) The fixed telephone system.
are, the more competition there is for bandwidth. The telephone system does not
have this particular property: downloading a large file over an ADSL line does not
reduce your neighbor's bandwidth. On the other hand, the bandwidth of coax is
much higher than that of twisted pairs, so you can get lucky if your neighbors do
not use the Internet much.
The way the cable industry has tackled this problem is to split up long cables
and connect each one directly to a fiber node. The bandwidth from the headend to
each fiber node is effectively infinite, so as long as there are not too many sub-
scribers on each cable segment, the amount of traffic is manageable. Typical


---

<a id="page-194"></a>

<!-- Page 194 of 888 -->

182 THE PHYSICAL LAYER CHAP. 2
cables nowadays have 500-2000 houses, but as more and more people subscribe
to Internet over cable, the load may become too great, requiring more splitting and
more fiber nodes.
#### 2.8.3 Spectrum Allocation
Throwing off all the TV channels and using the cable infrastructure strictly
for Internet access would probably generate a fair number of irate customers, so
cable companies are hesitant to do this. Furthermore, most cities heavily regulate
what is on the cable, so the cable operators would not be allowed to do this even if
they really wanted to. As a consequence, they needed to find a way to have tele-
vision and Internet peacefully coexist on the same cable.
The solution is to build on frequency division multiplexing. Cable television
channels in North America occupy the 54-550 MHz region (except for FM radio,
from 88 to 108 MHz). These channels are 6-MHz wide, including guard bands,
and can carry one traditional analog television channel or several digital television
channels. In Europe the low end is usually 65 MHz and the channels are 6-8
MHz wide for the higher resolution required by PAL and SECAM, but otherwise
the allocation scheme is similar. The low part of the band is not used. Modern
cables can also operate well above 550 MHz, often at up to 750 MHz or more.
The solution chosen was to introduce upstream channels in the 5-42 MHz band
(slightly higher in Europe) and use the frequencies at the high end for the down-
stream signals. The cable spectrum is illustrated in Fig. 2-52.
0 108
TV TV Downstream data
Downstream frequencies
maertspU
maertspU
atad
seicneuqerf
5 42 54 88
550 750 MHz
FM
Figure 2-52. Frequency allocation in a typical cable TV system used for Inter-
net access.
Note that since the television signals are all downstream, it is possible to use
upstream amplifiers that work only in the 5-42 MHz region and downstream
amplifiers that work only at 54 MHz and up, as shown in the figure. Thus, we get
an asymmetry in the upstream and downstream bandwidths because more spec-
trum is available above television than below it. On the other hand, most users
want more downstream traffic, so cable operators are not unhappy with this fact


---

<a id="page-195"></a>

<!-- Page 195 of 888 -->

SEC. 2.8 CABLE TELEVISION 183
of life. As we saw earlier, telephone companies usually offer an asymmetric DSL
service, even though they have no technical reason for doing so.
In addition to upgrading the amplifiers, the operator has to upgrade the
headend, too, from a dumb amplifier to an intelligent digital computer system
with a high-bandwidth fiber interface to an ISP. Often the name gets upgraded as
well, from ''headend'' to CMTS (Cable Modem Termination System). In the
following text, we will refrain from doing a name upgrade and stick with the tra-
ditional ''headend.''
#### 2.8.4 Cable Modems
Internet access requires a cable modem, a device that has two interfaces on it:
one to the computer and one to the cable network. In the early years of cable In-
ternet, each operator had a proprietary cable modem, which was installed by a
cable company technician. However, it soon became apparent that an open stan-
dard would create a competitive cable modem market and drive down prices, thus
encouraging use of the service. Furthermore, having the customers buy cable
modems in stores and install them themselves (as they do with wireless access
points) would eliminate the dreaded truck rolls.
Consequently, the larger cable operators teamed up with a company called
CableLabs to produce a cable modem standard and to test products for compli-
ance. This standard, called DOCSIS (Data Over Cable Service Interface Spe-
cification), has mostly replaced proprietary modems. DOCSIS version 1.0 came
out in 1997, and was soon followed by DOCSIS 2.0 in 2001. It increased up-
stream rates to better support symmetric services such as IP telephony. The most
recent version of the standard is DOCSIS 3.0, which came out in 2006. It uses
more bandwidth to increase rates in both directions. The European version of
these standards is called EuroDOCSIS. Not all cable operators like the idea of a
standard, however, since many of them were making good money leasing their
modems to their captive customers. An open standard with dozens of manufact-
urers selling cable modems in stores ends this lucrative practice.
The modem-to-computer interface is straightforward. It is normally Ethernet,
or occasionally USB. The other end is more complicated as it uses all of FDM,
TDM, and CDMA to share the bandwidth of the cable between subscribers.
When a cable modem is plugged in and powered up, it scans the downstream
channels looking for a special packet periodically put out by the headend to pro-
vide system parameters to modems that have just come online. Upon finding this
packet, the new modem announces its presence on one of the upstream channels.
The headend responds by assigning the modem to its upstream and downstream
channels. These assignments can be changed later if the headend deems it neces-
sary to balance the load.
The use of 6-MHz or 8-MHz channels is the FDM part. Each cable modem
sends data on one upstream and one downstream channel, or multiple channels


---

<a id="page-196"></a>

<!-- Page 196 of 888 -->

184 THE PHYSICAL LAYER CHAP. 2
under DOCSIS 3.0. The usual scheme is to take each 6 (or 8) MHz downstream
channel and modulate it with QAM-64 or, if the cable quality is exceptionally
good, QAM-256. With a 6-MHz channel and QAM-64, we get about 36 Mbps.
When the overhead is subtracted, the net payload is about 27 Mbps. With QAM-
256, the net payload is about 39 Mbps. The European values are 1/3 larger.
For upstream, there is more RF noise because the system was not originally
designed for data, and noise from multiple subscribers is funneled to the headend,
so a more conservative scheme is used. This ranges from QPSK to QAM-128,
where some of the symbols are used for error protection with Trellis Coded Mod-
ulation. With fewer bits per symbol on the upstream, the asymmetry between
upstream and downstream rates is much more than suggested by Fig. 2-52.
TDM is then used to share bandwidth on the upstream across multiple sub-
scribers. Otherwise their transmissions would collide at the headend. Time is di-
vided into minislots and different subscribers send in different minislots. To
make this work, the modem determines its distance from the headend by sending
it a special packet and seeing how long it takes to get the response. This process
is called ranging. It is important for the modem to know its distance to get the
timing right. Each upstream packet must fit in one or more consecutive minislots
at the headend when it is received. The headend announces the start of a new
round of minislots periodically, but the starting gun is not heard at all modems si-
multaneously due to the propagation time down the cable. By knowing how far it
is from the headend, each modem can compute how long ago the first minislot
really started. Minislot length is network dependent. A typical payload is 8 bytes.
During initialization, the headend assigns each modem to a minislot to use for
requesting upstream bandwidth. When a computer wants to send a packet, it
transfers the packet to the modem, which then requests the necessary number of
minislots for it. If the request is accepted, the headend puts an acknowledgement
on the downstream channel telling the modem which minislots have been reserved
for its packet. The packet is then sent, starting in the minislot allocated to it. Ad-
ditional packets can be requested using a field in the header.
As a rule, multiple modems will be assigned the same minislot, which leads to
contention. Two different possibilities exist for dealing with it. The first is that
CDMA is used to share the minislot between subscribers. This solves the con-
tention problem because all subscribers with a CDMA code sequence can send at
the same time, albeit at a reduced rate. The second option is that CDMA is not
used, in which case there may be no acknowledgement to the request because of a
collision. In this case, the modem just waits a random time and tries again. After
each successive failure, the randomization time is doubled. (For readers already
somewhat familiar with networking, this algorithm is just slotted ALOHA with bi-
nary exponential backoff. Ethernet cannot be used on cable because stations can-
not sense the medium. We will come back to these issues in Chap. 4.)
The downstream channels are managed differently from the upstream chan-
nels. For starters, there is only one sender (the headend), so there is no contention


---

<a id="page-197"></a>

<!-- Page 197 of 888 -->

SEC. 2.8 CABLE TELEVISION 185
and no need for minislots, which is actually just statistical time division multi-
plexing. For another, the amount of traffic downstream is usually much larger
than upstream, so a fixed packet size of 204 bytes is used. Part of that is a Reed-
Solomon error-correcting code and some other overhead, leaving a user payload
of 184 bytes. These numbers were chosen for compatibility with digital television
using MPEG-2, so the TV and downstream data channels are formatted the same
way. Logically, the connections are as depicted in Fig. 2-53.
Figure 2-53. Typical details of the upstream and downstream channels in North
America.
#### 2.8.5 ADSL Versus Cable
Which is better, ADSL or cable? That is like asking which operating system
is better. Or which language is better. Or which religion. Which answer you get
depends on whom you ask. Let us compare ADSL and cable on a few points.
Both use fiber in the backbone, but they differ on the edge. Cable uses coax;
ADSL uses twisted pair. The theoretical carrying capacity of coax is hundreds of
times more than twisted pair. However, the full capacity of the cable is not avail-
able for data users because much of the cable's bandwidth is wasted on useless
stuff such as television programs.
In practice, it is hard to generalize about effective capacity. ADSL providers
give specific statements about the bandwidth (e.g., 1 Mbps downstream, 256 kbps
upstream) and generally achieve about 80% of it consistently. Cable providers
may artificially cap the bandwidth to each user to help them make performance
predictions, but they cannot really give guarantees because the effective capacity
depends on how many people are currently active on the user's cable segment.
Sometimes it may be better than ADSL and sometimes it may be worse. What
can be annoying, though, is the unpredictability. Having great service one minute
does not guarantee great service the next minute since the biggest bandwidth hog
in town may have just turned on his computer.


---

<a id="page-198"></a>

<!-- Page 198 of 888 -->

186 THE PHYSICAL LAYER CHAP. 2
As an ADSL system acquires more users, their increasing numbers have little
effect on existing users, since each user has a dedicated connection. With cable,
as more subscribers sign up for Internet service, performance for existing users
will drop. The only cure is for the cable operator to split busy cables and connect
each one to a fiber node directly. Doing so costs time and money, so there are
business pressures to avoid it.
As an aside, we have already studied another system with a shared channel
like cable: the mobile telephone system. Here, too, a group of users-we could
call them cellmates-share a fixed amount of bandwidth. For voice traffic, which
is fairly smooth, the bandwidth is rigidly divided in fixed chunks among the active
users using FDM and TDM. But for data traffic, this rigid division is very ineffi-
cient because data users are frequently idle, in which case their reserved band-
width is wasted. As with cable, a more dynamic means is used to allocate the
shared bandwidth.
Availability is an issue on which ADSL and cable differ. Everyone has a tele-
phone, but not all users are close enough to their end offices to get ADSL. On the
other hand, not everyone has cable, but if you do have cable and the company pro-
vides Internet access, you can get it. Distance to the fiber node or headend is not
an issue. It is also worth noting that since cable started out as a television distrib-
ution medium, few businesses have it.
Being a point-to-point medium, ADSL is inherently more secure than cable.
Any cable user can easily read all the packets going down the cable. For this rea-
son, any decent cable provider will encrypt all traffic in both directions. Never-
theless, having your neighbor get your encrypted messages is still less secure than
having him not get anything at all.
The telephone system is generally more reliable than cable. For example, it
has backup power and continues to work normally even during a power outage.
With cable, if the power to any amplifier along the chain fails, all downstream
users are cut off instantly.
Finally, most ADSL providers offer a choice of ISPs. Sometimes they are
even required to do so by law. Such is not always the case with cable operators.
The conclusion is that ADSL and cable are much more alike than they are dif-
ferent. They offer comparable service and, as competition between them heats
up, probably comparable prices.
### 2.9 SUMMARY
The physical layer is the basis of all networks. Nature imposes two funda-
mental limits on all channels, and these determine their bandwidth. These limits
are the Nyquist limit, which deals with noiseless channels, and the Shannon limit,
which deals with noisy channels.


---

<a id="page-199"></a>

<!-- Page 199 of 888 -->

SEC. 2.9 SUMMARY 187
Transmission media can be guided or unguided. The principal guided media
are twisted pair, coaxial cable, and fiber optics. Unguided media include terres-
trial radio, microwaves, infrared, lasers through the air, and satellites.
Digital modulation methods send bits over guided and unguided media as ana-
log signals. Line codes operate at baseband, and signals can be placed in a
passband by modulating the amplitude, frequency, and phase of a carrier. Chan-
nels can be shared between users with time, frequency and code division multi-
plexing.
A key element in most wide area networks is the telephone system. Its main
components are the local loops, trunks, and switches. ADSL offers speeds up to
40 Mbps over the local loop by dividing it into many subcarriers that run in paral-
lel. This far exceeds the rates of telephone modems. PONs bring fiber to the
home for even greater access rates than ADSL.
Trunks carry digital information. They are multiplexed with WDM to provi-
sion many high capacity links over individual fibers, as well as with TDM to
share each high rate link between users. Both circuit switching and packet
switching are important.
For mobile applications, the fixed telephone system is not suitable. Mobile
phones are currently in widespread use for voice, and increasingly for data. They
have gone through three generations. The first generation, 1G, was analog and
dominated by AMPS. 2G was digital, with GSM presently the most widely de-
ployed mobile phone system in the world. 3G is digital and based on broadband
CDMA, with WCDMA and also CDMA2000 now being deployed.
An alternative system for network access is the cable television system. It has
gradually evolved from coaxial cable to hybrid fiber coax, and from television to
television and Internet. Potentially, it offers very high bandwidth, but the band-
width in practice depends heavily on the other users because it is shared.
PROBLEMS
1. Compute the Fourier coefficients for the function f(t) = t (0 ≤ t ≤ 1).
2. A noiseless 4-kHz channel is sampled every 1 msec. What is the maximum data rate?
How does the maximum data rate change if the channel is noisy, with a signal-to-noise
ratio of 30 dB?
3. Television channels are 6 MHz wide. How many bits/sec can be sent if four-level dig-
ital signals are used? Assume a noiseless channel.
4. If a binary signal is sent over a 3-kHz channel whose signal-to-noise ratio is 20 dB,
what is the maximum achievable data rate?
5. What signal-to-noise ratio is needed to put a T1 carrier on a 50-kHz line?
6. What are the advantages of fiber optics over copper as a transmission medium? Is
there any downside of using fiber optics over copper?


---

<a id="page-200"></a>

<!-- Page 200 of 888 -->

188 THE PHYSICAL LAYER CHAP. 2
7. How much bandwidth is there in 0.1 microns of spectrum at a wavelength of 1
micron?
8. It is desired to send a sequence of computer screen images over an optical fiber. The
screen is 2560 × 1600 pixels, each pixel being 24 bits. There are 60 screen images per
second. How much bandwidth is needed, and how many microns of wavelength are
needed for this band at 1.30 microns?
9. Is the Nyquist theorem true for high-quality single-mode optical fiber or only for
copper wire?
10. Radio antennas often work best when the diameter of the antenna is equal to the wave-
length of the radio wave. Reasonable antennas range from 1 cm to 5 meters in diame-
ter. What frequency range does this cover?
11. A laser beam 1 mm wide is aimed at a detector 1 mm wide 100 m away on the roof of
a building. How much of an angular diversion (in degrees) does the laser have to have
before it misses the detector?
12. The 66 low-orbit satellites in the Iridium project are divided into six necklaces around
the earth. At the altitude they are using, the period is 90 minutes. What is the average
interval for handoffs for a stationary transmitter?
13. Calculate the end-to-end transit time for a packet for both GEO (altitude: 35,800 km),
MEO (altitude: 18,000 km) and LEO (altitude: 750 km) satellites.
14. What is the latency of a call originating at the North Pole to reach the South Pole if the
call is routed via Iridium satellites? Assume that the switching time at the satellites is
10 microseconds and earth's radius is 6371 km.
15. What is the minimum bandwidth needed to achieve a data rate of B bits/sec if the sig-
nal is transmitted using NRZ, MLT-3, and Manchester encoding? Explain your
answer.
16. Prove that in 4B/5B encoding, a signal transition will occur at least every four bit
times.
17. How many end office codes were there pre-1984, when each end office was named by
its three-digit area code and the first three digits of the local number? Area codes
started with a digit in the range 2-9, had a 0 or 1 as the second digit, and ended with
any digit. The first two digits of a local number were always in the range 2-9. The
third digit could be any digit.
18. A simple telephone system consists of two end offices and a single toll office to which
each end office is connected by a 1-MHz full-duplex trunk. The average telephone is
used to make four calls per 8-hour workday. The mean call duration is 6 min. Ten
percent of the calls are long distance (i.e., pass through the toll office). What is the
maximum number of telephones an end office can support? (Assume 4 kHz per cir-
cuit.) Explain why a telephone company may decide to support a lesser number of
telephones than this maximum number at the end office.
19. A regional telephone company has 10 million subscribers. Each of their telephones is
connected to a central office by a copper twisted pair. The average length of these
twisted pairs is 10 km. How much is the copper in the local loops worth? Assume


---

<a id="page-201"></a>

<!-- Page 201 of 888 -->

CHAP. 2 PROBLEMS 189
that the cross section of each strand is a circle 1 mm in diameter, the density of copper
is 9.0 grams/cm3, and that copper sells for $6 per kilogram.
20. Is an oil pipeline a simplex system, a half-duplex system, a full-duplex system, or
none of the above? What about a river or a walkie-talkie-style communication?
21. The cost of a fast microprocessor has dropped to the point where it is now possible to
put one in each modem. How does that affect the handling of telephone line errors?
Does it negate the need for error checking/correction in layer 2?
22. A modem constellation diagram similar to Fig. 2-23 has data points at the following
coordinates: (1, 1), (1, −1), (−1, 1), and (−1, −1). How many bps can a modem with
these parameters achieve at 1200 symbols/second?
23. What is the maximum bit rate achievable in a V.32 standard modem if the baud rate is
1200 and no error correction is used?
24. How many frequencies does a full-duplex QAM-64 modem use?
25. Ten signals, each requiring 4000 Hz, are multiplexed onto a single channel using
FDM. What is the minimum bandwidth required for the multiplexed channel? As-
sume that the guard bands are 400 Hz wide.
26. Why has the PCM sampling time been set at 125 µsec?
27. What is the percent overhead on a T1 carrier? That is, what percent of the 1.544 Mbps
are not delivered to the end user? How does it relate to the percent overhead in OC-1
or OC-768 lines?
28. Compare the maximum data rate of a noiseless 4-kHz channel using
(a) Analog encoding (e.g., QPSK) with 2 bits per sample.
(b) The T1 PCM system.
29. If a T1 carrier system slips and loses track of where it is, it tries to resynchronize using
the first bit in each frame. How many frames will have to be inspected on average to
resynchronize with a probability of 0.001 of being wrong?
30. What is the difference, if any, between the demodulator part of a modem and the coder
part of a codec? (After all, both convert analog signals to digital ones.)
31. SONET clocks have a drift rate of about 1 part in 109. How long does it take for the
drift to equal the width of 1 bit? Do you see any practical implications of this calcula-
tion? If so, what?
32. How long will it take to transmit a 1-GB file from one VSAT to another using a hub
as shown in Figure 2-17? Assume that the uplink is 1 Mbps, the downlink is 7 Mbps,
and circuit switching is used with 1.2 sec circuit setup time.
33. Calculate the transmit time in the previous problem if packet switching is used instead.
Assume that the packet size is 64 KB, the switching delay in the satellite and hub is 10
microseconds, and the packet header size is 32 bytes.
34. In Fig. 2-40, the user data rate for OC-3 is stated to be 148.608 Mbps. Show how this
number can be derived from the SONET OC-3 parameters. What will be the gross,
SPE, and user data rates of an OC-3072 line?


---

<a id="page-202"></a>

<!-- Page 202 of 888 -->

190 THE PHYSICAL LAYER CHAP. 2
35. To accommodate lower data rates than STS-1, SONET has a system of virtual tribu-
taries (VTs). A VT is a partial payload that can be inserted into an STS-1 frame and
combined with other partial payloads to fill the data frame. VT1.5 uses 3 columns,
VT2 uses 4 columns, VT3 uses 6 columns, and VT6 uses 12 columns of an STS-1
frame. Which VT can accommodate
(a) A DS-1 service (1.544 Mbps)?
(b) European CEPT-1 service (2.048 Mbps)?
(c) A DS-2 service (6.312 Mbps)?
36. What is the available user bandwidth in an OC-12c connection?
37. Three packet-switching networks each contain n nodes. The first network has a star
topology with a central switch, the second is a (bidirectional) ring, and the third is
fully interconnected, with a wire from every node to every other node. What are the
best-, average-, and worst-case transmission paths in hops?
38. Compare the delay in sending an x-bit message over a k-hop path in a circuit-switched
network and in a (lightly loaded) packet-switched network. The circuit setup time is s
sec, the propagation delay is d sec per hop, the packet size is p bits, and the data rate is
b bps. Under what conditions does the packet network have a lower delay? Also, ex-
plain the conditions under which a packet-switched network is preferable to a circuit-
switched network.
39. Suppose that x bits of user data are to be transmitted over a k-hop path in a packet-
switched network as a series of packets, each containing p data bits and h header bits,
with x >> p + h. The bit rate of the lines is b bps and the propagation delay is negligi-
ble. What value of p minimizes the total delay?
40. In a typical mobile phone system with hexagonal cells, it is forbidden to reuse a fre-
quency band in an adjacent cell. If 840 frequencies are available, how many can be
used in a given cell?
41. The actual layout of cells is seldom as regular that as shown in Fig. 2-45. Even the
shapes of individual cells are typically irregular. Give a possible reason why this
might be. How do these irregular shapes affect frequency assignment to each cell?
42. Make a rough estimate of the number of PCS microcells 100 m in diameter it would
take to cover San Francisco (120 square km).
43. Sometimes when a mobile user crosses the boundary from one cell to another, the cur-
rent call is abruptly terminated, even though all transmitters and receivers are func-
tioning perfectly. Why?
44. Suppose that A, B, and C are simultaneously transmitting 0 bits, using a CDMA sys-
tem with the chip sequences of Fig. 2-28(a). What is the resulting chip sequence?
45. Consider a different way of looking at the orthogonality property of CDMA chip se-
quences. Each bit in a pair of sequences can match or not match. Express the ortho-
gonality property in terms of matches and mismatches.
46. A CDMA receiver gets the following chips: (−1 +1 −3 +1 −1 −3 +1 +1). Assuming
the chip sequences defined in Fig. 2-28(a), which stations transmitted, and which bits
did each one send?


---

<a id="page-203"></a>

<!-- Page 203 of 888 -->

CHAP. 2 PROBLEMS 191
47. In Figure 2-28, there are four stations that can transmit. Suppose four more stations
are added. Provide the chip sequences of these stations.
48. At the low end, the telephone system is star shaped, with all the local loops in a neigh-
borhood converging on an end office. In contrast, cable television consists of a single
long cable snaking its way past all the houses in the same neighborhood. Suppose that
a future TV cable were 10-Gbps fiber instead of copper. Could it be used to simulate
the telephone model of everybody having their own private line to the end office? If
so, how many one-telephone houses could be hooked up to a single fiber?
49. A cable company decides to provide Internet access over cable in a neighborhood con-
sisting of 5000 houses. The company uses a coaxial cable and spectrum allocation al-
lowing 100 Mbps downstream bandwidth per cable. To attract customers, the com-
pany decides to guarantee at least 2 Mbps downstream bandwidth to each house at any
time. Describe what the cable company needs to do to provide this guarantee.
50. Using the spectral allocation shown in Fig. 2-52 and the information given in the text,
how many Mbps does a cable system allocate to upstream and how many to down-
stream?
51. How fast can a cable user receive data if the network is otherwise idle? Assume that
the user interface is
(a) 10-Mbps Ethernet
(b) 100-Mbps Ethernet
(c) 54-Mbps Wireless.
52. Multiplexing STS-1 multiple data streams, called tributaries, plays an important role
in SONET. A 3:1 multiplexer multiplexes three input STS-1 tributaries onto one out-
put STS-3 stream. This multiplexing is done byte for byte. That is, the first three out-
put bytes are the first bytes of tributaries 1, 2, and 3, respectively. the next three out-
put bytes are the second bytes of tributaries 1, 2, and 3, respectively, and so on. Write
a program that simulates this 3:1 multiplexer. Your program should consist of five
processes. The main process creates four processes, one each for the three STS-1 tri-
butaries and one for the multiplexer. Each tributary process reads in an STS-1 frame
from an input file as a sequence of 810 bytes. They send their frames (byte by byte) to
the multiplexer process. The multiplexer process receives these bytes and outputs an
STS-3 frame (byte by byte) by writing it to standard output. Use pipes for communi-
cation among processes.
53. Write a program to implement CDMA. Assume that the length of a chip sequence is
eight and the number of stations transmitting is four. Your program consists of three
sets of processes: four transmitter processes (t0, t1, t2, and t3), one joiner process, and
four receiver processes (r0, r1, r2, and r3). The main program, which also acts as the
joiner process first reads four chip sequences (bipolar notation) from the standard
input and a sequence of 4 bits (1 bit per transmitter process to be transmitted), and
forks off four pairs of transmitter and receiver processes. Each pair of transmitter/re-
ceiver processes (t0,r0; t1,r1; t2,r2; t3,r3) is assigned one chip sequence and each
transmitter process is assigned 1 bit (first bit to t0, second bit to t1, and so on). Next,
each transmitter process computes the signal to be transmitted (a sequence of 8 bits)
and sends it to the joiner process. After receiving signals from all four transmitter
processes, the joiner process combines the signals and sends the combined signal to


---

<a id="page-204"></a>

<!-- Page 204 of 888 -->

192 THE PHYSICAL LAYER CHAP. 2
the four receiver processes. Each receiver process then computes the bit it has re-
ceived and prints it to standard output. Use pipes for communication between proc-
esses.
