# elkrs oracle

Java CLI (`ElkJsonRunner`) wrapping real ELK 0.11.0 (pulled from Maven
Central, not vendored), used to generate `goldens/expected/` and as the
reference for `tools/fuzz_diff.py`. See the main README's "How fidelity is
verified" section.

Now covers all 12 algorithms elkrs implements (`pom.xml` depends on every
`org.eclipse.elk.alg.*` artifact at 0.11.0). Algorithm IDs, verified against
`src/*/mod.rs` / `src/*/options.rs`:

| id | notes |
|---|---|
| `org.eclipse.elk.fixed` | |
| `org.eclipse.elk.box` | |
| `org.eclipse.elk.random` | needs `org.eclipse.elk.randomSeed` set to a **non-zero** value to be reproducible — seed 0 means "clock-seeded" in real ELK (see main README's known-divergences #3); a smoke test without an explicit seed will legitimately differ every oracle run |
| `org.eclipse.elk.layered` | primary target, see `goldens/` |
| `org.eclipse.elk.force` | |
| `org.eclipse.elk.stress` | |
| `org.eclipse.elk.radial` | |
| `org.eclipse.elk.mrtree` | |
| `org.eclipse.elk.rectpacking` | |
| `org.eclipse.elk.sporeOverlap` | operates on **existing** node positions (overlap removal) — a smoke-test graph with no `x`/`y` on its nodes is a degenerate all-coincident-points input and will diverge; give nodes real starting coordinates |
| `org.eclipse.elk.sporeCompaction` | same caveat as `sporeOverlap` |
| `org.eclipse.elk.disco` | echoes a debug option `org.eclipse.elk.disco.debug.discoGraph` containing a Java `Object.toString()` (`DCGraph@<hashcode>`); elkrs has no equivalent identity hash so this field will always differ — cosmetic only, matches the main README's known-divergences #2 |
| `org.eclipse.elk.topdownpacking` | |

Verified with a 3-node/2-edge smoke test per algorithm (see git history of
this file's introducing commit for the exact cases): 8 matched immediately,
`random`/`sporeOverlap`/`sporeCompaction` matched once given realistic
input as above, `disco` matches except for the documented debug-string
field. No new (undocumented) divergence found in this pass.

## Usage

Same as before, `ElkJsonRunner` is unchanged — just more algorithms are
now resolvable via ELK's own `ServiceLoader`-based algorithm registration
(no runner code changes were needed; adding the Maven dependencies was
sufficient):

```sh
mvn -q -f oracle/pom.xml exec:java "-Dexec.args=path/to/graph.json"
mvn -q -f oracle/pom.xml exec:java "-Dexec.args=--batch goldens/cases goldens/expected"
```
