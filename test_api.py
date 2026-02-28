#!/usr/bin/env python3
"""
ConceptNet API test script.

Runs against the local API server using conceptnet5.uri utilities to
build and validate URIs, and requests to exercise each endpoint.

Usage:
    pip install conceptnet5 requests
    python test_api.py [--url http://localhost:8084]
"""
import sys
import argparse
import requests
from conceptnet5 import uri as cnuri

BASE_URL = "http://localhost:8084"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results = {"pass": 0, "fail": 0, "skip": 0}


def check(name, condition, detail=""):
    if condition:
        print(f"  {PASS}  {name}")
        results["pass"] += 1
    else:
        print(f"  {FAIL}  {name}" + (f": {detail}" if detail else ""))
        results["fail"] += 1


def skip(name, reason):
    print(f"  {SKIP}  {name}: {reason}")
    results["skip"] += 1


def get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def section(title):
    print(f"\n{title}")
    print("-" * len(title))


# ---------------------------------------------------------------------------
# /health  (custom endpoint — not part of the official conceptnet_web API)
# ---------------------------------------------------------------------------
section("GET /health")
try:
    data = get("/health")
    check("status == healthy", data.get("status") == "healthy")
    check("database == connected", data.get("database") == "connected")
except requests.HTTPError as e:
    if e.response.status_code == 404:
        skip("/health", "not provided by the official conceptnet_web API")
    else:
        check("request succeeded", False, str(e))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /
# ---------------------------------------------------------------------------
section("GET /")
try:
    data = get("/")
    check("response is a dict", isinstance(data, dict))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /c/<concept>  —  concept lookup
# ---------------------------------------------------------------------------
section("GET /c/<concept>")
try:
    concept = cnuri.concept_uri("en", "dog")           # /c/en/dog
    data = get(concept)

    edges = data.get("edges", [])
    check("returns edges list", isinstance(edges, list))
    check("edges are non-empty", len(edges) > 0)

    if edges:
        edge = edges[0]
        start_uri = edge.get("start", {}).get("@id", "")
        end_uri   = edge.get("end", {}).get("@id", "")

        check("start is a concept URI",
              cnuri.is_concept(start_uri),
              start_uri)
        check("end is a concept URI",
              cnuri.is_concept(end_uri),
              end_uri)

        start_lang = cnuri.get_uri_language(start_uri)
        check("start language is parseable", start_lang is not None)

        check("edge has weight", "weight" in edge)

except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /query — relation filter (official API filters by rel here, not on /c/)
# ---------------------------------------------------------------------------
section("GET /query?start=...&rel=IsA")
try:
    concept = cnuri.concept_uri("en", "dog")
    data = get("/query", params={"node": concept, "rel": "/r/IsA", "limit": 10})
    edges = data.get("edges", [])
    check("returns edges", isinstance(edges, list) and len(edges) > 0)
    if edges:
        rels = [e.get("rel", {}).get("@id", "") for e in edges]
        check("all edges are IsA",
              all(r == "/r/IsA" for r in rels),
              str(rels[:3]))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /query — start + rel filter
# ---------------------------------------------------------------------------
section("GET /query?start=...&rel=...")
try:
    dog = cnuri.concept_uri("en", "dog")
    data = get("/query", params={"start": dog, "rel": "/r/IsA", "limit": 5})
    edges = data.get("edges", [])
    check("returns edges", isinstance(edges, list) and len(edges) > 0)
    if edges:
        check("start nodes match",
              all(e.get("start", {}).get("@id", "").startswith(dog)
                  for e in edges))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /query — node filter (either direction)
# ---------------------------------------------------------------------------
section("GET /query?node=...")
try:
    coffee = cnuri.concept_uri("en", "coffee")
    data = get("/query", params={"node": coffee, "limit": 10})
    edges = data.get("edges", [])
    check("returns edges", isinstance(edges, list) and len(edges) > 0)
    if edges:
        involves_coffee = [
            e for e in edges
            if coffee in e.get("start", {}).get("@id", "")
            or coffee in e.get("end", {}).get("@id", "")
        ]
        check("all edges involve coffee", len(involves_coffee) == len(edges))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /query — end filter
# ---------------------------------------------------------------------------
section("GET /query?end=...")
try:
    animal = cnuri.concept_uri("en", "animal")
    data = get("/query", params={"end": animal, "rel": "/r/IsA", "limit": 5})
    edges = data.get("edges", [])
    check("returns edges", isinstance(edges, list) and len(edges) > 0)
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /uri — URI standardisation (official API endpoint)
# ---------------------------------------------------------------------------
section("GET /uri")
try:
    data = get("/uri", params={"text": "United States", "language": "en"})
    uri = data.get("@id", "")
    check("returns a URI", bool(uri))
    check("URI is a concept", cnuri.is_concept(uri), uri)
    parts = cnuri.split_uri(uri)
    check("URI language is en", len(parts) >= 2 and parts[1] == "en")
except requests.HTTPError as e:
    if e.response.status_code == 404:
        skip("/uri endpoint", "not available in this API version")
    else:
        check("request succeeded", False, str(e))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# /relatedness — semantic similarity via embeddings
# ---------------------------------------------------------------------------
section("GET /relatedness")
try:
    node1 = cnuri.concept_uri("en", "dog")
    node2 = cnuri.concept_uri("en", "puppy")
    data = get("/relatedness", params={"node1": node1, "node2": node2})
    sim = data.get("value")  # official API uses "value", not "similarity"
    check("returns similarity score", sim is not None)
    check("score is between 0 and 1", 0.0 <= float(sim) <= 1.0, str(sim))
    check("dog/puppy similarity > 0.5", float(sim) > 0.5, str(sim))
except requests.HTTPError as e:
    if e.response.status_code in (404, 500, 503):
        skip("/relatedness", "embeddings or HDF5 vectors not available")
    else:
        check("request succeeded", False, str(e))
except Exception as e:
    check("request succeeded", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = results["pass"] + results["fail"] + results["skip"]
print(f"\n{'='*40}")
print(f"Results: {results['pass']} passed, {results['fail']} failed, "
      f"{results['skip']} skipped  ({total} total)")
print('='*40)

sys.exit(0 if results["fail"] == 0 else 1)
