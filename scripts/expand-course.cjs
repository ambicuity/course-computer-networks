#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const chaptersDir = path.join(root, 'chapters');
const phasesDir = path.join(root, 'phases');
const sitePhasesDir = path.join(root, 'site', 'phases');

const chapterFiles = {
  1: 'chapter-01-introduction.md',
  2: 'chapter-02-the-physical-layer.md',
  3: 'chapter-03-the-data-link-layer.md',
  4: 'chapter-04-the-medium-access-control-sublayer.md',
  5: 'chapter-05-the-network-layer.md',
  6: 'chapter-06-the-transport-layer.md',
  7: 'chapter-07-the-application-layer.md',
  8: 'chapter-08-network-security.md',
};

const phaseDefs = [
  { id: 0, name: 'Networking Lab & Foundations', slug: '00-networking-lab-and-foundations', desc: 'Build the local lab, packet-reading habits, and measurement discipline used throughout the course.', lessons: [] },
  { id: 1, name: 'Introduction & Network Architecture', slug: '01-introduction-and-architecture', desc: 'Map users, devices, standards, layers, and reference models before diving into protocols.', lessons: [] },
  { id: 2, name: 'Physical Layer & Transmission Systems', slug: '02-physical-layer-and-transmission-systems', desc: 'Study signals, media, modulation, multiplexing, telephony, mobile systems, and cable access.', lessons: [] },
  { id: 3, name: 'Data Link Foundations', slug: '03-data-link-foundations', desc: 'Turn raw bit streams into frames with link services, framing, error control, and flow control.', lessons: [] },
  { id: 4, name: 'Error Control & Link Protocols', slug: '04-error-control-and-link-protocols', desc: 'Build error-detection, correction, stop-and-wait, and sliding-window protocols from first principles.', lessons: [] },
  { id: 5, name: 'Medium Access Protocols', slug: '05-medium-access-protocols', desc: 'Coordinate shared media with ALOHA, CSMA, collision-free, limited-contention, and wireless MAC protocols.', lessons: [] },
  { id: 6, name: 'Ethernet, Wireless LANs & Switching', slug: '06-ethernet-wireless-lans-and-switching', desc: 'Inspect Ethernet, 802.11, broadband wireless, Bluetooth, RFID, bridges, switches, and VLANs.', lessons: [] },
  { id: 7, name: 'Network Layer Design & Routing', slug: '07-network-layer-design-and-routing', desc: 'Route packets with datagrams, virtual circuits, shortest paths, distance vectors, link state, and multicast.', lessons: [] },
  { id: 8, name: 'Congestion, QoS & Internetworking', slug: '08-congestion-qos-and-internetworking', desc: 'Control congestion, shape traffic, schedule packets, connect networks, fragment packets, and reason about QoS.', lessons: [] },
  { id: 9, name: 'Internet Protocols & IP Operations', slug: '09-internet-protocols-and-ip-operations', desc: 'Work through IPv4, addressing, IPv6, ICMP/ARP/DHCP, MPLS, OSPF, BGP, multicast, and Mobile IP.', lessons: [] },
  { id: 10, name: 'Transport Services & Protocol Mechanics', slug: '10-transport-services-and-protocol-mechanics', desc: 'Build process-to-process communication with addressing, connection setup, reliability, buffering, and multiplexing.', lessons: [] },
  { id: 11, name: 'TCP, UDP, Congestion & Performance', slug: '11-tcp-udp-congestion-and-performance', desc: 'Trace UDP, TCP state, congestion control, performance limits, and delay-tolerant networking.', lessons: [] },
  { id: 12, name: 'DNS, Email & Web Protocols', slug: '12-dns-email-and-web-protocols', desc: 'Debug names, mail, web architecture, static and dynamic pages, HTTP, mobile web, and search.', lessons: [] },
  { id: 13, name: 'Streaming, Real-Time Media & Content Delivery', slug: '13-streaming-real-time-media-and-content-delivery', desc: 'Understand audio/video encoding, streaming, conferencing, server farms, CDNs, and peer-to-peer distribution.', lessons: [] },
  { id: 14, name: 'Cryptography Foundations', slug: '14-cryptography-foundations', desc: 'Learn classical crypto, one-time pads, DES, AES, cipher modes, public-key algorithms, and cryptanalysis.', lessons: [] },
  { id: 15, name: 'Keys, Signatures & Authentication', slug: '15-keys-signatures-and-authentication', desc: 'Manage identity with signatures, digests, certificates, PKI, shared secrets, Diffie-Hellman, KDCs, Kerberos, and public-key auth.', lessons: [] },
  { id: 16, name: 'Secure Communication & Web Security', slug: '16-secure-communication-and-web-security', desc: 'Apply security to IPsec, firewalls, VPNs, wireless, email, secure naming, TLS, mobile code, and social issues.', lessons: [] },
  { id: 17, name: 'Integrated Troubleshooting Labs', slug: '17-integrated-troubleshooting-labs', desc: 'Combine layers into realistic packet-level investigations and operational runbooks.', lessons: [] },
  { id: 18, name: 'Design & Production Network Labs', slug: '18-design-and-production-network-labs', desc: 'Design small networks, policy controls, measurements, monitoring, and production-ready network documentation.', lessons: [] },
  { id: 19, name: 'Capstone Projects', slug: '19-capstone-projects', desc: 'Ship complete, portfolio-grade networking projects that prove end-to-end understanding.', lessons: [] },
];

const phaseById = Object.fromEntries(phaseDefs.map(p => [p.id, p]));

function titleCase(s) {
  const small = new Set(['and', 'or', 'the', 'of', 'to', 'in', 'for', 'with', 'a', 'an', 'on', 'over', 'at', 'by']);
  return s.replace(/\*/g, '').replace(/\s+/g, ' ').trim().split(' ').map((word, idx) => {
    const raw = word.replace(/^[-:]+|[-:]+$/g, '');
    if (!raw) return word;
    if (/^[A-Z0-9./-]+$/.test(raw) && raw.length <= 8) return raw;
    const lower = raw.toLowerCase();
    if (idx > 0 && small.has(lower)) return lower;
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }).join(' ')
    .replace(/Dns/g, 'DNS')
    .replace(/Tcp/g, 'TCP')
    .replace(/Udp/g, 'UDP')
    .replace(/Ipsec/g, 'IPsec')
    .replace(/Ipv4/g, 'IPv4')
    .replace(/Ipv6/g, 'IPv6')
    .replace(/Http/g, 'HTTP')
    .replace(/\bSsl\b/g, 'SSL')
    .replace(/\bTls\b/g, 'TLS')
    .replace(/\bRsa\b/g, 'RSA')
    .replace(/\bDes\b/g, 'DES')
    .replace(/\bAes\b/g, 'AES')
    .replace(/\bPgp\b/g, 'PGP')
    .replace(/\bMime\b/g, 'MIME')
    .replace(/S\/mime/gi, 'S/MIME')
    .replace(/Ospf/g, 'OSPF')
    .replace(/Bgp/g, 'BGP')
    .replace(/Mpls/g, 'MPLS')
    .replace(/Rfid/g, 'RFID')
    .replace(/Adsl/g, 'ADSL')
    .replace(/Sonet/g, 'SONET')
    .replace(/\bLans\b/g, 'LANs')
    .replace(/\bWans\b/g, 'WANs')
    .replace(/Wi-fi/g, 'Wi-Fi')
    .replace(/Wifi/g, 'WiFi')
    .replace(/Cdn/g, 'CDN')
    .replace(/Qos/g, 'QoS')
    .replace(/DESign/g, 'Design')
    .replace(/\bGo-back-n\b/g, 'Go-Back-N')
    .replace(/\bMedium-earth\b/g, 'Medium-Earth')
    .replace(/\bLow-earth\b/g, 'Low-Earth')
    .replace(/\bFirst-generation \(1g\)/g, 'First-Generation (1G)')
    .replace(/\bThird-generation \(3g\)/g, 'Third-Generation (3G)')
    .replace(/\bOne-bit\b/g, 'One-Bit')
    .replace(/\bStop-and-wait\b/g, 'Stop-and-Wait')
    .replace(/\bError-free\b/g, 'Error-Free')
    .replace(/\bError-correcting\b/g, 'Error-Correcting')
    .replace(/\bError-detecting\b/g, 'Error-Detecting')
    .replace(/\bLimited-contention\b/g, 'Limited-Contention')
    .replace(/\bConnection-oriented\b/g, 'Connection-Oriented')
    .replace(/\bConnectionless\b/g, 'Connectionless')
    .replace(/\bVirtual-circuit\b/g, 'Virtual-Circuit')
    .replace(/\bStore-and-forward\b/g, 'Store-and-Forward');
}

function slugify(s) {
  return s.toLowerCase()
    .replace(/ssl-the-secure-sockets-layer/, 'ssl-secure-sockets-layer')
    .replace(/dns-the-domain-name-system/, 'dns-domain-name-system')
    .replace(/http-the-hypertext-transfer-protocol/, 'http-hypertext-transfer-protocol')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 70);
}

function readChapter(ch) {
  return fs.readFileSync(path.join(chaptersDir, chapterFiles[ch]), 'utf8');
}

function parseHeadings(ch) {
  const text = readChapter(ch);
  const matches = [];
  const re = /^(#{3,4})\s+(\d+\.\d+(?:\.\d+)?)\s+(.+)$/gm;
  let m;
  while ((m = re.exec(text))) {
    const level = m[1].length;
    const num = m[2];
    let title = m[3].trim().replace(/,\s*\d+$/, '').replace(/\*+$/g, '').trim();
    if (/SUMMARY/i.test(title)) continue;
    if (!num.startsWith(String(ch) + '.')) continue;
    matches.push({ level, num, title: titleCase(title), rawTitle: title, index: m.index });
  }

  return matches.filter((h, idx) => {
    const next = matches[idx + 1];
    h.end = next ? next.index : text.length;
    return h.level === 4;
  }).map(h => ({ ...h, chapter: ch, file: chapterFiles[ch], text: text.slice(h.index, h.end).trim() }));
}

function extractSection(chapter, sectionNum) {
  const text = readChapter(chapter);
  const escaped = sectionNum.replace(/\./g, '\\.');
  const startRe = new RegExp('^#{3,4}\\s+' + escaped + '\\s+.+$', 'm');
  const start = text.search(startRe);
  if (start < 0) return '';
  const rest = text.slice(start);
  const nextRe = /^#{3,4}\s+\d+\.\d+(?:\.\d+)?\s+.+$/gm;
  nextRe.exec(rest);
  const next = nextRe.exec(rest);
  return rest.slice(0, next ? next.index : rest.length).trim();
}

function excerpt(text, max = 900) {
  const cleaned = text
    .split('\n')
    .filter(line => !/^#{3,4}\s+/.test(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (cleaned.length <= max) return cleaned.replace(/\s+$/g, '');
  const window = cleaned.slice(0, max);
  const lastSentence = Math.max(
    window.lastIndexOf('. '),
    window.lastIndexOf('! '),
    window.lastIndexOf('? '),
    window.lastIndexOf('.\n'),
    window.lastIndexOf('!\n'),
    window.lastIndexOf('?\n')
  );
  const cut = lastSentence > max * 0.5 ? lastSentence + 1 : (window.lastIndexOf(' ') > 0 ? window.lastIndexOf(' ') : max);
  return cleaned.slice(0, cut).replace(/\s+$/g, '');
}

function addManual(phaseId, title, type, lang, bodyKind) {
  phaseById[phaseId].lessons.push({ title, type, lang, manual: true, bodyKind, source: null });
}

function addSource(phaseId, item, type = 'Learn', lang = 'Wireshark, diagrams') {
  phaseById[phaseId].lessons.push({ title: item.title, type, lang, source: item });
}

function addGrouped(phaseId, title, items, type = 'Learn', lang = 'Wireshark, diagrams') {
  phaseById[phaseId].lessons.push({ title, type, lang, sourceGroup: items });
}

function byNums(ch, nums) {
  const headings = parseHeadings(ch);
  const map = Object.fromEntries(headings.map(h => [h.num, h]));
  return nums.map(n => map[n]).filter(Boolean);
}

function addAll(phaseId, ch, nums, type = 'Learn', lang = 'Wireshark, diagrams') {
  byNums(ch, nums).forEach(item => addSource(phaseId, item, type, lang));
}

function buildPlan() {
  [
    ['Network Lab Environment', 'Build', 'Python, shell, Wireshark', 'lab'],
    ['Packet Capture Workflow', 'Build', 'Wireshark, tcpdump', 'lab'],
    ['Reading RFCs and Standards', 'Learn', 'RFCs, standards', 'study'],
    ['Layered Debugging Method', 'Build', 'Python, shell', 'debug'],
    ['Measurement Basics', 'Build', 'Python', 'measure'],
    ['Trace Annotation Runbook', 'Build', 'Wireshark, Markdown', 'artifact'],
    ['Subnetting and Address Notation Primer', 'Build', 'Python, shell', 'addressing'],
    ['Course Portfolio Setup', 'Build', 'Markdown, Git', 'portfolio'],
  ].forEach(x => addManual(0, ...x));

  addAll(1, 1, ['1.1.1','1.1.2','1.1.3','1.1.4','1.2.1','1.2.2','1.2.3','1.2.4','1.2.5','1.3.1','1.3.2','1.3.3','1.3.4','1.3.5','1.4.1','1.4.2','1.4.3','1.4.4','1.4.5','1.4.6','1.5.1','1.5.2','1.5.3','1.5.4','1.6.1','1.6.2','1.6.3'], 'Learn', 'Diagrams, standards');
  addManual(1, 'Metric Units and Network Numbers', 'Build', 'Python', 'metrics');
  addManual(1, 'Architecture Review Lab', 'Build', 'Diagrams, Markdown', 'review');

  addAll(2, 2, ['2.1.1','2.1.2','2.1.3','2.2.1','2.2.2','2.2.3','2.2.4','2.2.5','2.3.1','2.3.2','2.3.3','2.3.4','2.3.5','2.4.1','2.4.2','2.4.3','2.4.4','2.5.1','2.5.2','2.5.3','2.5.4','2.5.5','2.6.1','2.6.2','2.6.3','2.6.4','2.6.5','2.7.1','2.7.2','2.7.3','2.8.1','2.8.2','2.8.3','2.8.4','2.8.5'], 'Learn', 'Python, signal diagrams');
  addManual(2, 'Physical Layer Measurement Lab', 'Build', 'Python, shell', 'measure');
  addManual(2, 'Modulation and Multiplexing Review Lab', 'Build', 'Python', 'review');

  addAll(3, 3, ['3.1.1','3.1.2','3.1.3','3.1.4'], 'Learn', 'Wireshark, diagrams');
  addManual(3, 'Frame Anatomy Lab', 'Build', 'Wireshark, Python', 'lab');
  addManual(3, 'Link-Layer Failure Modes', 'Build', 'Wireshark, runbooks', 'debug');

  addAll(4, 3, ['3.2.1','3.2.2','3.3.1','3.3.2','3.3.3','3.4.1','3.4.2','3.4.3','3.5.1','3.5.2'], 'Build', 'Python, Wireshark');
  addManual(4, 'CRC and Checksum Lab', 'Build', 'Python', 'lab');
  addManual(4, 'Sliding Window Simulator Lab', 'Build', 'Python', 'lab');

  addAll(5, 4, ['4.1.1','4.1.2','4.2.1','4.2.2','4.2.3','4.2.4','4.2.5'], 'Build', 'Python, models');
  addManual(5, 'ALOHA and CSMA Simulator Lab', 'Build', 'Python', 'lab');
  addManual(5, 'Wireless Hidden Terminal Lab', 'Build', 'Wireshark, diagrams', 'lab');

  addAll(6, 4, ['4.3.1','4.3.2','4.3.3','4.3.4','4.3.5','4.3.6','4.3.7','4.3.8','4.4.1','4.4.2','4.4.3','4.4.4','4.4.5','4.5.1','4.5.2','4.5.3','4.5.4','4.5.5','4.6.1','4.6.2','4.6.3','4.6.4','4.6.5','4.6.6','4.7.1','4.7.2','4.7.3','4.7.4','4.8.1','4.8.2','4.8.3','4.8.4','4.8.5'], 'Learn', 'Wireshark, diagrams');
  addManual(6, 'Ethernet Frame Trace Lab', 'Build', 'Wireshark, Python', 'lab');
  addManual(6, 'Bridge Learning Table Lab', 'Build', 'Python, diagrams', 'lab');

  addAll(7, 5, ['5.1.1','5.1.2','5.1.3','5.1.4','5.1.5','5.2.1','5.2.2','5.2.3','5.2.4','5.2.5','5.2.6','5.2.7','5.2.8','5.2.9','5.2.10','5.2.11'], 'Build', 'Python, routing traces');
  addManual(7, 'Shortest Path Routing Lab', 'Build', 'Python', 'lab');
  addManual(7, 'Distance Vector Failure Lab', 'Build', 'Python', 'debug');
  addManual(7, 'Link State Flooding Lab', 'Build', 'Python', 'lab');

  addAll(8, 5, ['5.3.1','5.3.2','5.3.3','5.3.4','5.3.5','5.4.1','5.4.2','5.4.3','5.4.4','5.4.5','5.4.6','5.5.1','5.5.2','5.5.3','5.5.4','5.5.5'], 'Build', 'Python, packet traces');
  addManual(8, 'Queueing and Congestion Lab', 'Build', 'Python', 'lab');
  addManual(8, 'Fragmentation and MTU Lab', 'Build', 'ping, tracepath, Python', 'lab');

  addAll(9, 5, ['5.6.1','5.6.2','5.6.3','5.6.4','5.6.5','5.6.6','5.6.7','5.6.8','5.6.9'], 'Build', 'IP tools, Wireshark');
  addManual(9, 'IPv4 Header Decoder Lab', 'Build', 'Python', 'lab');
  addManual(9, 'Subnetting and CIDR Drill', 'Build', 'Python', 'addressing');
  addManual(9, 'ICMP and Traceroute Lab', 'Build', 'ping, traceroute, Wireshark', 'lab');
  addManual(9, 'OSPF and BGP Policy Lab', 'Build', 'Diagrams, routing tables', 'lab');

  addAll(10, 6, ['6.1.1','6.1.2','6.1.3','6.1.4','6.1.5','6.2.1','6.2.2','6.2.3','6.2.4','6.2.5','6.2.6','6.2.7','6.2.8'], 'Build', 'Python, sockets');
  addManual(10, 'Socket Lifecycle Lab', 'Build', 'Python', 'lab');
  addManual(10, 'Reliable Transport State Machine Lab', 'Build', 'Python', 'lab');

  addAll(11, 6, ['6.3.1','6.3.2','6.3.3','6.3.4','6.3.5','6.3.6','6.3.7','6.3.8','6.4.1','6.4.2','6.4.3','6.5.1','6.5.2','6.5.3','6.5.4','6.5.5','6.5.6','6.5.7','6.5.8','6.5.9','6.5.10','6.5.11','6.6.1','6.6.2','6.6.3','6.6.4','6.6.5','6.6.6','6.7.1','6.7.2'], 'Build', 'Python, Wireshark');
  addManual(11, 'TCP Three-Way Handshake Lab', 'Build', 'Wireshark, Python', 'lab');
  addManual(11, 'TCP Congestion Trace Lab', 'Build', 'Wireshark, Python', 'lab');

  addAll(12, 7, ['7.1.1','7.1.2','7.1.3','7.2.1','7.2.2','7.2.3','7.2.4','7.2.5','7.3.1','7.3.2','7.3.3','7.3.4','7.3.5','7.3.6'], 'Build', 'dig, HTTP, Wireshark');
  addManual(12, 'DNS Trace Lab', 'Build', 'dig, Wireshark', 'lab');
  addManual(12, 'HTTP Request Lifecycle Lab', 'Build', 'curl, browser tools', 'lab');

  addAll(13, 7, ['7.4.1','7.4.2','7.4.3','7.4.4','7.4.5','7.5.1','7.5.2','7.5.3','7.5.4'], 'Learn', 'Wireshark, diagrams');
  addManual(13, 'Streaming Buffer Lab', 'Build', 'Python', 'lab');
  addManual(13, 'CDN Path Analysis Lab', 'Build', 'dig, traceroute', 'lab');

  addAll(14, 8, ['8.1.1','8.1.2','8.1.3','8.1.4','8.1.5','8.2.1','8.2.2','8.2.3','8.2.4','8.2.5','8.3.1','8.3.2'], 'Build', 'Python, crypto diagrams');
  addManual(14, 'Classical Cipher Lab', 'Build', 'Python', 'lab');
  addManual(14, 'AES Mode Misuse Lab', 'Build', 'Python', 'debug');

  addAll(15, 8, ['8.4.1','8.4.2','8.4.3','8.4.4','8.5.1','8.5.2','8.5.3','8.7.1','8.7.2','8.7.3','8.7.4','8.7.5'], 'Build', 'Python, protocol traces');
  addManual(15, 'Certificate Chain Inspection Lab', 'Build', 'openssl, browser tools', 'lab');
  addManual(15, 'Kerberos Message Flow Lab', 'Build', 'Diagrams, traces', 'lab');

  addAll(16, 8, ['8.6.1','8.6.2','8.6.3','8.6.4','8.8.1','8.8.2','8.9.1','8.9.2','8.9.3','8.9.4','8.10.1','8.10.2','8.10.3'], 'Learn', 'openssl, browser tools, Wireshark');
  addManual(16, 'TLS Handshake Lab', 'Build', 'openssl, Wireshark', 'lab');
  addManual(16, 'Firewall Policy Review Lab', 'Build', 'Diagrams, runbooks', 'lab');

  ['Physical-to-Application Outage Trace','DNS Works but HTTP Fails','High Latency Video Call','Intermittent Wi-Fi Loss','MTU Black Hole','TCP Retransmission Storm','TLS Certificate Failure','Routing Loop Investigation','Slow Web Page Waterfall','Mail Delivery Failure'].forEach((t, i) => addManual(17, t, 'Lab', i % 2 ? 'Wireshark, shell' : 'Python, Wireshark', 'integrated'));
  ['Small Campus Network Design','Home Network Security Baseline','Cloud VPC Connectivity Plan','Branch Office VPN Plan','Monitoring and Alerting Runbook','Address Plan and VLAN Design','QoS Policy for Voice and Video','Incident Response Packet Kit','Network Documentation Portfolio','Production Readiness Review'].forEach((t, i) => addManual(18, t, 'Project', i % 2 ? 'Diagrams, Markdown' : 'Python, shell', 'project'));
  ['Protocol Trace Portfolio','Design a Small Campus Network','Debug a Realistic Outage','Build a Minimal Reliable Protocol','Implement a Routing Simulator','Analyze an HTTPS Failure','Design a Secure Remote Access Plan','Build a DNS and HTTP Diagnostic Tool'].forEach((t, i) => addManual(19, t, 'Capstone', i % 2 ? 'Diagrams, Wireshark' : 'Python, shell', 'capstone'));
}

const targetLessonsByPhase = {
  0: 6,
  1: 10,
  2: 12,
  3: 6,
  4: 8,
  5: 7,
  6: 14,
  7: 14,
  8: 12,
  9: 10,
  10: 10,
  11: 13,
  12: 10,
  13: 8,
  14: 10,
  15: 9,
  16: 10,
  17: 7,
  18: 7,
  19: 6,
};

function lessonSources(lesson) {
  if (lesson.source) return [lesson.source];
  if (lesson.sourceGroup) return lesson.sourceGroup;
  return [];
}

function mergeLessonChunk(chunk) {
  if (chunk.length === 1) return chunk[0];

  const first = chunk[0];
  const last = chunk[chunk.length - 1];
  const sources = chunk.flatMap(lessonSources);
  const hasCapstone = chunk.some(l => l.type === 'Capstone');
  const hasProject = chunk.some(l => l.type === 'Project');
  const hasLab = chunk.some(l => l.type === 'Lab');
  const hasBuild = chunk.some(l => l.type === 'Build');
  const type = hasCapstone ? 'Capstone' : hasProject ? 'Project' : hasLab ? 'Lab' : hasBuild ? 'Build' : 'Learn';
  const lang = [...new Set(chunk.flatMap(l => l.lang.split(',').map(x => x.trim()).filter(Boolean)))].slice(0, 4).join(', ');
  const title = first.title === last.title ? first.title : `${first.title} to ${last.title}`;

  return {
    title,
    type,
    lang: lang || first.lang,
    sourceGroup: sources.length ? sources : undefined,
    manual: sources.length ? false : true,
    bodyKind: sources.length ? undefined : 'integrated',
  };
}

function compressLessons(lessons, target) {
  if (!target || lessons.length <= target) return lessons;

  const compressed = [];
  for (let i = 0; i < target; i++) {
    const start = Math.floor(i * lessons.length / target);
    const end = Math.floor((i + 1) * lessons.length / target);
    compressed.push(mergeLessonChunk(lessons.slice(start, end)));
  }
  return compressed;
}

function compressPlan() {
  phaseDefs.forEach(phase => {
    phase.lessons = compressLessons(phase.lessons, targetLessonsByPhase[phase.id]);
  });
}

function lessonPath(phase, lesson, idx) {
  return path.join(phasesDir, phase.slug, String(idx + 1).padStart(2, '0') + '-' + slugify(lesson.title));
}

function lessonRelPath(phase, lesson, idx) {
  return 'phases/' + phase.slug + '/' + String(idx + 1).padStart(2, '0') + '-' + slugify(lesson.title) + '/';
}

function sourceInfo(lesson) {
  if (lesson.source) return { chapter: lesson.source.chapter, file: lesson.source.file, nums: [lesson.source.num], title: lesson.source.title, text: lesson.source.text };
  if (lesson.sourceGroup) {
    return { chapter: lesson.sourceGroup[0].chapter, file: lesson.sourceGroup[0].file, nums: lesson.sourceGroup.map(s => s.num), title: lesson.title, text: lesson.sourceGroup.map(s => s.text).join('\n\n') };
  }
  return null;
}

function lessonDoc(phase, lesson, idx) {
  const src = sourceInfo(lesson);
  const minutes = lesson.type === 'Capstone' ? 180 : lesson.type === 'Project' ? 150 : lesson.type === 'Lab' ? 120 : lesson.type === 'Build' ? 90 : 75;
  const artifact = slugify(lesson.title);
  const lines = [];
  lines.push(`# ${lesson.title}`);
  lines.push('');
  lines.push('> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.');
  lines.push('');
  lines.push(`**Type:** ${lesson.type}`);
  lines.push(`**Languages:** ${lesson.lang}`);
  lines.push(`**Prerequisites:** Earlier lessons in Phase ${phase.id}`);
  lines.push(`**Time:** ~${minutes} minutes`);
  lines.push('');
  lines.push('## Learning Objectives');
  if (src) {
    src.nums.forEach(num => lines.push(`- Explain source section ${num} in operational terms`));
    lines.push('- Identify the packet fields, timers, counters, state, or logs that prove the behavior');
    lines.push('- Connect the concept to at least one realistic failure mode');
    lines.push('- Produce a reusable trace annotation, runbook, diagram, script, or prompt');
  } else {
    lines.push('- Set up a practical networking workflow that can be reused across later lessons');
    lines.push('- Capture or describe evidence instead of relying on guesses');
    lines.push('- Produce a reusable artifact for your course portfolio');
  }
  lines.push('');
  lines.push('## The Problem');
  lines.push(`${lesson.title} matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.`);
  lines.push('');
  lines.push('This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.');
  lines.push('');
  lines.push('## The Concept');
  if (src) {
    lines.push('');
    lines.push(`Source material: [\`chapters/${src.file}\`](../../../chapters/${src.file}) section${src.nums.length > 1 ? 's' : ''} \`${src.nums.join('`, `')}\`.`);
    lines.push('');
    lines.push(excerpt(src.text, 1200) || 'Read the linked source section and summarize the mechanism in your own words.');
  } else {
    lines.push('');
    lines.push('This is a hands-on course lesson. Use it to create the setup, measurement, design, or troubleshooting artifact named in the title.');
  }
  lines.push('');
  lines.push('### Working Model');
  lines.push('');
  lines.push('```text');
  lines.push('user-visible symptom');
  lines.push('        |');
  lines.push('        v');
  lines.push(`network mechanism: ${lesson.title}`);
  lines.push('        |');
  lines.push('        v');
  lines.push('observable evidence: packet fields, counters, timers, logs, or state');
  lines.push('        |');
  lines.push('        v');
  lines.push('engineering decision: explain, tune, reroute, retry, secure, or redesign');
  lines.push('```');
  lines.push('');
  lines.push('## Build It');
  lines.push('');
  lines.push('1. Write the one-paragraph mechanism summary in your own words.');
  lines.push('2. Draw the packet flow, state machine, queue, address mapping, or trust boundary.');
  lines.push('3. Identify the exact evidence that would confirm normal behavior.');
  lines.push('4. Identify one failure mode and the smallest test that would confirm or reject it.');
  if (lesson.type === 'Build' || lesson.type === 'Lab' || lesson.type === 'Project' || lesson.type === 'Capstone') {
    lines.push('5. Run or adapt `code/main.py` when present, then replace sample observations with your own evidence.');
  }
  lines.push('');
  lines.push('## Use It');
  lines.push('');
  lines.push('| Task | Evidence | What Good Looks Like |');
  lines.push('|---|---|---|');
  lines.push('| Locate the layer | Packet headers, protocol messages, counters | You can explain why this is not merely an application symptom |');
  lines.push('| Explain normal behavior | Source rules plus a clean trace or diagram | Observed fields and state transitions match the model |');
  lines.push('| Diagnose abnormal behavior | Before/after traces, timing, errors | The failure hypothesis predicts the evidence |');
  lines.push('');
  lines.push('## Ship It');
  lines.push('');
  lines.push('Create one artifact under `outputs/`:');
  lines.push('');
  lines.push('- A trace annotation checklist');
  lines.push('- A one-page failure-mode runbook');
  lines.push('- A protocol/state diagram');
  lines.push('- A small parser, calculator, simulator, or diagnostic script');
  lines.push('- A study prompt that teaches the topic from evidence');
  lines.push('');
  lines.push(`Start with [\`outputs/prompt-${artifact}.md\`](../outputs/prompt-${artifact}.md).`);
  lines.push('');
  lines.push('## Exercises');
  lines.push('');
  lines.push('1. List the source rules or assumptions that matter most for this topic.');
  lines.push('2. Capture or sketch one normal trace and annotate the important fields.');
  lines.push('3. Describe one realistic failure and the evidence you would collect first.');
  lines.push('4. Compare this mechanism with the layer directly above or below it.');
  lines.push('');
  lines.push('## Key Terms');
  lines.push('');
  lines.push('| Term | What people say | What it actually means |');
  lines.push('|---|---|---|');
  lines.push(`| ${lesson.title} | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |`);
  if (src) lines.push(`| Section ${src.nums[0]} | A book subsection | The authoritative source slice for this lesson |`);
  lines.push('| Artifact | Homework output | A reusable operational tool you can apply later |');
  lines.push('');
  lines.push('## Further Reading');
  lines.push('');
  lines.push('- The full source chapter linked above');
  lines.push('- Relevant RFCs or standards named in the source section');
  lines.push('- Wireshark display filter reference for packet evidence');
  return lines.join('\n') + '\n';
}

function promptDoc(phase, lesson, idx) {
  const slug = slugify(lesson.title);
  return `---\nname: prompt-${slug}\ndescription: Turn ${lesson.title} into an evidence-first networking artifact\nphase: ${phase.id}\nlesson: ${idx + 1}\n---\n\nYou are helping me study ${lesson.title} in a computer networks course.\n\nUse this structure:\n1. Explain the mechanism in one paragraph.\n2. List the packet fields, counters, timers, logs, or state that prove it.\n3. Give one normal trace checklist.\n4. Give one realistic failure mode and the smallest diagnostic test.\n5. Produce a reusable runbook, diagram outline, parser idea, or study drill.\n\nKeep the answer practical and tied to observable network evidence.\n`;
}

function quizJson(lesson) {
  return JSON.stringify({ questions: [
    { stage: 'pre', question: `What is the main goal of studying ${lesson.title}?`, options: ['Memorize a heading', 'Connect the mechanism to observable network evidence', 'Avoid packet traces', 'Replace every lower layer'], correct: 1, explanation: 'The course is evidence-first: protocol rules should map to fields, timing, counters, logs, or state.' },
    { stage: 'post', question: `Which artifact best proves understanding of ${lesson.title}?`, options: ['A copied paragraph with no evidence', 'An annotated trace, runbook, diagram, or script tied to the mechanism', 'A list of unrelated acronyms', 'A screenshot without explanation'], correct: 1, explanation: 'Every lesson ships a reusable artifact that connects concept to practical network work.' },
    { stage: 'post', question: 'Why debug layer by layer?', options: ['It prevents symptom-level guessing and narrows evidence cleanly', 'It makes every issue a DNS issue', 'It removes the need for measurements', 'It only works in labs'], correct: 0, explanation: 'Layered debugging separates physical, link, network, transport, application, and security evidence.' }
  ] }, null, 2) + '\n';
}

function codeMain(lesson) {
  const safe = lesson.title.replace(/'/g, "\\'");
  return `#!/usr/bin/env python3\n\nLESSON = '${safe}'\n\nobservations = [\n    ('symptom', 'replace with the user-visible problem'),\n    ('layer', 'replace with the suspected layer'),\n    ('evidence', 'replace with packet fields, counters, timers, logs, or state'),\n    ('decision', 'replace with the engineering decision'),\n]\n\n\ndef main():\n    print(f'Lesson: {LESSON}')\n    for key, value in observations:\n        print(f'{key}: {value}')\n\n\nif __name__ == '__main__':\n    main()\n`;
}

function phaseReadme(phase) {
  const lines = [`# Phase ${phase.id}: ${phase.name}`, '', phase.desc, '', '| # | Lesson | Type | Lang |', '|---|---|---|---|'];
  phase.lessons.forEach((lesson, idx) => {
    const dir = String(idx + 1).padStart(2, '0') + '-' + slugify(lesson.title);
    lines.push(`| ${String(idx + 1).padStart(2, '0')} | [${lesson.title}](${dir}/) | ${lesson.type} | ${lesson.lang} |`);
  });
  return lines.join('\n') + '\n';
}

function badgeColor() { return '2F80ED'; }

function readme(totalLessons) {
  const hours = Math.round(totalLessons * 1.35);
  const lines = [];
  lines.push('<p align="center">');
  lines.push('  <img src="assets/banner.svg" alt="Course: Computer Networks banner" width="100%">');
  lines.push('</p>');
  lines.push('');
  lines.push('<p align="center">');
  lines.push(`  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-1B365D?style=flat-square&labelColor=F7FBFF" alt="MIT License"></a>`);
  lines.push(`  <a href="ROADMAP.md"><img src="https://img.shields.io/badge/lessons-${totalLessons}-${badgeColor()}?style=flat-square&labelColor=F7FBFF" alt="${totalLessons} lessons"></a>`);
  lines.push(`  <a href="#contents"><img src="https://img.shields.io/badge/phases-${phaseDefs.length}-${badgeColor()}?style=flat-square&labelColor=F7FBFF" alt="${phaseDefs.length} phases"></a>`);
  lines.push('</p>');
  lines.push('');
  lines.push('<p align="center"><sub>by <b>Ritesh Rana</b> &nbsp;·&nbsp; <a href="mailto:contact@riteshrana.engineer">contact@riteshrana.engineer</a></sub></p>');
  lines.push('');
  lines.push('# Course: Computer Networks');
  lines.push('');
  lines.push('Computer networks are layered systems with measurable behavior: signals, frames, packets, segments, names, requests, keys, timers, queues, and failures. This curriculum turns the supplied open networking material into a deep, packet-first course you can read, trace, build, and debug.');
  lines.push('');
  lines.push(`${totalLessons} lessons. ${phaseDefs.length} phases. ~${hours} hours. Every lesson ships a reusable artifact: a trace annotation, runbook, diagram, script, or study prompt.`);
  lines.push('');
  lines.push('## How This Works');
  lines.push('');
  lines.push('The source material has been converted into chapter Markdown under [`chapters/`](chapters/). The course wraps that material in the same style as the AI Engineering course: many focused lessons, consistent folders, `docs/en.md`, `quiz.json`, runnable starters for build-heavy topics, and one reusable output artifact per lesson.');
  lines.push('');
  lines.push('Each lesson follows the same loop:');
  lines.push('');
  lines.push('1. Read the source section.');
  lines.push('2. Build the mental model.');
  lines.push('3. Inspect packet-level or measurement evidence.');
  lines.push('4. Explain a failure mode.');
  lines.push('5. Ship a reusable artifact.');
  lines.push('');
  lines.push('## The Shape of the Curriculum');
  lines.push('');
  lines.push('```mermaid');
  lines.push('flowchart TB');
  for (let i = 0; i < phaseDefs.length - 1; i++) lines.push(`  P${i}["Phase ${i} - ${phaseDefs[i].name}"] --> P${i + 1}["Phase ${i + 1} - ${phaseDefs[i + 1].name}"]`);
  lines.push('```');
  lines.push('');
  lines.push('## Getting Started');
  lines.push('');
  lines.push('Open the roadmap, then start with Phase 0 if you want a lab-driven path. If you already know Wireshark, tcpdump, and basic layering, jump to Phase 1.');
  lines.push('');
  lines.push('```bash');
  lines.push('python phases/00-networking-lab-and-foundations/01-network-lab-environment/code/main.py');
  lines.push('```');
  lines.push('');
  lines.push('### Prerequisites');
  lines.push('');
  lines.push('- Basic command-line comfort');
  lines.push('- Willingness to inspect packet captures and protocol diagrams');
  lines.push('- Python helps for the build labs, but the core course is language-independent');
  lines.push('');
  lines.push('<a id="contents"></a>');
  lines.push('');
  lines.push('## Contents');
  lines.push('');
  phaseDefs.forEach(phase => {
    lines.push('<details>');
    lines.push(`<summary><b>Phase ${phase.id} - ${phase.name}</b> &nbsp;<code>${phase.lessons.length} lessons</code>&nbsp; <em>${phase.desc}</em></summary>`);
    lines.push('');
    lines.push('| # | Lesson | Type | Lang |');
    lines.push('|---|--------|------|------|');
    phase.lessons.forEach((lesson, idx) => {
      lines.push(`| ${String(idx + 1).padStart(2, '0')} | [${lesson.title}](${lessonRelPath(phase, lesson, idx)}) | ${lesson.type} | ${lesson.lang} |`);
    });
    lines.push('');
    lines.push('</details>');
    lines.push('');
  });
  lines.push('## Source Material');
  lines.push('');
  lines.push('- [`open-source-computer-networks.md`](open-source-computer-networks.md) - full extracted Markdown');
  lines.push('- [`chapters/`](chapters/) - chapter-level Markdown splits');
  lines.push('');
  lines.push('## License');
  lines.push('');
  lines.push('Course scaffolding is MIT licensed. Source text rights follow the source PDF/materials you supplied.');
  return lines.join('\n') + '\n';
}

function roadmap(totalLessons) {
  const totalHours = Math.round(totalLessons * 1.35);
  const lines = ['# Roadmap', '', 'Status tracker for every phase and lesson. The status glyphs in this file feed the website (`site/build.js` parses them into `site/data.js`); do not change their shape.', '', `Total estimated time: ~${totalHours} hours, at your own pace.`, '', '**Legend:** ✅ Complete &nbsp;·&nbsp; 🚧 In Progress &nbsp;·&nbsp; ⬚ Planned', ''];
  phaseDefs.forEach(phase => {
    const hours = Math.round(phase.lessons.length * 1.35);
    lines.push(`## Phase ${phase.id}: ${phase.name} — ✅ (~${hours} hours)`);
    lines.push('');
    lines.push('| # | Lesson | Status | Est. |');
    lines.push('|---|--------|--------|------|');
    phase.lessons.forEach((lesson, idx) => {
      const est = lesson.type === 'Capstone' ? '~180 min' : lesson.type === 'Project' ? '~150 min' : lesson.type === 'Lab' ? '~120 min' : lesson.type === 'Build' ? '~90 min' : '~75 min';
      lines.push(`| ${String(idx + 1).padStart(2, '0')} | ${lesson.title} | ✅ | ${est} |`);
    });
    lines.push('');
  });
  return lines.join('\n');
}

function rimraf(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

function mkdir(dir) { fs.mkdirSync(dir, { recursive: true }); }

function write(file, content) { mkdir(path.dirname(file)); fs.writeFileSync(file, content); }

function copyDir(src, dest) {
  rimraf(dest);
  mkdir(dest);
  fs.cpSync(src, dest, { recursive: true });
}

function main() {
  buildPlan();
  compressPlan();
  const totalLessons = phaseDefs.reduce((sum, p) => sum + p.lessons.length, 0);
  if (totalLessons < 150 || totalLessons > 220) throw new Error(`Expanded lesson count ${totalLessons} outside target range`);

  rimraf(phasesDir);
  mkdir(phasesDir);

  for (const phase of phaseDefs) {
    const phaseDir = path.join(phasesDir, phase.slug);
    mkdir(phaseDir);
    write(path.join(phaseDir, 'README.md'), phaseReadme(phase));

    phase.lessons.forEach((lesson, idx) => {
      const dir = lessonPath(phase, lesson, idx);
      mkdir(path.join(dir, 'docs'));
      mkdir(path.join(dir, 'outputs'));
      write(path.join(dir, 'docs', 'en.md'), lessonDoc(phase, lesson, idx));
      write(path.join(dir, 'outputs', `prompt-${slugify(lesson.title)}.md`), promptDoc(phase, lesson, idx));
      write(path.join(dir, 'quiz.json'), quizJson(lesson));
      if (['Build', 'Lab', 'Project', 'Capstone'].includes(lesson.type)) {
        mkdir(path.join(dir, 'code'));
        write(path.join(dir, 'code', 'main.py'), codeMain(lesson));
      }
    });
  }

  write(path.join(root, 'README.md'), readme(totalLessons));
  write(path.join(root, 'ROADMAP.md'), roadmap(totalLessons));
  copyDir(phasesDir, sitePhasesDir);
  console.log(`expanded course: ${phaseDefs.length} phases, ${totalLessons} lessons`);
}

main();
