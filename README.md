# Fastly Next-Gen WAF agent: fail-open before rules load (test evidence)

Evidence for the writeup [Fastly Next-Gen WAF Agent: Fail-Open During Kubernetes Pod Startup](https://zaclohrenz.com/posts/cve/fastly-nextgen-waf/). 

## Finding

In the Kubernetes sidecar deployment Fastly publishes for its Next-Gen WAF (formerly Signal Sciences), the NGINX module and `sigsci-agent` pass traffic uninspected whenever the agent has not loaded a ruleset:

1. Until the agent creates its RPC socket, the module cannot connect (`errno=2`) and fails open.
2. The agent creates the socket when its first configuration download attempt ends, whether or not it succeeded. With no ruleset loaded, it answers every `RPC.PreRequest` with `WAFResponse 200` and `X-SigSci-Agent: disabled`, and keeps doing so until a download succeeds.

The pod reports Ready throughout. With default settings, the agent never logs that it is disabled. Fastly's opt-in startup probe holds the pod out of service until rules load; Fastly's published Helm values do not include it.

Fastly's position is that this is intended fail-open behavior and not a vulnerability.

## Tested

| | |
|---|---|
| Date | 2026-11-12 (America/Chicago) |
| Agent | `signalsciences/sigsci-agent:4.83.2`, index digest `sha256:4aa2f5296b5f2eeb1a71e79643a93afb19ce85a635a21895ff35b2d0701578d2` |
| Ingress controller | `signalsciences/sigsci-nginx-ingress-controller:1.15.1-fastly1.4.0`, index digest `sha256:a4c66bfe5c0b06c6507ce89881ba891711ab3009b2d5d934db192a91e0f452ba` |
| Module | `sigsci-module-nginx-native 1.4.0`, nginx 1.27.1 |
| Layout | Fastly's `sigsci-values.yaml` ([commit 9794dfb](https://github.com/signalsciences/sigsci-nginx-ingress-controller/blob/9794dfb38747fb7ec68e4e9286e3164debf1e665/sigsci-values.yaml)) on ingress-nginx chart 4.15.1 |
| Cluster | kind v1.31.0 on podman, macOS arm64 |

## Results in brief

- Four config-download failure types (connection drop, HTTP 403, DNS NXDOMAIN, TCP reset), 3 runs each, all produced the same allow-everything `disabled` state: 20,304 decoded agent responses, one distinct value.
- Startup probe configured: pod held out of Service endpoints, zero requests to the upstream, 3 of 3 runs.
- Readiness probe `initialDelaySeconds` of 10, 30 and 60 s: traffic, including attack payloads, reached the upstream after each delay expired.
- No documented module or agent option made either component fail closed.

Full results, with each claim labeled OBSERVED, INFERRED or UNTESTED and tied to an evidence file, are in [REPORT.md](REPORT.md).

## Limitations

No Fastly credentials were used. The agent could never load a ruleset, so a healthy start was not observed: whether a valid agent ever opens its socket before its first ruleset loads, the startup probe's 503 to 200 transition, and how these requests appear in Fastly's console are all untested. The 60-second window in the egress-blocked runs comes from how egress was blocked, not a typical duration. See section 6 and 9.9 of the report.

Testing was black-box: logs, documented flags, the agent's documented RPC debug dump, and HTTP headers. No binaries were decompiled or disassembled.

## Contents

| Path | |
|---|---|
| `REPORT.md` | Full report, method, results, limitations, reproduction steps |
| `manifests/` | Exact Helm values and Kubernetes manifests for each variant |
| `raw/<run>/` | Per-run evidence: agent, NGINX, echo-server and generator logs, decoded RPC, statsd, pod and endpoint watches |
| `src/` | Orchestration, analysis and RPC decoding scripts |
| `SHA256SUMS` | Checksums of every evidence file as collected |

The access keys in the manifests are format-valid dummy values (`00000000-0000-0000-0000-000000000000` and 43 `A` characters), not credentials. Upstream `sigsci-values.yaml` in `raw/` is Fastly's file, copied unmodified for reference.

## Verify

```bash
sha256sum -c SHA256SUMS
```

`SHA256SUMS` covers the evidence as collected on 2026-11-12 and 2026-11-13. This README was added afterward and is not included in it. `REPORT.md` was edited for publication on 2026-11-17 (environment notes trimmed), so the check reports that one file as changed; the original is in commit `32930cd`. Every file under `raw/`, `manifests/` and `src/` is unchanged.

## Reproduce

See section 7 of [REPORT.md](REPORT.md). Images should be pulled by the digests above.
