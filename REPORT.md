# Next-Gen WAF (Signal Sciences) NGINX module + agent: startup-window behavior

**Test date:** Thursday 2026-11-12 (first-report runs earlier that day; follow-up runs 16:26–18:23 CST). **Host timezone:** America/Chicago (CST, UTC−06:00, `date +%z` = -0600). **Timestamps in raw evidence are UTC** (cluster VM clock); host-vs-VM clock skew measured ≈30 ms. Labels used below: **OBSERVED** = directly seen in the evidence cited; **INFERRED** = reasoned from observations, not directly shown; **UNTESTED** = not run.

Black-box test in a disposable local kind cluster. **No Fastly credentials were available** (user answered "No keys"), so every run used format-valid **dummy** keys (`00000000-0000-0000-0000-000000000000` / 43×`A`). The agent can therefore never download a ruleset. See *Limitations* before citing anything.

All paths below are relative to `results/`. Times are seconds after the container's `startedAt` (pod status) unless stated.

## 1. Versions

| Item | Value |
|---|---|
| Ingress image | `signalsciences/sigsci-nginx-ingress-controller:1.15.1-fastly1.4.0` (Hub `latest` resolved to this tag, pushed 2026-03-24) |
| Ingress image index digest | `sha256:a4c66bfe5c0b06c6507ce89881ba891711ab3009b2d5d934db192a91e0f452ba` (arm64 manifest `sha256:aedaa4c2583250ca7d0666df376ac8296bf4dcb55df9d51a500d30d791c9687f`, image ID `95c83d43f2b7`) |
| Agent image | `signalsciences/sigsci-agent:4.83.2` (Hub `latest` resolved to this tag, pushed 2026-11-05) |
| Agent image index digest | `sha256:4aa2f5296b5f2eeb1a71e79643a93afb19ce85a635a21895ff35b2d0701578d2` (arm64 manifest `sha256:12edcd5f272c9cac9ea4b7defa7e2218ad1bab37ba8a8cbe96d4f9bbb0881118`, image ID `a55f33859038`) |
| Version the agent reports | `Signal Sciences Agent 4.83.2` (`raw/G-default1/agent.log:1`); upload metadata also lists `"AgentVersion":"4.83.1"`, `"BinaryVersion":"4.83.2"` (`raw/exploratory-D2-probe-debugflags-statsd/agent.log`) |
| Module | `sigsci-module-nginx-native 1.4.0`, nginx/1.27.1 (from decoded RPC, `raw/F-rep1/rpc-decoded.jsonl:1`) |
| Digest check | Both images were pulled **by the index digests above**; local `RepoDigests` contain them and `crictl images` in the kind node shows the same image IDs. |
| Chart | ingress-nginx 4.15.1 (app 1.15.1), image overridden to the local copies (`digest: ""`) |

## 2. Environment and deviations from the brief

- macOS arm64. Docker.app on this machine is broken (executable missing), so kind runs on **podman** (`KIND_EXPERIMENTAL_PROVIDER=podman`, machine set to rootful, 6 GiB). Node image `kindest/node:v1.31.0`. Installed with brew: kind, kubectl, socat, helm.
- Layout follows Fastly's `sigsci-values.yaml` from the GitHub repo (module via `main-snippet`, `sigsci_agent_host unix:/sigsci/tmp/sigsci.sock`, agent as `extraContainers`, shared `emptyDir`). Variant B adds `SIGSCI_STARTUP_PROBE_LISTENER=0.0.0.0:2024` + `startupProbe` (`/startup`, `failureThreshold: 90`, `periodSeconds: 2`) exactly as in the Kubernetes Agent + Module guide.
- Egress hold: a NetworkPolicy (`manifests/netpol-block-agent-egress.yaml`) allowing only cluster DNS and 10.0.0.0/8. Endpoints were taken from the agent's own log: `wafconf.signalsciences.net`, `sigsci-agent-wafconf.s3.amazonaws.com`, `sigsci-agent-wafconf-us-west-2.s3.amazonaws.com` (config), `c.signalsciences.net/0/push` (upload).
- **Lab-only init container** `wait-egress-blocked` (in variants A/B/D/E/F/G): the first pilot showed the CNI had not yet programmed the policy when the agent made its first request, so the first download leaked to Fastly (403). The init container waits until the connection is observed blocked. Consequence: container start is ~15 s after pod creation, which is why times are reported from container `startedAt`. Variant H (egress allowed) has no init container and no NetworkPolicy.
- **No socat/Python socket proxy was used.** A proxy would have to own the module-facing socket path, so it would create the socket before the agent does and change exactly the thing under test (socket existence). Instead: (a) the agent's own documented `--debug-log-rpc-data` hexdump, decoded with `src/decode_rpc.py`; (b) the module's own debug log (`error-log-level: debug`, nginx is built `--with-debug`). The hexdump was capped at 400 KB per run, so it covers 169 of ~1,566 disabled-phase requests in F-rep1.
- Kubelet log rotation (10 MiB) truncated the debug nginx log in my first pilot, so `src/run.py` streams container logs continuously. Debug nginx logs (38 MiB each) were trimmed to `nginx-debug-excerpt.log`; correlation was computed from the full logs before trimming.
- Backend: Python echo server logging epoch timestamp, `X-Request-ID`, all `X-SigSci-*` headers (and, in G/H, all headers). Generator: in-cluster, ~20 req/s, unique `X-Request-ID` with a SQLi / XSS / traversal / "custom block marker" payload cycling with a clean request (`manifests/gen.yaml`). The workspace custom block rule could not be created (no account).
- Only network contact outside the cluster: image/chart pulls (Docker Hub, kubernetes.github.io) and, in variant H and in the ~1 s race of the first pilot, the agent's own requests to Fastly's endpoints with dummy keys (HTTP 403).

## 3. Direct answers

### Q1. What does the agent return to the module before it has loaded a ruleset?

**Answer: (d), a sequence of (c) then (a). Not (b).** Confidence: **high** for what was observed with dummy keys; **low** for whether a healthy start with working keys has the same ordering (see Limitations).

Timeline, blocked egress (`raw/G-default1`, container `startedAt` = 22:09:05):

| t (s) | Event | Evidence |
|---|---|---|
| 0 | `controller` and `sigsci-agent` containers start | `raw/G-default1/pod.json` (containerStatuses.state.running.startedAt) |
| +0.58 | Agent prints its banner | `raw/G-default1/agent.log:1` |
| +2.8 | First module attempt: `cannot connect uds socket … errno=2` (controller's own `POST /configuration/backends`) | `raw/G-default1/nginx.log:27` |
| ~+15 | Pod Ready, enters Service endpoints (kubelet readiness on `:10254/healthz`, delay 10 s) | `raw/G-default1/pod.json` condition `Ready` (line 307) |
| +15.89 | First client request reaches the upstream **uninspected**, no `X-SigSci-*` header | `raw/G-default1/echo.log:4` |
| +60.65 | First config attempt fails; **RPC listener created in the same millisecond** | `raw/G-default1/agent.log:8-9` |
| +60.66 | First request answered by the agent: `WAFResponse 200` + `X-SigSci-Agent: disabled` | `raw/G-default1/echo.log:939` |
| 60.65 → end | Every request is answered `200`/disabled and passes | 1,564 upstream hits in this phase |

- **(c) socket absent.** Until the listener exists, the module's `connect()` fails with `errno=2` (ENOENT) in 0 ms, logs `Failed to open connection to agent`, and the request proceeds (`agent-resp-code=-2`, `nginx-debug-excerpt.log` of any A/F rep). 930–950 requests per run, including all attack payloads, reached the upstream in this phase.
- **(a) agent answers allow.** Once the socket exists the agent answers `RPC.PreRequest` with `{"WAFResponse": 200, "RequestID": "", "RequestHeaders": [["X-SigSci-Agent","disabled"]]}`. 169/169 decoded responses in F-rep1 are this exact message (`raw/F-rep1/rpc-decoded.jsonl`); the module debug log shows it parsed in 1–2 ms. The module then adds `X-SigSci-AgentResponse: 200` and `X-SigSci-Agent: disabled` to the upstream request.
- **(b) not observed.** 0 module timeout/fail-open-on-timeout messages across all runs (`module_timeout_messages: 0` in every `summary.json`). I did not verify the documented 100 ms default.
- **When does the socket appear?** In every run the agent created the listener the instant the **first config download attempt finished, success unknown, failure observed**: 1 ms after the failure line in `agent.log:8-9` (blocked: +60.65 s, because three URLs time out sequentially ~20 s each; egress allowed with dummy keys: +1.05 s, `raw/H-default-allowed1/agent.log:8-9`). Inside the sigsci-agent process the 60 s variance across reps was 60.06–60.07 s.
- Sample size: A ×3, B ×3, F ×3, G ×1, H ×1, release ×1 plus exploratory runs. Variance is negligible (below).

Variance, no-probe variant A (3 reps, container-independent, relative to scale-up T0):

| Metric | rep1 | rep2 | rep3 |
|---|---|---|---|
| Agent process start | 15.10 | 15.12 | 15.21 |
| RPC socket created | 75.16 | 75.20 | 75.28 |
| Endpoints ready | 30.40 | 30.40 | 30.39 |
| Attack payloads reaching upstream, socket absent | 748 | 745 | 750 |
| Attack payloads reaching upstream, socket present / disabled (90 s hold) | 291 | 289 | 289 |
| Requests blocked / inspected | 0 | 0 | 0 |

Source: `raw/A-rep{1,2,3}/summary.json`. F reps: 744/747/747 and 1249/1251/1251.

### Q2. What shows that requests were handled before rules loaded, and is it on by default?

**Answer: with default configuration, nothing in the agent log names the requests or the disabled state.** Confidence: **high** for "not observed at default", **medium** for the non-default list (found by flag name in `sigsci-agent -help` and confirmed by output; the docs page was not exhaustively cross-checked).

Default configuration (G/H), exact visible signals:

- Agent stdout: only the banner, `Config update failed try N: …` (reason differs, below), `Started RPC listener on "unix:/sigsci/tmp/sigsci.sock"`, and (blocked case) `Failed initial/periodic upload`. No line mentions the engine being disabled, requests, or uninspected traffic.
- NGINX at its default level `notice` (`/etc/nginx/nginx.conf:111,523`: `error_log /var/log/nginx/error.log notice;`): the module's `[error] … cannot connect uds socket …` **is** emitted, but only in the no-socket phase.

Non-default options that expose pre-rule-load handling (all observed in `raw/F-rep*` and `raw/exploratory-D2-…`):

| Option | What new appears |
|---|---|
| `SIGSCI_STATSD_ADDRESS=host:port` | Counters `sigsci.agent.waf.total`, `sigsci.agent.waf.allow`, `sigsci.agent.rpc.tx.dropped.engine_disabled` (F-rep1 window: 908/908/908, `raw/F-rep1/statsd-window.log`). **`…dropped.engine_disabled` is the metric that corresponds to "handled but engine not running".** In the exploratory run the first emission came ~60 s after the listener started, so counts lag the traffic; the final flush before collection was missing, so 908 < the 1,566 requests the module saw answered. |
| `SIGSCI_DEBUG_LOG_UPLOADS=1` (or `2`) | The agent logs its outgoing metadata JSON, including `AgentEnabled:0`, `AgentWAFConfigCounter:0`, `AgentTotalRequests` (0 → 908 → 1514 across successive uploads, `raw/F-rep1/agent.log`), `ConnectionsTotal`. |
| `SIGSCI_DEBUG_LOG_RPC_DATA=<file>` | Raw RPC hexdump (decoded by `src/decode_rpc.py`). |
| `SIGSCI_DEBUG_LOG_CONFIG_UPDATES=2` | Adds `Checking for new agent config: cdn=… direct=… failover=…`. |
| `error-log-level: debug` (NGINX, not agent) | Per-request `prerequest complete … agent-resp-code=200`, `Parsed RequestHeaders[0] X-SigSci-Agent: disabled`. |

`SIGSCI_DEBUG_LOG_WEB_INPUTS=1`, `…WEB_OUTPUTS=1`, `…CONNECTION_ERRORS=1`, `…ENGINE_ERRORS=2` were set in F and produced **no per-request lines** in the disabled state (not observed; this does not show they never log).

**Fastly console check: not performed** (no credentials). Whether these requests appear in the console is **not determined**.

## 4. Default-visibility table (what an operator sees with default settings)

Two runs, both with the Fastly layout, no probe, no debug, no statsd, dummy keys: **G** = egress blocked (agent log shows network failure), **H** = egress allowed (Fastly rejects the credentials with 403). Phase "no-socket" = before `Started RPC listener`; "disabled" = after it, no ruleset.

| Signal | Default on? | Phase | Exact evidence (file:line) |
|---|---|---|---|
| NGINX `[error] … sigsci_transport_open: cannot connect uds socket unix:/sigsci/tmp/sigsci.sock : errno=2 …` (level **error**; configured default level **notice**) | Yes | no-socket (G). **H: not observed**, socket (+1.05 s) preceded all nginx traffic | `raw/G-default1/nginx.log:27` (947 occurrences, one per request incl. controller-internal ones) |
| NGINX `[error] … sigsci:ss_send_prerequest: 0 ms: Failed to open connection to agent` | Yes | no-socket (G); H not observed | `raw/G-default1/nginx.log:28` |
| NGINX `[notice] sigsci_init_main_conf: Using default UDS socket: /var/run/sigsci.sock` and `sigsci:init: setting phase REWRITE` | Yes (once at start) | startup, both | `raw/G-default1/nginx.log:22-23`, `raw/H-default-allowed1/nginx.log:22-23`. (Message says "default" socket path, which differs from the configured one. Not investigated.) |
| Any NGINX sigsci/module line while the agent answers `disabled` | **Not observed** (0 module lines of any level after the socket existed, ~85 s window in G, ~140 s in H) | disabled | G and H `nginx.log` (zero module lines after `agent.log:9` time) |
| Agent: `Config update failed try 1: … context deadline exceeded (Client.Timeout exceeded while awaiting headers)` ×3 URLs | Yes | boundary (G, network failure) | `raw/G-default1/agent.log:8` |
| Agent: `Config update failed try N: … got HTTP error for "https://wafconf.signalsciences.net/4/<id>.conf": 403` ×3 URLs, repeats every ~30 s (tries 1–6 in 150 s) | Yes | no-socket→disabled (H, ~1 s, then disabled indefinitely) | `raw/H-default-allowed1/agent.log:8,10-14` |
| Agent: `Started RPC listener on "unix:/sigsci/tmp/sigsci.sock"` | Yes | start of disabled phase | `raw/G-default1/agent.log:9`, `raw/H-default-allowed1/agent.log:9` |
| Agent: `Failed initial upload` / `Failed periodic upload … context deadline exceeded` | Yes | disabled (G only); **H: not observed** | `raw/G-default1/agent.log:10-11` |
| Agent line saying engine disabled / requests passing uninspected / no ruleset | **Not observed** | any | G and H `agent.log` (full 150 s read, 11 and 14 lines) |
| Upstream header `X-SigSci-Agent: disabled` and `X-SigSci-AgentResponse: 200` | Yes (default module behavior) | **disabled: yes.** no-socket: **not observed** (935 requests, `sigsci=[]`, none) | disabled: `raw/G-default1/echo.log:939`, `raw/H-default-allowed1/echo.log:2560`; no-socket: `raw/G-default1/echo.log:4` |
| Kubernetes Warning events for the pod | **Not observed** (G: 12 Normal; H: 9 Normal; only `RELOAD` is notable) | both | `raw/G-default1/events-this-pod.txt`, `raw/H-default-allowed1/events-this-pod.txt` |
| Pod conditions | Ready/ContainersReady **True** (G +15 s, H +10 s) throughout; WAF state not reflected | both | `raw/G-default1/pod.json:307,313`; `raw/H-default-allowed1/pod.json:282,288` |
| Startup probe 503 / pod held out of endpoints | **No** (needs `SIGSCI_STARTUP_PROBE_LISTENER` + `startupProbe`) | n/a | see section 5 |
| statsd `…dropped.engine_disabled` | **No** (needs `SIGSCI_STATSD_ADDRESS`) | disabled | `raw/F-rep1/statsd-window.log` |
| Agent HTTP metrics/status endpoint | **Not observed** (only the startup-probe listener was examined; no other listener found in `agent-help.txt`; not exhaustively checked) | | |

Key operator-facing contrast (G vs H):
- **Egress blocked (G):** 45 s of requests (container +15.9 → +60.6 s) pass with the module logging `[error] cannot connect uds socket` on every request, then the agent socket appears and every request passes as `disabled`.
- **Credentials rejected (H):** no no-socket window at all (socket +1.05 s, first traffic +10.2 s). From then on 100% of requests (2,899 counted) pass with `X-SigSci-Agent: disabled`, the NGINX log is silent, the pod is Ready, and the only signal is a `Config update failed … 403` line in agent stdout every ~30 s.

## 5. Startup probe vs no startup probe (3 reps each)

| | No probe (A, 3 reps) | Probe (B, 3 reps) |
|---|---|---|
| Pod enters Service endpoints | Yes, at ~+30.4 s after scale-up (container +15 s) | **Never**: stays `1/2 Ready`; address only in `notReadyAddresses` (`raw/B-rep*/endpoints-watch.txt`, `pods-watch.txt`) |
| Requests reaching upstream | 1,294–1,299 per run (1,034–1,039 attack payloads) | **0** in all 3 reps (`summary.json`) |
| `/startup` (polled every 250 ms) | n/a | 503 for the whole run (315 samples), connection refused for the first ~13 s; **never 200** (`raw/B-rep*/poller.log`) |
| Kubelet | none | `Startup probe failed: HTTP probe failed with statuscode: 503` (`pod-describe.txt`) |

Confirmed: **without** the probe, traffic (including SQLi/XSS/traversal payloads) reaches the upstream before rules load, on agent 4.83.2. **With** the probe, the pod is held out of endpoints while `/startup` returns 503. **Not confirmed:** that it is released when rules load, and the 503→200 transition itself (no ruleset can load). Also note the guide's `failureThreshold: 90 × periodSeconds: 2` = 180 s; a pod whose agent cannot reach Fastly for >180 s would be restarted by the kubelet. Not exercised (runs were ≤150 s).

Egress release (`raw/A-release1`, dummy keys, policy deleted at T0+71.2 s): this run is not a clean "release while still loading" test, because the first config attempt happened to end (socket created at T0+71.5 s) 0.3 s after the release. After the release the agent retried and got 403 (`Config update failed try 2/3`, `raw/A-release1/agent.log`); 1,240 later requests were answered `disabled` and 7 hit the no-socket path in the 0.3 s before the socket appeared. It never reached "rules loaded".

Note: `startup probe` listener is up before rules load (`Starting HTTP engine startup probe endpoint: [::]:2024`) and returns 503 even after the RPC listener started, so **RPC listener existing does not mean rules are loaded**.

## 6. Limitations (read before publishing)

1. **No credentials.** An agent that can never authenticate is not necessarily in the same state as one that is still loading a valid ruleset. What is established: the agent starts its RPC listener as soon as its *first config download attempt completes*, including when it **fails**, and then answers allow with `X-SigSci-Agent: disabled`. **Not established:** whether, with working keys, the listener also appears (and answers allow) *before* a successful first download finishes parsing, or only after. The size of the vendor's "preliminary request handling" window in a healthy deployment is therefore **not determined**; the only duration measured (60 s) is an artifact of my egress block (3 URLs × ~20 s timeouts); with a fast rejection (H) it was ~1 s.
2. Because (1), the 503→200 startup-probe transition, the "release when rules load" half of the probe claim, the custom block rule, and the Fastly console check were **not performed**.
3. The `X-SigSci-Agent: disabled` value is observed behavior; I do not claim it means the same thing in a healthy-but-loading agent.
4. The init container shifts container start relative to pod creation and enforces the egress hold; it does not alter the agent or module, but the kubelet's readiness delay (10 s) is a property of the ingress-nginx chart, not of the WAF.
5. Replicates are in section 9 (G and H now 3 reps each). Release: one run, and not a clean test.
6. statsd and the RPC hexdump are partial: statsd lags by a flush interval, the hexdump was truncated (169 of ~1,566 requests). Counts from them are indicative only.
7. Only arm64 images/Linux-VM kernel were tested (podman machine, Fedora kernel); the default module request timeout (documented 100 ms) was not verified, and a hung-but-listening agent (case b) was not provoked.
8. NetworkPolicy enforcement is by kindnet; a pilot proved it had a start-up race (handled by the init container).
9. The `sigsci_init_main_conf: Using default UDS socket: /var/run/sigsci.sock` notice differs from the configured path; not investigated.
10. Everything is black-box: behavior inferred from logs, flags, wire hexdump and headers. No binaries were disassembled.

## 7. Reproduction

```bash
# prerequisites: brew install kind kubectl helm; podman machine (rootful, 6 GiB) started
export KIND_EXPERIMENTAL_PROVIDER=podman
kind create cluster --name ngwaf --image kindest/node:v1.31.0

# images, pulled by digest then tagged/loaded into the node
podman pull docker.io/signalsciences/sigsci-agent@sha256:4aa2f5296b5f2eeb1a71e79643a93afb19ce85a635a21895ff35b2d0701578d2
podman pull docker.io/signalsciences/sigsci-nginx-ingress-controller@sha256:a4c66bfe5c0b06c6507ce89881ba891711ab3009b2d5d934db192a91e0f452ba
podman pull docker.io/library/python:3.12-alpine
podman tag <agent> localhost/sigsci-agent:4.83.2; podman tag <ctrl> localhost/sigsci-nginx-ingress-controller:1.15.1-fastly1.4.0; podman tag <py> localhost/py:3.12-alpine
for i in sigsci-agent:4.83.2 sigsci-nginx-ingress-controller:1.15.1-fastly1.4.0 py:3.12-alpine; do
  podman save -o /tmp/img.tar localhost/$i && kind load image-archive /tmp/img.tar --name ngwaf; done

# backend, generator, statsd sink
kubectl apply -f manifests/00-base.yaml -f manifests/gen.yaml -f manifests/statsd.yaml
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx --version 4.15.1 -n ingress-nginx --create-namespace -f manifests/values-A-noprobe.yaml

# one scenario: <variant> <label> <hold_s> <release 0|1> [post_release_s]; NONETPOL=1 skips the egress block
python3 src/run.py A A-rep1 90 0          # no probe
python3 src/run.py B B-rep1 90 0          # with startup probe
python3 src/run.py F F-rep1 150 0         # no probe + debug flags + statsd
python3 src/run.py G G-default1 150 0     # Fastly layout, defaults, egress blocked
NONETPOL=1 python3 src/run.py H H-default-allowed1 150 0   # defaults, egress allowed (dummy keys -> 403)
python3 src/analyze.py raw/A-rep1         # per-request correlation.csv + summary.json
python3 src/default_vis.py raw/G-default1 # default-visibility numbers
python3 src/decode_rpc.py raw/F-rep1/rpc.hex > rpc-decoded.jsonl
```

## 8. Files

- `manifests/`: `00-base.yaml` (echo, ingress rule), `gen.yaml`, `netpol-block-agent-egress.yaml`, `statsd.yaml`, `poller.yaml.tmpl`, `values-A-noprobe.yaml`, `values-B-probe.yaml`, `values-D-debugflags.yaml`, `values-E-allthethings.yaml` (written, not run), `values-F-noprobe-debugflags.yaml`, `values-G-fastly-default.yaml`, `values-H-fastly-default-egress-allowed.yaml`, and for section 9: `values-I-default-nginx-agent-statsd-rpcdump.yaml`, `values-Ia-egress-allowed-no-initcontainer.yaml`, `values-J-sigsci_agent_timeout-1000.yaml`, `values-Ja-timeout1000-egress-allowed-no-initcontainer.yaml`, `values-K-debug-standalone-4.yaml`, `values-R10/R30/R60-readiness-delay-*.yaml`, `slowprobe.yaml`. CoreDNS NXDOMAIN toggle: `src/dns.sh`. Keys in the values files are the literal dummy values used in the runs (format-valid, non-credentials: access key `00000000-…`, secret = 43×`A`). They are left unredacted because redacting them makes the agent refuse to start (`Unable to start: invalid secretaccesskey`), which happened once during this work and invalidated a first attempt at the batch.
- `raw/<run>/`: `agent.log`, `nginx-debug-excerpt.log` (debug runs) or `nginx.log` (G/H, full), `echo.log`, `gen.log`, `correlation.csv` + `summary.json` (A/B/F/release), `poller.log`, `pods-watch.txt`, `endpoints-watch.txt`, `markers.txt`, `pod.json`, `events*.txt`, `rpc.hex`, `rpc-decoded.jsonl` (F-rep1), `statsd*.log`.
- `raw/agent-help.txt`: `sigsci-agent -help` for 4.83.2. `raw/upstream-sigsci-values.yaml`: Fastly's published values file as fetched.
- `src/`: orchestrator, analyzers, RPC decoder.

---

# 9. Follow-up tests (2026-11-12, after the first report)

All with dummy keys, same cluster, same images (digests unchanged), 20 req/s generator. Variant `I`/`Ia` = Fastly layout, **default NGINX log level**, plus agent `SIGSCI_STATSD_ADDRESS`, `SIGSCI_DEBUG_LOG_RPC_DATA` (uncapped this time), `SIGSCI_DEBUG_LOG_UPLOADS=1`. `Ia` has no egress-guard init container (see 9.8). Times are seconds after container `startedAt` unless noted. Per-run numbers: `raw/<run>/summary2.json`.

## 9.1 Failure-mode matrix (3 reps each)

| Failure injected | How | Agent log reason on first config attempt (`agent.log:8`) | RPC socket created (reps) | Requests reaching upstream while socket absent | After socket: decoded `RPC.PreRequest` responses | statsd |
|---|---|---|---|---|---|---|
| Egress dropped | NetworkPolicy | `context deadline exceeded` ×3 URLs | 60.71 / 61.06 / 60.45 s (`DROP-rep*`); also 60.65 / 60.34 / 60.63 s (`G-default1-3`) | 934 / 938 / 936 (all uninspected, no `X-SigSci-*` header) | 4,760/4,760 identical (see below) | `dropped.engine_disabled` = `waf.total` = `waf.allow` |
| Credentials rejected | real Fastly endpoints, dummy key | `got HTTP error … 403` ×3 URLs | 1.29 / 1.64 / 1.16 s (`CRED403-rep*`); 1.05 / 1.18 / 1.05 s (`H-default-allowed1-3`) | 0 | 2,747/2,747 identical | same |
| DNS NXDOMAIN | CoreDNS `template … rcode NXDOMAIN` for `wafconf./c.signalsciences.net` and both `sigsci-agent-wafconf*.s3.amazonaws.com` (`src/dns.sh`); other lookups unaffected | `lookup wafconf.signalsciences.net … no such host` | 0.25 / 0.91 / 0.94 s (`DNS-rep1,3` + `DNS-rep2` rerun 0.91) | 0 | 6,390/6,390 identical | same, plus `sigsci.agent.download.error` |
| TCP RST | `iptables -I OUTPUT -p tcp --dport 443 ! -d 10.0.0.0/8 -j REJECT --reject-with tcp-reset` in the pod netns (applied via `nsenter` from the node) | `connection refused` (a RST answering the SYN surfaces this way) | 0.78 / 0.16 / 0.53 s (`RST-rep*`) | 0 | 6,407/6,407 identical | same, plus `download.error` |

Identical response in all four, **OBSERVED**: `{"WAFResponse": 200, "RequestID": "", "RequestHeaders": [["X-SigSci-Agent","disabled"]]}`; the backend receives `X-SigSci-AgentResponse: 200` and `X-SigSci-Agent: disabled` on every request after the socket exists; attack payloads (SQLi/XSS/traversal/canary) pass; NGINX logs no sigsci line at default level after startup (only the two startup `[notice]` lines). Decoded totals: 4,760 + 2,747 + 6,390 + 6,407 = 20,304 responses, one distinct value.

**Do all observed failure types produce the same disabled/allow state? OBSERVED: yes, 4 of 4** (config unreachable by timeout, by 403, by NXDOMAIN, by RST). **In all four the agent starts its RPC listener in the same instant its first config attempt ends** (`agent.log:8-9`, ≤1 ms apart in every run), so the socket-creation delay is simply how long the failing attempt takes: ~60 s for silent drops (3 URLs × ~20 s timeouts), ≤1.7 s for the fast failures.

Consequences (some weaken a broad claim):
- **OBSERVED:** the uninspected *no-socket* window only occurred with the slow failure (drop). In the fast failures the pod only turned Ready ≥10 s after container start (chart readiness `initialDelaySeconds: 10`), by which time the socket already existed, so no request ever hit the no-socket path; all uninspected traffic was in the *disabled* state. **INFERRED:** the no-socket window needs a config failure that outlasts readiness (≳10–15 s here); the disabled window needs only that the config never loads.
- **OBSERVED:** the disabled state persists: the agent retried every ~30 s (`Config update failed try 1..6` in 150 s, `raw/H-default-allowed1/agent.log:8,10-14`) with no change in behavior.
- **UNTESTED:** mid-connection reset (`connection reset by peer`), TLS errors, HTTP 5xx, truncated/corrupt config body, DNS SERVFAIL/timeout, agent process crash. **OBSERVED during setup, not saved as raw evidence:** with no access key or an invalid secret the agent *exits* (`Unable to start: accesskeyid is required` / `invalid secretaccesskey`), so no socket exists (case c) for as long as it is down.

## 9.2 Documented failure/timeout/fail-open options (docs + `sigsci-agent -help` only)

Sources read: agent config reference <https://www.fastly.com/documentation/reference/ngwaf/agent-config/> (read in two chunks; 180 k chars); NGINX module directives <https://www.fastly.com/documentation/guides/next-gen-waf/setup-and-configuration/module-agent-deployment/nginx-module/installing-the-nginx-dynamic-module>; fail-open statement <https://www.fastly.com/documentation/guides/next-gen-waf/agent-response-codes/troubleshooting-agent-response-codes/>; <https://www.fastly.com/documentation/guides/next-gen-waf/setup-and-configuration/module-agent-deployment/troubleshooting-module-agent-deployments/>; <https://www.fastly.com/documentation/guides/next-gen-waf/setup-and-configuration/module-agent-deployment/nginx-module/about-the-nginx-module>; K8s guide as in section 2; `raw/agent-help.txt`.

| Option | Where documented | What it says | Touches fail-open/closed? | Test status |
|---|---|---|---|---|
| `sigsci_agent_timeout` (NGINX, default 100 ms) | module directives page | "Agent communication socket timeout in milliseconds" | Yes: timeout path. The troubleshooting page says on timeout the module "defaults to failing open" | **TESTED** (9.4, 9.6) |
| `sigsci_agent_host` / `sigsci_agent_port` | same | where to find the agent | indirectly (no socket ⇒ fail open, **OBSERVED**) | tested by construction |
| `sigsci_enabled` (on/off) | same | toggles inspection | not a failure option | UNTESTED |
| `inspection-timeout` (agent, default 100 ms) | agent-config + `-help` | "Envoy/revproxy global inspection timeout after which the system will fail open" | Yes, but scoped to Envoy/revproxy | **UNTESTED, not applicable to the NGINX module per the docs** |
| `debug-standalone` (bitfield; 4 = use empty rules) | agent-config + `-help`, EXPERIMENTAL | "0=normal, 1=no upload, 2=no download, 3=no networking, 4=use empty rules, 7=no net+empty rules" | closest to "no-config behavior"; not described as fail-closed | **TESTED** (9.6) |
| `download-url`, `download-failover-url`, `download-cdn-url`, `download-interval`, `download-config-version`, `download-config-cache` | agent-config + `-help` | where/how often to fetch config; `download-config-cache`: "Filename to cache latest downloaded config" | cache may help *restarts after a success*; says nothing on the no-config state | UNTESTED (needs a successful first download) |
| `startup-probe-listener`, `startup-probe-filepath` | agent-config, K8s guide | HTTP 200 / file "once the agent has loaded a ruleset" | readiness gate, not fail-closed | **TESTED** (section 5, variant B) |
| `sample-percent` | agent-config | "100=process everything, 0=ignore everything" | fail-open-ward, not fail-closed | UNTESTED |
| `max-backlog`, `max-connections`, `rpc-workers`, `context-expiration`, `service-shutdown-timeout` | agent-config + `-help` | queue/timeout sizing | no fail-open/closed statement found | UNTESTED |
| `validate-config` | `-help` | validate config entries | n/a | n/a |

**Finding, even though it weakens a "no mitigation exists" framing: no option for the NGINX module or the agent is documented as making the module or agent fail closed**, and none of the pages I read states what happens when the agent is absent or has no config. The only fail-open statement is the timeout one. **OBSERVED:** no tested option made any request blocked.

## 9.3 Fastly-suggested alternative: controller readinessProbe delay (egress dropped, 90 s, 1 rep each per instruction)

Chart `controller.readinessProbe.initialDelaySeconds` = 10 / 30 / 60 (`manifests/values-R*.yaml`); everything else default.

| Delay | Pod Ready (s after container start) | Socket created | Upstream hits, socket absent (uninspected, no header) | Upstream hits, disabled (`X-SigSci-Agent: disabled`) | Total reaching upstream after Ready | Attack payloads among them |
|---|---|---|---|---|---|---|
| 10 s | 16 | 60.85 s | 936 | 364 | 1,300 | 1,039 |
| 30 s | 35 | 60.14 s | 536 | 364 | 900 | 719 |
| 60 s | 65 | 60.45 s | 0 | 301 | 301 | 241 |

**OBSERVED:** every delay let traffic through once it expired; none held traffic out until a ruleset loaded (none could load). **OBSERVED, and a limit of this result:** the 60 s delay avoids the no-socket window only because the first config attempt happened to end at ~60 s here; traffic still passed uninspected in the disabled state. **INFERRED:** a readiness delay is a timer, not a signal that rules loaded; with working credentials it could cover a normal startup, which was not tested. Single rep per delay (deterministic design; counts match the egress-drop reps within ±3).

## 9.4 Documented timeout path for contrast: SIGSTOP the agent after the socket exists

Method: `kill -STOP` the `sigsci-agent` host PID from the kind node (`crictl inspect`), 25 s after the socket appeared, `kill -CONT` 20.2 s later; image untouched. Default module timeout; default NGINX log level.

- **Idle probe (`IDLEFREEZE-rep1-3`, generator paused, 1 req/s):** during the freeze 21 / 20 / 20 probe requests, **all returned 200 and reached the upstream with no `X-SigSci-*` header** (fail open). Client latency min / p50 / max: 64 / 323 / 569 ms; 316 / 319 / 327 ms; 315 / 324 / 508 ms, versus 5–13 ms before and after (disabled-allow path). After SIGCONT the very next requests were answered `disabled` again.
- **OBSERVED:** the fail-open wait is ≈320 ms, not ≈100 ms. **INFERRED (not tested):** about 3 × the 100 ms default (e.g. repeated attempts); the mechanism was not determined and debug logging was not enabled in this test.
- **OBSERVED: NGINX logged nothing at all (0 lines, any level) in the freeze window at default level** in all 3 idle reps and all 3 loaded reps. (`nginx.log` per run.)
- **Loaded (`FREEZE-rep1-3`, 20 req/s):** in the frozen window 398 / 399 / 391 client requests; 299 / 319 / 287 hit the 3 s client timeout; the upstream saw 128 / 101 / 135 fail-open requests (no header) plus 18 / 11 / 17 that carried the disabled header; median arrival delay of fail-open requests 1.4–1.7 s. **INFERRED:** the module's blocking wait stalls NGINX workers, so a dead agent also degrades availability under load.
- **Contrast, OBSERVED:** three different "uninspected" paths and their default-level footprint: (1) no socket: ~0 ms, `[error] cannot connect uds socket … errno=2` per request; (2) agent timeout: ~320 ms, **no log line at default level**; (3) disabled-allow: 5–13 ms, **no log line at default level**, marked only by the upstream header and agent-side counters. **So default-level silence is not unique to the disabled path; the documented timeout path is equally silent.**

## 9.5 Hexdump sample corroborated (statsd reconciliation, 3 reps)

`RECON-rep1-3`: egress allowed (403), generator stopped at T0+80 s, run to T0+200 s so statsd (flushed every ~30 s) could finish; hexdump uncapped.

| | rep1 | rep2 | rep3 |
|---|---|---|---|
| Requests received by upstream (echo), disabled phase | 1,438 | 1,438 | 1,438 |
| `RPC.PreRequest` in hexdump | 1,480 | 1,480 | 1,480 |
| of which generator (`X-Request-ID` present) / controller-internal | 1,438 / 42 | 1,438 / 42 | 1,438 / 42 |
| statsd `waf.total` = `waf.allow` = `rpc.tx.dropped.engine_disabled` | 1,476 | 1,476 | 1,476 |

**OBSERVED:** the hexdump now covers every generator request (1,438 = upstream count exactly). statsd accounts for 1,476 of 1,480 (99.7 %); the **same 4 are missing in all three reps; cause not determined**. All three counters are always equal. So the earlier 169-of-~1,566 sample was a truncation artifact (400 KB cap), and the counts corroborate it for this phase.

## 9.6 Option probes

- **`sigsci_agent_timeout 1000` (`J-*`, 1 rep each as instructed; no behavior change found in the allow path):** no-socket phase unchanged (946 `[error]` lines, 934 uninspected upstream hits, `J-drop-rep1`); disabled phase unchanged (`WAFResponse 200`, header `disabled`); freeze run (`J-freeze-rep1`): 354 of 399 client requests hit the 3 s client timeout and the upstream saw 23 requests, all carrying the disabled header and none fail-open. **INFERRED:** with a 1 s timeout the fail-open wait (≈3 × 1 s) exceeds my 3 s client timeout, so fail-open requests were not observable. It lengthens the documented timeout path only; nothing was blocked.
- **`SIGSCI_DEBUG_STANDALONE=4` (`K-standalone4-drop-rep1-3`, egress dropped; 3 reps because it changed behavior):** socket created at 0.42 / 0.20 / 0.61 s, so **no no-socket window** even with egress dropped; response is `{"WAFResponse": 200, "RequestID": "", "RequestHeaders": []}` (no `X-SigSci-Agent: disabled`; backend sees only `X-SigSci-AgentResponse: 200`); statsd shows `rpc.tx.process` (1,250 / 1,249 / 1,243) = `waf.total` = `waf.allow` and **no** `dropped.engine_disabled`. Attack payloads still reached the upstream (1,518 / 1,519 / 1,515 of ~1,900 requests); decoded 5,772/5,772 responses identical. **OBSERVED: not fail-closed; it removes the `disabled` marker and the no-socket window but still allows everything.** **INFERRED:** the engine runs with an empty ruleset. EXPERIMENTAL flag; not documented as a mitigation.

## 9.7 Default-settings runs, 3 reps each (Fastly layout, no debug, no statsd)

| | G-default1 | G-default2 | G-default3 | H-default-allowed1 | H-default-allowed2 | H-default-allowed3 |
|---|---|---|---|---|---|---|
| Egress | blocked | blocked | blocked | allowed (403) | allowed (403) | allowed (403) |
| Socket created (s after container start) | 60.65 | 60.34 | 60.63 | 1.05 | 1.18 | 1.05 |
| First upstream hit (s) | 15.89 | 15.54 | 15.81 | 10.21 | 10.40 | 10.26 |
| Uninspected, socket absent | 935 | 936 | 936 | 0 | 0 | 0 |
| `disabled` | 1,564 | 1,563 | 1,563 | 2,899 | 2,899 | 2,899 |
| `[error] cannot connect uds socket` lines | 947 | 948 | 948 | 0 | 0 | 0 |
| NGINX lines after socket exists | 0 | 0 | 0 | 0 | 0 | 0 |
| Warning events / warn+ NGINX lines | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Agent stdout lines in 150 s | 11 | 11 | 11 | 14 | 14 | 14 |

The section-4 table therefore holds on 3 of 3 reps per condition. (`G-default2` was rerun after its first run's echo log was lost to rotation; the invalid run is kept in `raw/_invalid-echo-log-rotated/`.)

## 9.8 Method notes and corrections for this follow-up

- **Invalid runs excluded:** (a) first attempt at this batch: my redaction pass had replaced the dummy secret inside the manifests, the agent refused to start; all those directories were deleted and rerun. (b) First RST attempt rejected *all* port-443 traffic, including the controller's Kubernetes API calls, so pods never became Ready; rerun with `! -d 10.0.0.0/8`. (c) First freeze/reconciliation attempt used a variant whose init container waits up to 60 s for egress to be blocked, so under egress-allowed it just delayed the pod and the freeze fired after the run ended; replaced by `Ia`/`Ja` (no init container). (d) Echo-server log rotation (kubelet, 10 MiB) truncated `G-default2`, `DNS-rep2`, `J-drop-rep1`; those were rerun and every run now starts with a restarted echo pod.
- `CRED403-rep*` used the init-container variant under egress allowed, so each waited 60 s before the containers started; all times are container-relative and the runs are valid, but they have fewer post-socket requests (≈900 vs ≈2,100).
- Gen client logs of the R10/R30 and some early runs are incomplete (kubelet rotation); upstream counts there come from `echo.log` and the agent log, not `gen.log`.
- statsd sink log is shared across runs and filtered by time window per run.
- Reps: failure matrix, freeze, reconciliation, default settings, RST: 3. Readiness delays, `sigsci_agent_timeout`: 1 (per instruction); `DEBUG_STANDALONE=4`: 3 (behavior changed).
- Exploratory/older directories (`raw/exploratory-D2-…`, `raw/A-*`, `raw/B-*`, `raw/F-*`) predate the echo-restart fix.

## 9.9 Added limitations

1. Still **no working credentials**: nothing here shows how the agent behaves while a *valid* first download is in flight or being parsed.
2. All failure types were induced at the network/DNS layer from inside the pod; real outages may differ (mid-stream resets, partial bodies, 5xx).
3. The ≈320 ms fail-open wait comes from n = 60 idle probes on one platform (arm64 VM); the 3× factor is a hypothesis.
4. Four requests in the statsd reconciliation are unexplained.
5. Fastly's documentation may contain options not on the pages I could read (the agent-config page was read in two fetches; the module-config page returned only a navigation index).
