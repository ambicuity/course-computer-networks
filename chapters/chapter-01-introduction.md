# Chapter 1: Introduction

_Source: printed pages 1-88; extracted PDF pages 13-100._

---

<a id="page-13"></a>

<!-- Page 13 of 888 -->

## Introduction
Each of the past three centuries was dominated by a single new technology.
The 18th century was the era of the great mechanical systems accompanying the
Industrial Revolution. The 19th century was the age of the steam engine. During
the 20th century, the key technology was information gathering, processing, and
distribution. Among other developments, we saw the installation of worldwide
telephone networks, the invention of radio and television, the birth and unpre-
cedented growth of the computer industry, the launching of communication satel-
lites, and, of course, the Internet.
As a result of rapid technological progress, these areas are rapidly converging
in the 21st century and the differences between collecting, transporting, storing,
and processing information are quickly disappearing. Organizations with hun-
dreds of offices spread over a wide geographical area routinely expect to be able
to examine the current status of even their most remote outpost at the push of a
button. As our ability to gather, process, and distribute information grows, the de-
mand for ever more sophisticated information processing grows even faster.
Although the computer industry is still young compared to other industries
(e.g., automobiles and air transportation), computers have made spectacular pro-
gress in a short time. During the first two decades of their existence, computer
systems were highly centralized, usually within a single large room. Not infre-
quently, this room had glass walls, through which visitors could gawk at the great
electronic wonder inside. A medium-sized company or university might have had



---

<a id="page-14"></a>

<!-- Page 14 of 888 -->

2 INTRODUCTION CHAP. 1
one or two computers, while very large institutions had at most a few dozen. The
idea that within forty years vastly more powerful computers smaller than postage
stamps would be mass produced by the billions was pure science fiction.
The merging of computers and communications has had a profound influence
on the way computer systems are organized. The once-dominant concept of the
''computer center'' as a room with a large computer to which users bring their
work for processing is now totally obsolete (although data centers holding thou-
sands of Internet servers are becoming common). The old model of a single com-
puter serving all of the organization's computational needs has been replaced by
one in which a large number of separate but interconnected computers do the job.
These systems are called computer networks. The design and organization of
these networks are the subjects of this book.
Throughout the book we will use the term ''computer network'' to mean a col-
lection of autonomous computers interconnected by a single technology. Two
computers are said to be interconnected if they are able to exchange information.
The connection need not be via a copper wire; fiber optics, microwaves, infrared,
and communication satellites can also be used. Networks come in many sizes,
shapes and forms, as we will see later. They are usually connected together to
make larger networks, with the Internet being the most well-known example of a
network of networks.
There is considerable confusion in the literature between a computer network
and a distributed system. The key distinction is that in a distributed system, a
collection of independent computers appears to its users as a single coherent sys-
tem. Usually, it has a single model or paradigm that it presents to the users. Of-
ten a layer of software on top of the operating system, called middleware, is
responsible for implementing this model. A well-known example of a distributed
system is the World Wide Web. It runs on top of the Internet and presents a
model in which everything looks like a document (Web page).
In a computer network, this coherence, model, and software are absent. Users
are exposed to the actual machines, without any attempt by the system to make
the machines look and act in a coherent way. If the machines have different hard-
ware and different operating systems, that is fully visible to the users. If a user
†
wants to run a program on a remote machine, he has to log onto that machine and
run it there.
In effect, a distributed system is a software system built on top of a network.
The software gives it a high degree of cohesiveness and transparency. Thus, the
distinction between a network and a distributed system lies with the software (es-
pecially the operating system), rather than with the hardware.
Nevertheless, there is considerable overlap between the two subjects. For ex-
ample, both distributed systems and computer networks need to move files
around. The difference lies in who invokes the movement, the system or the user.
† ''He'' should be read as ''he or she'' throughout this book.


---

<a id="page-15"></a>

<!-- Page 15 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 3
Although this book primarily focuses on networks, many of the topics are also im-
portant in distributed systems. For more information about distributed systems,
see Tanenbaum and Van Steen (2007).
### 1.1 USES OF COMPUTER NETWORKS
Before we start to examine the technical issues in detail, it is worth devoting
some time to pointing out why people are interested in computer networks and
what they can be used for. After all, if nobody were interested in computer net-
works, few of them would be built. We will start with traditional uses at com-
panies, then move on to home networking and recent developments regarding
mobile users, and finish with social issues.
#### 1.1.1 Business Applications
Most companies have a substantial number of computers. For example, a
company may have a computer for each worker and use them to design products,
write brochures, and do the payroll. Initially, some of these computers may have
worked in isolation from the others, but at some point, management may have
decided to connect them to be able to distribute information throughout the com-
pany.
Put in slightly more general form, the issue here is resource sharing. The
goal is to make all programs, equipment, and especially data available to anyone
on the network without regard to the physical location of the resource or the user.
An obvious and widespread example is having a group of office workers share a
common printer. None of the individuals really needs a private printer, and a
high-volume networked printer is often cheaper, faster, and easier to maintain
than a large collection of individual printers.
However, probably even more important than sharing physical resources such
as printers, and tape backup systems, is sharing information. Companies small
and large are vitally dependent on computerized information. Most companies
have customer records, product information, inventories, financial statements, tax
information, and much more online. If all of its computers suddenly went down, a
bank could not last more than five minutes. A modern manufacturing plant, with
a computer-controlled assembly line, would not last even 5 seconds. Even a small
travel agency or three-person law firm is now highly dependent on computer net-
works for allowing employees to access relevant information and documents
instantly.
For smaller companies, all the computers are likely to be in a single office or
perhaps a single building, but for larger ones, the computers and employees may
be scattered over dozens of offices and plants in many countries. Nevertheless, a
sales person in New York might sometimes need access to a product inventory


---

<a id="page-16"></a>

<!-- Page 16 of 888 -->

4 INTRODUCTION CHAP. 1
database in Singapore. Networks called VPNs (Virtual Private Networks) may
be used to join the individual networks at different sites into one extended net-
work. In other words, the mere fact that a user happens to be 15,000 km away
from his data should not prevent him from using the data as though they were
local. This goal may be summarized by saying that it is an attempt to end the
''tyranny of geography.''
In the simplest of terms, one can imagine a company's information system as
consisting of one or more databases with company information and some number
of employees who need to access them remotely. In this model, the data are stor-
ed on powerful computers called servers. Often these are centrally housed and
maintained by a system administrator. In contrast, the employees have simpler
machines, called clients, on their desks, with which they access remote data, for
example, to include in spreadsheets they are constructing. (Sometimes we will
refer to the human user of the client machine as the ''client,'' but it should be
clear from the context whether we mean the computer or its user.) The client and
server machines are connected by a network, as illustrated in Fig. 1-1. Note that
we have shown the network as a simple oval, without any detail. We will use this
form when we mean a network in the most abstract sense. When more detail is
required, it will be provided.
Client
Server
Network
Figure 1-1. A network with two clients and one server.
This whole arrangement is called the client-server model. It is widely used
and forms the basis of much network usage. The most popular realization is that
of a Web application, in which the server generates Web pages based on its data-
base in response to client requests that may update the database. The client-server
model is applicable when the client and server are both in the same building (and
belong to the same company), but also when they are far apart. For example,
when a person at home accesses a page on the World Wide Web, the same model
is employed, with the remote Web server being the server and the user's personal


---

<a id="page-17"></a>

<!-- Page 17 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 5
computer being the client. Under most conditions, one server can handle a large
number (hundreds or thousands) of clients simultaneously.
If we look at the client-server model in detail, we see that two processes (i.e.,
running programs) are involved, one on the client machine and one on the server
machine. Communication takes the form of the client process sending a message
over the network to the server process. The client process then waits for a reply
message. When the server process gets the request, it performs the requested
work or looks up the requested data and sends back a reply. These messages are
shown in Fig. 1-2.
Client machine Server machine
Request
Network
Reply
Client process Server process
Figure 1-2. The client-server model involves requests and replies.
A second goal of setting up a computer network has to do with people rather
than information or even computers. A computer network can provide a powerful
communication medium among employees. Virtually every company that has
two or more computers now has email (electronic mail), which employees gener-
ally use for a great deal of daily communication. In fact, a common gripe around
the water cooler is how much email everyone has to deal with, much of it quite
meaningless because bosses have discovered that they can send the same (often
content-free) message to all their subordinates at the push of a button.
Telephone calls between employees may be carried by the computer network
instead of by the phone company. This technology is called IP telephony or
Voice over IP (VoIP) when Internet technology is used. The microphone and
speaker at each end may belong to a VoIP-enabled phone or the employee's com-
puter. Companies find this a wonderful way to save on their telephone bills.
Other, richer forms of communication are made possible by computer net-
works. Video can be added to audio so that employees at distant locations can see
and hear each other as they hold a meeting. This technique is a powerful tool for
eliminating the cost and time previously devoted to travel. Desktop sharing lets
remote workers see and interact with a graphical computer screen. This makes it
easy for two or more people who work far apart to read and write a shared black-
board or write a report together. When one worker makes a change to an online
document, the others can see the change immediately, instead of waiting several
days for a letter. Such a speedup makes cooperation among far-flung groups of
people easy where it previously had been impossible. More ambitious forms of
remote coordination such as telemedicine are only now starting to be used (e.g.,


---

<a id="page-18"></a>

<!-- Page 18 of 888 -->

6 INTRODUCTION CHAP. 1
remote patient monitoring) but may become much more important. It is some-
times said that communication and transportation are having a race, and which-
ever wins will make the other obsolete.
A third goal for many companies is doing business electronically, especially
with customers and suppliers. This new model is called e-commerce (electronic
commerce) and it has grown rapidly in recent years. Airlines, bookstores, and
other retailers have discovered that many customers like the convenience of shop-
ping from home. Consequently, many companies provide catalogs of their goods
and services online and take orders online. Manufacturers of automobiles, air-
craft, and computers, among others, buy subsystems from a variety of suppliers
and then assemble the parts. Using computer networks, manufacturers can place
orders electronically as needed. This reduces the need for large inventories and
enhances efficiency.
#### 1.1.2 Home Applications
In 1977, Ken Olsen was president of the Digital Equipment Corporation, then
the number two computer vendor in the world (after IBM). When asked why Dig-
ital was not going after the personal computer market in a big way, he said:
''There is no reason for any individual to have a computer in his home.'' History
showed otherwise and Digital no longer exists. People initially bought computers
for word processing and games. Recently, the biggest reason to buy a home com-
puter was probably for Internet access. Now, many consumer electronic devices,
such as set-top boxes, game consoles, and clock radios, come with embedded
computers and computer networks, especially wireless networks, and home net-
works are broadly used for entertainment, including listening to, looking at, and
creating music, photos, and videos.
Internet access provides home users with connectivity to remote computers.
As with companies, home users can access information, communicate with other
people, and buy products and services with e-commerce. The main benefit now
comes from connecting outside of the home. Bob Metcalfe, the inventor of Ether-
net, hypothesized that the value of a network is proportional to the square of the
number of users because this is roughly the number of different connections that
may be made (Gilder, 1993). This hypothesis is known as ''Metcalfe's law.'' It
helps to explain how the tremendous popularity of the Internet comes from its
size.
Access to remote information comes in many forms. It can be surfing the
World Wide Web for information or just for fun. Information available includes
the arts, business, cooking, government, health, history, hobbies, recreation, sci-
ence, sports, travel, and many others. Fun comes in too many ways to mention,
plus some ways that are better left unmentioned.
Many newspapers have gone online and can be personalized. For example, it
is sometimes possible to tell a newspaper that you want everything about corrupt


---

<a id="page-19"></a>

<!-- Page 19 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 7
politicians, big fires, scandals involving celebrities, and epidemics, but no foot-
ball, thank you. Sometimes it is possible to have the selected articles downloaded
to your computer while you sleep. As this trend continues, it will cause massive
unemployment among 12-year-old paperboys, but newspapers like it because dis-
tribution has always been the weakest link in the whole production chain. Of
course, to make this model work, they will first have to figure out how to make
money in this new world, something not entirely obvious since Internet users
expect everything to be free.
The next step beyond newspapers (plus magazines and scientific journals) is
the online digital library. Many professional organizations, such as the ACM
(www.acm.org) and the IEEE Computer Society (www.computer.org), already
have all their journals and conference proceedings online. Electronic book read-
ers and online libraries may make printed books obsolete. Skeptics should take
note of the effect the printing press had on the medieval illuminated manuscript.
Much of this information is accessed using the client-server model, but there
is different, popular model for accessing information that goes by the name of
peer-to-peer communication (Parameswaran et al., 2001). In this form, individu-
als who form a loose group can communicate with others in the group, as shown
in Fig. 1-3. Every person can, in principle, communicate with one or more other
people; there is no fixed division into clients and servers.
Figure 1-3. In a peer-to-peer system there are no fixed clients and servers.
Many peer-to-peer systems, such BitTorrent (Cohen, 2003), do not have any
central database of content. Instead, each user maintains his own database locally
and provides a list of other nearby people who are members of the system. A new
user can then go to any existing member to see what he has and get the names of
other members to inspect for more content and more names. This lookup process
can be repeated indefinitely to build up a large local database of what is out there.
It is an activity that would get tedious for people but computers excel at it.


---

<a id="page-20"></a>

<!-- Page 20 of 888 -->

8 INTRODUCTION CHAP. 1
Peer-to-peer communication is often used to share music and videos. It really
hit the big time around 2000 with a music sharing service called Napster that was
shut down after what was probably the biggest copyright infringement case in all
of recorded history (Lam and Tan, 2001; and Macedonia, 2000). Legal applica-
tions for peer-to-peer communication also exist. These include fans sharing pub-
lic domain music, families sharing photos and movies, and users downloading
public software packages. In fact, one of the most popular Internet applications
of all, email, is inherently peer-to-peer. This form of communication is likely to
grow considerably in the future.
All of the above applications involve interactions between a person and a re-
mote database full of information. The second broad category of network use is
person-to-person communication, basically the 21st century's answer to the 19th
century's telephone. E-mail is already used on a daily basis by millions of people
all over the world and its use is growing rapidly. It already routinely contains
audio and video as well as text and pictures. Smell may take a while.
Any teenager worth his or her salt is addicted to instant messaging. This
facility, derived from the UNIX talk program in use since around 1970, allows two
people to type messages at each other in real time. There are multi-person mes-
saging services too, such as the Twitter service that lets people send short text
messages called ''tweets'' to their circle of friends or other willing audiences.
The Internet can be used by applications to carry audio (e.g., Internet radio
stations) and video (e.g., YouTube). Besides being a cheap way to call to distant
friends, these applications can provide rich experiences such as telelearning,
meaning attending 8 A.M. classes without the inconvenience of having to get out
of bed first. In the long run, the use of networks to enhance human-to-human
communication may prove more important than any of the others. It may become
hugely important to people who are geographically challenged, giving them the
same access to services as people living in the middle of a big city.
Between person-to-person communications and accessing information are
social network applications. Here, the flow of information is driven by the rela-
tionships that people declare between each other. One of the most popular social
networking sites is Facebook. It lets people update their personal profiles and
shares the updates with other people who they have declared to be their friends.
Other social networking applications can make introductions via friends of
friends, send news messages to friends such as Twitter above, and much more.
Even more loosely, groups of people can work together to create content. A
wiki, for example, is a collaborative Web site that the members of a community
edit. The most famous wiki is the Wikipedia, an encyclopedia anyone can edit,
but there are thousands of other wikis.
Our third category is electronic commerce in the broadest sense of the term.
Home shopping is already popular and enables users to inspect the online catalogs
of thousands of companies. Some of these catalogs are interactive, showing pro-
ducts from different viewpoints and in configurations that can be personalized.


---

<a id="page-21"></a>

<!-- Page 21 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 9
After the customer buys a product electronically but cannot figure out how to use
it, online technical support may be consulted.
Another area in which e-commerce is widely used is access to financial insti-
tutions. Many people already pay their bills, manage their bank accounts, and
handle their investments electronically. This trend will surely continue as net-
works become more secure.
One area that virtually nobody foresaw is electronic flea markets (e-flea?).
Online auctions of second-hand goods have become a massive industry. Unlike
traditional e-commerce, which follows the client-server model, online auctions
are peer-to-peer in the sense that consumers can act as both buyers and sellers.
Some of these forms of e-commerce have acquired cute little tags based on
the fact that ''to'' and ''2'' are pronounced the same. The most popular ones are
listed in Fig. 1-4.
Tag Full name Example
B2C Business-to-consumer Ordering books online
B2B Business-to-business Car manufacturer ordering tires from supplier
G2C Government-to-consumer Government distributing tax forms electronically
C2C Consumer-to-consumer Auctioning second-hand products online
P2P Peer-to-peer Music sharing
Figure 1-4. Some forms of e-commerce.
Our fourth category is entertainment. This has made huge strides in the home
in recent years, with the distribution of music, radio and television programs, and
movies over the Internet beginning to rival that of traditional mechanisms. Users
can find, buy, and download MP3 songs and DVD-quality movies and add them
to their personal collection. TV shows now reach many homes via IPTV (IP
TeleVision) systems that are based on IP technology instead of cable TV or radio
transmissions. Media streaming applications let users tune into Internet radio sta-
tions or watch recent episodes of their favorite TV shows. Naturally, all of this
content can be moved around your house between different devices, displays and
speakers, usually with a wireless network.
Soon, it may be possible to search for any movie or television program ever
made, in any country, and have it displayed on your screen instantly. New films
may become interactive, where the user is occasionally prompted for the story
direction (should Macbeth murder Duncan or just bide his time?) with alternative
scenarios provided for all cases. Live television may also become interactive,
with the audience participating in quiz shows, choosing among contestants, and so
on.
Another form of entertainment is game playing. Already we have multiperson
real-time simulation games, like hide-and-seek in a virtual dungeon, and flight


---

<a id="page-22"></a>

<!-- Page 22 of 888 -->

10 INTRODUCTION CHAP. 1
simulators with the players on one team trying to shoot down the players on the
opposing team. Virtual worlds provide a persistent setting in which thousands of
users can experience a shared reality with three-dimensional graphics.
Our last category is ubiquitous computing, in which computing is embedded
into everyday life, as in the vision of Mark Weiser (1991). Many homes are al-
ready wired with security systems that include door and window sensors, and
there are many more sensors that can be folded in to a smart home monitor, such
as energy consumption. Your electricity, gas and water meters could also report
usage over the network. This would save money as there would be no need to
send out meter readers. And your smoke detectors could call the fire department
instead of making a big noise (which has little value if no one is home). As the
cost of sensing and communication drops, more and more measurement and re-
porting will be done with networks.
Increasingly, consumer electronic devices are networked. For example, some
high-end cameras already have a wireless network capability and use it to send
photos to a nearby display for viewing. Professional sports photographers can
also send their photos to their editors in real-time, first wirelessly to an access
point then over the Internet. Devices such as televisions that plug into the wall
can use power-line networks to send information throughout the house over the
wires that carry electricity. It may not be very surprising to have these objects on
the network, but objects that we do not think of as computers may sense and com-
municate information too. For example, your shower may record water usage,
give you visual feedback while you lather up, and report to a home environmental
monitoring application when you are done to help save on your water bill.
A technology called RFID (Radio Frequency IDentification) will push this
idea even further in the future. RFID tags are passive (i.e., have no battery) chips
the size of stamps and they can already be affixed to books, passports, pets, credit
cards, and other items in the home and out. This lets RFID readers locate and
communicate with the items over a distance of up to several meters, depending on
the kind of RFID. Originally, RFID was commercialized to replace barcodes. It
has not succeeded yet because barcodes are free and RFID tags cost a few cents.
Of course, RFID tags offer much more and their price is rapidly declining. They
may turn the real world into the Internet of things (ITU, 2005).
#### 1.1.3 Mobile Users
Mobile computers, such as laptop and handheld computers, are one of the
fastest-growing segments of the computer industry. Their sales have already
overtaken those of desktop computers. Why would anyone want one? People on
the go often want to use their mobile devices to read and send email, tweet, watch
movies, download music, play games, or simply to surf the Web for information.
They want to do all of the things they do at home and in the office. Naturally, they
want to do them from anywhere on land, sea or in the air.


---

<a id="page-23"></a>

<!-- Page 23 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 11
Connectivity to the Internet enables many of these mobile uses. Since having
a wired connection is impossible in cars, boats, and airplanes, there is a lot of
interest in wireless networks. Cellular networks operated by the telephone com-
panies are one familiar kind of wireless network that blankets us with coverage
for mobile phones. Wireless hotspots based on the 802.11 standard are another
kind of wireless network for mobile computers. They have sprung up everywhere
that people go, resulting in a patchwork of coverage at cafes, hotels, airports,
schools, trains and planes. Anyone with a laptop computer and a wireless modem
can just turn on their computer on and be connected to the Internet through the
hotspot, as though the computer were plugged into a wired network.
Wireless networks are of great value to fleets of trucks, taxis, delivery vehi-
cles, and repairpersons for keeping in contact with their home base. For example,
in many cities, taxi drivers are independent businessmen, rather than being em-
ployees of a taxi company. In some of these cities, the taxis have a display the
driver can see. When a customer calls up, a central dispatcher types in the pickup
and destination points. This information is displayed on the drivers' displays and
a beep sounds. The first driver to hit a button on the display gets the call.
Wireless networks are also important to the military. If you have to be able to
fight a war anywhere on Earth at short notice, counting on using the local net-
working infrastructure is probably not a good idea. It is better to bring your own.
Although wireless networking and mobile computing are often related, they
are not identical, as Fig. 1-5 shows. Here we see a distinction between fixed
wireless and mobile wireless networks. Even notebook computers are sometimes
wired. For example, if a traveler plugs a notebook computer into the wired net-
work jack in a hotel room, he has mobility without a wireless network.
Wireless Mobile Typical applications
No No Desktop computers in offices
No Yes A notebook computer used in a hotel room
Yes No Networks in unwired buildings
Yes Yes Store inventory with a handheld computer
Figure 1-5. Combinations of wireless networks and mobile computing.
Conversely, some wireless computers are not mobile. In the home, and in
offices or hotels that lack suitable cabling, it can be more convenient to connect
desktop computers or media players wirelessly than to install wires. Installing a
wireless network may require little more than buying a small box with some elec-
tronics in it, unpacking it, and plugging it in. This solution may be far cheaper
than having workmen put in cable ducts to wire the building.
Finally, there are also true mobile, wireless applications, such as people walk-
ing around stores with a handheld computers recording inventory. At many busy


---

<a id="page-24"></a>

<!-- Page 24 of 888 -->

12 INTRODUCTION CHAP. 1
airports, car rental return clerks work in the parking lot with wireless mobile com-
puters. They scan the barcodes or RFID chips of returning cars, and their mobile
device, which has a built-in printer, calls the main computer, gets the rental infor-
mation, and prints out the bill on the spot.
Perhaps the key driver of mobile, wireless applications is the mobile phone.
Text messaging or texting is tremendously popular. It lets a mobile phone user
type a short message that is then delivered by the cellular network to another
mobile subscriber. Few people would have predicted ten years ago that having
teenagers tediously typing short text messages on mobile phones would be an
immense money maker for telephone companies. But texting (or Short Message
Service as it is known outside the U.S.) is very profitable since it costs the carrier
but a tiny fraction of one cent to relay a text message, a service for which they
charge far more.
The long-awaited convergence of telephones and the Internet has finally
arrived, and it will accelerate the growth of mobile applications. Smart phones,
such as the popular iPhone, combine aspects of mobile phones and mobile com-
puters. The (3G and 4G) cellular networks to which they connect can provide fast
data services for using the Internet as well as handling phone calls. Many ad-
vanced phones connect to wireless hotspots too, and automatically switch between
networks to choose the best option for the user.
Other consumer electronics devices can also use cellular and hotspot networks
to stay connected to remote computers. Electronic book readers can download a
newly purchased book or the next edition of a magazine or today's newspaper
wherever they roam. Electronic picture frames can update their displays on cue
with fresh images.
Since mobile phones know their locations, often because they are equipped
with GPS (Global Positioning System) receivers, some services are intentionally
location dependent. Mobile maps and directions are an obvious candidate as your
GPS-enabled phone and car probably have a better idea of where you are than you
do. So, too, are searches for a nearby bookstore or Chinese restaurant, or a local
weather forecast. Other services may record location, such as annotating photos
and videos with the place at which they were made. This annotation is known as
''geo-tagging.''
An area in which mobile phones are now starting to be used is m-commerce
(mobile-commerce) (Senn, 2000). Short text messages from the mobile are used
to authorize payments for food in vending machines, movie tickets, and other
small items instead of cash and credit cards. The charge then appears on the
mobile phone bill. When equipped with NFC (Near Field Communication)
technology the mobile can act as an RFID smartcard and interact with a nearby
reader for payment. The driving forces behind this phenomenon are the mobile
device makers and network operators, who are trying hard to figure out how to get
a piece of the e-commerce pie. From the store's point of view, this scheme may
save them most of the credit card company's fee, which can be several percent.


---

<a id="page-25"></a>

<!-- Page 25 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 13
Of course, this plan may backfire, since customers in a store might use the RFID
or barcode readers on their mobile devices to check out competitors' prices before
buying and use them to get a detailed report on where else an item can be pur-
chased nearby and at what price.
One huge thing that m-commerce has going for it is that mobile phone users
are accustomed to paying for everything (in contrast to Internet users, who expect
everything to be free). If an Internet Web site charged a fee to allow its customers
to pay by credit card, there would be an immense howling noise from the users.
If, however, a mobile phone operator its customers to pay for items in a store by
waving the phone at the cash register and then tacked on a fee for this conveni-
ence, it would probably be accepted as normal. Time will tell.
No doubt the uses of mobile and wireless computers will grow rapidly in the
future as the size of computers shrinks, probably in ways no one can now foresee.
Let us take a quick look at some possibilities. Sensor networks are made up of
nodes that gather and wirelessly relay information they sense about the state of the
physical world. The nodes may be part of familiar items such as cars or phones,
or they may be small separate devices. For example, your car might gather data
on its location, speed, vibration, and fuel efficiency from its on-board diagnostic
system and upload this information to a database (Hull et al., 2006). Those data
can help find potholes, plan trips around congested roads, and tell you if you are a
''gas guzzler'' compared to other drivers on the same stretch of road.
Sensor networks are revolutionizing science by providing a wealth of data on
behavior that could not previously be observed. One example is tracking the
migration of individual zebras by placing a small sensor on each animal (Juang et
al., 2002). Researchers have packed a wireless computer into a cube 1 mm on
edge (Warneke et al., 2001). With mobile computers this small, even small birds,
rodents, and insects can be tracked.
Even mundane uses, such as in parking meters, can be significant because
they make use of data that were not previously available. Wireless parking meters
can accept credit or debit card payments with instant verification over the wireless
link. They can also report when they are in use over the wireless network. This
would let drivers download a recent parking map to their car so they can find an
available spot more easily. Of course, when a meter expires, it might also check
for the presence of a car (by bouncing a signal off it) and report the expiration to
parking enforcement. It has been estimated that city governments in the U.S.
alone could collect an additional $10 billion this way (Harte et al., 2000).
Wearable computers are another promising application. Smart watches with
radios have been part of our mental space since their appearance in the Dick
Tracy comic strip in 1946; now you can buy them. Other such devices may be
implanted, such as pacemakers and insulin pumps. Some of these can be con-
trolled over a wireless network. This lets doctors test and reconfigure them more
easily. It could also lead to some nasty problems if the devices are as insecure as
the average PC and can be hacked easily (Halperin et al., 2008).


---

<a id="page-26"></a>

<!-- Page 26 of 888 -->

14 INTRODUCTION CHAP. 1
#### 1.1.4 Social Issues
Computer networks, like the printing press 500 years ago, allow ordinary
citizens to distribute and view content in ways that were not previously possible.
But along with the good comes the bad, as this new-found freedom brings with it
many unsolved social, political, and ethical issues. Let us just briefly mention a
few of them; a thorough study would require a full book, at least.
Social networks, message boards, content sharing sites, and a host of other ap-
plications allow people to share their views with like-minded individuals. As long
as the subjects are restricted to technical topics or hobbies like gardening, not too
many problems will arise.
The trouble comes with topics that people actually care about, like politics,
religion, or sex. Views that are publicly posted may be deeply offensive to some
people. Worse yet, they may not be politically correct. Furthermore, opinions
need not be limited to text; high-resolution color photographs and video clips are
easily shared over computer networks. Some people take a live-and-let-live view,
but others feel that posting certain material (e.g., verbal attacks on particular
countries or religions, pornography, etc.) is simply unacceptable and that such
content must be censored. Different countries have different and conflicting laws
in this area. Thus, the debate rages.
In the past, people have sued network operators, claiming that they are re-
sponsible for the contents of what they carry, just as newspapers and magazines
are. The inevitable response is that a network is like a telephone company or the
post office and cannot be expected to police what its users say.
It should now come only as a slight surprise to learn that some network opera-
tors block content for their own reasons. Some users of peer-to-peer applications
had their network service cut off because the network operators did not find it pro-
fitable to carry the large amounts of traffic sent by those applications. Those
same operators would probably like to treat different companies differently. If
you are a big company and pay well then you get good service, but if you are a
small-time player, you get poor service. Opponents of this practice argue that
peer-to-peer and other content should be treated in the same way because they are
all just bits to the network. This argument for communications that are not dif-
ferentiated by their content or source or who is providing the content is known as
network neutrality (Wu, 2003). It is probably safe to say that this debate will go
on for a while.
Many other parties are involved in the tussle over content. For instance, pi-
rated music and movies fueled the massive growth of peer-to-peer networks,
which did not please the copyright holders, who have threatened (and sometimes
taken) legal action. There are now automated systems that search peer-to-peer
networks and fire off warnings to network operators and users who are suspected
of infringing copyright. In the United States, these warnings are known as
DMCA takedown notices after the Digital Millennium Copyright Act. This


---

<a id="page-27"></a>

<!-- Page 27 of 888 -->

SEC. 1.1 USES OF COMPUTER NETWORKS 15
search is an arms' race because it is hard to reliably catch copyright infringement.
Even your printer might be mistaken for a culprit (Piatek et al., 2008).
Computer networks make it very easy to communicate. They also make it
easy for the people who run the network to snoop on the traffic. This sets up con-
flicts over issues such as employee rights versus employer rights. Many people
read and write email at work. Many employers have claimed the right to read and
possibly censor employee messages, including messages sent from a home com-
puter outside working hours. Not all employees agree with this, especially the lat-
ter part.
Another conflict is centered around government versus citizen's rights. The
FBI has installed systems at many Internet service providers to snoop on all in-
coming and outgoing email for nuggets of interest. One early system was origi-
nally called Carnivore, but bad publicity caused it to be renamed to the more
innocent-sounding DCS1000 (Blaze and Bellovin, 2000; Sobel, 2001; and Zacks,
2001). The goal of such systems is to spy on millions of people in the hope of
perhaps finding information about illegal activities. Unfortunately for the spies,
the Fourth Amendment to the U.S. Constitution prohibits government searches
without a search warrant, but the government often ignores it.
Of course, the government does not have a monopoly on threatening people's
privacy. The private sector does its bit too by profiling users. For example,
small files called cookies that Web browsers store on users' computers allow
companies to track users' activities in cyberspace and may also allow credit card
numbers, social security numbers, and other confidential information to leak all
over the Internet (Berghel, 2001). Companies that provide Web-based services
may maintain large amounts of personal information about their users that allows
them to study user activities directly. For example, Google can read your email
and show you advertisements based on your interests if you use its email service,
Gmail.
A new twist with mobile devices is location privacy (Beresford and Stajano,
2003). As part of the process of providing service to your mobile device the net-
work operators learn where you are at different times of day. This allows them to
track your movements. They may know which nightclub you frequent and which
medical center you visit.
Computer networks also offer the potential to increase privacy by sending
anonymous messages. In some situations, this capability may be desirable.
Beyond preventing companies from learning your habits, it provides, for example,
a way for students, soldiers, employees, and citizens to blow the whistle on illegal
behavior on the part of professors, officers, superiors, and politicians without fear
of reprisals. On the other hand, in the United States and most other democracies,
the law specifically permits an accused person the right to confront and challenge
his accuser in court so anonymous accusations cannot be used as evidence.
The Internet makes it possible to find information quickly, but a great deal of
it is ill considered, misleading, or downright wrong. That medical advice you


---

<a id="page-28"></a>

<!-- Page 28 of 888 -->

16 INTRODUCTION CHAP. 1
plucked from the Internet about the pain in your chest may have come from a
Nobel Prize winner or from a high-school dropout.
Other information is frequently unwanted. Electronic junk mail (spam) has
become a part of life because spammers have collected millions of email address-
es and would-be marketers can cheaply send computer-generated messages to
them. The resulting flood of spam rivals the flow messages from real people.
Fortunately, filtering software is able to read and discard the spam generated by
other computers, with lesser or greater degrees of success.
Still other content is intended for criminal behavior. Web pages and email
messages containing active content (basically, programs or macros that execute on
the receiver's machine) can contain viruses that take over your computer. They
might be used to steal your bank account passwords, or to have your computer
send spam as part of a botnet or pool of compromised machines.
Phishing messages masquerade as originating from a trustworthy party, for
example, your bank, to try to trick you into revealing sensitive information, for
example, credit card numbers. Identity theft is becoming a serious problem as
thieves collect enough information about a victim to obtain credit cards and other
documents in the victim's name.
It can be difficult to prevent computers from impersonating people on the In-
ternet. This problem has led to the development of CAPTCHAs, in which a com-
puter asks a person to solve a short recognition task, for example, typing in the
letters shown in a distorted image, to show that they are human (von Ahn, 2001).
This process is a variation on the famous Turing test in which a person asks ques-
tions over a network to judge whether the entity responding is human.
A lot of these problems could be solved if the computer industry took com-
puter security seriously. If all messages were encrypted and authenticated, it
would be harder to commit mischief. Such technology is well established and we
will study it in detail in Chap. 8. The problem is that hardware and software ven-
dors know that putting in security features costs money and their customers are
not demanding such features. In addition, a substantial number of the problems
are caused by buggy software, which occurs because vendors keep adding more
and more features to their programs, which inevitably means more code and thus
more bugs. A tax on new features might help, but that might be a tough sell in
some quarters. A refund for defective software might be nice, except it would
bankrupt the entire software industry in the first year.
Computer networks raise new legal problems when they interact with old
laws. Electronic gambling provides an example. Computers have been simulating
things for decades, so why not simulate slot machines, roulette wheels, blackjack
dealers, and more gambling equipment? Well, because it is illegal in a lot of
places. The trouble is, gambling is legal in a lot of other places (England, for ex-
ample) and casino owners there have grasped the potential for Internet gambling.
What happens if the gambler, the casino, and the server are all in different coun-
tries, with conflicting laws? Good question.


---

<a id="page-29"></a>

<!-- Page 29 of 888 -->

SEC. 1.2 NETWORK HARDWARE 17
### 1.2 NETWORK HARDWARE
It is now time to turn our attention from the applications and social aspects of
networking (the dessert) to the technical issues involved in network design (the
spinach). There is no generally accepted taxonomy into which all computer net-
works fit, but two dimensions stand out as important: transmission technology and
scale. We will now examine each of these in turn.
Broadly speaking, there are two types of transmission technology that are in
widespread use: broadcast links and point-to-point links.
Point-to-point links connect individual pairs of machines. To go from the
source to the destination on a network made up of point-to-point links, short mes-
sages, called packets in certain contexts, may have to first visit one or more inter-
mediate machines. Often multiple routes, of different lengths, are possible, so
finding good ones is important in point-to-point networks. Point-to-point
transmission with exactly one sender and exactly one receiver is sometimes called
unicasting.
In contrast, on a broadcast network, the communication channel is shared by
all the machines on the network; packets sent by any machine are received by all
the others. An address field within each packet specifies the intended recipient.
Upon receiving a packet, a machine checks the address field. If the packet is in-
tended for the receiving machine, that machine processes the packet; if the packet
is intended for some other machine, it is just ignored.
A wireless network is a common example of a broadcast link, with communi-
cation shared over a coverage region that depends on the wireless channel and the
transmitting machine. As an analogy, consider someone standing in a meeting
room and shouting ''Watson, come here. I want you.'' Although the packet may
actually be received (heard) by many people, only Watson will respond; the others
just ignore it.
Broadcast systems usually also allow the possibility of addressing a packet to
all destinations by using a special code in the address field. When a packet with
this code is transmitted, it is received and processed by every machine on the net-
work. This mode of operation is called broadcasting. Some broadcast systems
also support transmission to a subset of the machines, which known as multicast-
ing.
An alternative criterion for classifying networks is by scale. Distance is im-
portant as a classification metric because different technologies are used at dif-
ferent scales.
In Fig. 1-6 we classify multiple processor systems by their rough physical
size. At the top are the personal area networks, networks that are meant for one
person. Beyond these come longer-range networks. These can be divided into
local, metropolitan, and wide area networks, each with increasing scale. Finally,
the connection of two or more networks is called an internetwork. The worldwide
Internet is certainly the best-known (but not the only) example of an internetwork.


---

<a id="page-30"></a>

<!-- Page 30 of 888 -->

18 INTRODUCTION CHAP. 1
Soon we will have even larger internetworks with the Interplanetary Internet
that connects networks across space (Burleigh et al., 2003).
Interprocessor Processors Example
distance located in same
1 m Square meter Personal area network
10 m Room
100 m Building Local area network
1 km Campus
10 km City Metropolitan area network
100 km Country
Wide area network
1000 km Continent
10,000 km Planet The Internet
Figure 1-6. Classification of interconnected processors by scale.
In this book we will be concerned with networks at all these scales. In the
following sections, we give a brief introduction to network hardware by scale.
#### 1.2.1 Personal Area Networks
PANs (Personal Area Networks) let devices communicate over the range of
a person. A common example is a wireless network that connects a computer
with its peripherals. Almost every computer has an attached monitor, keyboard,
mouse, and printer. Without using wireless, this connection must be done with
cables. So many new users have a hard time finding the right cables and plugging
them into the right little holes (even though they are usually color coded) that
most computer vendors offer the option of sending a technician to the user's home
to do it. To help these users, some companies got together to design a short-range
wireless network called Bluetooth to connect these components without wires.
The idea is that if your devices have Bluetooth, then you need no cables. You just
put them down, turn them on, and they work together. For many people, this ease
of operation is a big plus.
In the simplest form, Bluetooth networks use the master-slave paradigm of
Fig. 1-7. The system unit (the PC) is normally the master, talking to the mouse,
keyboard, etc., as slaves. The master tells the slaves what addresses to use, when
they can broadcast, how long they can transmit, what frequencies they can use,
and so on.
Bluetooth can be used in other settings, too. It is often used to connect a
headset to a mobile phone without cords and it can allow your digital music player


---

<a id="page-31"></a>

<!-- Page 31 of 888 -->

SEC. 1.2 NETWORK HARDWARE 19
Figure 1-7. Bluetooth PAN configuration.
to connect to your car merely being brought within range. A completely different
kind of PAN is formed when an embedded medical device such as a pacemaker,
insulin pump, or hearing aid talks to a user-operated remote control. We will dis-
cuss Bluetooth in more detail in Chap. 4.
PANs can also be built with other technologies that communicate over short
ranges, such as RFID on smartcards and library books. We will study RFID in
Chap. 4.
#### 1.2.2 Local Area Networks
The next step up is the LAN (Local Area Network). A LAN is a privately
owned network that operates within and nearby a single building like a home, of-
fice or factory. LANs are widely used to connect personal computers and consu-
mer electronics to let them share resources (e.g., printers) and exchange informa-
tion. When LANs are used by companies, they are called enterprise networks.
Wireless LANs are very popular these days, especially in homes, older office
buildings, cafeterias, and other places where it is too much trouble to install
cables. In these systems, every computer has a radio modem and an antenna that
it uses to communicate with other computers. In most cases, each computer talks
to a device in the ceiling as shown in Fig. 1-8(a). This device, called an AP
(Access Point), wireless router, or base station, relays packets between the
wireless computers and also between them and the Internet. Being the AP is like
being the popular kid as school because everyone wants to talk to you. However,
if other computers are close enough, they can communicate directly with one an-
other in a peer-to-peer configuration.
There is a standard for wireless LANs called IEEE 802.11, popularly known
as WiFi, which has become very widespread. It runs at speeds anywhere from 11


---

<a id="page-32"></a>

<!-- Page 32 of 888 -->

20 INTRODUCTION CHAP. 1
Access To wired network Ethernet
point Ports switch To rest of
network
Figure 1-8. Wireless and wired LANs. (a) 802.11. (b) Switched Ethernet.
to hundreds of Mbps. (In this book we will adhere to tradition and measure line
speeds in megabits/sec, where 1 Mbps is 1,000,000 bits/sec, and gigabits/sec,
where 1 Gbps is 1,000,000,000 bits/sec.) We will discuss 802.11 in Chap. 4.
Wired LANs use a range of different transmission technologies. Most of
them use copper wires, but some use optical fiber. LANs are restricted in size,
which means that the worst-case transmission time is bounded and known in ad-
vance. Knowing these bounds helps with the task of designing network protocols.
Typically, wired LANs run at speeds of 100 Mbps to 1 Gbps, have low delay
(microseconds or nanoseconds), and make very few errors. Newer LANs can op-
erate at up to 10 Gbps. Compared to wireless networks, wired LANs exceed them
in all dimensions of performance. It is just easier to send signals over a wire or
through a fiber than through the air.
The topology of many wired LANs is built from point-to-point links. IEEE
802.3, popularly called Ethernet, is, by far, the most common type of wired
LAN. Fig. 1-8(b) shows a sample topology of switched Ethernet. Each com-
puter speaks the Ethernet protocol and connects to a box called a switch with a
point-to-point link. Hence the name. A switch has multiple ports, each of which
can connect to one computer. The job of the switch is to relay packets between
computers that are attached to it, using the address in each packet to determine
which computer to send it to.
To build larger LANs, switches can be plugged into each other using their
ports. What happens if you plug them together in a loop? Will the network still
work? Luckily, the designers thought of this case. It is the job of the protocol to
sort out what paths packets should travel to safely reach the intended computer.
We will see how this works in Chap. 4.
It is also possible to divide one large physical LAN into two smaller logical
LANs. You might wonder why this would be useful. Sometimes, the layout of the
network equipment does not match the organization's structure. For example, the


---

<a id="page-33"></a>

<!-- Page 33 of 888 -->

SEC. 1.2 NETWORK HARDWARE 21
engineering and finance departments of a company might have computers on the
same physical LAN because they are in the same wing of the building but it might
be easier to manage the system if engineering and finance logically each had its
own network Virtual LAN or VLAN. In this design each port is tagged with a
''color,'' say green for engineering and red for finance. The switch then forwards
packets so that computers attached to the green ports are separated from the com-
puters attached to the red ports. Broadcast packets sent on a red port, for example,
will not be received on a green port, just as though there were two different
LANs. We will cover VLANs at the end of Chap. 4.
There are other wired LAN topologies too. In fact, switched Ethernet is a
modern version of the original Ethernet design that broadcast all the packets over
a single linear cable. At most one machine could successfully transmit at a time,
and a distributed arbitration mechanism was used to resolve conflicts. It used a
simple algorithm: computers could transmit whenever the cable was idle. If two
or more packets collided, each computer just waited a random time and tried later.
We will call that version classic Ethernet for clarity, and as you suspected, you
will learn about it in Chap. 4.
Both wireless and wired broadcast networks can be divided into static and
dynamic designs, depending on how the channel is allocated. A typical static al-
location would be to divide time into discrete intervals and use a round-robin al-
gorithm, allowing each machine to broadcast only when its time slot comes up.
Static allocation wastes channel capacity when a machine has nothing to say dur-
ing its allocated slot, so most systems attempt to allocate the channel dynamically
(i.e., on demand).
Dynamic allocation methods for a common channel are either centralized or
decentralized. In the centralized channel allocation method, there is a single enti-
ty, for example, the base station in cellular networks, which determines who goes
next. It might do this by accepting multiple packets and prioritizing them accord-
ing to some internal algorithm. In the decentralized channel allocation method,
there is no central entity; each machine must decide for itself whether to transmit.
You might think that this approach would lead to chaos, but it does not. Later we
will study many algorithms designed to bring order out of the potential chaos.
It is worth spending a little more time discussing LANs in the home. In the
future, it is likely that every appliance in the home will be capable of communi-
cating with every other appliance, and all of them will be accessible over the In-
ternet. This development is likely to be one of those visionary concepts that
nobody asked for (like TV remote controls or mobile phones), but once they
arrived nobody can imagine how they lived without them.
Many devices are already capable of being networked. These include com-
puters, entertainment devices such as TVs and DVDs, phones and other consumer
electronics such as cameras, appliances like clock radios, and infrastructure like
utility meters and thermostats. This trend will only continue. For instance, the
average home probably has a dozen clocks (e.g., in appliances), all of which could


---

<a id="page-34"></a>

<!-- Page 34 of 888 -->

22 INTRODUCTION CHAP. 1
adjust to daylight savings time automatically if the clocks were on the Internet.
Remote monitoring of the home is a likely winner, as many grown children would
be willing to spend some money to help their aging parents live safely in their
own homes.
While we could think of the home network as just another LAN, it is more
likely to have different properties than other networks. First, the networked de-
vices have to be very easy to install. Wireless routers are the most returned con-
sumer electronic item. People buy one because they want a wireless network at
home, find that it does not work ''out of the box,'' and then return it rather than
listen to elevator music while on hold on the technical helpline.
Second, the network and devices have to be foolproof in operation. Air con-
ditioners used to have one knob with four settings: OFF, LOW, MEDIUM, and
HIGH. Now they have 30-page manuals. Once they are networked, expect the
chapter on security alone to be 30 pages. This is a problem because only com-
puter users are accustomed to putting up with products that do not work; the car-,
television-, and refrigerator-buying public is far less tolerant. They expect pro-
ducts to work 100% without the need to hire a geek.
Third, low price is essential for success. People will not pay a $50 premium
for an Internet thermostat because few people regard monitoring their home tem-
perature from work that important. For $5 extra, though, it might sell.
Fourth, it must be possible to start out with one or two devices and expand the
reach of the network gradually. This means no format wars. Telling consumers
to buy peripherals with IEEE 1394 (FireWire) interfaces and a few years later
retracting that and saying USB 2.0 is the interface-of-the-month and then switch-
ing that to 802.11g-oops, no, make that 802.11n-I mean 802.16 (different wire-
less networks)-is going to make consumers very skittish. The network interface
will have to remain stable for decades, like the television broadcasting standards.
Fifth, security and reliability will be very important. Losing a few files to an
email virus is one thing; having a burglar disarm your security system from his
mobile computer and then plunder your house is something quite different.
An interesting question is whether home networks will be wired or wireless.
Convenience and cost favors wireless networking because there are no wires to
fit, or worse, retrofit. Security favors wired networking because the radio waves
that wireless networks use are quite good at going through walls. Not everyone is
overjoyed at the thought of having the neighbors piggybacking on their Internet
connection and reading their email. In Chap. 8 we will study how encryption can
be used to provide security, but it is easier said than done with inexperienced
users.
A third option that may be appealing is to reuse the networks that are already
in the home. The obvious candidate is the electric wires that are installed
throughout the house. Power-line networks let devices that plug into outlets
broadcast information throughout the house. You have to plug in the TV anyway,
and this way it can get Internet connectivity at the same time. The difficulty is


---

<a id="page-35"></a>

<!-- Page 35 of 888 -->

SEC. 1.2 NETWORK HARDWARE 23
how to carry both power and data signals at the same time. Part of the answer is
that they use different frequency bands.
In short, home LANs offer many opportunities and challenges. Most of the
latter relate to the need for the networks to be easy to manage, dependable, and
secure, especially in the hands of nontechnical users, as well as low cost.
#### 1.2.3 Metropolitan Area Networks
A MAN (Metropolitan Area Network) covers a city. The best-known ex-
amples of MANs are the cable television networks available in many cities.
These systems grew from earlier community antenna systems used in areas with
poor over-the-air television reception. In those early systems, a large antenna was
placed on top of a nearby hill and a signal was then piped to the subscribers'
houses.
At first, these were locally designed, ad hoc systems. Then companies began
jumping into the business, getting contracts from local governments to wire up en-
tire cities. The next step was television programming and even entire channels
designed for cable only. Often these channels were highly specialized, such as all
news, all sports, all cooking, all gardening, and so on. But from their inception
until the late 1990s, they were intended for television reception only.
When the Internet began attracting a mass audience, the cable TV network
operators began to realize that with some changes to the system, they could pro-
vide two-way Internet service in unused parts of the spectrum. At that point, the
cable TV system began to morph from simply a way to distribute television to a
metropolitan area network. To a first approximation, a MAN might look some-
thing like the system shown in Fig. 1-9. In this figure we see both television sig-
nals and Internet being fed into the centralized cable headend for subsequent dis-
tribution to people's homes. We will come back to this subject in detail in Chap.
2.
Cable television is not the only MAN, though. Recent developments in high-
speed wireless Internet access have resulted in another MAN, which has been
standardized as IEEE 802.16 and is popularly known as WiMAX. We will look
at it in Chap. 4.
#### 1.2.4 Wide Area Networks
A WAN (Wide Area Network) spans a large geographical area, often a
country or continent. We will begin our discussion with wired WANs, using the
example of a company with branch offices in different cities.
The WAN in Fig. 1-10 is a network that connects offices in Perth, Melbourne,
and Brisbane. Each of these offices contains computers intended for running user
(i.e., application) programs. We will follow traditional usage and call these ma-
chines hosts. The rest of the network that connects these hosts is then called the


---

<a id="page-36"></a>

<!-- Page 36 of 888 -->

24 INTRODUCTION CHAP. 1
Junction
box
Antenna
Head end
Internet
Figure 1-9. A metropolitan area network based on cable TV.
communication subnet, or just subnet for short. The job of the subnet is to carry
messages from host to host, just as the telephone system carries words (really just
sounds) from speaker to listener.
In most WANs, the subnet consists of two distinct components: transmission
lines and switching elements. Transmission lines move bits between machines.
They can be made of copper wire, optical fiber, or even radio links. Most com-
panies do not have transmission lines lying about, so instead they lease the lines
from a telecommunications company. Switching elements, or just switches, are
specialized computers that connect two or more transmission lines. When data
arrive on an incoming line, the switching element must choose an outgoing line on
which to forward them. These switching computers have been called by various
names in the past; the name router is now most commonly used. Unfortunately,
some people pronounce it ''rooter'' while others have it rhyme with ''doubter.''
Determining the correct pronunciation will be left as an exercise for the reader.
(Note: the perceived correct answer may depend on where you live.)
A short comment about the term ''subnet'' is in order here. Originally, its
only meaning was the collection of routers and communication lines that moved
packets from the source host to the destination host. Readers should be aware that
it has acquired a second, more recent meaning in conjunction with network ad-
dressing. We will discuss that meaning in Chap. 5 and stick with the original
meaning (a collection of lines and routers) until then.
The WAN as we have described it looks similar to a large wired LAN, but
there are some important differences that go beyond long wires. Usually in a
WAN, the hosts and subnet are owned and operated by different people. In our


---

<a id="page-37"></a>

<!-- Page 37 of 888 -->

SEC. 1.2 NETWORK HARDWARE 25
Subnet
Transmission
line
Brisbane
Router
Perth
Melbourne
Figure 1-10. WAN that connects three branch offices in Australia.
example, the employees might be responsible for their own computers, while the
company's IT department is in charge of the rest of the network. We will see
clearer boundaries in the coming examples, in which the network provider or tele-
phone company operates the subnet. Separation of the pure communication
aspects of the network (the subnet) from the application aspects (the hosts) greatly
simplifies the overall network design.
A second difference is that the routers will usually connect different kinds of
networking technology. The networks inside the offices may be switched Ether-
net, for example, while the long-distance transmission lines may be SONET links
(which we will cover in Chap. 2). Some device needs to join them. The astute
reader will notice that this goes beyond our definition of a network. This means
that many WANs will in fact be internetworks, or composite networks that are
made up of more than one network. We will have more to say about internet-
works in the next section.
A final difference is in what is connected to the subnet. This could be indivi-
dual computers, as was the case for connecting to LANs, or it could be entire
LANs. This is how larger networks are built from smaller ones. As far as the sub-
net is concerned, it does the same job.
We are now in a position to look at two other varieties of WANs. First, rather
than lease dedicated transmission lines, a company might connect its offices to the
Internet This allows connections to be made between the offices as virtual links


---

<a id="page-38"></a>

<!-- Page 38 of 888 -->

26 INTRODUCTION CHAP. 1
that use the underlying capacity of the Internet. This arrangement, shown in
Fig. 1-11, is called a VPN (Virtual Private Network). Compared to the dedi-
cated arrangement, a VPN has the usual advantage of virtualization, which is that
it provides flexible reuse of a resource (Internet connectivity). Consider how easy
it is to add a fourth office to see this. A VPN also has the usual disadvantage of
virtualization, which is a lack of control over the underlying resources. With a
dedicated line, the capacity is clear. With a VPN your mileage may vary with
your Internet service.
Internet
Link via the
internet Brisbane
Perth
Melbourne
Figure 1-11. WAN using a virtual private network.
The second variation is that the subnet may be run by a different company.
The subnet operator is known as a network service provider and the offices are
its customers. This structure is shown in Fig. 1-12. The subnet operator will con-
nect to other customers too, as long as they can pay and it can provide service.
Since it would be a disappointing network service if the customers could only
send packets to each other, the subnet operator will also connect to other networks
that are part of the Internet. Such a subnet operator is called an ISP (Internet
Service Provider) and the subnet is an ISP network. Its customers who connect
to the ISP receive Internet service.
We can use the ISP network to preview some key issues that we will study in
later chapters. In most WANs, the network contains many transmission lines,
each connecting a pair of routers. If two routers that do not share a transmission
line wish to communicate, they must do this indirectly, via other routers. There


---

<a id="page-39"></a>

<!-- Page 39 of 888 -->

SEC. 1.2 NETWORK HARDWARE 27
ISP network
Transmission
line
Brisbane
Customer
network
Perth
Melbourne
Figure 1-12. WAN using an ISP network.
may be many paths in the network that connect these two routers. How the net-
work makes the decision as to which path to use is called the routing algorithm.
Many such algorithms exist. How each router makes the decision as to where to
send a packet next is called the forwarding algorithm. Many of them exist too.
We will study some of both types in detail in Chap. 5.
Other kinds of WANs make heavy use of wireless technologies. In satellite
systems, each computer on the ground has an antenna through which it can send
data to and receive data from to a satellite in orbit. All computers can hear the
output from the satellite, and in some cases they can also hear the upward
transmissions of their fellow computers to the satellite as well. Satellite networks
are inherently broadcast and are most useful when the broadcast property is im-
portant.
The cellular telephone network is another example of a WAN that uses wire-
less technology. This system has already gone through three generations and a
fourth one is on the horizon. The first generation was analog and for voice only.
The second generation was digital and for voice only. The third generation is dig-
ital and is for both voice and data. Each cellular base station covers a distance
much larger than a wireless LAN, with a range measured in kilometers rather than
tens of meters. The base stations are connected to each other by a backbone net-
work that is usually wired. The data rates of cellular networks are often on the
order of 1 Mbps, much smaller than a wireless LAN that can range up to on the
order of 100 Mbps. We will have a lot to say about these networks in Chap. 2.


---

<a id="page-40"></a>

<!-- Page 40 of 888 -->

28 INTRODUCTION CHAP. 1
#### 1.2.5 Internetworks
Many networks exist in the world, often with different hardware and software.
People connected to one network often want to communicate with people attached
to a different one. The fulfillment of this desire requires that different, and fre-
quently incompatible, networks be connected. A collection of interconnected net-
works is called an internetwork or internet. These terms will be used in a gen-
eric sense, in contrast to the worldwide Internet (which is one specific internet),
which we will always capitalize. The Internet uses ISP networks to connect en-
terprise networks, home networks, and many other networks. We will look at the
Internet in great detail later in this book.
Subnets, networks, and internetworks are often confused. The term ''subnet''
makes the most sense in the context of a wide area network, where it refers to the
collection of routers and communication lines owned by the network operator. As
an analogy, the telephone system consists of telephone switching offices connect-
ed to one another by high-speed lines, and to houses and businesses by low-speed
lines. These lines and equipment, owned and managed by the telephone com-
pany, form the subnet of the telephone system. The telephones themselves (the
hosts in this analogy) are not part of the subnet.
A network is formed by the combination of a subnet and its hosts. However,
the word ''network'' is often used in a loose sense as well. A subnet might be de-
scribed as a network, as in the case of the ''ISP network'' of Fig. 1-12. An inter-
network might also be described as a network, as in the case of the WAN in
Fig. 1-10. We will follow similar practice, and if we are distinguishing a network
from other arrangements, we will stick with our original definition of a collection
of computers interconnected by a single technology.
Let us say more about what constitutes an internetwork. We know that an in-
ternet is formed when distinct networks are interconnected. In our view, connect-
ing a LAN and a WAN or connecting two LANs is the usual way to form an inter-
network, but there is little agreement in the industry over terminology in this area.
There are two rules of thumb that are useful. First, if different organizations have
paid to construct different parts of the network and each maintains its part, we
have an internetwork rather than a single network. Second, if the underlying tech-
nology is different in different parts (e.g., broadcast versus point-to-point and
wired versus wireless), we probably have an internetwork.
To go deeper, we need to talk about how two different networks can be con-
nected. The general name for a machine that makes a connection between two or
more networks and provides the necessary translation, both in terms of hardware
and software, is a gateway. Gateways are distinguished by the layer at which
they operate in the protocol hierarchy. We will have much more to say about lay-
ers and protocol hierarchies starting in the next section, but for now imagine that
higher layers are more tied to applications, such as the Web, and lower layers are
more tied to transmission links, such as Ethernet.


---

<a id="page-41"></a>

<!-- Page 41 of 888 -->

SEC. 1.2 NETWORK HARDWARE 29
Since the benefit of forming an internet is to connect computers across net-
works, we do not want to use too low-level a gateway or we will be unable to
make connections between different kinds of networks. We do not want to use
too high-level a gateway either, or the connection will only work for particular ap-
plications. The level in the middle that is ''just right'' is often called the network
layer, and a router is a gateway that switches packets at the network layer. We
can now spot an internet by finding a network that has routers.
### 1.3 NETWORK SOFTWARE
The first computer networks were designed with the hardware as the main
concern and the software as an afterthought. This strategy no longer works. Net-
work software is now highly structured. In the following sections we examine the
software structuring technique in some detail. The approach described here forms
the keystone of the entire book and will occur repeatedly later on.
#### 1.3.1 Protocol Hierarchies
To reduce their design complexity, most networks are organized as a stack of
layers or levels, each one built upon the one below it. The number of layers, the
name of each layer, the contents of each layer, and the function of each layer dif-
fer from network to network. The purpose of each layer is to offer certain ser-
vices to the higher layers while shielding those layers from the details of how the
offered services are actually implemented. In a sense, each layer is a kind of vir-
tual machine, offering certain services to the layer above it.
This concept is actually a familiar one and is used throughout computer sci-
ence, where it is variously known as information hiding, abstract data types, data
encapsulation, and object-oriented programming. The fundamental idea is that a
particular piece of software (or hardware) provides a service to its users but keeps
the details of its internal state and algorithms hidden from them.
When layer n on one machine carries on a conversation with layer n on anoth-
er machine, the rules and conventions used in this conversation are collectively
known as the layer n protocol. Basically, a protocol is an agreement between the
communicating parties on how communication is to proceed. As an analogy,
when a woman is introduced to a man, she may choose to stick out her hand. He,
in turn, may decide to either shake it or kiss it, depending, for example, on wheth-
er she is an American lawyer at a business meeting or a European princess at a
formal ball. Violating the protocol will make communication more difficult, if
not completely impossible.
A five-layer network is illustrated in Fig. 1-13. The entities comprising the
corresponding layers on different machines are called peers. The peers may be


---

<a id="page-42"></a>

<!-- Page 42 of 888 -->

30 INTRODUCTION CHAP. 1
software processes, hardware devices, or even human beings. In other words, it is
the peers that communicate by using the protocol to talk to each other.
Host 1 Host 2
Layer 5 protocol
Layer 5 Layer 5
Layer 4/5 interface
Layer 4 protocol
Layer 4 Layer 4
Layer 3/4 interface
Layer 3 protocol
Layer 3 Layer 3
Layer 2/3 interface
Layer 2 protocol
Layer 2 Layer 2
Layer 1/2 interface
Layer 1 protocol
Layer 1 Layer 1
Physical medium
Figure 1-13. Layers, protocols, and interfaces.
In reality, no data are directly transferred from layer n on one machine to
layer n on another machine. Instead, each layer passes data and control infor-
mation to the layer immediately below it, until the lowest layer is reached. Below
layer 1 is the physical medium through which actual communication occurs. In
Fig. 1-13, virtual communication is shown by dotted lines and physical communi-
cation by solid lines.
Between each pair of adjacent layers is an interface. The interface defines
which primitive operations and services the lower layer makes available to the
upper one. When network designers decide how many layers to include in a net-
work and what each one should do, one of the most important considerations is
defining clean interfaces between the layers. Doing so, in turn, requires that each
layer perform a specific collection of well-understood functions. In addition to
minimizing the amount of information that must be passed between layers, clear-
cut interfaces also make it simpler to replace one layer with a completely different
protocol or implementation (e.g., replacing all the telephone lines by satellite
channels) because all that is required of the new protocol or implementation is
that it offer exactly the same set of services to its upstairs neighbor as the old one
did. It is common that different hosts use different implementations of the same
protocol (often written by different companies). In fact, the protocol itself can
change in some layer without the layers above and below it even noticing.


---

<a id="page-43"></a>

<!-- Page 43 of 888 -->

SEC. 1.3 NETWORK SOFTWARE 31
A set of layers and protocols is called a network architecture. The specif-
ication of an architecture must contain enough information to allow an imple-
menter to write the program or build the hardware for each layer so that it will
correctly obey the appropriate protocol. Neither the details of the implementation
nor the specification of the interfaces is part of the architecture because these are
hidden away inside the machines and not visible from the outside. It is not even
necessary that the interfaces on all machines in a network be the same, provided
that each machine can correctly use all the protocols. A list of the protocols used
by a certain system, one protocol per layer, is called a protocol stack. Network
architectures, protocol stacks, and the protocols themselves are the principal sub-
jects of this book.
An analogy may help explain the idea of multilayer communication. Imagine
two philosophers (peer processes in layer 3), one of whom speaks Urdu and
English and one of whom speaks Chinese and French. Since they have no com-
mon language, they each engage a translator (peer processes at layer 2), each of
whom in turn contacts a secretary (peer processes in layer 1). Philosopher 1
wishes to convey his affection for oryctolagus cuniculus to his peer. To do so, he
passes a message (in English) across the 2/3 interface to his translator, saying ''I
like rabbits,'' as illustrated in Fig. 1-14. The translators have agreed on a neutral
language known to both of them, Dutch, so the message is converted to ''Ik vind
konijnen leuk.'' The choice of the language is the layer 2 protocol and is up to the
layer 2 peer processes.
The translator then gives the message to a secretary for transmission, for ex-
ample, by email (the layer 1 protocol). When the message arrives at the other
secretary, it is passed to the local translator, who translates it into French and
passes it across the 2/3 interface to the second philosopher. Note that each proto-
col is completely independent of the other ones as long as the interfaces are not
changed. The translators can switch from Dutch to, say, Finnish, at will, provided
that they both agree and neither changes his interface with either layer 1 or layer
3. Similarly, the secretaries can switch from email to telephone without disturb-
ing (or even informing) the other layers. Each process may add some information
intended only for its peer. This information is not passed up to the layer above.
Now consider a more technical example: how to provide communication to
the top layer of the five-layer network in Fig. 1-15. A message, M, is produced by
an application process running in layer 5 and given to layer 4 for transmission.
Layer 4 puts a header in front of the message to identify the message and passes
the result to layer 3. The header includes control information, such as addresses,
to allow layer 4 on the destination machine to deliver the message. Other ex-
amples of control information used in some layers are sequence numbers (in case
the lower layer does not preserve message order), sizes, and times.
In many networks, no limit is placed on the size of messages transmitted in
the layer 4 protocol but there is nearly always a limit imposed by the layer 3 pro-
tocol. Consequently, layer 3 must break up the incoming messages into smaller


---

<a id="page-44"></a>

<!-- Page 44 of 888 -->

32 INTRODUCTION CHAP. 1
Location A Location B
I like J'aime
Message Philosopher
rabbits bien les
lapins
3 3
Information
L: Dutch L: Dutch
for the remote Translator
Ik vind translator Ik vind
konijnen konijnen
2 2
leuk leuk
Information
Fax #--- for the remote Fax #---
L: Dutch secretary Secretary L: Dutch
Ik vind Ik vind
1 1
konijnen konijnen
leuk leuk
Figure 1-14. The philosopher-translator-secretary architecture.
units, packets, prepending a layer 3 header to each packet. In this example, M is
split into two parts, M and M , that will be transmitted separately.
1 2
Layer 3 decides which of the outgoing lines to use and passes the packets to
layer 2. Layer 2 adds to each piece not only a header but also a trailer, and gives
the resulting unit to layer 1 for physical transmission. At the receiving machine
the message moves upward, from layer to layer, with headers being stripped off as
it progresses. None of the headers for layers below n are passed up to layer n.
The important thing to understand about Fig. 1-15 is the relation between the
virtual and actual communication and the difference between protocols and inter-
faces. The peer processes in layer 4, for example, conceptually think of their
communication as being ''horizontal,'' using the layer 4 protocol. Each one is
likely to have procedures called something like SendToOtherSide and GetFrom-
OtherSide, even though these procedures actually communicate with lower layers
across the 3/4 interface, and not with the other side.


---

<a id="page-45"></a>

<!-- Page 45 of 888 -->

SEC. 1.3 NETWORK SOFTWARE 33
Layer
Layer 5 protocol
## 5 M M
Layer 4 protocol
## 4 H 4 M H 4 M
Layer 3
protocol
## 3 H H M H M H H M H M
3 4 1 3 2 3 4 1 3 2
Layer 2
protocol
2 H H H M T H H M T H H H M T H H M T
2 3 4 1 2 2 3 2 2 2 3 4 1 2 2 3 2 2

Source machine Destination machine
Figure 1-15. Example information flow supporting virtual communication in
layer 5.
The peer process abstraction is crucial to all network design. Using it, the
unmanageable task of designing the complete network can be broken into several
smaller, manageable design problems, namely, the design of the individual layers.
Although Sec. 1.3 is called ''Network Software,'' it is worth pointing out that
the lower layers of a protocol hierarchy are frequently implemented in hardware
or firmware. Nevertheless, complex protocol algorithms are involved, even if
they are embedded (in whole or in part) in hardware.
#### 1.3.2 Design Issues for the Layers
Some of the key design issues that occur in computer networks will come up
in layer after layer. Below, we will briefly mention the more important ones.
Reliability is the design issue of making a network that operates correctly
even though it is made up of a collection of components that are themselves
unreliable. Think about the bits of a packet traveling through the network. There
is a chance that some of these bits will be received damaged (inverted) due to
fluke electrical noise, random wireless signals, hardware flaws, software bugs and
so on. How is it possible that we find and fix these errors?
One mechanism for finding errors in received information uses codes for er-
ror detection. Information that is incorrectly received can then be retransmitted


---

<a id="page-46"></a>

<!-- Page 46 of 888 -->

34 INTRODUCTION CHAP. 1
until it is received correctly. More powerful codes allow for error correction,
where the correct message is recovered from the possibly incorrect bits that were
originally received. Both of these mechanisms work by adding redundant infor-
mation. They are used at low layers, to protect packets sent over individual links,
and high layers, to check that the right contents were received.
Another reliability issue is finding a working path through a network. Often
there are multiple paths between a source and destination, and in a large network,
there may be some links or routers that are broken. Suppose that the network is
down in Germany. Packets sent from London to Rome via Germany will not get
through, but we could instead send packets from London to Rome via Paris. The
network should automatically make this decision. This topic is called routing.
A second design issue concerns the evolution of the network. Over time, net-
works grow larger and new designs emerge that need to be connected to the exist-
ing network. We have recently seen the key structuring mechanism used to sup-
port change by dividing the overall problem and hiding implementation details:
protocol layering. There are many other strategies as well.
Since there are many computers on the network, every layer needs a mechan-
ism for identifying the senders and receivers that are involved in a particular mes-
sage. This mechanism is called addressing or naming, in the low and high lay-
ers, respectively.
An aspect of growth is that different network technologies often have dif-
ferent limitations. For example, not all communication channels preserve the
order of messages sent on them, leading to solutions that number messages. An-
other example is differences in the maximum size of a message that the networks
can transmit. This leads to mechanisms for disassembling, transmitting, and then
reassembling messages. This overall topic is called internetworking .
When networks get large, new problems arise. Cities can have traffic jams, a
shortage of telephone numbers, and it is easy to get lost. Not many people have
these problems in their own neighborhood, but citywide they may be a big issue.
Designs that continue to work well when the network gets large are said to be
scalable.
A third design issue is resource allocation. Networks provide a service to
hosts from their underlying resources, such as the capacity of transmission lines.
To do this well, they need mechanisms that divide their resources so that one host
does not interfere with another too much.
Many designs share network bandwidth dynamically, according to the short-
term needs of hosts, rather than by giving each host a fixed fraction of the band-
width that it may or may not use. This design is called statistical multiplexing,
meaning sharing based on the statistics of demand. It can be applied at low layers
for a single link, or at high layers for a network or even applications that use the
network.
An allocation problem that occurs at every level is how to keep a fast sender
from swamping a slow receiver with data. Feedback from the receiver to the


---

<a id="page-47"></a>

<!-- Page 47 of 888 -->

SEC. 1.3 NETWORK SOFTWARE 35
sender is often used. This subject is called flow control. Sometimes the problem
is that the network is oversubscribed because too many computers want to send
too much traffic, and the network cannot deliver it all. This overloading of the
network is called congestion. One strategy is for each computer to reduce its de-
mand when it experiences congestion. It, too, can be used in all layers.
It is interesting to observe that the network has more resources to offer than
simply bandwidth. For uses such as carrying live video, the timeliness of delivery
matters a great deal. Most networks must provide service to applications that want
this real-time delivery at the same time that they provide service to applications
that want high throughput. Quality of service is the name given to mechanisms
that reconcile these competing demands.
The last major design issue is to secure the network by defending it against
different kinds of threats. One of the threats we have mentioned previously is that
of eavesdropping on communications. Mechanisms that provide confidentiality
defend against this threat, and they are used in multiple layers. Mechanisms for
authentication prevent someone from impersonating someone else. They might
be used to tell fake banking Web sites from the real one, or to let the cellular net-
work check that a call is really coming from your phone so that you will pay the
bill. Other mechanisms for integrity prevent surreptitious changes to messages,
such as altering ''debit my account $10'' to ''debit my account $1000.'' All of
these designs are based on cryptography, which we shall study in Chap. 8.
#### 1.3.3 Connection-Oriented Versus Connectionless Service
Layers can offer two different types of service to the layers above them: con-
nection-oriented and connectionless. In this section we will look at these two
types and examine the differences between them.
Connection-oriented service is modeled after the telephone system. To talk
to someone, you pick up the phone, dial the number, talk, and then hang up. Simi-
larly, to use a connection-oriented network service, the service user first estab-
lishes a connection, uses the connection, and then releases the connection. The
essential aspect of a connection is that it acts like a tube: the sender pushes objects
(bits) in at one end, and the receiver takes them out at the other end. In most
cases the order is preserved so that the bits arrive in the order they were sent.
In some cases when a connection is established, the sender, receiver, and sub-
net conduct a negotiation about the parameters to be used, such as maximum
message size, quality of service required, and other issues. Typically, one side
makes a proposal and the other side can accept it, reject it, or make a counter-
proposal. A circuit is another name for a connection with associated resources,
such as a fixed bandwidth. This dates from the telephone network in which a cir-
cuit was a path over copper wire that carried a phone conversation.
In contrast to connection-oriented service, connectionless service is modeled
after the postal system. Each message (letter) carries the full destination address,


---

<a id="page-48"></a>

<!-- Page 48 of 888 -->

36 INTRODUCTION CHAP. 1
and each one is routed through the intermediate nodes inside the system indepen-
dent of all the subsequent messages. There are different names for messages in
different contexts; a packet is a message at the network layer. When the inter-
mediate nodes receive a message in full before sending it on to the next node, this
is called store-and-forward switching. The alternative, in which the onward
transmission of a message at a node starts before it is completely received by the
node, is called cut-through switching. Normally, when two messages are sent to
the same destination, the first one sent will be the first one to arrive. However, it
is possible that the first one sent can be delayed so that the second one arrives
first.
Each kind of service can further be characterized by its reliability. Some ser-
vices are reliable in the sense that they never lose data. Usually, a reliable service
is implemented by having the receiver acknowledge the receipt of each message
so the sender is sure that it arrived. The acknowledgement process introduces
overhead and delays, which are often worth it but are sometimes undesirable.
A typical situation in which a reliable connection-oriented service is appropri-
ate is file transfer. The owner of the file wants to be sure that all the bits arrive
correctly and in the same order they were sent. Very few file transfer customers
would prefer a service that occasionally scrambles or loses a few bits, even if it is
much faster.
Reliable connection-oriented service has two minor variations: message se-
quences and byte streams. In the former variant, the message boundaries are pre-
served. When two 1024-byte messages are sent, they arrive as two distinct 1024-
byte messages, never as one 2048-byte message. In the latter, the connection is
simply a stream of bytes, with no message boundaries. When 2048 bytes arrive at
the receiver, there is no way to tell if they were sent as one 2048-byte message,
two 1024-byte messages, or 2048 1-byte messages. If the pages of a book are sent
over a network to a phototypesetter as separate messages, it might be important to
preserve the message boundaries. On the other hand, to download a DVD movie,
a byte stream from the server to the user's computer is all that is needed. Mes-
sage boundaries within the movie are not relevant.
For some applications, the transit delays introduced by acknowledgements are
unacceptable. One such application is digitized voice traffic for voice over IP. It
is less disruptive for telephone users to hear a bit of noise on the line from time to
time than to experience a delay waiting for acknowledgements. Similarly, when
transmitting a video conference, having a few pixels wrong is no problem, but
having the image jerk along as the flow stops and starts to correct errors is irritat-
ing.
Not all applications require connections. For example, spammers send elec-
tronic junk-mail to many recipients. The spammer probably does not want to go
to the trouble of setting up and later tearing down a connection to a recipient just
to send them one item. Nor is 100 percent reliable delivery essential, especially if
it costs more. All that is needed is a way to send a single message that has a high


---

<a id="page-49"></a>

<!-- Page 49 of 888 -->

SEC. 1.3 NETWORK SOFTWARE 37
probability of arrival, but no guarantee. Unreliable (meaning not acknowledged)
connectionless service is often called datagram service, in analogy with telegram
service, which also does not return an acknowledgement to the sender. Despite it
being unreliable, it is the dominant form in most networks for reasons that will
become clear later
In other situations, the convenience of not having to establish a connection to
send one message is desired, but reliability is essential. The acknowledged
datagram service can be provided for these applications. It is like sending a reg-
istered letter and requesting a return receipt. When the receipt comes back, the
sender is absolutely sure that the letter was delivered to the intended party and not
lost along the way. Text messaging on mobile phones is an example.
Still another service is the request-reply service. In this service the sender
transmits a single datagram containing a request; the reply contains the answer.
Request-reply is commonly used to implement communication in the client-server
model: the client issues a request and the server responds to it. For example, a
mobile phone client might send a query to a map server to retrieve the map data
for the current location. Figure 1-16 summarizes the types of services discussed
above.
Service Example
Reliable message stream Sequence of pages
Connection-
oriented
Reliable byte stream Movie download
Unreliable connection Voice over IP
Unreliable datagram Electronic junk mail
Connection-
Acknowledged datagram Text messaging
less
Request-reply Database query
Figure 1-16. Six different types of service.
The concept of using unreliable communication may be confusing at first.
After all, why would anyone actually prefer unreliable communication to reliable
communication? First of all, reliable communication (in our sense, that is,
acknowledged) may not be available in a given layer. For example, Ethernet does
not provide reliable communication. Packets can occasionally be damaged in
transit. It is up to higher protocol levels to recover from this problem. In particu-
lar, many reliable services are built on top of an unreliable datagram service. Sec-
ond, the delays inherent in providing a reliable service may be unacceptable, espe-
cially in real-time applications such as multimedia. For these reasons, both reli-
able and unreliable communication coexist.


---

<a id="page-50"></a>

<!-- Page 50 of 888 -->

38 INTRODUCTION CHAP. 1
#### 1.3.4 Service Primitives
A service is formally specified by a set of primitives (operations) available to
user processes to access the service. These primitives tell the service to perform
some action or report on an action taken by a peer entity. If the protocol stack is
located in the operating system, as it often is, the primitives are normally system
calls. These calls cause a trap to kernel mode, which then turns control of the ma-
chine over to the operating system to send the necessary packets.
The set of primitives available depends on the nature of the service being pro-
vided. The primitives for connection-oriented service are different from those of
connectionless service. As a minimal example of the service primitives that
might provide a reliable byte stream, consider the primitives listed in Fig. 1-17.
They will be familiar to fans of the Berkeley socket interface, as the primitives are
a simplified version of that interface.
Primitive Meaning
LISTEN Block waiting for an incoming connection
CONNECT Establish a connection with a waiting peer
ACCEPT Accept an incoming connection from a peer
RECEIVE Block waiting for an incoming message
SEND Send a message to the peer
DISCONNECT Terminate a connection
Figure 1-17. Six service primitives that provide a simple connection-oriented
service.
These primitives might be used for a request-reply interaction in a client-ser-
ver environment. To illustrate how, We sketch a simple protocol that implements
the service using acknowledged datagrams.
First, the server executes LISTEN to indicate that it is prepared to accept in-
coming connections. A common way to implement LISTEN is to make it a block-
ing system call. After executing the primitive, the server process is blocked until
a request for connection appears.
Next, the client process executes CONNECT to establish a connection with the
server. The CONNECT call needs to specify who to connect to, so it might have a
parameter giving the server's address. The operating system then typically sends
a packet to the peer asking it to connect, as shown by (1) in Fig. 1-18. The client
process is suspended until there is a response.
When the packet arrives at the server, the operating system sees that the pack-
et is requesting a connection. It checks to see if there is a listener, and if so it
unblocks the listener. The server process can then establish the connection with
the ACCEPT call. This sends a response (2) back to the client process to accept the


---

<a id="page-51"></a>

<!-- Page 51 of 888 -->

SEC. 1.3 NETWORK SOFTWARE 39
Client machine Server machine
(1) Connect request
Client (2) Accept response
process
System
(3) Request for data
process
(4) Reply
System
calls
(5) Disconnect
Operating Protocol Protocol
Kernel Drivers (6) Disconnect Kernel Drivers
system stack stack
Figure 1-18. A simple client-server interaction using acknowledged datagrams.
connection. The arrival of this response then releases the client. At this point the
client and server are both running and they have a connection established.
The obvious analogy between this protocol and real life is a customer (client)
calling a company's customer service manager. At the start of the day, the service
manager sits next to his telephone in case it rings. Later, a client places a call.
When the manager picks up the phone, the connection is established.
The next step is for the server to execute RECEIVE to prepare to accept the first
request. Normally, the server does this immediately upon being released from the
LISTEN, before the acknowledgement can get back to the client. The RECEIVE call
blocks the server.
Then the client executes SEND to transmit its request (3) followed by the ex-
ecution of RECEIVE to get the reply. The arrival of the request packet at the server
machine unblocks the server so it can handle the request. After it has done the
work, the server uses SEND to return the answer to the client (4). The arrival of
this packet unblocks the client, which can now inspect the answer. If the client
has additional requests, it can make them now.
When the client is done, it executes DISCONNECT to terminate the connection
(5). Usually, an initial DISCONNECT is a blocking call, suspending the client and
sending a packet to the server saying that the connection is no longer needed.
When the server gets the packet, it also issues a DISCONNECT of its own, ack-
nowledging the client and releasing the connection (6). When the server's packet
gets back to the client machine, the client process is released and the connection is
broken. In a nutshell, this is how connection-oriented communication works.
Of course, life is not so simple. Many things can go wrong here. The timing
can be wrong (e.g., the CONNECT is done before the LISTEN), packets can get lost,
and much more. We will look at these issues in great detail later, but for the
moment, Fig. 1-18 briefly summarizes how client-server communication might
work with acknowledged datagrams so that we can ignore lost packets.
Given that six packets are required to complete this protocol, one might
wonder why a connectionless protocol is not used instead. The answer is that in a
perfect world it could be, in which case only two packets would be needed: one


---

<a id="page-52"></a>

<!-- Page 52 of 888 -->

40 INTRODUCTION CHAP. 1
for the request and one for the reply. However, in the face of large messages in
either direction (e.g., a megabyte file), transmission errors, and lost packets, the
situation changes. If the reply consisted of hundreds of packets, some of which
could be lost during transmission, how would the client know if some pieces were
missing? How would the client know whether the last packet actually received
was really the last packet sent? Suppose the client wanted a second file. How
could it tell packet 1 from the second file from a lost packet 1 from the first file
that suddenly found its way to the client? In short, in the real world, a simple re-
quest-reply protocol over an unreliable network is often inadequate. In Chap. 3
we will study a variety of protocols in detail that overcome these and other prob-
lems. For the moment, suffice it to say that having a reliable, ordered byte stream
between processes is sometimes very convenient.
#### 1.3.5 The Relationship of Services to Protocols
Services and protocols are distinct concepts. This distinction is so important
that we emphasize it again here. A service is a set of primitives (operations) that
a layer provides to the layer above it. The service defines what operations the
layer is prepared to perform on behalf of its users, but it says nothing at all about
how these operations are implemented. A service relates to an interface between
two layers, with the lower layer being the service provider and the upper layer
being the service user.
A protocol, in contrast, is a set of rules governing the format and meaning of
the packets, or messages that are exchanged by the peer entities within a layer.
Entities use protocols to implement their service definitions. They are free to
change their protocols at will, provided they do not change the service visible to
their users. In this way, the service and the protocol are completely decoupled.
This is a key concept that any network designer should understand well.
To repeat this crucial point, services relate to the interfaces between layers, as
illustrated in Fig. 1-19. In contrast, protocols relate to the packets sent between
peer entities on different machines. It is very important not to confuse the two
concepts.
An analogy with programming languages is worth making. A service is like
an abstract data type or an object in an object-oriented language. It defines opera-
tions that can be performed on an object but does not specify how these operations
are implemented. In contrast, a protocol relates to the implementation of the ser-
vice and as such is not visible to the user of the service.
Many older protocols did not distinguish the service from the protocol. In ef-
fect, a typical layer might have had a service primitive SEND PACKET with the user
providing a pointer to a fully assembled packet. This arrangement meant that all
changes to the protocol were immediately visible to the users. Most network de-
signers now regard such a design as a serious blunder.


---

<a id="page-53"></a>

<!-- Page 53 of 888 -->

SEC. 1.4 REFERENCE MODELS 41
Layer k + 1 Layer k + 1
Service provided by layer k
Protocol
Layer k Layer k
Layer k - 1 Layer k - 1
Figure 1-19. The relationship between a service and a protocol.
### 1.4 REFERENCE MODELS
Now that we have discussed layered networks in the abstract, it is time to look
at some examples. We will discuss two important network architectures: the OSI
reference model and the TCP/IP reference model. Although the protocols associ-
ated with the OSI model are not used any more, the model itself is actually quite
general and still valid, and the features discussed at each layer are still very im-
portant. The TCP/IP model has the opposite properties: the model itself is not of
much use but the protocols are widely used. For this reason we will look at both
of them in detail. Also, sometimes you can learn more from failures than from
successes.
#### 1.4.1 The OSI Reference Model
The OSI model (minus the physical medium) is shown in Fig. 1-20. This
model is based on a proposal developed by the International Standards Organiza-
tion (ISO) as a first step toward international standardization of the protocols used
in the various layers (Day and Zimmermann, 1983). It was revised in 1995 (Day,
1995). The model is called the ISO OSI (Open Systems Interconnection) Ref-
erence Model because it deals with connecting open systems-that is, systems
that are open for communication with other systems. We will just call it the OSI
model for short.
The OSI model has seven layers. The principles that were applied to arrive at
the seven layers can be briefly summarized as follows:
1. A layer should be created where a different abstraction is needed.
2. Each layer should perform a well-defined function.
3. The function of each layer should be chosen with an eye toward
defining internationally standardized protocols.


---

<a id="page-54"></a>

<!-- Page 54 of 888 -->

42 INTRODUCTION CHAP. 1
Layer Name of unit
exchanged
Application protocol
7 Application Application APDU
Interface
Presentation protocol
6 Presentation Presentation PPDU
Session protocol
5 Session Session SPDU
Transport protocol
4 Transport Transport TPDU
Communication subnet boundary
Internal subnet protocol
3 Network Network Network Network Packet
2 Data link Data link Data link Data link Frame
1 Physical Physical Physical Physical Bit
Host A Router Router Host B
Network layer host-router protocol
Data link layer host-router protocol
Physical layer host-router protocol
Figure 1-20. The OSI reference model.
4. The layer boundaries should be chosen to minimize the information
flow across the interfaces.
5. The number of layers should be large enough that distinct functions
need not be thrown together in the same layer out of necessity and
small enough that the architecture does not become unwieldy.
Below we will discuss each layer of the model in turn, starting at the bottom
layer. Note that the OSI model itself is not a network architecture because it does
not specify the exact services and protocols to be used in each layer. It just tells
what each layer should do. However, ISO has also produced standards for all the
layers, although these are not part of the reference model itself. Each one has
been published as a separate international standard. The model (in part) is widely
used although the associated protocols have been long forgotten.


---

<a id="page-55"></a>

<!-- Page 55 of 888 -->

SEC. 1.4 REFERENCE MODELS 43
The Physical Layer
The physical layer is concerned with transmitting raw bits over a communi-
cation channel. The design issues have to do with making sure that when one side
sends a 1 bit it is received by the other side as a 1 bit, not as a 0 bit. Typical ques-
tions here are what electrical signals should be used to represent a 1 and a 0, how
many nanoseconds a bit lasts, whether transmission may proceed simultaneously
in both directions, how the initial connection is established, how it is torn down
when both sides are finished, how many pins the network connector has, and what
each pin is used for. These design issues largely deal with mechanical, electrical,
and timing interfaces, as well as the physical transmission medium, which lies
below the physical layer.
The Data Link Layer
The main task of the data link layer is to transform a raw transmission facil-
ity into a line that appears free of undetected transmission errors. It does so by
masking the real errors so the network layer does not see them. It accomplishes
this task by having the sender break up the input data into data frames (typically
a few hundred or a few thousand bytes) and transmit the frames sequentially. If
the service is reliable, the receiver confirms correct receipt of each frame by send-
ing back an acknowledgement frame.
Another issue that arises in the data link layer (and most of the higher layers
as well) is how to keep a fast transmitter from drowning a slow receiver in data.
Some traffic regulation mechanism may be needed to let the transmitter know
when the receiver can accept more data.
Broadcast networks have an additional issue in the data link layer: how to
control access to the shared channel. A special sublayer of the data link layer, the
medium access control sublayer, deals with this problem.
The Network Layer
The network layer controls the operation of the subnet. A key design issue is
determining how packets are routed from source to destination. Routes can be
based on static tables that are ''wired into'' the network and rarely changed, or
more often they can be updated automatically to avoid failed components. They
can also be determined at the start of each conversation, for example, a terminal
session, such as a login to a remote machine. Finally, they can be highly dynam-
ic, being determined anew for each packet to reflect the current network load.
If too many packets are present in the subnet at the same time, they will get in
one another's way, forming bottlenecks. Handling congestion is also a responsi-
bility of the network layer, in conjunction with higher layers that adapt the load


---

<a id="page-56"></a>

<!-- Page 56 of 888 -->

44 INTRODUCTION CHAP. 1
they place on the network. More generally, the quality of service provided (delay,
transit time, jitter, etc.) is also a network layer issue.
When a packet has to travel from one network to another to get to its destina-
tion, many problems can arise. The addressing used by the second network may
be different from that used by the first one. The second one may not accept the
packet at all because it is too large. The protocols may differ, and so on. It is up
to the network layer to overcome all these problems to allow heterogeneous net-
works to be interconnected.
In broadcast networks, the routing problem is simple, so the network layer is
often thin or even nonexistent.
The Transport Layer
The basic function of the transport layer is to accept data from above it, split
it up into smaller units if need be, pass these to the network layer, and ensure that
the pieces all arrive correctly at the other end. Furthermore, all this must be done
efficiently and in a way that isolates the upper layers from the inevitable changes
in the hardware technology over the course of time.
The transport layer also determines what type of service to provide to the ses-
sion layer, and, ultimately, to the users of the network. The most popular type of
transport connection is an error-free point-to-point channel that delivers messages
or bytes in the order in which they were sent. However, other possible kinds of
transport service exist, such as the transporting of isolated messages with no guar-
antee about the order of delivery, and the broadcasting of messages to multiple
destinations. The type of service is determined when the connection is esta-
blished. (As an aside, an error-free channel is completely impossible to achieve;
what people really mean by this term is that the error rate is low enough to ignore
in practice.)
The transport layer is a true end-to-end layer; it carries data all the way from
the source to the destination. In other words, a program on the source machine
carries on a conversation with a similar program on the destination machine, using
the message headers and control messages. In the lower layers, each protocols is
between a machine and its immediate neighbors, and not between the ultimate
source and destination machines, which may be separated by many routers. The
difference between layers 1 through 3, which are chained, and layers 4 through 7,
which are end-to-end, is illustrated in Fig. 1-20.
The Session Layer
The session layer allows users on different machines to establish sessions be-
tween them. Sessions offer various services, including dialog control (keeping
track of whose turn it is to transmit), token management (preventing two parties
from attempting the same critical operation simultaneously), and synchronization


---

<a id="page-57"></a>

<!-- Page 57 of 888 -->

SEC. 1.4 REFERENCE MODELS 45
(checkpointing long transmissions to allow them to pick up from where they left
off in the event of a crash and subsequent recovery).
The Presentation Layer
Unlike the lower layers, which are mostly concerned with moving bits around,
the presentation layer is concerned with the syntax and semantics of the infor-
mation transmitted. In order to make it possible for computers with different in-
ternal data representations to communicate, the data structures to be exchanged
can be defined in an abstract way, along with a standard encoding to be used ''on
the wire.'' The presentation layer manages these abstract data structures and al-
lows higher-level data structures (e.g., banking records) to be defined and
exchanged.
The Application Layer
The application layer contains a variety of protocols that are commonly
needed by users. One widely used application protocol is HTTP (HyperText
Transfer Protocol), which is the basis for the World Wide Web. When a
browser wants a Web page, it sends the name of the page it wants to the server
hosting the page using HTTP. The server then sends the page back. Other appli-
cation protocols are used for file transfer, electronic mail, and network news.
#### 1.4.2 The TCP/IP Reference Model
Let us now turn from the OSI reference model to the reference model used in
the grandparent of all wide area computer networks, the ARPANET, and its suc-
cessor, the worldwide Internet. Although we will give a brief history of the
ARPANET later, it is useful to mention a few key aspects of it now. The
ARPANET was a research network sponsored by the DoD (U.S. Department of
Defense). It eventually connected hundreds of universities and government instal-
lations, using leased telephone lines. When satellite and radio networks were
added later, the existing protocols had trouble interworking with them, so a new
reference architecture was needed. Thus, from nearly the beginning, the ability to
connect multiple networks in a seamless way was one of the major design goals.
This architecture later became known as the TCP/IP Reference Model, after its
two primary protocols. It was first described by Cerf and Kahn (1974), and later
refined and defined as a standard in the Internet community (Braden, 1989). The
design philosophy behind the model is discussed by Clark (1988).
Given the DoD's worry that some of its precious hosts, routers, and internet-
work gateways might get blown to pieces at a moment's notice by an attack from
the Soviet Union, another major goal was that the network be able to survive loss
of subnet hardware, without existing conversations being broken off. In other


---

<a id="page-58"></a>

<!-- Page 58 of 888 -->

46 INTRODUCTION CHAP. 1
words, the DoD wanted connections to remain intact as long as the source and
destination machines were functioning, even if some of the machines or transmis-
sion lines in between were suddenly put out of operation. Furthermore, since ap-
plications with divergent requirements were envisioned, ranging from transferring
files to real-time speech transmission, a flexible architecture was needed.
The Link Layer
All these requirements led to the choice of a packet-switching network based
on a connectionless layer that runs across different networks. The lowest layer in
the model, the link layer describes what links such as serial lines and classic Eth-
ernet must do to meet the needs of this connectionless internet layer. It is not
really a layer at all, in the normal sense of the term, but rather an interface be-
tween hosts and transmission links. Early material on the TCP/IP model has little
to say about it.
The Internet Layer
The internet layer is the linchpin that holds the whole architecture together.
It is shown in Fig. 1-21 as corresponding roughly to the OSI network layer. Its
job is to permit hosts to inject packets into any network and have them travel in-
dependently to the destination (potentially on a different network). They may
even arrive in a completely different order than they were sent, in which case it is
the job of higher layers to rearrange them, if in-order delivery is desired. Note
that ''internet'' is used here in a generic sense, even though this layer is present in
the Internet.
OSI TCP/IP
7 Application Application
6 Presentation
Not present
in the model
5 Session
4 Transport Transport
3 Network Internet
2 Data link Link
1 Physical
Figure 1-21. The TCP/IP reference model.
The analogy here is with the (snail) mail system. A person can drop a se-
quence of international letters into a mailbox in one country, and with a little luck,


---

<a id="page-59"></a>

<!-- Page 59 of 888 -->

SEC. 1.4 REFERENCE MODELS 47
most of them will be delivered to the correct address in the destination country.
The letters will probably travel through one or more international mail gateways
along the way, but this is transparent to the users. Furthermore, that each country
(i.e., each network) has its own stamps, preferred envelope sizes, and delivery
rules is hidden from the users.
The internet layer defines an official packet format and protocol called IP
(Internet Protocol), plus a companion protocol called ICMP (Internet Control
Message Protocol) that helps it function. The job of the internet layer is to
deliver IP packets where they are supposed to go. Packet routing is clearly a
major issue here, as is congestion (though IP has not proven effective at avoiding
congestion).
The Transport Layer
The layer above the internet layer in the TCP/IP model is now usually called
the transport layer. It is designed to allow peer entities on the source and desti-
nation hosts to carry on a conversation, just as in the OSI transport layer. Two
end-to-end transport protocols have been defined here. The first one, TCP
(Transmission Control Protocol), is a reliable connection-oriented protocol that
allows a byte stream originating on one machine to be delivered without error on
any other machine in the internet. It segments the incoming byte stream into
discrete messages and passes each one on to the internet layer. At the destination,
the receiving TCP process reassembles the received messages into the output
stream. TCP also handles flow control to make sure a fast sender cannot swamp a
slow receiver with more messages than it can handle.
The second protocol in this layer, UDP (User Datagram Protocol), is an
unreliable, connectionless protocol for applications that do not want TCP's
sequencing or flow control and wish to provide their own. It is also widely used
for one-shot, client-server-type request-reply queries and applications in which
prompt delivery is more important than accurate delivery, such as transmitting
speech or video. The relation of IP, TCP, and UDP is shown in Fig. 1-22. Since
the model was developed, IP has been implemented on many other networks.
The Application Layer
The TCP/IP model does not have session or presentation layers. No need for
them was perceived. Instead, applications simply include any session and pres-
entation functions that they require. Experience with the OSI model has proven
this view correct: these layers are of little use to most applications.
On top of the transport layer is the application layer. It contains all the high-
er-level protocols. The early ones included virtual terminal (TELNET), file trans-
fer (FTP), and electronic mail (SMTP). Many other protocols have been added to
these over the years. Some important ones that we will study, shown in Fig. 1-22,


---

<a id="page-60"></a>

<!-- Page 60 of 888 -->

48 INTRODUCTION CHAP. 1
Application HTTP SMTP RTP DNS
Transport TCP UDP
Layers Protocols
Internet IP ICMP
Link DSL SONET 802.11 Ethernet
Figure 1-22. The TCP/IP model with some protocols we will study.
include the Domain Name System (DNS), for mapping host names onto their net-
work addresses, HTTP, the protocol for fetching pages on the World Wide Web,
and RTP, the protocol for delivering real-time media such as voice or movies.
#### 1.4.3 The Model Used in This Book
As mentioned earlier, the strength of the OSI reference model is the model it-
self (minus the presentation and session layers), which has proven to be ex-
ceptionally useful for discussing computer networks. In contrast, the strength of
the TCP/IP reference model is the protocols, which have been widely used for
many years. Since computer scientists like to have their cake and eat it, too, we
will use the hybrid model of Fig. 1-23 as the framework for this book.
5 Application
4 Transport
3 Network
2 Link
1 Physical
Figure 1-23. The reference model used in this book.
This model has five layers, running from the physical layer up through the
link, network and transport layers to the application layer. The physical layer
specifies how to transmit bits across different kinds of media as electrical (or
other analog) signals. The link layer is concerned with how to send finite-length
messages between directly connected computers with specified levels of reliabil-
ity. Ethernet and 802.11 are examples of link layer protocols.


---

<a id="page-61"></a>

<!-- Page 61 of 888 -->

SEC. 1.4 REFERENCE MODELS 49
The network layer deals with how to combine multiple links into networks,
and networks of networks, into internetworks so that we can send packets between
distant computers. This includes the task of finding the path along which to send
the packets. IP is the main example protocol we will study for this layer. The
transport layer strengthens the delivery guarantees of the Network layer, usually
with increased reliability, and provide delivery abstractions, such as a reliable
byte stream, that match the needs of different applications. TCP is an important
example of a transport layer protocol.
Finally, the application layer contains programs that make use of the network.
Many, but not all, networked applications have user interfaces, such as a Web
browser. Our concern, however, is with the portion of the program that uses the
network. This is the HTTP protocol in the case of the Web browser. There are
also important support programs in the application layer, such as the DNS, that
are used by many applications.
Our chapter sequence is based on this model. In this way, we retain the value
of the OSI model for understanding network architectures, but concentrate pri-
marily on protocols that are important in practice, from TCP/IP and related proto-
cols to newer ones such as 802.11, SONET, and Bluetooth.
#### 1.4.4 A Comparison of the OSI and TCP/IP Reference Models
The OSI and TCP/IP reference models have much in common. Both are
based on the concept of a stack of independent protocols. Also, the functionality
of the layers is roughly similar. For example, in both models the layers up
through and including the transport layer are there to provide an end-to-end, net-
work-independent transport service to processes wishing to communicate. These
layers form the transport provider. Again in both models, the layers above tran-
sport are application-oriented users of the transport service.
Despite these fundamental similarities, the two models also have many dif-
ferences. In this section we will focus on the key differences between the two ref-
erence models. It is important to note that we are comparing the reference models
here, not the corresponding protocol stacks. The protocols themselves will be dis-
cussed later. For an entire book comparing and contrasting TCP/IP and OSI, see
Piscitello and Chapin (1993).
Three concepts are central to the OSI model:
1. Services.
2. Interfaces.
3. Protocols.
Probably the biggest contribution of the OSI model is that it makes the distinction
between these three concepts explicit. Each layer performs some services for the


---

<a id="page-62"></a>

<!-- Page 62 of 888 -->

50 INTRODUCTION CHAP. 1
layer above it. The service definition tells what the layer does, not how entities
above it access it or how the layer works. It defines the layer's semantics.
A layer's interface tells the processes above it how to access it. It specifies
what the parameters are and what results to expect. It, too, says nothing about
how the layer works inside.
Finally, the peer protocols used in a layer are the layer's own business. It can
use any protocols it wants to, as long as it gets the job done (i.e., provides the
offered services). It can also change them at will without affecting software in
higher layers.
These ideas fit very nicely with modern ideas about object-oriented pro-
gramming. An object, like a layer, has a set of methods (operations) that proc-
esses outside the object can invoke. The semantics of these methods define the set
of services that the object offers. The methods' parameters and results form the
object's interface. The code internal to the object is its protocol and is not visible
or of any concern outside the object.
The TCP/IP model did not originally clearly distinguish between services, in-
terfaces, and protocols, although people have tried to retrofit it after the fact to
make it more OSI-like. For example, the only real services offered by the internet
layer are SEND IP PACKET and RECEIVE IP PACKET. As a consequence, the proto-
cols in the OSI model are better hidden than in the TCP/IP model and can be
replaced relatively easily as the technology changes. Being able to make such
changes transparently is one of the main purposes of having layered protocols in
the first place.
The OSI reference model was devised before the corresponding protocols
were invented. This ordering meant that the model was not biased toward one
particular set of protocols, a fact that made it quite general. The downside of this
ordering was that the designers did not have much experience with the subject and
did not have a good idea of which functionality to put in which layer.
For example, the data link layer originally dealt only with point-to-point net-
works. When broadcast networks came around, a new sublayer had to be hacked
into the model. Furthermore, when people started to build real networks using the
OSI model and existing protocols, it was discovered that these networks did not
match the required service specifications (wonder of wonders), so convergence
sublayers had to be grafted onto the model to provide a place for papering over
the differences. Finally, the committee originally expected that each country
would have one network, run by the government and using the OSI protocols, so
no thought was given to internetworking. To make a long story short, things did
not turn out that way.
With TCP/IP the reverse was true: the protocols came first, and the model was
really just a description of the existing protocols. There was no problem with the
protocols fitting the model. They fit perfectly. The only trouble was that the
model did not fit any other protocol stacks. Consequently, it was not especially
useful for describing other, non-TCP/IP networks.


---

<a id="page-63"></a>

<!-- Page 63 of 888 -->

SEC. 1.4 REFERENCE MODELS 51
Turning from philosophical matters to more specific ones, an obvious dif-
ference between the two models is the number of layers: the OSI model has seven
layers and the TCP/IP model has four. Both have (inter)network, transport, and
application layers, but the other layers are different.
Another difference is in the area of connectionless versus connection-oriented
communication. The OSI model supports both connectionless and connection-
oriented communication in the network layer, but only connection-oriented com-
munication in the transport layer, where it counts (because the transport service is
visible to the users). The TCP/IP model supports only one mode in the network
layer (connectionless) but both in the transport layer, giving the users a choice.
This choice is especially important for simple request-response protocols.
#### 1.4.5 A Critique of the OSI Model and Protocols
Neither the OSI model and its protocols nor the TCP/IP model and its proto-
cols are perfect. Quite a bit of criticism can be, and has been, directed at both of
them. In this section and the next one, we will look at some of these criticisms.
We will begin with OSI and examine TCP/IP afterward.
At the time the second edition of this book was published (1989), it appeared
to many experts in the field that the OSI model and its protocols were going to
take over the world and push everything else out of their way. This did not hap-
pen. Why? A look back at some of the reasons may be useful. They can be sum-
marized as:
1. Bad timing.
2. Bad technology.
3. Bad implementations.
4. Bad politics.
Bad Timing
First let us look at reason one: bad timing. The time at which a standard is
established is absolutely critical to its success. David Clark of M.I.T. has a theory
of standards that he calls the apocalypse of the two elephants, which is illustrated
in Fig. 1-24.
This figure shows the amount of activity surrounding a new subject. When
the subject is first discovered, there is a burst of research activity in the form of
discussions, papers, and meetings. After a while this activity subsides, corpora-
tions discover the subject, and the billion-dollar wave of investment hits.
It is essential that the standards be written in the trough in between the two
''elephants.'' If they are written too early (before the research results are well


---

<a id="page-64"></a>

<!-- Page 64 of 888 -->

52 INTRODUCTION CHAP. 1
Time
ytivitcA
Billion dollar
Research investment
Standards
Figure 1-24. The apocalypse of the two elephants.
established), the subject may still be poorly understood; the result is a bad stan-
dard. If they are written too late, so many companies may have already made ma-
jor investments in different ways of doing things that the standards are effectively
ignored. If the interval between the two elephants is very short (because everyone
is in a hurry to get started), the people developing the standards may get crushed.
It now appears that the standard OSI protocols got crushed. The competing
TCP/IP protocols were already in widespread use by research universities by the
time the OSI protocols appeared. While the billion-dollar wave of investment had
not yet hit, the academic market was large enough that many vendors had begun
cautiously offering TCP/IP products. When OSI came around, they did not want
to support a second protocol stack until they were forced to, so there were no ini-
tial offerings. With every company waiting for every other company to go first,
no company went first and OSI never happened.
Bad Technology
The second reason that OSI never caught on is that both the model and the
protocols are flawed. The choice of seven layers was more political than techni-
cal, and two of the layers (session and presentation) are nearly empty, whereas
two other ones (data link and network) are overfull.
The OSI model, along with its associated service definitions and protocols, is
extraordinarily complex. When piled up, the printed standards occupy a signifi-
cant fraction of a meter of paper. They are also difficult to implement and ineffi-
cient in operation. In this context, a riddle posed by Paul Mockapetris and cited
by Rose (1993) comes to mind:
Q: What do you get when you cross a mobster with an international standard?
A: Someone who makes you an offer you can't understand.


---

<a id="page-65"></a>

<!-- Page 65 of 888 -->

SEC. 1.4 REFERENCE MODELS 53
In addition to being incomprehensible, another problem with OSI is that some
functions, such as addressing, flow control, and error control, reappear again and
again in each layer. Saltzer et al. (1984), for example, have pointed out that to be
effective, error control must be done in the highest layer, so that repeating it over
and over in each of the lower layers is often unnecessary and inefficient.
Bad Implementations
Given the enormous complexity of the model and the protocols, it will come
as no surprise that the initial implementations were huge, unwieldy, and slow.
Everyone who tried them got burned. It did not take long for people to associate
''OSI'' with ''poor quality.'' Although the products improved in the course of
time, the image stuck.
In contrast, one of the first implementations of TCP/IP was part of Berkeley
UNIX and was quite good (not to mention, free). People began using it quickly,
which led to a large user community, which led to improvements, which led to an
even larger community. Here the spiral was upward instead of downward.
Bad Politics
On account of the initial implementation, many people, especially in
academia, thought of TCP/IP as part of UNIX, and UNIX in the 1980s in academia
was not unlike parenthood (then incorrectly called motherhood) and apple pie.
OSI, on the other hand, was widely thought to be the creature of the European
telecommunication ministries, the European Community, and later the U.S. Gov-
ernment. This belief was only partly true, but the very idea of a bunch of govern-
ment bureaucrats trying to shove a technically inferior standard down the throats
of the poor researchers and programmers down in the trenches actually develop-
ing computer networks did not aid OSI's cause. Some people viewed this de-
velopment in the same light as IBM announcing in the 1960s that PL/I was the
language of the future, or the DoD correcting this later by announcing that it was
actually Ada.
#### 1.4.6 A Critique of the TCP/IP Reference Model
The TCP/IP model and protocols have their problems too. First, the model
does not clearly distinguish the concepts of services, interfaces, and protocols.
Good software engineering practice requires differentiating between the specif-
ication and the implementation, something that OSI does very carefully, but
TCP/IP does not. Consequently, the TCP/IP model is not much of a guide for de-
signing new networks using new technologies.
Second, the TCP/IP model is not at all general and is poorly suited to describ-
ing any protocol stack other than TCP/IP. Trying to use the TCP/IP model to
describe Bluetooth, for example, is completely impossible.


---

<a id="page-66"></a>

<!-- Page 66 of 888 -->

54 INTRODUCTION CHAP. 1
Third, the link layer is not really a layer at all in the normal sense of the term
as used in the context of layered protocols. It is an interface (between the network
and data link layers). The distinction between an interface and a layer is crucial,
and one should not be sloppy about it.
Fourth, the TCP/IP model does not distinguish between the physical and data
link layers. These are completely different. The physical layer has to do with the
transmission characteristics of copper wire, fiber optics, and wireless communica-
tion. The data link layer's job is to delimit the start and end of frames and get
them from one side to the other with the desired degree of reliability. A proper
model should include both as separate layers. The TCP/IP model does not do this.
Finally, although the IP and TCP protocols were carefully thought out and
well implemented, many of the other protocols were ad hoc, generally produced
by a couple of graduate students hacking away until they got tired. The protocol
implementations were then distributed free, which resulted in their becoming
widely used, deeply entrenched, and thus hard to replace. Some of them are a bit
of an embarrassment now. The virtual terminal protocol, TELNET, for example,
was designed for a ten-character-per-second mechanical Teletype terminal. It
knows nothing of graphical user interfaces and mice. Nevertheless, it is still in
use some 30 years later.
### 1.5 EXAMPLE NETWORKS
The subject of computer networking covers many different kinds of networks,
large and small, well known and less well known. They have different goals,
scales, and technologies. In the following sections, we will look at some ex-
amples, to get an idea of the variety one finds in the area of computer networking.
We will start with the Internet, probably the best known network, and look at
its history, evolution, and technology. Then we will consider the mobile phone
network. Technically, it is quite different from the Internet, contrasting nicely
with it. Next we will introduce IEEE 802.11, the dominant standard for wireless
LANs. Finally, we will look at RFID and sensor networks, technologies that ex-
tend the reach of the network to include the physical world and everyday objects.
#### 1.5.1 The Internet
The Internet is not really a network at all, but a vast collection of different
networks that use certain common protocols and provide certain common ser-
vices. It is an unusual system in that it was not planned by anyone and is not con-
trolled by anyone. To better understand it, let us start from the beginning and see
how it has developed and why. For a wonderful history of the Internet, John
Naughton's (2000) book is highly recommended. It is one of those rare books that
is not only fun to read, but also has 20 pages of ibid.'s and op. cit.'s for the serious
historian. Some of the material in this section is based on this book.


---

<a id="page-67"></a>

<!-- Page 67 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 55
Of course, countless technical books have been written about the Internet and
its protocols as well. For more information, see, for example, Maufer (1999).
The ARPANET
The story begins in the late 1950s. At the height of the Cold War, the U.S.
DoD wanted a command-and-control network that could survive a nuclear war.
At that time, all military communications used the public telephone network,
which was considered vulnerable. The reason for this belief can be gleaned from
Fig. 1-25(a). Here the black dots represent telephone switching offices, each of
which was connected to thousands of telephones. These switching offices were,
in turn, connected to higher-level switching offices (toll offices), to form a
national hierarchy with only a small amount of redundancy. The vulnerability of
the system was that the destruction of a few key toll offices could fragment it into
many isolated islands.
Switching
office
Toll
office
(a) (b)
Figure 1-25. (a) Structure of the telephone system. (b) Baran's proposed dis-
tributed switching system.
Around 1960, the DoD awarded a contract to the RAND Corporation to find a
solution. One of its employees, Paul Baran, came up with the highly distributed
and fault-tolerant design of Fig. 1-25(b). Since the paths between any two switch-
ing offices were now much longer than analog signals could travel without distor-
tion, Baran proposed using digital packet-switching technology. Baran wrote sev-
eral reports for the DoD describing his ideas in detail (Baran, 1964). Officials at
the Pentagon liked the concept and asked AT&T, then the U.S.' national tele-
phone monopoly, to build a prototype. AT&T dismissed Baran's ideas out of
hand. The biggest and richest corporation in the world was not about to allow


---

<a id="page-68"></a>

<!-- Page 68 of 888 -->

56 INTRODUCTION CHAP. 1
some young whippersnapper tell it how to build a telephone system. They said
Baran's network could not be built and the idea was killed.
Several years went by and still the DoD did not have a better command-and-
control system. To understand what happened next, we have to go back all the
way to October 1957, when the Soviet Union beat the U.S. into space with the
launch of the first artificial satellite, Sputnik. When President Eisenhower tried to
find out who was asleep at the switch, he was appalled to find the Army, Navy,
and Air Force squabbling over the Pentagon's research budget. His immediate
response was to create a single defense research organization, ARPA, the
Advanced Research Projects Agency. ARPA had no scientists or laboratories;
in fact, it had nothing more than an office and a small (by Pentagon standards)
budget. It did its work by issuing grants and contracts to universities and com-
panies whose ideas looked promising to it.
For the first few years, ARPA tried to figure out what its mission should be.
In 1967, the attention of Larry Roberts, a program manager at ARPA who was
trying to figure out how to provide remote access to computers, turned to net-
working. He contacted various experts to decide what to do. One of them, Wes-
ley Clark, suggested building a packet-switched subnet, connecting each host to
its own router.
After some initial skepticism, Roberts bought the idea and presented a some-
what vague paper about it at the ACM SIGOPS Symposium on Operating System
Principles held in Gatlinburg, Tennessee in late 1967 (Roberts, 1967). Much to
Roberts' surprise, another paper at the conference described a similar system that
had not only been designed but actually fully implemented under the direction of
Donald Davies at the National Physical Laboratory in England. The NPL system
was not a national system (it just connected several computers on the NPL
campus), but it demonstrated that packet switching could be made to work. Fur-
thermore, it cited Baran's now discarded earlier work. Roberts came away from
Gatlinburg determined to build what later became known as the ARPANET.
The subnet would consist of minicomputers called IMPs (Interface Message
Processors) connected by 56-kbps transmission lines. For high reliability, each
IMP would be connected to at least two other IMPs. The subnet was to be a
datagram subnet, so if some lines and IMPs were destroyed, messages could be
automatically rerouted along alternative paths.
Each node of the network was to consist of an IMP and a host, in the same
room, connected by a short wire. A host could send messages of up to 8063 bits
to its IMP, which would then break these up into packets of at most 1008 bits and
forward them independently toward the destination. Each packet was received in
its entirety before being forwarded, so the subnet was the first electronic store-
and-forward packet-switching network.
ARPA then put out a tender for building the subnet. Twelve companies bid
for it. After evaluating all the proposals, ARPA selected BBN, a consulting firm
based in Cambridge, Massachusetts, and in December 1968 awarded it a contract


---

<a id="page-69"></a>

<!-- Page 69 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 57
to build the subnet and write the subnet software. BBN chose to use specially
modified Honeywell DDP-316 minicomputers with 12K 16-bit words of core
memory as the IMPs. The IMPs did not have disks, since moving parts were con-
sidered unreliable. The IMPs were interconnected by 56-kbps lines leased from
telephone companies. Although 56 kbps is now the choice of teenagers who can-
not afford DSL or cable, it was then the best money could buy.
The software was split into two parts: subnet and host. The subnet software
consisted of the IMP end of the host-IMP connection, the IMP-IMP protocol, and
a source IMP to destination IMP protocol designed to improve reliability. The
original ARPANET design is shown in Fig. 1-26.
Host-host protocol
Host
Host-IMP
protocol
Source IMP to
destination IMP protocol
IMP-IMP protocol IM pr P o - to IM co P l Subnet
IMP
Figure 1-26. The original ARPANET design.
Outside the subnet, software was also needed, namely, the host end of the
host-IMP connection, the host-host protocol, and the application software. It soon
became clear that BBN was of the opinion that when it had accepted a message on
a host-IMP wire and placed it on the host-IMP wire at the destination, its job was
done.
Roberts had a problem, though: the hosts needed software too. To deal with
it, he convened a meeting of network researchers, mostly graduate students, at
Snowbird, Utah, in the summer of 1969. The graduate students expected some
network expert to explain the grand design of the network and its software to them
and then assign each of them the job of writing part of it. They were astounded
when there was no network expert and no grand design. They had to figure out
what to do on their own.
Nevertheless, somehow an experimental network went online in December
1969 with four nodes: at UCLA, UCSB, SRI, and the University of Utah. These
four were chosen because all had a large number of ARPA contracts, and all had
different and completely incompatible host computers (just to make it more fun).
The first host-to-host message had been sent two months earlier from the UCLA


---

<a id="page-70"></a>

<!-- Page 70 of 888 -->

58 INTRODUCTION CHAP. 1
node by a team led by Len Kleinrock (a pioneer of the theory of packet switching)
to the SRI node. The network grew quickly as more IMPs were delivered and
installed; it soon spanned the United States. Figure 1-27 shows how rapidly the
ARPANET grew in the first 3 years.
## Sri Utah Sri Utah Mit Sri Utah Illinois Mit Lincoln Case
## Ucsb Ucsb Sdc Ucsb Sdc Carn
STAN
## Ucla Ucla Rand Bbn Ucla Rand Bbn Harvard Burroughs
(a) (b) (c)
## Sri Lbl Mcclellan Utah Illinois Mit
CCA
## Mcclellan Ames Tip
BBN
## Sri Utah Ncar Gwc Lincoln Case Ames Imp Harvard Linc
## Radc X-Parc Aberdeen
## Illinois Carn Stanford Nbs
## Ames Usc Linc Etac
## Ucsb Stan Sdc Mit Mitre Fnwc Rand Tinker Arpa
ETAC
## Mitre Radc
## Ucsb Ucsd Saac
## Ucla Rand Tinker Bbn Harvard Nbs Belvoir
CMU
## Ucla Sdc Usc Noaa Gwc Case
(d) (e)
Figure 1-27. Growth of the ARPANET. (a) December 1969. (b) July 1970.
(c) March 1971. (d) April 1972. (e) September 1972.
In addition to helping the fledgling ARPANET grow, ARPA also funded re-
search on the use of satellite networks and mobile packet radio networks. In one
now famous demonstration, a truck driving around in California used the packet
radio network to send messages to SRI, which were then forwarded over the
ARPANET to the East Coast, where they were shipped to University College in
London over the satellite network. This allowed a researcher in the truck to use a
computer in London while driving around in California.
This experiment also demonstrated that the existing ARPANET protocols
were not suitable for running over different networks. This observation led to
more research on protocols, culminating with the invention of the TCP/IP model
and protocols (Cerf and Kahn, 1974). TCP/IP was specifically designed to handle
communication over internetworks, something becoming increasingly important
as more and more networks were hooked up to the ARPANET.


---

<a id="page-71"></a>

<!-- Page 71 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 59
To encourage adoption of these new protocols, ARPA awarded several con-
tracts to implement TCP/IP on different computer platforms, including IBM,
DEC, and HP systems, as well as for Berkeley UNIX. Researchers at the Univer-
sity of California at Berkeley rewrote TCP/IP with a new programming interface
called sockets for the upcoming 4.2BSD release of Berkeley UNIX. They also
wrote many application, utility, and management programs to show how con-
venient it was to use the network with sockets.
The timing was perfect. Many universities had just acquired a second or third
VAX computer and a LAN to connect them, but they had no networking software.
When 4.2BSD came along, with TCP/IP, sockets, and many network utilities, the
complete package was adopted immediately. Furthermore, with TCP/IP, it was
easy for the LANs to connect to the ARPANET, and many did.
During the 1980s, additional networks, especially LANs, were connected to
the ARPANET. As the scale increased, finding hosts became increasingly expen-
sive, so DNS (Domain Name System) was created to organize machines into do-
mains and map host names onto IP addresses. Since then, DNS has become a
generalized, distributed database system for storing a variety of information relat-
ed to naming. We will study it in detail in Chap. 7.
NSFNET
By the late 1970s, NSF (the U.S. National Science Foundation) saw the enor-
mous impact the ARPANET was having on university research, allowing scien-
tists across the country to share data and collaborate on research projects. How-
ever, to get on the ARPANET a university had to have a research contract with
the DoD. Many did not have a contract. NSF's initial response was to fund the
Computer Science Network (CSNET) in 1981. It connected computer science de-
partments and industrial research labs to the ARPANET via dial-up and leased
lines. In the late 1980s, the NSF went further and decided to design a successor to
the ARPANET that would be open to all university research groups.
To have something concrete to start with, NSF decided to build a backbone
network to connect its six supercomputer centers, in San Diego, Boulder, Cham-
paign, Pittsburgh, Ithaca, and Princeton. Each supercomputer was given a little
brother, consisting of an LSI-11 microcomputer called a fuzzball. The fuzzballs
were connected with 56-kbps leased lines and formed the subnet, the same hard-
ware technology the ARPANET used. The software technology was different
however: the fuzzballs spoke TCP/IP right from the start, making it the first
TCP/IP WAN.
NSF also funded some (eventually about 20) regional networks that connected
to the backbone to allow users at thousands of universities, research labs, libraries,
and museums to access any of the supercomputers and to communicate with one
another. The complete network, including backbone and the regional networks,
was called NSFNET. It connected to the ARPANET through a link between an


---

<a id="page-72"></a>

<!-- Page 72 of 888 -->

60 INTRODUCTION CHAP. 1
IMP and a fuzzball in the Carnegie-Mellon machine room. The first NSFNET
backbone is illustrated in Fig. 1-28 superimposed on a map of the U.S.
NSF Supercomputer center
NSF Midlevel network
Both
Figure 1-28. The NSFNET backbone in 1988.
NSFNET was an instantaneous success and was overloaded from the word go.
NSF immediately began planning its successor and awarded a contract to the
Michigan-based MERIT consortium to run it. Fiber optic channels at 448 kbps
were leased from MCI (since merged with WorldCom) to provide the version 2
backbone. IBM PC-RTs were used as routers. This, too, was soon overwhelmed,
and by 1990, the second backbone was upgraded to 1.5 Mbps.
As growth continued, NSF realized that the government could not continue
financing networking forever. Furthermore, commercial organizations wanted to
join but were forbidden by NSF's charter from using networks NSF paid for.
Consequently, NSF encouraged MERIT, MCI, and IBM to form a nonprofit cor-
poration, ANS (Advanced Networks and Services), as the first step along the
road to commercialization. In 1990, ANS took over NSFNET and upgraded the
1.5-Mbps links to 45 Mbps to form ANSNET. This network operated for 5 years
and was then sold to America Online. But by then, various companies were offer-
ing commercial IP service and it was clear the government should now get out of
the networking business.
To ease the transition and make sure every regional network could communi-
cate with every other regional network, NSF awarded contracts to four different
network operators to establish a NAP (Network Access Point). These operators
were PacBell (San Francisco), Ameritech (Chicago), MFS (Washington, D.C.),
and Sprint (New York City, where for NAP purposes, Pennsauken, New Jersey
counts as New York City). Every network operator that wanted to provide back-
bone service to the NSF regional networks had to connect to all the NAPs.


---

<a id="page-73"></a>

<!-- Page 73 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 61
This arrangement meant that a packet originating on any regional network had
a choice of backbone carriers to get from its NAP to the destination's NAP. Con-
sequently, the backbone carriers were forced to compete for the regional net-
works' business on the basis of service and price, which was the idea, of course.
As a result, the concept of a single default backbone was replaced by a commer-
cially driven competitive infrastructure. Many people like to criticize the Federal
Government for not being innovative, but in the area of networking, it was DoD
and NSF that created the infrastructure that formed the basis for the Internet and
then handed it over to industry to operate.
During the 1990s, many other countries and regions also built national re-
search networks, often patterned on the ARPANET and NSFNET. These in-
cluded EuropaNET and EBONE in Europe, which started out with 2-Mbps lines
and then upgraded to 34-Mbps lines. Eventually, the network infrastructure in
Europe was handed over to industry as well.
The Internet has changed a great deal since those early days. It exploded in
size with the emergence of the World Wide Web (WWW) in the early 1990s.
Recent data from the Internet Systems Consortium puts the number of visible In-
ternet hosts at over 600 million. This guess is only a low-ball estimate, but it far
exceeds the few million hosts that were around when the first conference on the
WWW was held at CERN in 1994.
The way we use the Internet has also changed radically. Initially, applications
such as email-for-academics, newsgroups, remote login, and file transfer dom-
inated. Later it switched to email-for-everyman, then the Web and peer-to-peer
content distribution, such as the now-shuttered Napster. Now real-time media dis-
tribution, social networks (e.g., Facebook), and microblogging (e.g., Twitter) are
taking off. These switches brought richer kinds of media to the Internet and hence
much more traffic. In fact, the dominant traffic on the Internet seems to change
with some regularity as, for example, new and better ways to work with music or
movies can become very popular very quickly.
Architecture of the Internet
The architecture of the Internet has also changed a great deal as it has grown
explosively. In this section, we will attempt to give a brief overview of what it
looks like today. The picture is complicated by continuous upheavals in the
businesses of telephone companies (telcos), cable companies and ISPs that often
make it hard to tell who is doing what. One driver of these upheavals is telecom-
munications convergence, in which one network is used for previously different
uses. For example, in a ''triple play'' one company sells you telephony, TV, and
Internet service over the same network connection on the assumption that this will
save you money. Consequently, the description given here will be of necessity
somewhat simpler than reality. And what is true today may not be true tomorrow.


---

<a id="page-74"></a>

<!-- Page 74 of 888 -->

62 INTRODUCTION CHAP. 1
The big picture is shown in Fig. 1-29. Let us examine this figure piece by
piece, starting with a computer at home (at the edges of the figure). To join the
Internet, the computer is connected to an Internet Service Provider, or simply
ISP, from who the user purchases Internet access or connectivity. This lets the
computer exchange packets with all of the other accessible hosts on the Internet.
The user might send packets to surf the Web or for any of a thousand other uses, it
does not matter. There are many kinds of Internet access, and they are usually
distinguished by how much bandwidth they provide and how much they cost, but
the most important attribute is connectivity.
Data
Tier 1 ISP
center
Backbone
Router
Peering 3G mobile
at IXP phone
Fiber
(FTTH)
Dialup
Cable
DSL
Other
ISPs Cable
DSLAM POP modem
Data
CMTS
path
DSL modem
Figure 1-29. Overview of the Internet architecture.
A common way to connect to an ISP is to use the phone line to your house, in
which case your phone company is your ISP. DSL, short for Digital Subscriber
Line, reuses the telephone line that connects to your house for digital data
transmission. The computer is connected to a device called a DSL modem that
converts between digital packets and analog signals that can pass unhindered over
the telephone line. At the other end, a device called a DSLAM (Digital Sub-
scriber Line Access Multiplexer) converts between signals and packets.
Several other popular ways to connect to an ISP are shown in Fig. 1-29. DSL
is a higher-bandwidth way to use the local telephone line than to send bits over a
traditional telephone call instead of a voice conversation. That is called dial-up
and done with a different kind of modem at both ends. The word modem is short
for ''modulator demodulator'' and refers to any device that converts between digi-
tal bits and analog signals.
Another method is to send signals over the cable TV system. Like DSL, this
is a way to reuse existing infrastructure, in this case otherwise unused cable TV


---

<a id="page-75"></a>

<!-- Page 75 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 63
channels. The device at the home end is called a cable modem and the device at
the cable headend is called the CMTS (Cable Modem Termination System).
DSL and cable provide Internet access at rates from a small fraction of a
megabit/sec to multiple megabit/sec, depending on the system. These rates are
much greater than dial-up rates, which are limited to 56 kbps because of the nar-
row bandwidth used for voice calls. Internet access at much greater than dial-up
speeds is called broadband. The name refers to the broader bandwidth that is
used for faster networks, rather than any particular speed.
The access methods mentioned so far are limited by the bandwidth of the
''last mile'' or last leg of transmission. By running optical fiber to residences, fast-
er Internet access can be provided at rates on the order of 10 to 100 Mbps. This
design is called FTTH (Fiber to the Home). For businesses in commercial
areas, it may make sense to lease a high-speed transmission line from the offices
to the nearest ISP. For example, in North America, a T3 line runs at roughly 45
Mbps.
Wireless is used for Internet access too. An example we will explore shortly is
that of 3G mobile phone networks. They can provide data delivery at rates of 1
Mbps or higher to mobile phones and fixed subscribers in the coverage area.
We can now move packets between the home and the ISP. We call the loca-
tion at which customer packets enter the ISP network for service the ISP's POP
(Point of Presence). We will next explain how packets are moved between the
POPs of different ISPs. From this point on, the system is fully digital and packet
switched.
ISP networks may be regional, national, or international in scope. We have
already seen that their architecture is made up of long-distance transmission lines
that interconnect routers at POPs in the different cities that the ISPs serve. This
equipment is called the backbone of the ISP. If a packet is destined for a host
served directly by the ISP, that packet is routed over the backbone and delivered
to the host. Otherwise, it must be handed over to another ISP.
ISPs connect their networks to exchange traffic at IXPs (Internet eXchange
Points). The connected ISPs are said to peer with each other. There are many
IXPs in cities around the world. They are drawn vertically in Fig. 1-29 because
ISP networks overlap geographically. Basically, an IXP is a room full of routers,
at least one per ISP. A LAN in the room connects all the routers, so packets can
be forwarded from any ISP backbone to any other ISP backbone. IXPs can be
large and independently owned facilities. One of the largest is the Amsterdam In-
ternet Exchange, to which hundreds of ISPs connect and through which they
exchange hundreds of gigabits/sec of traffic.
The peering that happens at IXPs depends on the business relationships be-
tween ISPs. There are many possible relationships. For example, a small ISP
might pay a larger ISP for Internet connectivity to reach distant hosts, much as a
customer purchases service from an Internet provider. In this case, the small ISP
is said to pay for transit. Alternatively, two large ISPs might decide to exchange


---

<a id="page-76"></a>

<!-- Page 76 of 888 -->

64 INTRODUCTION CHAP. 1
traffic so that each ISP can deliver some traffic to the other ISP without having to
pay for transit. One of the many paradoxes of the Internet is that ISPs who pub-
licly compete with one another for customers often privately cooperate to do peer-
ing (Metz, 2001).
The path a packet takes through the Internet depends on the peering choices of
the ISPs. If the ISP delivering a packet peers with the destination ISP, it might
deliver the packet directly to its peer. Otherwise, it might route the packet to the
nearest place at which it connects to a paid transit provider so that provider can
deliver the packet. Two example paths across ISPs are drawn in Fig. 1-29. Often,
the path a packet takes will not be the shortest path through the Internet.
At the top of the food chain are a small handful of companies, like AT&T and
Sprint, that operate large international backbone networks with thousands of rout-
ers connected by high-bandwidth fiber optic links. These ISPs do not pay for
transit. They are usually called tier 1 ISPs and are said to form the backbone of
the Internet, since everyone else must connect to them to be able to reach the en-
tire Internet.
Companies that provide lots of content, such as Google and Yahoo!, locate
their computers in data centers that are well connected to the rest of the Internet.
These data centers are designed for computers, not humans, and may be filled
with rack upon rack of machines called a server farm. Colocation or hosting
data centers let customers put equipment such as servers at ISP POPs so that
short, fast connections can be made between the servers and the ISP backbones.
The Internet hosting industry has become increasingly virtualized so that it is now
common to rent a virtual machine that is run on a server farm instead of installing
a physical computer. These data centers are so large (tens or hundreds of
thousands of machines) that electricity is a major cost, so data centers are some-
times built in areas where electricity is cheap.
This ends our quick tour of the Internet. We will have a great deal to say
about the individual components and their design, algorithms, and protocols in
subsequent chapters. One further point worth mentioning here is that what it
means to be on the Internet is changing. It used to be that a machine was on the
Internet if it: (1) ran the TCP/IP protocol stack; (2) had an IP address; and (3)
could send IP packets to all the other machines on the Internet. However, ISPs
often reuse IP addresses depending on which computers are in use at the moment,
and home networks often share one IP address between multiple computers. This
practice undermines the second condition. Security measures such as firewalls
can also partly block computers from receiving packets, undermining the third
condition. Despite these difficulties, it makes sense to regard such machines as
being on the Internet while they are connected to their ISPs.
Also worth mentioning in passing is that some companies have interconnected
all their existing internal networks, often using the same technology as the Inter-
net. These intranets are typically accessible only on company premises or from
company notebooks but otherwise work the same way as the Internet.


---

<a id="page-77"></a>

<!-- Page 77 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 65
#### 1.5.2 Third-Generation Mobile Phone Networks
People love to talk on the phone even more than they like to surf the Internet,
and this has made the mobile phone network the most successful network in the
world. It has more than four billion subscribers worldwide. To put this number in
perspective, it is roughly 60% of the world's population and more than the number
of Internet hosts and fixed telephone lines combined (ITU, 2009).
The architecture of the mobile phone network has changed greatly over the
past 40 years along with its tremendous growth. First-generation mobile phone
systems transmitted voice calls as continuously varying (analog) signals rather
than sequences of (digital) bits. AMPS (Advanced Mobile Phone System),
which was deployed in the United States in 1982, was a widely used first-
generation system. Second-generation mobile phone systems switched to trans-
mitting voice calls in digital form to increase capacity, improve security, and offer
text messaging. GSM (Global System for Mobile communications), which was
deployed starting in 1991 and has become the most widely used mobile phone
system in the world, is a 2G system.
The third generation, or 3G, systems were initially deployed in 2001 and offer
both digital voice and broadband digital data services. They also come with a lot
of jargon and many different standards to choose from. 3G is loosely defined by
the ITU (an international standards body we will discuss in the next section) as
providing rates of at least 2 Mbps for stationary or walking users and 384 kbps in
a moving vehicle. UMTS (Universal Mobile Telecommunications System),
also called WCDMA (Wideband Code Division Multiple Access), is the main
3G system that is being rapidly deployed worldwide. It can provide up to 14
Mbps on the downlink and almost 6 Mbps on the uplink. Future releases will use
multiple antennas and radios to provide even greater speeds for users.
The scarce resource in 3G systems, as in 2G and 1G systems before them, is
radio spectrum. Governments license the right to use parts of the spectrum to the
mobile phone network operators, often using a spectrum auction in which network
operators submit bids. Having a piece of licensed spectrum makes it easier to de-
sign and operate systems, since no one else is allowed transmit on that spectrum,
but it often costs a serious amount of money. In the UK in 2000, for example, five
3G licenses were auctioned for a total of about $40 billion.
It is the scarcity of spectrum that led to the cellular network design shown in
Fig. 1-30 that is now used for mobile phone networks. To manage the radio
interference between users, the coverage area is divided into cells. Within a cell,
users are assigned channels that do not interfere with each other and do not cause
too much interference for adjacent cells. This allows for good reuse of the spec-
trum, or frequency reuse, in the neighboring cells, which increases the capacity
of the network. In 1G systems, which carried each voice call on a specific fre-
quency band, the frequencies were carefully chosen so that they did not conflict
with neighboring cells. In this way, a given frequency might only be reused once


---

<a id="page-78"></a>

<!-- Page 78 of 888 -->

66 INTRODUCTION CHAP. 1
in several cells. Modern 3G systems allow each cell to use all frequencies, but in
a way that results in a tolerable level of interference to the neighboring cells.
There are variations on the cellular design, including the use of directional or sec-
tored antennas on cell towers to further reduce interference, but the basic idea is
the same.
Cells
Base station
Figure 1-30. Cellular design of mobile phone networks.
The architecture of the mobile phone network is very different than that of the
Internet. It has several parts, as shown in the simplified version of the UMTS ar-
chitecture in Fig. 1-31. First, there is the air interface. This term is a fancy name
for the radio communication protocol that is used over the air between the mobile
device (e.g., the cell phone) and the cellular base station. Advances in the air in-
terface over the past decades have greatly increased wireless data rates. The
UMTS air interface is based on Code Division Multiple Access (CDMA), a tech-
nique that we will study in Chap. 2.
The cellular base station together with its controller forms the radio access
network. This part is the wireless side of the mobile phone network. The con-
troller node or RNC (Radio Network Controller) controls how the spectrum is
used. The base station implements the air interface. It is called Node B, a tem-
porary label that stuck.
The rest of the mobile phone network carries the traffic for the radio access
network. It is called the core network. The UMTS core network evolved from
the core network used for the 2G GSM system that came before it. However,
something surprising is happening in the UMTS core network.
Since the beginning of networking, a war has been going on between the peo-
ple who support packet networks (i.e., connectionless subnets) and the people who
support circuit networks (i.e., connection-oriented subnets). The main proponents
of packets come from the Internet community. In a connectionless design, every
packet is routed independently of every other packet. As a consequence, if some
routers go down during a session, no harm will be done as long as the system can


---

<a id="page-79"></a>

<!-- Page 79 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 67
Air
Access
interface Node B / Core
("Uu")
interface
("Iu")
RNC
Circuits MSC / GMSC PSTN
MGW / MGW
("Iu-CS")
RNC HSS
Packets SGSN GGSN Internet
("Iu-PS")
Packets
Radio access network Core network
Figure 1-31. Architecture of the UMTS 3G mobile phone network.
dynamically reconfigure itself so that subsequent packets can find some route to
the destination, even if it is different from that which previous packets used.
The circuit camp comes from the world of telephone companies. In the tele-
phone system, a caller must dial the called party's number and wait for a connec-
tion before talking or sending data. This connection setup establishes a route
through the telephone system that is maintained until the call is terminated. All
words or packets follow the same route. If a line or switch on the path goes down,
the call is aborted, making it less fault tolerant than a connectionless design.
The advantage of circuits is that they can support quality of service more easi-
ly. By setting up a connection in advance, the subnet can reserve resources such
as link bandwidth, switch buffer space, and CPU. If an attempt is made to set up
a call and insufficient resources are available, the call is rejected and the caller
gets a kind of busy signal. In this way, once a connection has been set up, the
connection will get good service.
With a connectionless network, if too many packets arrive at the same router
at the same moment, the router will choke and probably lose packets. The sender
will eventually notice this and resend them, but the quality of service will be jerky
and unsuitable for audio or video unless the network is lightly loaded. Needless to
say, providing adequate audio quality is something telephone companies care
about very much, hence their preference for connections.
The surprise in Fig. 1-31 is that there is both packet and circuit switched
equipment in the core network. This shows the mobile phone network in transi-
tion, with mobile phone companies able to implement one or sometimes both of


---

<a id="page-80"></a>

<!-- Page 80 of 888 -->

68 INTRODUCTION CHAP. 1
the alternatives. Older mobile phone networks used a circuit-switched core in the
style of the traditional phone network to carry voice calls. This legacy is seen in
the UMTS network with the MSC (Mobile Switching Center), GMSC (Gate-
way Mobile Switching Center), and MGW (Media Gateway) elements that set
up connections over a circuit-switched core network such as the PSTN (Public
Switched Telephone Network).
Data services have become a much more important part of the mobile phone
network than they used to be, starting with text messaging and early packet data
services such as GPRS (General Packet Radio Service) in the GSM system.
These older data services ran at tens of kbps, but users wanted more. Newer mo-
bile phone networks carry packet data at rates of multiple Mbps. For comparison,
a voice call is carried at a rate of 64 kbps, typically 3-4x less with compression.
To carry all this data, the UMTS core network nodes connect directly to a
packet-switched network. The SGSN (Serving GPRS Support Node) and the
GGSN (Gateway GPRS Support Node) deliver data packets to and from
mobiles and interface to external packet networks such as the Internet.
This transition is set to continue in the mobile phone networks that are now
being planned and deployed. Internet protocols are even used on mobiles to set up
connections for voice calls over a packet data network, in the manner of voice-
over-IP. IP and packets are used all the way from the radio access through to the
core network. Of course, the way that IP networks are designed is also changing
to support better quality of service. If it did not, then problems with chopped-up
audio and jerky video would not impress paying customers. We will return to this
subject in Chap. 5.
Another difference between mobile phone networks and the traditional Inter-
net is mobility. When a user moves out of the range of one cellular base station
and into the range of another one, the flow of data must be re-routed from the old
to the new cell base station. This technique is known as handover or handoff,
and it is illustrated in Fig. 1-32.
(a) (b)
Figure 1-32. Mobile phone handover (a) before, (b) after.
Either the mobile device or the base station may request a handover when the
quality of the signal drops. In some cell networks, usually those based on CDMA


---

<a id="page-81"></a>

<!-- Page 81 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 69
technology, it is possible to connect to the new base station before disconnecting
from the old base station. This improves the connection quality for the mobile be-
cause there is no break in service; the mobile is actually connected to two base
stations for a short while. This way of doing a handover is called a soft handover
to distinguish it from a hard handover, in which the mobile disconnects from the
old base station before connecting to the new one.
A related issue is how to find a mobile in the first place when there is an in-
coming call. Each mobile phone network has a HSS (Home Subscriber Server)
in the core network that knows the location of each subscriber, as well as other
profile information that is used for authentication and authorization. In this way,
each mobile can be found by contacting the HSS.
A final area to discuss is security. Historically, phone companies have taken
security much more seriously than Internet companies for a long time because of
the need to bill for service and avoid (payment) fraud. Unfortunately that is not
saying much. Nevertheless, in the evolution from 1G through 3G technologies,
mobile phone companies have been able to roll out some basic security mechan-
isms for mobiles.
Starting with the 2G GSM system, the mobile phone was divided into a
handset and a removable chip containing the subscriber's identity and account
information. The chip is informally called a SIM card, short for Subscriber
Identity Module. SIM cards can be switched to different handsets to activate
them, and they provide a basis for security. When GSM customers travel to other
countries on vacation or business, they often bring their handsets but buy a new
SIM card for few dollars upon arrival in order to make local calls with no roaming
charges.
To reduce fraud, information on SIM cards is also used by the mobile phone
network to authenticate subscribers and check that they are allowed to use the net-
work. With UMTS, the mobile also uses the information on the SIM card to
check that it is talking to a legitimate network.
Another aspect of security is privacy. Wireless signals are broadcast to all
nearby receivers, so to make it difficult to eavesdrop on conversations, crypto-
graphic keys on the SIM card are used to encrypt transmissions. This approach
provides much better privacy than in 1G systems, which were easily tapped, but is
not a panacea due to weaknesses in the encryption schemes.
Mobile phone networks are destined to play a central role in future networks.
They are now more about mobile broadband applications than voice calls, and this
has major implications for the air interfaces, core network architecture, and secu-
rity of future networks. 4G technologies that are faster and better are on the draw-
ing board under the name of LTE (Long Term Evolution), even as 3G design
and deployment continues. Other wireless technologies also offer broadband In-
ternet access to fixed and mobile clients, notably 802.16 networks under the com-
mon name of WiMAX. It is entirely possible that LTE and WiMAX are on a col-
lision course with each other and it is hard to predict what will happen to them.


---

<a id="page-82"></a>

<!-- Page 82 of 888 -->

70 INTRODUCTION CHAP. 1
#### 1.5.3 Wireless LANs: 802.11
Almost as soon as laptop computers appeared, many people had a dream of
walking into an office and magically having their laptop computer be connected to
the Internet. Consequently, various groups began working on ways to accomplish
this goal. The most practical approach is to equip both the office and the laptop
computers with short-range radio transmitters and receivers to allow them to talk.
Work in this field rapidly led to wireless LANs being marketed by a variety of
companies. The trouble was that no two of them were compatible. The prolifera-
tion of standards meant that a computer equipped with a brand X radio would not
work in a room equipped with a brand Y base station. In the mid 1990s, the indus-
try decided that a wireless LAN standard might be a good idea, so the IEEE com-
mittee that had standardized wired LANs was given the task of drawing up a wire-
less LAN standard.
The first decision was the easiest: what to call it. All the other LAN standards
had numbers like 802.1, 802.2, and 802.3, up to 802.10, so the wireless LAN stan-
dard was dubbed 802.11. A common slang name for it is WiFi but it is an impor-
tant standard and deserves respect, so we will call it by its proper name, 802.11.
The rest was harder. The first problem was to find a suitable frequency band
that was available, preferably worldwide. The approach taken was the opposite of
that used in mobile phone networks. Instead of expensive, licensed spectrum,
### 802.11 systems operate in unlicensed bands such as the ISM (Industrial, Scien-
tific, and Medical) bands defined by ITU-R (e.g., 902-928 MHz, 2.4-2.5 GHz,
5.725-5.825 GHz). All devices are allowed to use this spectrum provided that
they limit their transmit power to let different devices coexist. Of course, this
means that 802.11 radios may find themselves competing with cordless phones,
garage door openers, and microwave ovens.
### 802.11 networks are made up of clients, such as laptops and mobile phones,
and infrastructure called APs (access points) that is installed in buildings. Access
points are sometimes called base stations. The access points connect to the wired
network, and all communication between clients goes through an access point. It
is also possible for clients that are in radio range to talk directly, such as two com-
puters in an office without an access point. This arrangement is called an ad hoc
network. It is used much less often than the access point mode. Both modes are
shown in Fig. 1-33.
### 802.11 transmission is complicated by wireless conditions that vary with even
small changes in the environment. At the frequencies used for 802.11, radio sig-
nals can be reflected off solid objects so that multiple echoes of a transmission
may reach a receiver along different paths. The echoes can cancel or reinforce
each other, causing the received signal to fluctuate greatly. This phenomenon is
called multipath fading, and it is shown in Fig. 1-34.
The key idea for overcoming variable wireless conditions is path diversity,
or the sending of information along multiple, independent paths. In this way, the


---

<a id="page-83"></a>

<!-- Page 83 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 71
Access To wired network
point
(a) (b)
Figure 1-33. (a) Wireless network with an access point. (b) Ad hoc network.
information is likely to be received even if one of the paths happens to be poor
due to a fade. These independent paths are typically built into the digital modula-
tion scheme at the physical layer. Options include using different frequencies a-
cross the allowed band, following different spatial paths between different pairs of
antennas, or repeating bits over different periods of time.
Multiple paths
Non-faded signal
Wireless
transmitter
Reflector Faded signal
Wireless
receiver
Figure 1-34. Multipath fading.
Different versions of 802.11 have used all of these techniques. The initial
(1997) standard defined a wireless LAN that ran at either 1 Mbps or 2 Mbps by
hopping between frequencies or spreading the signal across the allowed spectrum.
Almost immediately, people complained that it was too slow, so work began on
faster standards. The spread spectrum design was extended and became the
(1999) 802.11b standard running at rates up to 11 Mbps. The 802.11a (1999) and
802.11g (2003) standards switched to a different modulation scheme called
OFDM (Orthogonal Frequency Division Multiplexing). It divides a wide band
of spectrum into many narrow slices over which different bits are sent in parallel.
This improved scheme, which we will study in Chap. 2, boosted the 802.11a/g bit


---

<a id="page-84"></a>

<!-- Page 84 of 888 -->

72 INTRODUCTION CHAP. 1
rates up to 54 Mbps. That is a significant increase, but people still wanted more
throughput to support more demanding uses. The latest version is 802.11n (2009).
It uses wider frequency bands and up to four antennas per computer to achieve
rates up to 450 Mbps.
Since wireless is inherently a broadcast medium, 802.11 radios also have to
deal with the problem that multiple transmissions that are sent at the same time
will collide, which may interfere with reception. To handle this problem, 802.11
uses a CSMA (Carrier Sense Multiple Access) scheme that draws on ideas from
classic wired Ethernet, which, ironically, drew from an early wireless network
developed in Hawaii and called ALOHA. Computers wait for a short random
interval before transmitting, and defer their transmissions if they hear that some-
one else is already transmitting. This scheme makes it less likely that two com-
puters will send at the same time. It does not work as well as in the case of wired
networks, though. To see why, examine Fig. 1-35. Suppose that computer A is
transmitting to computer B, but the radio range of A's transmitter is too short to
reach computer C. If C wants to transmit to B it can listen before starting, but the
fact that it does not hear anything does not mean that its transmission will
succeed. The inability of C to hear A before starting causes some collisions to oc-
cur. After any collision, the sender then waits another, longer, random delay and
retransmits the packet. Despite this and some other issues, the scheme works well
enough in practice.
Range Range
of A's of C's
radio radio
A B C
Figure 1-35. The range of a single radio may not cover the entire system.
Another problem is that of mobility. If a mobile client is moved away from
the access point it is using and into the range of a different access point, some way
of handing it off is needed. The solution is that an 802.11 network can consist of
multiple cells, each with its own access point, and a distribution system that con-
nects the cells. The distribution system is often switched Ethernet, but it can use
any technology. As the clients move, they may find another access point with a
better signal than the one they are currently using and change their association.
From the outside, the entire system looks like a single wired LAN.


---

<a id="page-85"></a>

<!-- Page 85 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 73
That said, mobility in 802.11 has been of limited value so far compared to
mobility in the mobile phone network. Typically, 802.11 is used by nomadic cli-
ents that go from one fixed location to another, rather than being used on-the-go.
Mobility is not really needed for nomadic usage. Even when 802.11 mobility is
used, it extends over a single 802.11 network, which might cover at most a large
building. Future schemes will need to provide mobility across different networks
and across different technologies (e.g., 802.21).
Finally, there is the problem of security. Since wireless transmissions are
broadcast, it is easy for nearby computers to receive packets of information that
were not intended for them. To prevent this, the 802.11 standard included an en-
cryption scheme known as WEP (Wired Equivalent Privacy). The idea was to
make wireless security like that of wired security. It is a good idea, but unfor-
tunately the scheme was flawed and soon broken (Borisov et al., 2001). It has
since been replaced with newer schemes that have different cryptographic details
in the 802.11i standard, also called WiFi Protected Access, initially called WPA
but now replaced by WPA2.
### 802.11 has caused a revolution in wireless networking that is set to continue.
Beyond buildings, it is starting to be installed in trains, planes, boats, and automo-
biles so that people can surf the Internet wherever they go. Mobile phones and all
manner of consumer electronics, from game consoles to digital cameras, can com-
municate with it. We will come back to it in detail in Chap. 4.
#### 1.5.4 RFID and Sensor Networks
The networks we have studied so far are made up of computing devices that
are easy to recognize, from computers to mobile phones. With Radio Frequency
IDentification (RFID), everyday objects can also be part of a computer network.
An RFID tag looks like a postage stamp-sized sticker that can be affixed to
(or embedded in) an object so that it can be tracked. The object might be a cow, a
passport, a book or a shipping pallet. The tag consists of a small microchip with a
unique identifier and an antenna that receives radio transmissions. RFID readers
installed at tracking points find tags when they come into range and interrogate
them for their information as shown in Fig. 1-36. Applications include checking
identities, managing the supply chain, timing races, and replacing barcodes.
There are many kinds of RFID, each with different properties, but perhaps the
most fascinating aspect of RFID technology is that most RFID tags have neither
an electric plug nor a battery. Instead, all of the energy needed to operate them is
supplied in the form of radio waves by RFID readers. This technology is called
passive RFID to distinguish it from the (less common) active RFID in which
there is a power source on the tag.
One common form of RFID is UHF RFID (Ultra-High Frequency RFID).
It is used on shipping pallets and some drivers licenses. Readers send signals in


---

<a id="page-86"></a>

<!-- Page 86 of 888 -->

74 INTRODUCTION CHAP. 1
RFID
tag
RFID
reader
Figure 1-36. RFID used to network everyday objects.
the 902-928 MHz band in the United States. Tags communicate at distances of
several meters by changing the way they reflect the reader signals; the reader is
able to pick up these reflections. This way of operating is called backscatter.
Another popular kind of RFID is HF RFID (High Frequency RFID). It
operates at 13.56 MHz and is likely to be in your passport, credit cards, books,
and noncontact payment systems. HF RFID has a short range, typically a meter
or less, because the physical mechanism is based on induction rather than back-
scatter. There are also other forms of RFID using other frequencies, such as LF
RFID (Low Frequency RFID), which was developed before HF RFID and used
for animal tracking. It is the kind of RFID likely to be in your cat.
RFID readers must somehow solve the problem of dealing with multiple tags
within reading range. This means that a tag cannot simply respond when it hears
a reader, or the signals from multiple tags may collide. The solution is similar to
the approach taken in 802.11: tags wait for a short random interval before re-
sponding with their identification, which allows the reader to narrow down indivi-
dual tags and interrogate them further.
Security is another problem. The ability of RFID readers to easily track an ob-
ject, and hence the person who uses it, can be an invasion of privacy. Unfor-
tunately, it is difficult to secure RFID tags because they lack the computation and
communication power to run strong cryptographic algorithms. Instead, weak
measures like passwords (which can easily be cracked) are used. If an identity
card can be remotely read by an official at a border, what is to stop the same card
from being tracked by other people without your knowledge? Not much.
RFID tags started as identification chips, but are rapidly turning into full-
fledged computers. For example, many tags have memory that can be updated and
later queried, so that information about what has happened to the tagged object
can be stored with it. Rieback et al. (2006) demonstrated that this means that all
of the usual problems of computer malware apply, only now your cat or your
passport might be used to spread an RFID virus.
A step up in capability from RFID is the sensor network. Sensor networks
are deployed to monitor aspects of the physical world. So far, they have mostly
been used for scientific experimentation, such as monitoring bird habitats, vol-
canic activity, and zebra migration, but business applications including healthcare,


---

<a id="page-87"></a>

<!-- Page 87 of 888 -->

SEC. 1.5 EXAMPLE NETWORKS 75
monitoring equipment for vibration, and tracking of frozen, refrigerated, or other-
wise perishable goods cannot be too far behind.
Sensor nodes are small computers, often the size of a key fob, that have tem-
perature, vibration, and other sensors. Many nodes are placed in the environment
that is to be monitored. Typically, they have batteries, though they may scavenge
energy from vibrations or the sun. As with RFID, having enough energy is a key
challenge, and the nodes must communicate carefully to be able to deliver their
sensor information to an external collection point. A common strategy is for the
nodes to self-organize to relay messages for each other, as shown in Fig. 1-37.
This design is called a multihop network.
Wireless
hop
Sensor
node
Data
collection
point
Figure 1-37. Multihop topology of a sensor network.
RFID and sensor networks are likely to become much more capable and per-
vasive in the future. Researchers have already combined the best of both technolo-
gies by prototyping programmable RFID tags with light, movement, and other
sensors (Sample et al., 2008).
### 1.6 NETWORK STANDARDIZATION
Many network vendors and suppliers exist, each with its own ideas of how
things should be done. Without coordination, there would be complete chaos, and
users would get nothing done. The only way out is to agree on some network
standards. Not only do good standards allow different computers to communicate,
but they also increase the market for products adhering to the standards. A larger
market leads to mass production, economies of scale in manufacturing, better im-
plementations, and other benefits that decrease price and further increase ac-
ceptance.
In this section we will take a quick look at the important but little-known,
world of international standardization. But let us first discuss what belongs in a


---

<a id="page-88"></a>

<!-- Page 88 of 888 -->

76 INTRODUCTION CHAP. 1
standard. A reasonable person might assume that a standard tells you how a pro-
tocol should work so that you can do a good job of implementing it. That person
would be wrong.
Standards define what is needed for interoperability: no more, no less. That
lets the larger market emerge and also lets companies compete on the basis of
how good their products are. For example, the 802.11 standard defines many
transmission rates but does not say when a sender should use which rate, which is
a key factor in good performance. That is up to whoever makes the product.
Often getting to interoperability this way is difficult, since there are many imple-
mentation choices and standards usually define many options. For 802.11, there
were so many problems that, in a strategy that has become common practice, a
trade group called the WiFi Alliance was started to work on interoperability with-
in the 802.11 standard.
Similarly, a protocol standard defines the protocol over the wire but not the
service interface inside the box, except to help explain the protocol. Real service
interfaces are often proprietary. For example, the way TCP interfaces to IP within
a computer does not matter for talking to a remote host. It only matters that the re-
mote host speaks TCP/IP. In fact, TCP and IP are commonly implemented toget-
her without any distinct interface. That said, good service interfaces, like good
APIs, are valuable for getting protocols used, and the best ones (such as Berkeley
sockets) can become very popular.
Standards fall into two categories: de facto and de jure. De facto (Latin for
''from the fact'') standards are those that have just happened, without any formal
plan. HTTP, the protocol on which the Web runs, started life as a de facto stan-
dard. It was part of early WWW browsers developed by Tim Berners-Lee at
CERN, and its use took off with the growth of the Web. Bluetooth is another ex-
ample. It was originally developed by Ericsson but now everyone is using it.
De jure (Latin for ''by law'') standards, in contrast, are adopted through the
rules of some formal standardization body. International standardization authori-
ties are generally divided into two classes: those established by treaty among
national governments, and those comprising voluntary, nontreaty organizations.
In the area of computer network standards, there are several organizations of each
type, notably ITU, ISO, IETF and IEEE, all of which we will discuss below.
In practice, the relationships between standards, companies, and stan-
dardization bodies are complicated. De facto standards often evolve into de jure
standards, especially if they are successful. This happened in the case of HTTP,
which was quickly picked up by IETF. Standards bodies often ratify each others'
standards, in what looks like patting one another on the back, to increase the
market for a technology. These days, many ad hoc business alliances that are
formed around particular technologies also play a significant role in developing
and refining network standards. For example, 3GPP (Third Generation
Partnership Project) is a collaboration between telecommunications associations
that drives the UMTS 3G mobile phone standards.


---

<a id="page-89"></a>

<!-- Page 89 of 888 -->

SEC. 1.6 NETWORK STANDARDIZATION 77
#### 1.6.1 Who's Who in the Telecommunications World
The legal status of the world's telephone companies varies considerably from
country to country. At one extreme is the United States, which has over 2000 sep-
arate, (mostly very small) privately owned telephone companies. A few more
were added with the breakup of AT&T in 1984 (which was then the world's larg-
est corporation, providing telephone service to about 80 percent of America's
telephones), and the Telecommunications Act of 1996 that overhauled regulation
to foster competition.
At the other extreme are countries in which the national government has a
complete monopoly on all communication, including the mail, telegraph, tele-
phone, and often radio and television. Much of the world falls into this category.
In some cases the telecommunication authority is a nationalized company, and in
others it is simply a branch of the government, usually known as the PTT (Post,
Telegraph & Telephone administration). Worldwide, the trend is toward liberal-
ization and competition and away from government monopoly. Most European
countries have now (partially) privatized their PTTs, but elsewhere the process is
still only slowly gaining steam.
With all these different suppliers of services, there is clearly a need to provide
compatibility on a worldwide scale to ensure that people (and computers) in one
country can call their counterparts in another one. Actually, this need has existed
for a long time. In 1865, representatives from many European governments met
to form the predecessor to today's ITU (International Telecommunication
Union). Its job was to standardize international telecommunications, which in
those days meant telegraphy. Even then it was clear that if half the countries used
Morse code and the other half used some other code, there was going to be a prob-
lem. When the telephone was put into international service, ITU took over the job
of standardizing telephony (pronounced te-LEF-ony) as well. In 1947, ITU
became an agency of the United Nations.
ITU has about 200 governmental members, including almost every member of
the United Nations. Since the United States does not have a PTT, somebody else
had to represent it in ITU. This task fell to the State Department, probably on the
grounds that ITU had to do with foreign countries, the State Department's spe-
cialty. ITU also has more than 700 sector and associate members. They include
telephone companies (e.g., AT&T, Vodafone, Sprint), telecom equipment manu-
facturers (e.g., Cisco, Nokia, Nortel), computer vendors (e.g., Microsoft, Agilent,
Toshiba), chip manufacturers (e.g., Intel, Motorola, TI), and other interested com-
panies (e.g., Boeing, CBS, VeriSign).
ITU has three main sectors. We will focus primarily on ITU-T, the Telecom-
munications Standardization Sector, which is concerned with telephone and data
communication systems. Before 1993, this sector was called CCITT, which is an
acronym for its French name, Comite´ Consultatif International Te´le´graphique et
Te´le´phonique. ITU-R, the Radiocommunications Sector, is concerned with


---

<a id="page-90"></a>

<!-- Page 90 of 888 -->

78 INTRODUCTION CHAP. 1
coordinating the use by competing interest groups of radio frequencies worldwide.
The other sector is ITU-D, the Development Sector. It promotes the development
of information and communication technologies to narrow the ''digital divide''
between countries with effective access to the information technologies and coun-
tries with limited access.
ITU-T's task is to make technical recommendations about telephone, tele-
graph, and data communication interfaces. These often become internationally
recognized standards, though technically the recommendations are only sugges-
tions that governments can adopt or ignore, as they wish (because governments
are like 13-year-old boys-they do not take kindly to being given orders). In
practice, a country that wishes to adopt a telephone standard different from that
used by the rest of the world is free to do so, but at the price of cutting itself off
from everyone else. This might work for North Korea, but elsewhere it would be
a real problem.
The real work of ITU-T is done in its Study Groups. There are currently 10
Study Groups, often as large as 400 people, that cover topics ranging from tele-
phone billing to multimedia services to security. SG 15, for example, standardizes
the DSL technologies popularly used to connect to the Internet. In order to make
it possible to get anything at all done, the Study Groups are divided into Working
Parties, which are in turn divided into Expert Teams, which are in turn divided
into ad hoc groups. Once a bureaucracy, always a bureaucracy.
Despite all this, ITU-T actually does get things done. Since its inception, it
has produced more than 3000 recommendations, many of which are widely used
in practice. For example, Recommendation H.264 (also an ISO standard known
as MPEG-4 AVC) is widely used for video compression, and X.509 public key
certificates are used for secure Web browsing and digitally signed email.
As the field of telecommunications completes the transition started in the
1980s from being entirely national to being entirely global, standards will become
increasingly important, and more and more organizations will want to become
involved in setting them. For more information about ITU, see Irmer (1994).
#### 1.6.2 Who's Who in the International Standards World
International standards are produced and published by ISO (International
†
Standards Organization ), a voluntary nontreaty organization founded in 1946.
Its members are the national standards organizations of the 157 member countries.
These members include ANSI (U.S.), BSI (Great Britain), AFNOR (France), DIN
(Germany), and 153 others.
ISO issues standards on a truly vast number of subjects, ranging from nuts and
bolts (literally) to telephone pole coatings [not to mention cocoa beans (ISO
2451), fishing nets (ISO 1530), women's underwear (ISO 4416) and quite a few
† For the purist, ISO's true name is the International Organization for Standardization.


---

<a id="page-91"></a>

<!-- Page 91 of 888 -->

SEC. 1.6 NETWORK STANDARDIZATION 79
other subjects one might not think were subject to standardization]. On issues of
telecommunication standards, ISO and ITU-T often cooperate (ISO is a member
of ITU-T) to avoid the irony of two official and mutually incompatible interna-
tional standards.
Over 17,000 standards have been issued, including the OSI standards. ISO
has over 200 Technical Committees (TCs), numbered in the order of their crea-
tion, each dealing with a specific subject. TC1 deals with the nuts and bolts (stan-
dardizing screw thread pitches). JTC1 deals with information technology, includ-
ing networks, computers, and software. It is the first (and so far only) Joint
Technical Committee, created in 1987 by merging TC97 with activities in IEC,
yet another standardization body. Each TC has subcommittees (SCs) divided into
working groups (WGs).
The real work is done largely in the WGs by over 100,000 volunteers world-
wide. Many of these ''volunteers'' are assigned to work on ISO matters by their
employers, whose products are being standardized. Others are government offi-
cials keen on having their country's way of doing things become the international
standard. Academic experts also are active in many of the WGs.
The procedure used by ISO for adopting standards has been designed to
achieve as broad a consensus as possible. The process begins when one of the
national standards organizations feels the need for an international standard in
some area. A working group is then formed to come up with a CD (Committee
Draft). The CD is then circulated to all the member bodies, which get 6 months
to criticize it. If a substantial majority approves, a revised document, called a DIS
(Draft International Standard) is produced and circulated for comments and
voting. Based on the results of this round, the final text of the IS (International
Standard) is prepared, approved, and published. In areas of great controversy, a
CD or DIS may have to go through several versions before acquiring enough
votes, and the whole process can take years.
NIST (National Institute of Standards and Technology) is part of the U.S.
Department of Commerce. It used to be called the National Bureau of Standards.
It issues standards that are mandatory for purchases made by the U.S. Govern-
ment, except for those of the Department of Defense, which defines its own stan-
dards.
Another major player in the standards world is IEEE (Institute of Electrical
and Electronics Engineers), the largest professional organization in the world.
In addition to publishing scores of journals and running hundreds of conferences
each year, IEEE has a standardization group that develops standards in the area of
electrical engineering and computing. IEEE's 802 committee has standardized
many kinds of LANs. We will study some of its output later in this book. The ac-
tual work is done by a collection of working groups, which are listed in Fig. 1-38.
The success rate of the various 802 working groups has been low; having an 802.x
number is no guarantee of success. Still, the impact of the success stories (espe-
cially 802.3 and 802.11) on the industry and the world has been enormous.


---

<a id="page-92"></a>

<!-- Page 92 of 888 -->

80 INTRODUCTION CHAP. 1
Number Topic
### 802.1 Overview and architecture of LANs
### 802.2 ↓ Logical link control
### 802.3 * Ethernet
### 802.4 ↓ Token bus (was briefly used in manufacturing plants)
### 802.5 Token ring (IBM's entry into the LAN world)
### 802.6 ↓ Dual queue dual bus (early metropolitan area network)
### 802.7 ↓ Technical advisory group on broadband technologies
### 802.8 † Technical advisory group on fiber optic technologies
### 802.9 ↓ Isochronous LANs (for real-time applications)
### 802.10 ↓ Virtual LANs and security
### 802.11 * Wireless LANs (WiFi)
### 802.12 ↓ Demand priority (Hewlett-Packard's AnyLAN)
### 802.13 Unlucky number; nobody wanted it
### 802.14 ↓ Cable modems (defunct: an industry consortium got there first)
### 802.15 * Personal area networks (Bluetooth, Zigbee)
### 802.16 * Broadband wireless (WiMAX)
### 802.17 Resilient packet ring
### 802.18 Technical advisory group on radio regulatory issues
### 802.19 Technical advisory group on coexistence of all these standards
### 802.20 Mobile broadband wireless (similar to 802.16e)
### 802.21 Media independent handoff (for roaming over technologies)
### 802.22 Wireless regional area network
Figure 1-38. The 802 working groups. The important ones are marked with *.
The ones marked with ↓ are hibernating. The one marked with † gave up and
disbanded itself.
#### 1.6.3 Who's Who in the Internet Standards World
The worldwide Internet has its own standardization mechanisms, very dif-
ferent from those of ITU-T and ISO. The difference can be crudely summed up
by saying that the people who come to ITU or ISO standardization meetings wear
suits, while the people who come to Internet standardization meetings wear jeans
(except when they meet in San Diego, when they wear shorts and T-shirts).
ITU-T and ISO meetings are populated by corporate officials and government
civil servants for whom standardization is their job. They regard standardization
as a Good Thing and devote their lives to it. Internet people, on the other hand,
prefer anarchy as a matter of principle. However, with hundreds of millions of


---

<a id="page-93"></a>

<!-- Page 93 of 888 -->

SEC. 1.6 NETWORK STANDARDIZATION 81
people all doing their own thing, little communication can occur. Thus, standards,
however regrettable, are sometimes needed. In this context, David Clark of
M.I.T. once made a now-famous remark about Internet standardization consisting
of ''rough consensus and running code.''
When the ARPANET was set up, DoD created an informal committee to
oversee it. In 1983, the committee was renamed the IAB (Internet Activities
Board) and was given a slighter broader mission, namely, to keep the researchers
involved with the ARPANET and the Internet pointed more or less in the same
direction, an activity not unlike herding cats. The meaning of the acronym
''IAB'' was later changed to Internet Architecture Board.
Each of the approximately ten members of the IAB headed a task force on
some issue of importance. The IAB met several times a year to discuss results
and to give feedback to the DoD and NSF, which were providing most of the
funding at this time. When a standard was needed (e.g., a new routing algorithm),
the IAB members would thrash it out and then announce the change so the gradu-
ate students who were the heart of the software effort could implement it. Com-
munication was done by a series of technical reports called RFCs (Request For
Comments). RFCs are stored online and can be fetched by anyone interested in
them from www.ietf.org/rfc. They are numbered in chronological order of crea-
tion. Over 5000 now exist. We will refer to many RFCs in this book.
By 1989, the Internet had grown so large that this highly informal style no
longer worked. Many vendors by then offered TCP/IP products and did not want
to change them just because ten researchers had thought of a better idea. In the
summer of 1989, the IAB was reorganized again. The researchers were moved to
the IRTF (Internet Research Task Force), which was made subsidiary to IAB,
along with the IETF (Internet Engineering Task Force). The IAB was repopu-
lated with people representing a broader range of organizations than just the re-
search community. It was initially a self-perpetuating group, with members serv-
ing for a 2-year term and new members being appointed by the old ones. Later,
the Internet Society was created, populated by people interested in the Internet.
The Internet Society is thus in a sense comparable to ACM or IEEE. It is
governed by elected trustees who appoint the IAB's members.
The idea of this split was to have the IRTF concentrate on long-term research
while the IETF dealt with short-term engineering issues. The IETF was divided
up into working groups, each with a specific problem to solve. The chairmen of
these working groups initially met as a steering committee to direct the engineer-
ing effort. The working group topics include new applications, user information,
OSI integration, routing and addressing, security, network management, and stan-
dards. Eventually, so many working groups were formed (more than 70) that they
were grouped into areas and the area chairmen met as the steering committee.
In addition, a more formal standardization process was adopted, patterned
after ISOs. To become a Proposed Standard, the basic idea must be explained
in an RFC and have sufficient interest in the community to warrant consideration.


---

<a id="page-94"></a>

<!-- Page 94 of 888 -->

82 INTRODUCTION CHAP. 1
To advance to the Draft Standard stage, a working implementation must have
been rigorously tested by at least two independent sites for at least 4 months. If
the IAB is convinced that the idea is sound and the software works, it can declare
the RFC to be an Internet Standard. Some Internet Standards have become
DoD standards (MIL-STD), making them mandatory for DoD suppliers.
For Web standards, the World Wide Web Consortium (W3C) develops pro-
tocols and guidelines to facilitate the long-term growth of the Web. It is an indus-
try consortium led by Tim Berners-Lee and set up in 1994 as the Web really
begun to take off. W3C now has more than 300 members from around the world
and has produced more than 100 W3C Recommendations, as its standards are
called, covering topics such as HTML and Web privacy.
### 1.7 METRIC UNITS
To avoid any confusion, it is worth stating explicitly that in this book, as in
computer science in general, metric units are used instead of traditional English
units (the furlong-stone-fortnight system). The principal metric prefixes are listed
in Fig. 1-39. The prefixes are typically abbreviated by their first letters, with the
units greater than 1 capitalized (KB, MB, etc.). One exception (for historical rea-
sons) is kbps for kilobits/sec. Thus, a 1-Mbps communication line transmits 106
bits/sec and a 100-psec (or 100-ps) clock ticks every 10−10 seconds. Since milli
and micro both begin with the letter ''m,'' a choice had to be made. Normally,
''m'' is used for milli and ''µ'' (the Greek letter mu) is used for micro.
Exp. Explicit Prefix Exp. Explicit Prefix
10−3 0.001 milli 103 1,000 Kilo
10−6 0.000001 micro 106 1,000,000 Mega
10−9 0.000000001 nano 109 1,000,000,000 Giga
10−12 0.000000000001 pico 1012 1,000,000,000,000 Tera
10−15 0.000000000000001 femto 1015 1,000,000,000,000,000 Peta
10−18 0.0000000000000000001 atto 1018 1,000,000,000,000,000,000 Exa
10−21 0.0000000000000000000001 zepto 1021 1,000,000,000,000,000,000,000 Zetta
10−24 0.0000000000000000000000001 yocto 1024 1,000,000,000,000,000,000,000,000 Yotta
Figure 1-39. The principal metric prefixes.
It is also worth pointing out that for measuring memory, disk, file, and data-
base sizes, in common industry practice, the units have slightly different mean-
ings. There, kilo means 210 (1024) rather than 103 (1000) because memories are
always a power of two. Thus, a 1-KB memory contains 1024 bytes, not 1000
bytes. Note also the capital ''B'' in that usage to mean ''bytes'' (units of eight


---

<a id="page-95"></a>

<!-- Page 95 of 888 -->

SEC. 1.7 METRIC UNITS 83
bits), instead of a lowercase ''b'' that means ''bits.'' Similarly, a 1-MB memory
contains 220 (1,048,576) bytes, a 1-GB memory contains 230 (1,073,741,824)
bytes, and a 1-TB database contains 240 (1,099,511,627,776) bytes. However, a
1-kbps communication line transmits 1000 bits per second and a 10-Mbps LAN
runs at 10,000,000 bits/sec because these speeds are not powers of two. Unfor-
tunately, many people tend to mix up these two systems, especially for disk sizes.
To avoid ambiguity, in this book, we will use the symbols KB, MB, GB, and TB
for 210, 220, 230, and 240 bytes, respectively, and the symbols kbps, Mbps, Gbps,
and Tbps for 103, 106, 109, and 1012 bits/sec, respectively.
### 1.8 OUTLINE OF THE REST OF THE BOOK
This book discusses both the principles and practice of computer networking.
Most chapters start with a discussion of the relevant principles, followed by a
number of examples that illustrate these principles. These examples are usually
taken from the Internet and wireless networks such as the mobile phone network
since these are both important and very different. Other examples will be given
where relevant.
The book is structured according to the hybrid model of Fig. 1-23. Starting
with Chap. 2, we begin working our way up the protocol hierarchy beginning at
the bottom. We provide some background in the field of data communication that
covers both wired and wireless transmission systems. This material is concerned
with how to deliver information over physical channels, although we cover only
the architectural rather than the hardware aspects. Several examples of the physi-
cal layer, such as the public switched telephone network, the mobile telephone
network, and the cable television network are also discussed.
Chapters 3 and 4 discuss the data link layer in two parts. Chap. 3 looks at the
problem of how to send packets across a link, including error detection and cor-
rection. We look at DSL (used for broadband Internet access over phone lines) as
a real-world example of a data link protocol.
In Chap. 4, we examine the medium access sublayer. This is the part of the
data link layer that deals with how to share a channel between multiple com-
puters. The examples we look at include wireless, such as 802.11 and RFID, and
wired LANs such as classic Ethernet. Link layer switches that connect LANs,
such as switched Ethernet, are also discussed here.
Chapter 5 deals with the network layer, especially routing. Many routing algo-
rithms, both static and dynamic, are covered. Even with good routing algorithms,
though, if more traffic is offered than the network can handle, some packets will
be delayed or discarded. We discuss this issue from how to prevent congestion to
how to guarantee a certain quality of service. Connecting heterogeneous net-
works to form internetworks also leads to numerous problems that are discussed
here. The network layer in the Internet is given extensive coverage.


---

<a id="page-96"></a>

<!-- Page 96 of 888 -->

84 INTRODUCTION CHAP. 1
Chapter 6 deals with the transport layer. Much of the emphasis is on connec-
tion-oriented protocols and reliability, since many applications need these. Both
Internet transport protocols, UDP and TCP, are covered in detail, as are their per-
formance issues.
Chapter 7 deals with the application layer, its protocols, and its applications.
The first topic is DNS, which is the Internet's telephone book. Next comes email,
including a discussion of its protocols. Then we move on to the Web, with de-
tailed discussions of static and dynamic content, and what happens on the client
and server sides. We follow this with a look at networked multimedia, including
streaming audio and video. Finally, we discuss content-delivery networks, includ-
ing peer-to-peer technology.
Chapter 8 is about network security. This topic has aspects that relate to all
layers, so it is easiest to treat it after all the layers have been thoroughly explain-
ed. The chapter starts with an introduction to cryptography. Later, it shows how
cryptography can be used to secure communication, email, and the Web. The
chapter ends with a discussion of some areas in which security collides with
privacy, freedom of speech, censorship, and other social issues.
Chapter 9 contains an annotated list of suggested readings arranged by chap-
ter. It is intended to help those readers who would like to pursue their study of
networking further. The chapter also has an alphabetical bibliography of all the
references cited in this book.
The authors' Web site at Pearson:
http://www.pearsonhighered.com/tanenbaum
has a page with links to many tutorials, FAQs, companies, industry consortia, pro-
fessional organizations, standards organizations, technologies, papers, and more.
### 1.9 SUMMARY
Computer networks have many uses, both for companies and for individuals,
in the home and while on the move. Companies use networks of computers to
share corporate information, typically using the client-server model with
employee desktops acting as clients accessing powerful servers in the machine
room. For individuals, networks offer access to a variety of information and
entertainment resources, as well as a way to buy and sell products and services.
Individuals often access the Internet via their phone or cable providers at home,
though increasingly wireless access is used for laptops and phones. Technology
advances are enabling new kinds of mobile applications and networks with com-
puters embedded in appliances and other consumer devices. The same advances
raise social issues such as privacy concerns.
Roughly speaking, networks can be divided into LANs, MANs, WANs, and
internetworks. LANs typical cover a building and operate at high speeds. MANs


---

<a id="page-97"></a>

<!-- Page 97 of 888 -->

SEC. 1.9 SUMMARY 85
usually cover a city. An example is the cable television system, which is now used
by many people to access the Internet. WANs may cover a country or a continent.
Some of the technologies used to build these networks are point-to-point (e.g., a
cable) while others are broadcast (e.g.,wireless). Networks can be interconnected
with routers to form internetworks, of which the Internet is the largest and best
known example. Wireless networks, for example 802.11 LANs and 3G mobile
telephony, are also becoming extremely popular.
Network software is built around protocols, which are rules by which proc-
esses communicate. Most networks support protocol hierarchies, with each layer
providing services to the layer above it and insulating them from the details of the
protocols used in the lower layers. Protocol stacks are typically based either on
the OSI model or on the TCP/IP model. Both have link, network, transport, and
application layers, but they differ on the other layers. Design issues include
reliability, resource allocation, growth, security, and more. Much of this book
deals with protocols and their design.
Networks provide various services to their users. These services can range
from connectionless best-efforts packet delivery to connection-oriented guaran-
teed delivery. In some networks, connectionless service is provided in one layer
and connection-oriented service is provided in the layer above it.
Well-known networks include the Internet, the 3G mobile telephone network,
and 802.11 LANs. The Internet evolved from the ARPANET, to which other net-
works were added to form an internetwork. The present-day Internet is actually a
collection of many thousands of networks that use the TCP/IP protocol stack. The
3G mobile telephone network provides wireless and mobile access to the Internet
at speeds of multiple Mbps, and, of course, carries voice calls as well. Wireless
LANs based on the IEEE 802.11 standard are deployed in many homes and cafes
and can provide connectivity at rates in excess of 100 Mbps. New kinds of net-
works are emerging too, such as embedded sensor networks and networks based
on RFID technology.
Enabling multiple computers to talk to each other requires a large amount of
standardization, both in the hardware and software. Organizations such as ITU-T,
ISO, IEEE, and IAB manage different parts of the standardization process.
PROBLEMS
1. Imagine that you have trained your St. Bernard, Bernie, to carry a box of three 8-mm
tapes instead of a flask of brandy. (When your disk fills up, you consider that an
emergency.) These tapes each contain 7 gigabytes. The dog can travel to your side,
wherever you may be, at 18 km/hour. For what range of distances does Bernie have a
higher data rate than a transmission line whose data rate (excluding overhead) is 150
Mbps? How does your answer change if (i) Bernie's speed is doubled; (ii) each tape
capacity is doubled; (iii) the data rate of the transmission line is doubled.


---

<a id="page-98"></a>

<!-- Page 98 of 888 -->

86 INTRODUCTION CHAP. 1
2. An alternative to a LAN is simply a big timesharing system with terminals for all
users. Give two advantages of a client-server system using a LAN.
3. The performance of a client-server system is strongly influenced by two major net-
work characteristics: the bandwidth of the network (that is, how many bits/sec it can
transport) and the latency (that is, how many seconds it takes for the first bit to get
from the client to the server). Give an example of a network that exhibits high band-
width but also high latency. Then give an example of one that has both low bandwidth
and low latency.
4. Besides bandwidth and latency, what other parameter is needed to give a good charac-
terization of the quality of service offered by a network used for (i) digitized voice
traffic? (ii) video traffic? (iii) financial transaction traffic?
5. A factor in the delay of a store-and-forward packet-switching system is how long it
takes to store and forward a packet through a switch. If switching time is 10 µsec, is
this likely to be a major factor in the response of a client-server system where the cli-
ent is in New York and the server is in California? Assume the propagation speed in
copper and fiber to be 2/3 the speed of light in vacuum.
6. A client-server system uses a satellite network, with the satellite at a height of 40,000
km. What is the best-case delay in response to a request?
7. In the future, when everyone has a home terminal connected to a computer network,
instant public referendums on important pending legislation will become possible.
Ultimately, existing legislatures could be eliminated, to let the will of the people be
expressed directly. The positive aspects of such a direct democracy are fairly obvious;
discuss some of the negative aspects.
8. Five routers are to be connected in a point-to-point subnet. Between each pair of
routers, the designers may put a high-speed line, a medium-speed line, a low-speed
line, or no line. If it takes 100 ms of computer time to generate and inspect each
topology, how long will it take to inspect all of them?
9. A disadvantage of a broadcast subnet is the capacity wasted when multiple hosts at-
tempt to access the channel at the same time. As a simplistic example, suppose that
time is divided into discrete slots, with each of the n hosts attempting to use the chan-
nel with probability p during each slot. What fraction of the slots will be wasted due
to collisions?
10. What are two reasons for using layered protocols? What is one possible disadvantage
of using layered protocols?
11. The president of the Specialty Paint Corp. gets the idea to work with a local beer
brewer to produce an invisible beer can (as an anti-litter measure). The president tells
her legal department to look into it, and they in turn ask engineering for help. As a re-
sult, the chief engineer calls his counterpart at the brewery to discuss the technical
aspects of the project. The engineers then report back to their respective legal depart-
ments, which then confer by telephone to arrange the legal aspects. Finally, the two
corporate presidents discuss the financial side of the deal. What principle of a mul-
tilayer protocol in the sense of the OSI model does this communication mechanism
violate?


---

<a id="page-99"></a>

<!-- Page 99 of 888 -->

CHAP. 1 PROBLEMS 87
12. Two networks each provide reliable connection-oriented service. One of them offers
a reliable byte stream and the other offers a reliable message stream. Are these identi-
cal? If so, why is the distinction made? If not, give an example of how they differ.
13. What does ''negotiation'' mean when discussing network protocols? Give an example.
14. In Fig. 1-19, a service is shown. Are any other services implicit in this figure? If so,
where? If not, why not?
15. In some networks, the data link layer handles transmission errors by requesting that
damaged frames be retransmitted. If the probability of a frame's being damaged is p,
what is the mean number of transmissions required to send a frame? Assume that
acknowledgements are never lost.
16. A system has an n-layer protocol hierarchy. Applications generate messages of length
M bytes. At each of the layers, an h-byte header is added. What fraction of the net-
work bandwidth is filled with headers?
17. What is the main difference between TCP and UDP?
18. The subnet of Fig. 1-25(b) was designed to withstand a nuclear war. How many
bombs would it take to partition the nodes into two disconnected sets? Assume that
any bomb wipes out a node and all of the links connected to it.
19. The Internet is roughly doubling in size every 18 months. Although no one really
knows for sure, one estimate put the number of hosts on it at 600 million in 2009. Use
these data to compute the expected number of Internet hosts in the year 2018. Do you
believe this? Explain why or why not.
20. When a file is transferred between two computers, two acknowledgement strategies
are possible. In the first one, the file is chopped up into packets, which are individu-
ally acknowledged by the receiver, but the file transfer as a whole is not acknow-
ledged. In the second one, the packets are not acknowledged individually, but the en-
tire file is acknowledged when it arrives. Discuss these two approaches.
21. Mobile phone network operators need to know where their subscribers' mobile phones
(hence their users) are located. Explain why this is bad for users. Now give reasons
why this is good for users.
22. How long was a bit in the original 802.3 standard in meters? Use a transmission speed
of 10 Mbps and assume the propagation speed in coax is 2/3 the speed of light in
vacuum.
23. An image is 1600 × 1200 pixels with 3 bytes/pixel. Assume the image is
uncompressed. How long does it take to transmit it over a 56-kbps modem channel?
Over a 1-Mbps cable modem? Over a 10-Mbps Ethernet? Over 100-Mbps Ethernet?
Over gigabit Ethernet?
24. Ethernet and wireless networks have some similarities and some differences. One
property of Ethernet is that only one frame at a time can be transmitted on an Ethernet.
Does 802.11 share this property with Ethernet? Discuss your answer.
25. List two advantages and two disadvantages of having international standards for net-
work protocols.


---

<a id="page-100"></a>

<!-- Page 100 of 888 -->

88 INTRODUCTION CHAP. 1
26. When a system has a permanent part and a removable part (such as a CD-ROM drive
and the CD-ROM), it is important that the system be standardized, so that different
companies can make both the permanent and removable parts and everything still
works together. Give three examples outside the computer industry where such inter-
national standards exist. Now give three areas outside the computer industry where
they do not exist.
27. Suppose the algorithms used to implement the operations at layer k is changed. How
does this impact operations at layers k − 1 and k + 1?
28. Suppose there is a change in the service (set of operations) provided by layer k. How
does this impact services at layers k-1 and k+1?
29. Provide a list of reasons for why the response time of a client may be larger than the
best-case delay.
30. What are the disadvantages of using small, fixed-length cells in ATM?
31. Make a list of activities that you do every day in which computer networks are used.
How would your life be altered if these networks were suddenly switched off?
32. Find out what networks are used at your school or place of work. Describe the net-
work types, topologies, and switching methods used there.
33. The ping program allows you to send a test packet to a given location and see how
long it takes to get there and back. Try using ping to see how long it takes to get from
your location to several known locations. From these data, plot the one-way transit
time over the Internet as a function of distance. It is best to use universities since the
location of their servers is known very accurately. For example, berkeley.edu is in
Berkeley, California; mit.edu is in Cambridge, Massachusetts; vu.nl is in Amsterdam;
The Netherlands; www.usyd.edu.au is in Sydney, Australia; and www.uct.ac.za is in
Cape Town, South Africa.
34. Go to IETF's Web site, www.ietf.org, to see what they are doing. Pick a project you
like and write a half-page report on the problem and the proposed solution.
35. The Internet is made up of a large number of networks. Their arrangement determines
the topology of the Internet. A considerable amount of information about the Internet
topology is available on line. Use a search engine to find out more about the Internet
topology and write a short report summarizing your findings.
36. Search the Internet to find out some of the important peering points used for routing
packets in the Internet at present.
37. Write a program that implements message flow from the top layer to the bottom layer
of the 7-layer protocol model. Your program should include a separate protocol func-
tion for each layer. Protocol headers are sequence up to 64 characters. Each protocol
function has two parameters: a message passed from the higher layer protocol (a char
buffer) and the size of the message. This function attaches its header in front of the
message, prints the new message on the standard output, and then invokes the protocol
function of the lower-layer protocol. Program input is an application message (a se-
quence of 80 characters or less).
