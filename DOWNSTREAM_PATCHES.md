# Temporary DSPy integration patches

Upstream release: lm15 v2.2.0 at
`b30ff1f638b2993415c3b697152245f82bbb1e25`.
Contract pin: `9d8e1cecd30387e04b129f168ab156c04adf9745`.

Replay these commits in order on a newer eligible release, omitting a patch
only when its regression is covered by the upstream release. Keep fork main
unpatched and do not rewrite published integration branches.

The v2.2.0 replay retains all twelve patches in the same order:

1. `2a56bb6d6e389a67e7f13cf18a61c30d842a6e52`
2. `3060df87e722a988457a8cde6e1a74fa976ea4cb`
3. `fe870dd158d8aacc274e4c7270765d11405501b3`
4. `1aaf895e09ab3a8731d8963fb47887091d75b2bc`
5. `bf623be4adca65e108229835aca7c1a3efb7fc29`
6. `508e267d1cc230e86fbb940f52df875465e12bf7`
7. `54a445cd4af24c2d838fa1a5ebcd26315e19abbf`
8. `12d378bf3acdcdf5ed01a2c65226c0ac8371614b`
9. `79d63701886dd424f0e46283774613b310137b89`
10. `36507e1d74bf62b4ab34057c52f7309681ad3e62`
11. `cbe1af0324f75285a617960658bdb618b8d06d4a`
12. `36285881048bdd258f901b4df697645a6b5b7f89`

Patch-retirement audit: the only upstream runtime change is Anthropic summary
display in the request writer. All patched runtime files are unchanged; neither
the direct fixes nor alternative implementations are present. No textual or
semantic conflict was found. The copied public regression files on pristine
2.2.0 produced 64 failures and 62 passes. Source inspection and these failures
retain patches 1, 2, 3, 5, 6, 7, 10 and 12. Patch 11's original file cannot
collect on pristine because it imports a downstream helper; an independent
public Chat/Responses complete() probe instead reproduced missing billed usage
on both dialects (None before, 22 tokens after).

Companion patches were tested with their prerequisite stack: after patch 3,
both replacement-transport cases fail without patch 4. After patch 7, the
post-approval expiry case fails without patch 8, and four route-admission plus
two single-worker cancellation cases fail without patch 9. All 199 focused
patch/reasoning tests pass with the full stack. Patch 10 still omits the old
cloud-settings runtime hunk already solved upstream in 1.4.1. No patch was
retired or replaced in 2.2.0; clean cherry-picks alone were not the evidence.

Exact-release upstream CI 42322853022 and tag CI 42323183290 pass. Strict
conformance, the pinned harness and types pass (32 user programs, zero new
findings). Full source suite: 3,900 passed, 9 skipped, with only the two
approved reserved-IP connect-timeout orb exceptions. The stack is on
integration/lm15-2.2.0-patches and the separate
contribution branch fix/managed-request-snapshots-2.2.0. Prior stacks and the
standalone fix/stream-final-json-types-2.1.0 contribution remain intact.

12. Distinguish JSON booleans from numbers when comparing argument fragments
    with their final copy (MAP-20). Python treats true == 1 and false == 0;
    the stream previously accepted these contradictory tool inputs. The
    existing public stream-reader regression now fails both scalar/nested
    contradictions before the fix, with other cases passing. Tag numeric
    values and compare with Decimal so 1 and 1.0 still agree, without float
    rounding. Ordered objects and whitespace/escape equivalence remain.
    Tests live in tests/test_stream_final_copy.py. Prepared for a separate
    upstream contribution on fix/stream-final-json-types-2.1.0; not claimed
    submitted until upstream access succeeds.

The following numbered motivations retain their v1.5.0 and original commit
identities for traceability; each corresponds to the same replay number above.

11. `c4686f8343a1f0c47e33141ab114877d4f6b723b`: preserve billed usage on
    nonstream OpenAI Chat/Responses parsing failures. Added to DSPy's 1.5.0
    snapshot on October23; dropping it loses usage when a reply contains an
    unnamed tool call. Tests/test_complete_partial_usage.py covers sync/async
    error accounting, malformed telemetry, missing and inconsistent totals,
    successful controls, and separate reasoning. The replay uses 2.0's
    canonical unknown-counter semantics instead of constructing invalid Usage.
    This patch remains downstream pending upstream contribution access.

1. `cc8a5b20763718faf4a70a1f8c5bd902eccb7827` (original `bf96a4fe32edfa72125a2f9c2ee7ea0cc206c655`):
   enforce the selected model for keyword requests as well as explicit Request
   values. Otherwise a bound client can silently request a different model.
   The regression in tests/test_login.py verifies matching spellings and
   rejection before dispatch for request, plan, complete and stream.
2. `b0f32a1cb566c9cf0559051e66333fa3115e5f7e` (original `3a5cac83983aa462841f32a7f9842a085ac052ef`):
   classify renewal HTTP 429 as RateLimitError rather than LoginDenied. A
   temporary rate limit must not delete saved credentials. The regression in
   tests/test_login.py checks preserved credentials/revision, cleared in-flight
   state, no automatic retry and a successful later renewal.
3. `2f0d9b7fe7158778b4a3edc1a3087b13142bb29d` (original `dd0662c866dfd208ffed443f071e10123170ef0e`):
   keep credentials, account headers and endpoints in one per-operation
   snapshot. Retained adapters acquire the active connection for each
   operation; bound clients retain their selected identity. Dispatch checks
   the snapshot's generation before every transport handoff, including delayed
   streams and multi-wire operations. Renewal cannot silently change a known
   account ID. Regression coverage in tests/test_managed_dispatch.py includes
   sync/async replacement, renewal, logout races, batch upload/submit, explicit
   endpoints and offline planning.
4. `dfb1e390073fbb6a2ff668996f9d2bb7e394dd0a` (original `046f2bfa5c12b55c6a199f388879e5d689397a87`):
   preserve the retained adapter's transport and adaptation policy when
   preparing an operation. Sync/async regressions verify the documented
   transport replacement escape hatch sends only through the caller's
   replacement transport.
5. `37ebcfbc66899e18633663034bd27788ed8f8c5f` (original `8671868feb55408c2a11bbea2413f9a7d70ebe9b`): expose the descriptor
   collection as `lm15.login_providers` (also `lm15.login.providers`).
   The attempted lazy `providers` export was hidden by the existing provider
   implementation package. Keep that package and its submodules intact.
   Fresh-interpreter import-order regressions live in tests/test_login_exports.py.
6. `89df856db40f0a4f2b9926e20b7184f21de6033b` (original `cd7ef071d0399af28b0e88a71bfd11f97a859cb8`): wait for dismissed terminal
   manual input to relinquish stdin before returning to a subsequent picker.
   The existing "press Enter to continue" interaction remains; no portable
   cancellation of blocking input is assumed. Tests/test_terminal_login.py
   covers a real loopback callback with controlled input, early dismissal,
   completed reads and interrupted reads.
7. `ff3f297ed5795f02d203c32bf1e26c204bfa4d71` (original `a838f91648c844416d75697273c38646caddec8f`): resolve sibling routes to
   their advertised saved connection for requests, renewal, status and
   logout; explicit route slots (including logout markers) take precedence.
   Async task cancellation signals and durably releases only its own login
   attempt before returning CancelledError. A commit already won is not
   undone. Verification pins the checked connection and records results
   only if its identity/generation still matches. Tests/test_login.py covers
   all three Meta routes with remint/endpoint change/logout, cooperative and
   non-cooperative cancelled login workers, and valid/rejected verification
   with and without concurrent replacement.
8. `07816eca2bda2d7ee149266b48a92c430377293c` (original `c9d45beb2744835a79bc46ea7aa8d2e209f9139e`): keep the post-approval
   cancellation/deadline check inside the existing typed-error boundary.
   Self-review of patch 7 reproduced a raw LoginExpired escaping if approval
   finished after the deadline. The public regression in tests/test_login.py
   now gets AuthOperationError(reason="login_expired"), persists no credential,
   and can start a new login immediately. This patch is downstream only.
9. `d8dab6150caf86e0328385c89475d8255ac3fd88` (original `dd900d292a393c6c04fab7d1c57248dfee25e90b`): preserve the originally
   requested route through renewal and re-resolve it at dispatch admission.
   A newly saved or signed-out route-specific slot must supersede the shared
   owner even for an already prepared request. Run durable async login
   cancellation on an independent executor so a blocked login cannot occupy
   the only worker available to release its reservation. The second Greptile
   review reproduced both races. Four sync/async route replacement/logout
   cases and two one-worker cancellation cases fail before and pass after.
   Cancellation frees the reservation before the login worker is released;
   it does not interrupt blocking terminal input or undo a completed commit.
   These fixes are downstream only, pending upstream contribution access.
10. `d2c73eb1e5099f9ddd53e638ccd8071a907d55f3` (original `359f90953dd90089c306ceb5a69fe10bbb14c483`): preserve the selected account.
    Bound clients and saved-account model listing
    discard config identity overrides while retaining execution settings;
    ordinary routers keep their explicit-identity precedence. The original
    cloud-settings runtime hunk is omitted: upstream PR #21, released in
    v1.4.1, now owns it. Retain the public sync/async replacement regressions
    to verify that upstream settings resolution composes with patch 3.
    The October 15 Greptile review reproduced wrong-account dispatch and
    ignored project/region selection. Ten public-operation cases fail before
    and pass after, covering catalog/inference keys, named cloud identities,
    logout/replacement, absent/conflicting ambient settings and partial
    explicit overrides. Tests live in tests/test_login.py and
    tests/test_managed_dispatch.py. This patch is downstream only, pending
    upstream contribution access.

During the v1.5.0 replay, the first nine patches remained necessary. Conflicts preserved
upstream's measurable-judgment filtering, bounding_box export and typed
Connection declaration alongside our snapshot and descriptor fixes. Patch 10
now changes only bound identity selection plus regressions; it has no router
runtime diff. All retained regression tests pass, including eight cloud
settings/replacement cases using the upstream implementation.
Meta login remains unverified and requires explicit opt-in because of the
documented terms and data-use risks.

Patches 5–7 address five reproduced findings from DSPy #10540's October 13
Greptile review. The focused before/after run failed 14 cases on the previous
tip (with 3 controls passing); all pass after the fixes. These new patches
are downstream only and are published on the integration and contribution
branches below, not claimed submitted or merged upstream.

The first two fixes originate on cmpnd-ai/lm15-python branch
fix/managed-auth-review. The routing fixes are published on
fix/managed-request-snapshots, with the 1.3.0 stack and review fixes on
fix/managed-request-snapshots-1.3.0 and integration/lm15-1.3.0-patches.
The v1.5.0 replay is on fix/managed-request-snapshots-1.5.0 and
integration/lm15-1.5.0-patches; prior branches remain unchanged.
Upstream PR submission was denied by GitHub
integration permissions; no patch is claimed to be merged upstream. Check
for an existing upstream PR before attempting submission again.

Managed websocket operations and raw request builders that bypass operation
preparation fail closed; explicit/unmanaged credentials retain their existing
behavior. No shared adapter fields are mutated during requests. A snapshot
admitted before logout may still reach the transport: logout cannot recall an
already admitted request.

Full source tests, strict conformance, the exact pinned contract harness,
type checks and DSPy integration tests must pass on every changed stack before
import. The only approved orb exceptions are the sync/async reserved-IP
connect-timeout tests, with passing exact-release upstream CI. Do not infer
that passing existing contract tests alone demonstrates the race regressions.
No live provider calls are needed.
