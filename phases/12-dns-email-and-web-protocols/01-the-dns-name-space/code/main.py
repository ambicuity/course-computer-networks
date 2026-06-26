#!/usr/bin/env python3
"""DNS namespace validator and tree walker.

Validates domain names against the DNS naming rules (RFC 1034/1035):
  - Component max length: 63 characters
  - Full path max length: 255 characters
  - Case-insensitive
  - Components: letters, digits, hyphens (not at start/end)
Also classifies TLDs as generic or country and walks the hierarchy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Generic TLDs with start dates and restriction status (subset from RFC/ICANN)
GENERIC_TLDS: dict[str, tuple[int, bool]] = {
    "com": (1985, False),
    "edu": (1985, True),
    "gov": (1985, True),
    "int": (1988, True),
    "mil": (1985, True),
    "net": (1985, False),
    "org": (1985, False),
    "aero": (2001, True),
    "biz": (2001, False),
    "coop": (2001, True),
    "info": (2002, False),
    "museum": (2002, True),
    "name": (2002, False),
    "pro": (2002, True),
    "cat": (2005, True),
    "jobs": (2005, True),
    "mobi": (2005, True),
    "tel": (2005, True),
    "travel": (2005, True),
    "xxx": (2010, False),
}

# ISO 3166 country codes (sample — the full list has 249 entries)
COUNTRY_TLDS: set[str] = {
    "au", "jp", "uk", "us", "nl", "de", "fr", "ca", "cn", "in",
    "br", "ru", "se", "no", "fi", "dk", "it", "es", "mx", "kr",
    "tv", "to", "nz", "ie", "pt", "ch", "at", "be", "pl", "tr",
}

MAX_COMPONENT_LENGTH = 63
MAX_FULL_PATH_LENGTH = 255
COMPONENT_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$")


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a domain name."""
    domain: str
    is_valid: bool
    is_absolute: bool
    tld: Optional[str]
    tld_type: Optional[str]  # "generic", "country", or None
    issues: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)


def validate_domain_name(domain: str) -> ValidationResult:
    """Validate a domain name against DNS naming rules (RFC 1034/1035).

    Checks component length (63), full path (255), character rules,
    absolute vs relative, and TLD classification.
    """
    issues: list[str] = []
    original = domain

    # Check for absolute vs relative
    is_absolute = domain.endswith(".")
    if is_absolute:
        domain = domain[:-1]  # Strip trailing dot for analysis

    if not domain:
        issues.append("Empty domain name")
        return ValidationResult(original, False, is_absolute, None, None, issues)

    # Split into components
    components = domain.split(".")

    # Check full path length (RFC 1035: 255 octets including length octets)
    # Simplified: check the total string length
    total_length = sum(len(c) for c in components) + len(components) - 1
    if total_length > MAX_FULL_PATH_LENGTH:
        issues.append(
            f"Full path length {total_length} exceeds max {MAX_FULL_PATH_LENGTH}"
        )

    # Validate each component
    for i, comp in enumerate(components):
        if not comp:
            issues.append(f"Empty component at position {i}")
            continue

        if len(comp) > MAX_COMPONENT_LENGTH:
            issues.append(
                f"Component '{comp}' length {len(comp)} exceeds max "
                f"{MAX_COMPONENT_LENGTH} (at position {i})"
            )

        if not COMPONENT_PATTERN.match(comp):
            issues.append(
                f"Component '{comp}' has invalid characters "
                f"(at position {i})"
            )

    # Classify TLD (last component, or root if trailing dot)
    tld = components[-1].lower() if components else None
    tld_type: Optional[str] = None
    if tld:
        if tld in GENERIC_TLDS:
            tld_type = "generic"
        elif tld in COUNTRY_TLDS:
            tld_type = "country"

    is_valid = len(issues) == 0
    return ValidationResult(
        original, is_valid, is_absolute, tld, tld_type, issues, components
    )


def describe_tld(tld: str) -> str:
    """Return a human-readable description of a TLD."""
    tld_lower = tld.lower()
    if tld_lower in GENERIC_TLDS:
        start, restricted = GENERIC_TLDS[tld_lower]
        restriction = "restricted" if restricted else "open"
        return f"generic TLD, started {start}, {restriction}"
    if tld_lower in COUNTRY_TLDS:
        return f"country code TLD (ISO 3166)"
    return "unknown/unrecognized TLD"


def walk_hierarchy(domain: str) -> list[str]:
    """Walk the DNS hierarchy from root to the given domain.

    Returns a list of zones queried, e.g.:
    root -> com -> cisco -> eng
    """
    result = validate_domain_name(domain)
    if not result.is_valid:
        return [f"INVALID: {issue}" for issue in result.issues]

    # Remove trailing dot if present
    clean = domain.rstrip(".")
    components = clean.split(".")
    # Reverse to go from root (TLD) down to the leaf
    components_reversed = list(reversed(components))

    path: list[str] = ["root (.)"]
    current = ""
    for comp in components_reversed:
        if current:
            current = f"{comp}.{current}"
        else:
            current = comp
        path.append(f"  → {comp}  ({current}.)")

    return path


def main() -> None:
    """Run the DNS namespace validator with sample domains."""
    print("=" * 70)
    print("DNS Namespace Validator")
    print("=" * 70)

    test_domains: list[str] = [
        "eng.cisco.com.",              # Absolute, valid
        "robot.cs.washington.edu",     # Relative, valid
        "cs.vu.nl",                    # Relative, valid, country TLD
        "cs.keio.ac.jp",              # Relative, valid, country TLD
        "www.example.com.",           # Absolute, valid
        "a" * 64 + ".example.com",    # Component too long (64 chars)
        "-invalid.example.com",        # Leading hyphen
        "valid-but-very-long-" + "x" * 240 + ".com",  # Path too long
        "example.tv",                  # Country TLD (Tuvalu)
        "Example.COM",                # Case-insensitive
    ]

    for domain in test_domains:
        result = validate_domain_name(domain)
        print(f"\nDomain: {domain}")
        print(f"  Valid: {result.is_valid}")
        print(f"  Absolute (FQDN): {result.is_absolute}")
        if result.tld:
            print(f"  TLD: {result.tld} → {describe_tld(result.tld)}")
        if result.issues:
            for issue in result.issues:
                print(f"  Issue: {issue}")

    # Demonstrate hierarchy walk
    print("\n" + "=" * 70)
    print("Hierarchy Walk: robot.cs.washington.edu.")
    print("=" * 70)
    steps = walk_hierarchy("robot.cs.washington.edu.")
    for step in steps:
        print(step)

    # Show TLD classification summary
    print("\n" + "=" * 70)
    print("TLD Classification Summary")
    print("=" * 70)
    sample_tlds = ["com", "edu", "org", "uk", "jp", "nl", "tv", "mobi", "pro", "aero"]
    for tld in sample_tlds:
        print(f"  .{tld:8s} → {describe_tld(tld)}")


if __name__ == "__main__":
    main()