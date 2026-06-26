# Zero Trust Microsegmentation and Reachability Verification

> Design a zero-trust microsegmentation policy for a multi-tier application, implement the policy as a distributed firewall rule set, and verify reachability with a simulated network scanner.

**Type:** Capstone
**Languages:** Python, nmap, shell
**Prerequisites:** Phase 16 security lessons; understanding of firewalls, VLANs, access control lists, and least-privilege principles
**Time:** ~150 minutes

## Learning Objectives

- Design a zero-trust microsegmentation policy: every workload is isolated by default, communication is explicitly allowed only for defined flows
- Model a multi-tier application (web, app, database, cache, message queue) with explicit allowed-flow rules
- Implement a distributed firewall rule engine that evaluates (source, destination, protocol, port) tuples against the policy
- Simulate a network scanner that probes all (workload, port) pairs and reports allowed vs. denied flows
- Verify that the policy enforces least privilege: the web tier can reach the app tier on port 8080, but NOT the database on port 3306
- Detect policy violations: identify any allowed flow that is not in the policy (over-permissive) or any denied flow that should be allowed (under-permissive)

## The Problem

Traditional network security uses perimeter firewalls: hard outer shell, soft interior. Once an attacker breaches the perimeter (via phishing, vulnerable web app, or insider), they have free rein inside the network. Lateral movement is trivial because internal segmentation is weak.

Zero trust eliminates this: there is no "inside" and "outside." Every workload is a distinct trust zone. Communication between workloads must be explicitly allowed by a microsegmentation policy. The default is deny-all. The web tier can talk to the app tier on port 8080, but the web tier cannot talk to the database directly. The app tier can talk to the database on port 3306, but not to other app tiers unless explicitly allowed.

This capstone asks you to design a zero-trust microsegmentation policy for a 5-tier application, implement it as a distributed firewall rule set, simulate a reachability scanner, and verify that the policy enforces least privilege. You must also detect over-permissive rules (allowing flows that should be denied) and under-permissive rules (denying flows that should be allowed).

## The Approach

The design and verification follows six stages:

1. **Workload inventory** - Define all workloads: 3 web servers, 2 app servers, 2 database servers, 1 Redis cache, 1 message queue, 1 load balancer, 1 admin bastion. Each workload has an IP, tags (tier, environment, sensitivity), and exposed ports.

2. **Policy definition** - Define the allowed flows as (source, destination, protocol, port, action) tuples. Example: (web, app, TCP, 8080, ALLOW), (app, db, TCP, 3306, ALLOW), (web, db, TCP, 3306, DENY - implicit deny). The policy is a list of explicit allows; everything else is denied by default.

3. **Distributed firewall** - Implement a rule engine that takes a flow request (src_ip, dst_ip, protocol, dst_port) and evaluates it against the policy. Return ALLOW or DENY. The engine is "distributed" in that each workload has its own local rules, but the policy is centrally defined.

4. **Reachability scanner** - Simulate scanning all (source_workload, destination_port) pairs. For each pair, evaluate the policy and record ALLOW or DENY. Produce a reachability matrix.

5. **Policy verification** - Compare the actual reachability matrix against the expected reachability (from the policy definition). Flag any discrepancies: over-permissive (actual allows but policy denies) or under-permissive (actual denies but policy allows).

6. **Violation detection** - Check for common policy mistakes: any-to-any rules, overly broad CIDR ranges, rules allowing admin ports (22, 3389) from non-bastion sources, and rules allowing database access from the web tier.

## Build It

1. Define dataclasses for Workload, MicrosegmentationPolicy, FirewallRule, FlowRequest, and ScanResult.
2. Implement the workload inventory: 12 workloads across 5 tiers with tags and IPs.
3. Implement the policy: explicit allow rules for defined flows, implicit deny for everything else.
4. Implement the distributed firewall rule engine: evaluate flow requests against the policy.
5. Implement the reachability scanner: probe all (source, destination, port) combinations and record results.
6. Implement policy verification: compare actual reachability to expected, flag violations.
7. Implement violation detection: scan for common policy mistakes (any-to-any, broad CIDRs, admin port exposure).
8. Run `code/main.py` and study the reachability matrix, verification results, and violation report.

## Expected Outcomes

When you run `code/main.py` you should observe:

- 12 workloads across 5 tiers (web, app, database, cache, message queue) plus load balancer and admin bastion
- A policy with 15 explicit allow rules and implicit deny for all other flows
- Reachability matrix: web -> app:8080 ALLOWED, web -> db:3306 DENIED, app -> db:3306 ALLOWED
- Scanner results: 120 total flow checks, 15 allowed, 105 denied
- Policy verification: 0 over-permissive violations, 0 under-permissive violations (policy matches design)
- Violation detection: no any-to-any rules, no broad CIDRs, admin ports only accessible from bastion
- A simulated attack scenario: a compromised web server attempting to reach the database is blocked

## Deliverables

- `outputs/reachability-matrix.txt` - Full reachability matrix: source x destination x port with ALLOW/DENY
- `outputs/policy-verification.txt` - Verification report showing policy compliance and any violations
- `outputs/violation-detection.txt` - Detected policy mistakes with severity and remediation
- `outputs/attack-scenario.txt` - Simulated lateral movement attempt with blocked flows
- `outputs/zero-trust-runbook.md` - A runbook for designing and verifying zero-trust microsegmentation

## Exercises

1. Add a service mesh (e.g., Istio-style) with mTLS between workloads and show how it complements microsegmentation. What does the service mesh add that the firewall does not?
2. Implement a policy change request workflow: a developer requests access from a new service to the database. Model the approval process, the policy update, and the re-verification of reachability.
3. Add a compromised workload scenario: the web server is infected with malware that tries to scan the internal network. How does microsegmentation limit the blast radius? What flows are attempted and blocked?
4. Model a policy with a mistake: an over-permissive rule allowing web -> any:3306. Run the verification and show how the violation detector catches it.
5. Implement a time-based policy: admin access is only allowed during business hours (09:00-17:00). Show how the reachability matrix changes outside those hours.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Zero trust | No perimeter | A security model where no workload is trusted by default; every flow must be explicitly allowed |
| Microsegmentation | Fine-grained firewalls | Dividing the network into per-workload security zones with explicit allow rules, not broad VLAN trust |
| Least privilege | Minimal access | Each workload has only the network access it needs to function, nothing more |
| Reachability matrix | Who can talk to whom | A matrix showing which sources can reach which destinations on which ports |
| Lateral movement | Attacker pivoting | An attacker moving from one compromised workload to others; microsegmentation prevents this |

## Further Reading

- NIST Special Publication 800-207 - Zero Trust Architecture
- "Zero Trust Networks" by Evan Gilman and Doug Barth
- VMware NSX Distributed Firewall documentation
- Istio service mesh security model
- "BeyondCorp" Google's zero trust implementation (USENIX ;login:)